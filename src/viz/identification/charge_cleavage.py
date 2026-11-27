"""Charge states and missed cleavages: per file, the share of target PSMs
with each precursor charge and the share of identified peptides with 0, 1 and
2 or more missed cleavages, two checks of the sample preparation. A tryptic
digest gives mostly 2+ and 3+ precursors; many 1+ ones point to contamination,
and a large share of missed cleavages to an incomplete digestion.

Insight components: a ``Table`` with one row per file and an *All files* row,
then two ``SeriesPlot`` bar plots, the files side by side.

Columns read (one row per target PSM after the FDR filter): ``file``,
``charge``, ``sequence`` (unmodified) and ``missed_cleavages`` (missing for a
search without an enzyme). Missed cleavages are counted once per distinct
peptide of a file.
"""

from __future__ import annotations

import pandas as pd
import polars as pl

from src.viz.plumbing import as_polars

COMPONENT = "Table"
ALL_FILES = "All files"
MAX_CHARGE = 4  # charges of 4 and more share one bin
MAX_MISSED = 2  # missed cleavages of 2 and more share one bin

CHARGE_BINS = [str(z) for z in range(1, MAX_CHARGE)] + [f"{MAX_CHARGE}+"]
MISSED_BINS = [str(m) for m in range(MAX_MISSED)] + [f"{MAX_MISSED}+"]
# Sequential blues: low charge / no missed cleavage light, high dark
SHADES = ["#9ecae1", "#4292c6", "#2171b5", "#08519c"]


def _bin(value: int, top: int) -> str:
    return f"{top}+" if value >= top else str(int(value))


def _shares(values: pd.Series, bins: list[str]) -> tuple[pd.Series, pd.Series]:
    """Count and share (%) of each bin, 0 for an empty bin."""
    counts = values.value_counts().reindex(bins, fill_value=0)
    total = counts.sum()
    return counts, (counts / total * 100.0) if total else counts.astype(float)


def summary(psms) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """``(per_file, charges, missed)`` of a PSM table (see the module docstring).

    ``per_file`` has one row per file, *All files* first (``file_id`` 0):
    target PSMs, the share of each charge state, the share of peptides by
    missed cleavages and the mean missed cleavages per peptide. ``charges`` and
    ``missed`` hold one row per file and bin (``file``, ``bin``, ``share``,
    ``count``) for the bar plots; ``missed`` is empty when no file has
    missed cleavages counted.
    """
    psms = as_polars(psms).to_pandas()
    psms["charge_bin"] = psms["charge"].map(lambda z: _bin(z, MAX_CHARGE))
    has_missed = psms["missed_cleavages"].notna().any()
    files = sorted(psms["file"].unique())
    groups = [(0, ALL_FILES, psms)] + [(i + 1, f, psms[psms["file"] == f]) for i, f in enumerate(files)]
    rows, charge_rows, missed_rows = [], [], []
    for file_id, name, part in groups:
        row = {"file_id": file_id, "File": name, "Target PSMs": len(part)}
        counts, shares = _shares(part["charge_bin"], CHARGE_BINS)
        for bin_ in CHARGE_BINS:
            row[f"Charge {bin_} (%)"] = round(float(shares[bin_]), 1)
            charge_rows.append({"file": name, "bin": bin_, "share": float(shares[bin_]), "count": int(counts[bin_])})
        if has_missed:
            peptides = part.drop_duplicates(["file", "sequence"])
            values = peptides["missed_cleavages"].dropna().astype(int)
            counts, shares = _shares(values.map(lambda m: _bin(m, MAX_MISSED)), MISSED_BINS)
            for bin_ in MISSED_BINS:
                row[f"{bin_} missed (%)"] = round(float(shares[bin_]), 1)
                missed_rows.append({"file": name, "bin": bin_, "share": float(shares[bin_]), "count": int(counts[bin_])})
            row["Mean missed"] = round(float(values.mean()), 2) if len(values) else None
        rows.append(row)
    columns = ["file", "bin", "share", "count"]
    return pd.DataFrame(rows), pd.DataFrame(charge_rows, columns=columns), pd.DataFrame(missed_rows, columns=columns)


