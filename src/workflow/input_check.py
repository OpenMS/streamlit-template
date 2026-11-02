"""Input check: inspect mzML and FASTA files before a workflow runs.

A file a TOPP tool cannot read (not an mzML, cut off during a copy, no
spectra, a FASTA without entries or with a duplicate accession) otherwise
fails somewhere inside the run, often minutes in and with a message that does
not name the file. ``inspect_file()`` reads only what it needs (the mzML
header and tail, a stream over the FASTA) and returns an ``InputReport``:

- ``errors``: the file is unusable, the Run page refuses to start
- ``warnings``: the run can start, but the user should know
- ``summary``: a short count, e.g. "799 spectra, MS2 present" or "6,721 proteins"

Kept free of Streamlit so ``execution()`` and the queue worker can use it.
Results are cached per (path, size, modification time).
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

MZML_TYPES = ("mzml",)
FASTA_TYPES = ("fasta", "fa", "faa", "fas")

# Accessions marking decoy entries, as written by OpenMS DecoyDatabase and
# common search engines.
DECOY_PREFIXES = ("DECOY_", "decoy_", "rev_", "REV_")

_CHUNK = 4 * 1024 * 1024
_SPECTRUM_LIST = re.compile(rb'<spectrumList\b[^>]*?\bcount="(\d+)"')
_CHROMATOGRAM_LIST = re.compile(rb'<chromatogramList\b[^>]*?\bcount="(\d+)"')
# "ms level" cvParam (MS:1000511) with a value of 2 or more
_MSN = re.compile(rb'accession="MS:1000511"[^>]*?value="([2-9]|\d\d+)"')
_AMINO_ACIDS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ*")

_cache: Dict[Tuple[str, int, int, bool], "InputReport"] = {}


@dataclass
class InputReport:
    """What the input check found in one file."""

    path: str
    kind: str = ""  # "mzML", "FASTA" or "" when the type is not checked
    summary: str = ""
    counts: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def checked(self) -> bool:
        return bool(self.kind)

    @property
    def usable(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        """"unusable", "warning", "ok" or "unchecked"."""
        if self.errors:
            return "unusable"
        if self.warnings:
            return "warning"
        return "ok" if self.kind else "unchecked"

    def problems(self) -> List[str]:
        return self.errors + self.warnings

    def describe(self) -> str:
        """One line naming the file, its counts and its problems."""
        parts = [p for p in [self.summary] + self.problems() if p]
        return f"{self.name}: " + "; ".join(parts) if parts else self.name


def file_kind(path) -> str:
    """ "mzML", "FASTA" or "" for a path, from its extension."""
    suffix = Path(str(path)).suffix.lower().lstrip(".")
    if suffix in MZML_TYPES:
        return "mzML"
    if suffix in FASTA_TYPES:
        return "FASTA"
    return ""


def inspect_file(path, require_ms2: bool = False) -> InputReport:
    """Inspect an mzML or FASTA file; other types come back unchecked.

    Args:
        path: The file.
        require_ms2: Make an mzML without MS2 spectra unusable, for workflows
            that identify peptides from fragment spectra. Otherwise "MS1 only"
            is just part of the summary.
    """
    path = str(path)
    kind = file_kind(path)
    if not kind:
        return InputReport(path)
    try:
        st = os.stat(path)
    except OSError:
        return InputReport(path, kind, errors=["file not found"])
    key = (os.path.abspath(path), st.st_size, st.st_mtime_ns, require_ms2)
    if key not in _cache:
        if os.path.isdir(path):
            report = InputReport(path, kind, errors=["is a folder, not a file"])
        elif kind == "mzML":
            report = inspect_mzml(path, require_ms2=require_ms2)
        else:
            report = inspect_fasta(path)
        _cache[key] = report
    return _cache[key]


def check_inputs(paths: Iterable, require_ms2: bool = False) -> List[InputReport]:
    """Inspect several files; see ``inspect_file()``."""
    return [inspect_file(p, require_ms2=require_ms2) for p in paths]


def unusable(reports: Iterable[InputReport]) -> List[InputReport]:
    """The reports of files a workflow must not start with."""
    return [r for r in reports if r.errors]


def inspect_mzml(path, require_ms2: bool = False) -> InputReport:
    """Spectrum count from the header, MS2 presence, and whether the file is complete."""
    report = InputReport(str(path), "mzML")
    size = os.path.getsize(path)
    if size == 0:
        report.errors.append("empty file")
        return report

    with open(path, "rb") as f:
        head = f.read(64 * 1024)
        if head[:2] == b"\x1f\x8b":
            report.errors.append("gzip-compressed, unpack it first")
            return report
        if b"<mzML" not in head and b"<indexedmzML" not in head:
            report.errors.append("not an mzML file")
            return report

        f.seek(max(0, size - 4096))
        tail = f.read().rstrip()
        complete = tail.endswith(b"</mzML>") or tail.endswith(b"</indexedmzML>")

        # One pass from the start: the spectrum count is in the header and an
        # MSn spectrum is usually within the first few MB, so the loop stops
        # early; an MS1-only file is read once to the end.
        f.seek(0)
        n_spectra = n_chrom = None
        has_msn = False
        carry = b""
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            buf = carry + chunk
            if n_spectra is None:
                m = _SPECTRUM_LIST.search(buf)
                if m:
                    n_spectra = int(m.group(1))
            if n_chrom is None:
                m = _CHROMATOGRAM_LIST.search(buf)
                if m:
                    n_chrom = int(m.group(1))
            if not has_msn and _MSN.search(buf):
                has_msn = True
            if n_spectra is not None and (has_msn or n_spectra == 0):
                break
            carry = buf[-512:]

    n_spectra = n_spectra or 0
    report.counts = {"spectra": n_spectra, "chromatograms": n_chrom or 0, "ms2": int(has_msn)}
    if not complete:
        report.errors.append("cut off: the file ends before its closing tag (incomplete copy or download?)")
    if n_spectra == 0:
        report.errors.append("no spectra")
        report.summary = f"{n_chrom:,} chromatograms" if n_chrom else ""
        return report
    report.summary = f"{n_spectra:,} spectra" + (", MS2 present" if has_msn else ", MS1 only")
    if not has_msn and require_ms2:
        report.errors.append("no MS2 spectra")
    return report


def inspect_fasta(path) -> InputReport:
    """Entry count, duplicate accessions and residue problems of a FASTA file."""
    report = InputReport(str(path), "FASTA")
    if os.path.getsize(path) == 0:
        report.errors.append("empty file")
        return report

    n_entries = n_decoys = 0
    seen = set()
    duplicates: List[str] = []
    no_accession = empty_seq = lowercase = 0
    odd_chars: set = set()
    entries_with_odd = 0
    longest = 0

    current_len = None  # residues of the open entry; None before the first header
    current_lower = current_odd = False

    def close_entry():
        nonlocal empty_seq, lowercase, entries_with_odd, longest
        if current_len is None:
            return
        if current_len == 0:
            empty_seq += 1
        lowercase += current_lower
        entries_with_odd += current_odd
        longest = max(longest, current_len)

    with open(path, "rb") as f:
        first = f.read(4)
        if first.startswith(b"\xef\xbb\xbf"):
            report.warnings.append("starts with a byte-order mark")
        f.seek(0)
        for i, raw in enumerate(f):
            if i == 0 and raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            if b"\x00" in raw:
                report.errors.append("not a FASTA file (binary content)")
                return report
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if line.startswith(">"):
                close_entry()
                current_len, current_lower, current_odd = 0, False, False
                n_entries += 1
                accession = line[1:].split(maxsplit=1)[0] if line[1:].strip() else ""
                if not accession:
                    no_accession += 1
                    continue
                if accession.startswith(DECOY_PREFIXES):
                    n_decoys += 1
                if accession in seen:
                    if len(duplicates) < 1000:
                        duplicates.append(accession)
                else:
                    seen.add(accession)
            elif line.startswith(";"):
                continue  # old-style comment line
            elif current_len is None:
                report.errors.append("not a FASTA file (does not start with a '>' header)")
                return report
            else:
                current_len += len(line)
                if not current_lower and line != line.upper():
                    current_lower = True
                bad = set(line.upper()) - _AMINO_ACIDS
                if bad:
                    current_odd = True
                    odd_chars |= bad
    close_entry()

    report.counts = {"entries": n_entries, "decoys": n_decoys, "duplicates": len(duplicates)}
    if n_entries == 0:
        report.errors.append("no entries")
        return report
    report.summary = f"{n_entries:,} proteins" + (f" ({n_decoys:,} decoys)" if n_decoys else "")
    if duplicates:
        shown = ", ".join(sorted(set(duplicates))[:3])
        report.errors.append(
            f"{len(duplicates):,} duplicate accession{'s' if len(duplicates) > 1 else ''} ({shown})"
        )
    if no_accession:
        report.errors.append(f"{no_accession:,} entr{'ies' if no_accession > 1 else 'y'} without an accession")
    if empty_seq:
        report.warnings.append(f"{empty_seq:,} entr{'ies' if empty_seq > 1 else 'y'} without a sequence")
    if lowercase:
        report.warnings.append(f"lowercase residues in {lowercase:,} entr{'ies' if lowercase > 1 else 'y'}")
    if entries_with_odd:
        chars = "".join(sorted(odd_chars))[:10]
        report.warnings.append(
            f"characters that are not residues ({chars}) in {entries_with_odd:,} entr{'ies' if entries_with_odd > 1 else 'y'}"
        )
    return report


def clear_cache() -> None:
    _cache.clear()


def param_files(params: dict) -> List[str]:
    """Paths in a workflow's params that the input check can inspect.

    Looks at every string or list of strings, so files picked with
    ``select_input_file()`` and FASTA paths typed into a text field both count.
    """
    found: List[str] = []
    for value in params.values():
        values = value if isinstance(value, list) else [value]
        for v in values:
            if isinstance(v, str) and file_kind(v) and v not in found and os.path.exists(v):
                found.append(v)
    return found


def summarize(reports: List[InputReport]) -> Optional[str]:
    """ "2 mzML, 1 FASTA checked" for the checked files, or None."""
    kinds: Dict[str, int] = {}
    for r in reports:
        if r.checked:
            kinds[r.kind] = kinds.get(r.kind, 0) + 1
    if not kinds:
        return None
    return ", ".join(f"{n} {k}" for k, n in kinds.items())
