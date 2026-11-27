"""The line above a narrowed peptide or PSM table: what it is narrowed to.

Picking a protein narrows the peptides, a peptide the PSMs. A line above each
narrowed table names what it is narrowed to and its place in the list it was
picked from ("Protein P02769 · 3 of 132"), steps to the previous or next one
without going back up, and shows everything again.

Not a component of its own: the peptide and PSM panels draw it above their
table. It reads the shared selection identifiers ``protein``, ``peptide`` and
``psm`` and the column contracts of the protein table (``accession``) and the
peptides of a protein (``accession``, ``peptide``).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

# Picking a protein forgets the peptide and PSM of the last one, a peptide its PSM
BELOW = {"protein": ("peptide", "psm"), "peptide": ("psm",)}


def ordered(values) -> list:
    """``values`` once each, in the order they come."""
    return list(dict.fromkeys(v for v in values if pd.notna(v)))


def place(items: list, current) -> tuple[int, int] | None:
    """``current``'s place in ``items``, counted from 1, and their number; None when it is not there."""
    try:
        return items.index(current) + 1, len(items)
    except ValueError:
        return None


def neighbour(items: list, current, step: int):
    """The item ``step`` places from ``current`` (wrapping around), or None."""
    where = place(items, current)
    if where is None:
        return None
    return items[(where[0] - 1 + step) % where[1]]


def proteins_of(proteins: pd.DataFrame) -> list:
    """The proteins in the order of the protein table."""
    return ordered(proteins["accession"]) if "accession" in proteins.columns else []


def peptides_of(peptides: pd.DataFrame, protein) -> list:
    """The peptides of ``protein`` in the order of the peptide table."""
    if protein is None or not {"accession", "peptide"} <= set(peptides.columns):
        return []
    return ordered(peptides.loc[peptides["accession"] == protein, "peptide"])


def _pick(state, identifier: str, value) -> None:
    for below in BELOW.get(identifier, ()):
        state.clear_selection(below)
    if value is None:
        state.clear_selection(identifier)
    else:
        state.set_selection(identifier, value)


def _line(state, identifier: str, label: str, items: list, key: str) -> None:
    current = state.get_selection(identifier)
    where = place(items, current)
    if where is None:
        return
    row = st.container(horizontal=True, vertical_alignment="center", gap="small")
    row.markdown(f"{label} **{current}** · {where[0]} of {where[1]}", width="content")
    many = where[1] > 1
    row.button("◀", key=f"{key}-prev", help=f"Previous {label.lower()}", disabled=not many,
               on_click=_pick, args=(state, identifier, neighbour(items, current, -1)))
    row.button("▶", key=f"{key}-next", help=f"Next {label.lower()}", disabled=not many,
               on_click=_pick, args=(state, identifier, neighbour(items, current, 1)))
    row.button("Show all", key=f"{key}-all", help=f"Show the rows of every {label.lower()} again",
               on_click=_pick, args=(state, identifier, None))


def narrowed_to(state, proteins: pd.DataFrame, peptides: pd.DataFrame, key: str, levels: tuple) -> None:
    """The line above a narrowed table, one row for each of ``levels`` ("protein", "peptide")."""
    if "protein" in levels:
        _line(state, "protein", "Protein", proteins_of(proteins), f"{key}-protein")
    if "peptide" in levels:
        protein = state.get_selection("protein")
        _line(state, "peptide", "Peptide", peptides_of(peptides, protein), f"{key}-peptide")
