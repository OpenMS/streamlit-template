"""Identifications across runs: every entity any run of a comparison found,
with how many runs detected it, how many found it at all (detected or matched)
and, per run, how that run found it. A click picks the entity.

Insight component: ``Table``. Columns: ``RowIndex``, ``label``, one per run
and ``Detected``, ``Found``; ``protein_label``, ``mass``, ``proteoforms`` and
``PrSMs`` shown when present.
"""

from __future__ import annotations

from src.viz.columns import fixed

COMPONENT = "Table"
RUN_HELP = ("detected; matched, identified (match between runs, identified in the run); "
            "matched (match between runs); missing")


def columns(fields, runs, noun: str, sample_noun: str = "Run", with_protein: bool = False) -> list[dict]:
    """The column definitions for a table with ``fields``."""
    singular = noun[:-1].capitalize() if noun.endswith("s") else noun
    out = [{"title": singular, "field": "label", "sorter": "string"}]
    if "protein_label" in fields and with_protein:
        out.append({"title": "Protein", "field": "protein_label", "sorter": "string"})
    if "mass" in fields:
        out.append({"title": "Mass (Da)", "field": "mass", "sorter": "number", **fixed(2)})
    if "proteoforms" in fields:
        out.append({"title": "Proteoforms", "field": "proteoforms", "sorter": "number"})
    if "PrSMs" in fields:
        out.append({"title": "PrSMs", "field": "PrSMs", "sorter": "number",
                    "headerTooltip": "Spectra (PrSMs) that identify it, over all runs."})
    out += [
        {"title": "Detected", "field": "Detected", "sorter": "number",
         "headerTooltip": f"{sample_noun}s that found it themselves."},
        {"title": "Found", "field": "Found", "sorter": "number",
         "headerTooltip": f"{sample_noun}s that found it themselves or matched it from another one."},
    ]
    out += [{"title": run, "field": run, "sorter": "string", "headerTooltip": RUN_HELP} for run in runs]
    return out


def settings(column_definitions: list[dict], title: str, selection: str = "entry", **overrides) -> dict:
    """Constructor arguments, the data left out."""
    return dict(
        column_definitions=column_definitions, index_field="RowIndex", title=title,
        go_to_fields=["label"], row_overview="{label}", interactivity={selection: "RowIndex"},
    ) | overrides