def _title(column: str) -> str:
    """A short column title: "2+" for charge 2, "≥1 MC" for one or more missed cleavages."""
    if column.startswith("Charge "):
        charge = column.split()[1]
        return f"≥{charge.rstrip('+')}+" if charge.endswith("+") else f"{charge}+"
    if column.endswith(" missed (%)"):
        count = column.split()[0]
        return f"≥{count.rstrip('+')} MC" if count.endswith("+") else f"{count} MC"
    return {"Target PSMs": "PSMs", "Mean missed": "Mean MC"}.get(column, column)


def _column(column: str) -> dict:
    """The short title, the full name as its tooltip, one decimal (two for the mean)."""
    definition = {"field": column, "title": _title(column), "sorter": "number", "hozAlign": "right"}
    if column == "Target PSMs":
        return definition
    return {
        **definition,
        "formatter": "money",
        "formatterParams": {"precision": 2 if column == "Mean missed" else 1, "thousand": False},
        "headerTooltip": "Mean missed cleavages per peptide" if column == "Mean missed" else column,
    }


def table_settings(per_file, **overrides) -> dict:
    """Constructor arguments of the per-file table, with ``data``."""
    frame = as_polars(per_file)
    return dict(
        data=frame.lazy(), index_field="file_id", title="Charge states and missed cleavages per file",
        layout="fitColumns", pagination=False,
        column_definitions=[{"field": "File", "title": "File", "widthGrow": 4}]
        + [_column(c) for c in frame.columns if c not in ("file_id", "File")],
    ) | overrides


def table_height(per_file, most: int = 12) -> int:
    """Height (px) that shows ``most`` files without scrolling."""
    return 90 + 34 * min(len(per_file), most)


def short_name(file: str, most: int = 28) -> str:
    """A file name short enough for an axis: without its extension, and the
    middle left out when it is still longer than ``most`` characters."""
    stem = file.rsplit(".", 1)[0] if "." in file else file
    if len(stem) <= most:
        return stem
    half = (most - 1) // 2
    return f"{stem[:half]}…{stem[-(most - 1 - half):]}"


def _bars(data, bins: list[str], legend: str, noun: str, title: str, name: str, **overrides) -> dict:
    frame = as_polars(data)
    names = {f: short_name(f) for f in frame["file"].unique().to_list()}
    if len(set(names.values())) < len(names):  # shortened names would collide
        names = {f: f for f in names}
    frame = frame.with_columns(
        pl.format("{}<br>{} {}: {}% ({} {})", "file", pl.lit(legend), "bin", pl.col("share").round(1), "count",
                  pl.lit(noun)).alias("hover"),
        pl.col("file").replace_strict(names, return_dtype=pl.Utf8).alias("file"),
    )
    return dict(
        data=frame, x_column="file", y_column="share", series_column="bin",
        series_names={b: f"{legend} {b}" for b in bins},
        series_colors={b: SHADES[len(SHADES) - len(bins) + i] for i, b in enumerate(bins)},
        mode="bars", hover_column="hover", title=title, x_label="File", y_label="Share (%)",
        svg_filename=name,
    ) | overrides


def charge_settings(charges, **overrides) -> dict:
    """Constructor arguments of the charge state bars, with ``data``."""
    return _bars(charges, CHARGE_BINS, "Charge", "PSMs", "Precursor charge states of target PSMs",
                 "charge-states", **overrides)


def cleavage_settings(missed, **overrides) -> dict:
    """Constructor arguments of the missed cleavage bars, with ``data``."""
    return _bars(missed, MISSED_BINS, "Missed cleavages", "peptides", "Missed cleavages of identified peptides",
                 "missed-cleavages", **overrides)
