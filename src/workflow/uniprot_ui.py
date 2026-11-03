"""Widget: find a proteome on UniProt and add its FASTA to an upload folder.

Drawn by ``StreamlitUI.uniprot_proteome_download(key)`` below the
``upload_widget`` of a protein database. The file lands in that widget's
folder (``<workflow_dir>/input-files/<key>/``) and becomes the selected file of
``select_input_file(key)``. The UniProt calls are in ``uniprot.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.workflow import uniprot

REVIEWED = "Reviewed proteins only (Swiss-Prot)"
ALL = "All proteins of the proteome (Swiss-Prot and TrEMBL)"


@st.cache_data(ttl=3600, show_spinner=False)
def _search(text: str, reference_only: bool):
    return uniprot.search_proteomes(text, reference_only)


@st.cache_data(ttl=3600, show_spinner=False)
def _count(query: str):
    return uniprot.count_proteins(query)


def _format_size(n_bytes: int) -> str:
    return f"{n_bytes / 1e6:.1f} MB" if n_bytes >= 1e5 else f"{n_bytes / 1e3:.0f} kB"


def _select(ui, key: str, path: Path, target: dict) -> None:
    """Make the downloaded file the selection of ``select_input_file(key)``."""
    files_dir = path.parent
    # The example file only stands in while the folder has nothing else
    for fallback in target.get("fallback", []):
        copy = Path(files_dir, Path(fallback).name)
        if copy != path and copy.is_file():
            copy.unlink()
    current = ui.params.get(key)
    if isinstance(current, list):
        current = [f for f in current if Path(f).exists() and Path(f) != path]
        ui.params[key] = current + [str(path)]
    else:
        ui.params[key] = str(path)
    with open(ui.parameter_manager.params_file, "w", encoding="utf-8") as f:
        json.dump(ui.params, f, indent=4)
    # The widget takes the stored value only when it has none of its own
    st.session_state.pop(f"{ui.parameter_manager.param_prefix}{key}", None)


def proteome_download(ui, key: str, name: str = "") -> None:
    """Search UniProt proteomes by organism or taxon and download one as FASTA."""
    files_dir = Path(ui.workflow_dir, "input-files", key)
    target = ui.upload_targets.get(key, {})
    name = name or target.get("name") or key.replace("-", " ")
    state = f"uniprot-{key}"

    st.markdown("**🔎 Get a proteome from UniProt**")
    st.caption(
        f"Search the proteomes of [UniProt](https://www.uniprot.org/proteomes) by organism "
        f"name or NCBI taxonomy ID and add one as FASTA to the **{name}** files."
    )
    with st.form(f"{state}-form", border=False):
        c1, c2 = st.columns([4, 1])
        text = c1.text_input(
            "Organism or taxonomy ID", placeholder="e.g. Escherichia coli, human or 9606",
            label_visibility="collapsed", key=f"{state}-text",
        )
        searched = c2.form_submit_button("Search", use_container_width=True)
        reference_only = st.checkbox(
            "Reference proteomes only", value=True, key=f"{state}-reference",
            help="Reference proteomes are the curated, representative proteome of an "
                 "organism. Switch this off for strains without one.",
        )
    if searched:
        try:
            st.session_state[f"{state}-results"] = (text, _search(text, reference_only))
        except (ValueError, uniprot.UniProtError) as e:
            st.session_state.pop(f"{state}-results", None)
            st.error(str(e))

    found = st.session_state.get(f"{state}-results")
    if not found:
        return
    text, proteomes = found
    if not proteomes:
        st.warning(
            f"No {'reference ' if reference_only else ''}proteome found for **{text}**."
            + (" Try without *Reference proteomes only*." if reference_only else "")
        )
        return

    labels = {p.upid: p.label() for p in proteomes}
    upid = st.selectbox(
        f"{len(proteomes)} proteome{'s' if len(proteomes) != 1 else ''} found",
        list(labels), format_func=labels.get, key=f"{state}-pick",
    )
    proteome = next(p for p in proteomes if p.upid == upid)
    c1, c2 = st.columns([3, 1])
    scope = c1.radio("Proteins", [REVIEWED, ALL], key=f"{state}-scope", horizontal=True)
    reviewed_only = scope == REVIEWED
    isoforms = c2.checkbox(
        "Isoforms", value=False, key=f"{state}-isoforms",
        help="Add the alternative isoforms of reviewed entries as entries of their own.",
    )
    query = uniprot.fasta_query(upid, reviewed_only)
    try:
        count = _count(query)
    except uniprot.UniProtError:
        count = None
    filename = uniprot.fasta_filename(proteome, reviewed_only, isoforms)
    if count == 0:
        st.warning("This proteome has no reviewed entries. Choose all proteins instead.")
        return
    if count is not None:
        st.caption(f"{count:,} proteins{' plus isoforms' if isoforms else ''} as `{filename}`.")

    if st.button(f"⬇️ Add to **{name}** files", type="primary", key=f"{state}-download"):
        files_dir.mkdir(parents=True, exist_ok=True)
        dest = Path(files_dir, filename)
        bar = st.progress(0.0, text="Asking UniProt for the proteins…")

        def progress(n_bytes, n_entries):
            fraction = min(n_entries / count, 1.0) if count else 0.0
            bar.progress(fraction, text=f"{n_entries:,} proteins, {_format_size(n_bytes)}")

        try:
            n_entries = uniprot.download_fasta(query, dest, isoforms=isoforms, progress=progress)
        except uniprot.UniProtError as e:
            bar.empty()
            st.error(str(e))
            return
        bar.empty()
        _select(ui, key, dest, target)
        st.session_state[f"{state}-done"] = f"Added `{filename}` with {n_entries:,} proteins."
        st.rerun()

    done = st.session_state.pop(f"{state}-done", None)
    if done:
        st.success(done)
