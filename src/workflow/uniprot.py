"""Find a proteome on UniProt and download its proteins as FASTA.

Streamlit-free (the widget is ``uniprot_ui.py``), so it can be tested and used
from scripts. It talks to the UniProt REST API
(https://www.uniprot.org/help/api_queries) only:

- ``search_proteomes(text)`` looks proteomes up by organism name or NCBI
  taxonomy ID in ``/proteomes/search``;
- ``fasta_query(upid, reviewed_only)`` is the UniProtKB query for the proteins
  of one proteome, all of them or the reviewed (Swiss-Prot) entries only;
- ``count_proteins(query)`` asks ``/uniprotkb/search`` how many entries the
  query has;
- ``download_fasta(query, dest)`` streams ``/uniprotkb/stream`` into a file,
  through a ``.part`` file so a cut-off download never looks finished.

``UNIPROT_REST_URL`` in the environment points it at another server (a mirror,
or a stand-in for tests).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import requests

BASE_URL = os.environ.get("UNIPROT_REST_URL", "https://rest.uniprot.org").rstrip("/")
TIMEOUT = (15, 300)  # connect, read (UniProt starts streaming large proteomes slowly)
HEADERS = {"User-Agent": "OpenMS-WebApp (https://github.com/OpenMS/streamlit-template)"}

REFERENCE = "1"  # proteome_type of reference proteomes


class UniProtError(RuntimeError):
    """UniProt could not be reached or answered with an error."""


@dataclass
class Proteome:
    upid: str
    organism: str
    common_name: str
    taxon_id: Optional[int]
    proteome_type: str
    protein_count: Optional[int]

    @property
    def is_reference(self) -> bool:
        return "reference" in self.proteome_type.lower()

    def label(self) -> str:
        name = self.organism
        if self.common_name and self.common_name.lower() not in name.lower():
            name += f" ({self.common_name})"
        parts = [name, self.upid]
        if self.taxon_id is not None:
            parts.append(f"taxon {self.taxon_id}")
        if self.protein_count is not None:
            parts.append(f"{self.protein_count:,} proteins")
        if self.proteome_type:
            parts.append(self.proteome_type)
        return " · ".join(parts)


def _get(path: str, params: dict, stream: bool = False) -> requests.Response:
    try:
        response = requests.get(
            f"{BASE_URL}{path}", params=params, headers=HEADERS, timeout=TIMEOUT, stream=stream
        )
    except requests.RequestException as e:
        raise UniProtError(f"UniProt could not be reached: {e}") from e
    if response.status_code != 200:
        message = ""
        try:
            message = "; ".join(response.json().get("messages", []))
        except ValueError:
            pass
        raise UniProtError(
            f"UniProt answered {response.status_code}" + (f": {message}" if message else "")
        )
    return response


def proteome_query(text: str, reference_only: bool = True) -> str:
    """The /proteomes query for an organism name or taxonomy ID."""
    text = text.strip()
    if not text:
        raise ValueError("Enter an organism name or a taxonomy ID.")
    if text.isdigit():
        query = f"(organism_id:{text} OR taxonomy_id:{text})"
    else:
        # Quotes keep "Homo sapiens" one phrase; quotes in the text would end it
        cleaned = text.replace('"', " ").strip()
        query = f'(organism_name:"{cleaned}")'
    if reference_only:
        query += f" AND (proteome_type:{REFERENCE})"
    return query


def _proteome(entry: dict) -> Proteome:
    taxonomy = entry.get("taxonomy") or {}
    taxon_id = taxonomy.get("taxonId")
    count = entry.get("proteinCount")
    return Proteome(
        upid=entry.get("id") or entry.get("upid") or "",
        organism=taxonomy.get("scientificName") or entry.get("organism") or "",
        common_name=taxonomy.get("commonName") or "",
        taxon_id=int(taxon_id) if isinstance(taxon_id, (int, str)) and str(taxon_id).isdigit() else None,
        proteome_type=entry.get("proteomeType") or "",
        protein_count=int(count) if isinstance(count, int) else None,
    )


def search_proteomes(text: str, reference_only: bool = True, size: int = 25) -> List[Proteome]:
    """Proteomes of the organisms that match an organism name or taxonomy ID:
    reference proteomes first, representative ones among them before the rest,
    larger ones before smaller ones."""
    query = proteome_query(text, reference_only)
    results = _get("/proteomes/search", {"query": query, "format": "json", "size": size}).json()
    proteomes = [p for p in map(_proteome, results.get("results", [])) if p.upid]
    proteomes.sort(key=lambda p: (
        not p.is_reference, "representative" not in p.proteome_type.lower(), -(p.protein_count or 0)
    ))
    return proteomes


def fasta_query(upid: str, reviewed_only: bool) -> str:
    """The UniProtKB query for the proteins of one proteome."""
    if not re.fullmatch(r"UP\d{9,}", upid):
        raise ValueError(f"Not a UniProt proteome ID: {upid}")
    query = f"(proteome:{upid})"
    if reviewed_only:
        query += " AND (reviewed:true)"
    return query


def count_proteins(query: str) -> Optional[int]:
    """How many UniProtKB entries the query has (None if UniProt does not say)."""
    response = _get("/uniprotkb/search", {"query": query, "format": "json", "size": 1})
    total = response.headers.get("x-total-results")
    return int(total) if total and total.isdigit() else None


def fasta_filename(proteome: Proteome, reviewed_only: bool, isoforms: bool) -> str:
    organism = re.sub(r"[^A-Za-z0-9]+", "_", proteome.organism).strip("_") or "proteome"
    name = f"{proteome.upid}_{organism}_{'swissprot' if reviewed_only else 'all'}"
    if isoforms:
        name += "_isoforms"
    return name + ".fasta"


def download_fasta(
    query: str,
    dest: Path,
    isoforms: bool = False,
    progress: Optional[Callable[[int, int], None]] = None,
) -> int:
    """Stream the proteins of ``query`` as FASTA into ``dest``.

    ``progress(bytes, entries)`` is called while the file arrives. Returns the
    number of entries; raises ``UniProtError`` (and leaves no file) when the
    download fails or is empty.
    """
    dest = Path(dest)
    part = dest.with_name(f".{dest.name}.part")
    params = {"query": query, "format": "fasta"}
    if isoforms:
        params["includeIsoform"] = "true"
    response = _get("/uniprotkb/stream", params, stream=True)
    n_bytes = n_entries = 0
    first = last = b""
    try:
        with open(part, "wb") as f:
            # requests undoes the gzip transfer encoding UniProt applies
            for chunk in response.iter_content(chunk_size=1 << 20):
                if not chunk:
                    continue
                if not first:
                    first = chunk[:1]
                f.write(chunk)
                n_bytes += len(chunk)
                # Headers start a line; one may straddle two chunks
                n_entries += chunk.count(b"\n>") + (last == b"\n" and chunk[:1] == b">")
                last = chunk[-1:]
                if progress is not None:
                    progress(n_bytes, n_entries + (first == b">"))
    except (requests.RequestException, OSError) as e:
        part.unlink(missing_ok=True)
        raise UniProtError(f"The download from UniProt broke off: {e}") from e
    finally:
        response.close()
    n_entries += first == b">"
    if not n_entries:
        part.unlink(missing_ok=True)
        raise UniProtError("UniProt returned no proteins for this proteome.")
    os.replace(part, dest)
    return n_entries
