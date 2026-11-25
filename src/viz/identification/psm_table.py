"""PSMs: every peptide-spectrum match of a run with its sequence, charge,
precursor m/z and retention time, score, decoy mark, proteins and contaminant
mark. A click picks the PSM, its file and its spectrum. ``menu()`` adds a
q-value column with thresholds, a contaminant switch and a search over the
sequence and proteins.

Insight component: ``Table``. Columns: ``id_idx`` (the PSM), ``file_index``,
``scan_id``, ``sequence``, ``charge``, ``mz``, ``rt``, ``score``, ``decoy``,
``protein_accession``, ``contaminant``, ``proforma``, ``filename``; with the
menu also ``q_value`` and ``not_contaminant``.

``all_files_settings()`` is the same table over the PSMs of several files at
once: the rows of each file's table put together, with ``file_name`` (shown
first, searchable) and a row id of their own, ``psm_row``, which a click picks
under ``psm_all``. The app keeps ``source`` (the file a row comes from) to map
a picked row back to that file's ``id_idx``, ``file_index`` and ``scan_id``.
"""

from __future__ import annotations

import copy

COMPONENT = "Table"

COLUMNS = [
    {"field": "sequence", "title": "Sequence"},
    {"field": "charge", "title": "Z", "sorter": "number"},
    {"field": "mz", "title": "m/z", "sorter": "number"},
    {"field": "rt", "title": "RT", "sorter": "number"},
    {"field": "score", "title": "Score", "sorter": "number"},
    # Only decoys get a mark (a tick, no cross on targets), so they stand out. Next to
    # the score, so it stays in view when a narrow table folds the last columns away.
    {"field": "decoy", "title": "Decoy", "formatter": "tickCross", "formatterParams": {"crossElement": False},
     "sorter": "boolean", "hozAlign": "center"},
    {"field": "protein_accession", "title": "Proteins"},
    {"field": "contaminant", "title": "Contaminant", "formatter": "tickCross", "sorter": "boolean"},
    {"field": "proforma", "title": "ProForma", "visible": False},
    {"field": "filename", "title": "File", "visible": False},
    {"field": "scan_id", "title": "Scan", "sorter": "number", "visible": False},
]

Q_FIELD = "q_value"
CLEAN_FIELD = "not_contaminant"
SEARCH_FIELDS = ("sequence", "proforma", "protein_accession")
# Rounded for display (the cache holds float32 noise like 494.2902526855469)
ROUNDING = {"mz": 4, "rt": 1}


def columns() -> list[dict]:
    """A fresh copy of the columns for one Table."""
    return copy.deepcopy(COLUMNS)


def settings(ascending: bool = True, file: str = "file", spectrum: str = "spectrum",
             psm: str = "identification", **overrides) -> dict:
    """``ascending`` says whether a lower score is better (an error probability
    or q-value), so the best matches come first."""
    return dict(
        interactivity={file: "file_index", spectrum: "scan_id", psm: "id_idx"},
        column_definitions=columns(),
        initial_sort=[{"column": "score", "dir": "asc" if ascending else "desc"}],
        index_field="id_idx",
    ) | overrides


def _money(precision: int) -> dict:
    return {"formatter": "money", "formatterParams": {"thousand": False, "precision": precision}}


def q_value_column(tooltip: str = "The lowest FDR at which this match is accepted") -> dict:
    return {"field": Q_FIELD, "title": "q-value", "sorter": "number", **_money(5), "headerTooltip": tooltip}


def with_q_value(column_definitions: list[dict], tooltip: str | None = None) -> list[dict]:
    """The columns rounded for display, with the q-value column after the score."""
    shown = [
        {**c, **_money(ROUNDING[c["field"]])} if c.get("field") in ROUNDING and "formatter" not in c else c
        for c in column_definitions
    ]
    after = next((i for i, c in enumerate(shown) if c.get("field") == "score"), len(shown) - 1)
    shown.insert(after + 1, q_value_column(*([tooltip] if tooltip else [])))
    return shown


def menu(fields: list[str], q_suggestions: list | None = None, search_fields: tuple = SEARCH_FIELDS,
         placeholder: str = "Peptide or protein") -> dict:
    """The table's menu over the columns in ``fields``: hide contaminants,
    search, and q-value thresholds."""
    return dict(
        toggle_filters=[{"label": "Hide contaminants", "column": CLEAN_FIELD, "default": False}],
        search=[c for c in search_fields if c in fields],
        search_placeholder=placeholder,
        numeric_filters={Q_FIELD: {"op": "<=", "suggestions": list(q_suggestions or [])}},
    )


# The table of several files: its own row id, picked under ALL_FILES_SELECTION
ROW_FIELD = "psm_row"
FILE_FIELD = "file_name"
ALL_FILES_SELECTION = "psm_all"


def all_files_columns(column_definitions: list[dict], file_title: str = "File") -> list[dict]:
    """The columns of one file's table, rounded for display, with the file first."""
    shown = [
        {**c, **_money(ROUNDING[c["field"]])} if c.get("field") in ROUNDING and "formatter" not in c else c
        for c in column_definitions
    ]
    return [{"field": FILE_FIELD, "title": file_title, "headerTooltip": "The input file of this PSM"}] + shown


def all_files_settings(column_definitions: list[dict], fields, search_fields: tuple = SEARCH_FIELDS,
                       selection: str = ALL_FILES_SELECTION, **overrides) -> dict:
    """Constructor arguments of the PSM table over several files. ``column_definitions``
    are one file's columns, ``fields`` the columns of the merged rows."""
    return dict(
        interactivity={selection: ROW_FIELD},
        column_definitions=all_files_columns(column_definitions),
        index_field=ROW_FIELD,
        toggle_filters=[{"label": "Hide contaminants", "column": CLEAN_FIELD, "default": False}],
        search=[c for c in (FILE_FIELD, *search_fields) if c in fields],
        search_placeholder="File, peptide or protein",
    ) | overrides
