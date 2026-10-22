"""Experimental design: which condition, biological replicate and fraction each MS file belongs to.

The design is a table with one row per file and the columns ``file`` (the
file name), ``condition``, ``replicate`` (biological replicate, 1-based) and
``fraction`` (1-based). Two rows with the same condition, replicate and
fraction are technical replicates of one sample.

It is read from and written to the OpenMS experimental design format
(``design.tsv``, which ProteomicsLFQ, ProteinQuantifier and MSstatsConverter
take via ``-design``), and read from SDRF. This module has no Streamlit
dependency, so ``execution()`` can call ``load_design()`` inside a queue
worker.
"""
import io
import re
from pathlib import Path
from typing import List, Union

import pandas as pd

DESIGN_FILE = "experimental-design.tsv"
COLUMNS = ["file", "condition", "replicate", "fraction"]

_FILE_SECTION = ["Fraction_Group", "Fraction", "Spectra_Filepath", "Label", "Sample"]
_SAMPLE_SECTION = ["Sample", "MSstats_Condition", "MSstats_BioReplicate"]


def _file_name(path: str) -> str:
    """The last component of a path, splitting on / and \\ so Windows paths work on any host."""
    return re.split(r"[\\/]", path)[-1]


def default_design(files: List[str]) -> pd.DataFrame:
    """A design for ``files`` with no conditions set, one biological replicate per file and no fractions.

    Conditions are left empty rather than guessed from file names.
    """
    names = [_file_name(str(f)) for f in files]
    return pd.DataFrame({
        "file": names,
        "condition": [""] * len(names),
        "replicate": list(range(1, len(names) + 1)),
        "fraction": [1] * len(names),
    })


def _normalize(design: pd.DataFrame) -> pd.DataFrame:
    """Coerce a design to COLUMNS with string conditions and positive integer replicates and fractions."""
    out = design.reindex(columns=COLUMNS).copy()
    out["file"] = out["file"].fillna("").astype(str).map(lambda f: _file_name(f) if f else f)
    out["condition"] = out["condition"].fillna("").astype(str).str.strip()
    for col in ("replicate", "fraction"):
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(1).astype(int).clip(lower=1)
    return out.reset_index(drop=True)


def align_design(design: pd.DataFrame, files: List[str]) -> pd.DataFrame:
    """The design restricted to ``files``, in their order, with default rows for files it does not list.

    Files are matched by name, so a design written on another machine (other
    directories) still applies.
    """
    design = _normalize(design).drop_duplicates("file", keep="first")
    out = default_design(files).merge(design, on="file", how="left", suffixes=("_default", ""))
    for col in COLUMNS[1:]:
        out[col] = out[col].where(out[col].notna(), out[f"{col}_default"])
    return _normalize(out)


def _is_sdrf(header: List[str]) -> bool:
    lowered = [h.strip().lower() for h in header]
    return "source name" in lowered or any(h.startswith("comment[data file") for h in lowered)


def _from_sdrf(df: pd.DataFrame) -> pd.DataFrame:
    """Design rows from an SDRF table (one row per file and label)."""
    cols = {c.strip().lower(): c for c in df.columns}

    def first(*names):
        for name in names:
            if name in cols:
                return df[cols[name]]
        return None

    files = first("comment[data file]")
    if files is None:
        raise ValueError("SDRF has no 'comment[data file]' column.")
    factors = [cols[c] for c in cols if c.startswith("factor value[")]
    if factors:
        condition = df[factors].astype(str).agg(" | ".join, axis=1)
    else:
        condition = pd.Series([""] * len(df))
    replicate = first("characteristics[biological replicate]", "comment[biological replicate]")
    fraction = first("comment[fraction identifier]")
    design = pd.DataFrame({
        "file": files,
        "condition": condition,
        "replicate": replicate if replicate is not None else 1,
        "fraction": fraction if fraction is not None else 1,
    })
    # Multiplexed SDRFs list a file once per label; the design is per file.
    return design.drop_duplicates("file", keep="first")


def _from_openms(text: str) -> pd.DataFrame:
    """Design rows from an OpenMS design (one-table, or file and sample tables separated by a blank line)."""
    blocks = [b for b in text.replace("\r\n", "\n").split("\n\n") if b.strip()]
    if not blocks:
        raise ValueError("The file is empty.")
    files = pd.read_csv(io.StringIO(blocks[0]), sep="\t", dtype=str)
    if "Spectra_Filepath" not in files.columns:
        raise ValueError("Not an OpenMS design: no 'Spectra_Filepath' column.")
    if len(blocks) > 1:
        samples = pd.read_csv(io.StringIO(blocks[1]), sep="\t", dtype=str)
        files = files.merge(samples, on="Sample", how="left", suffixes=("", "_sample"))
    condition = files["MSstats_Condition"] if "MSstats_Condition" in files.columns else files.get("Sample", "")
    replicate = files["MSstats_BioReplicate"] if "MSstats_BioReplicate" in files.columns else 1
    design = pd.DataFrame({
        "file": files["Spectra_Filepath"],
        # to_openms_design writes an unset condition as NA, MSstats' missing value
        "condition": pd.Series(condition).replace("NA", ""),
        "replicate": replicate,
        "fraction": files["Fraction"] if "Fraction" in files.columns else 1,
    })
    return design.drop_duplicates("file", keep="first")


def read_design(source: Union[str, Path, bytes]) -> pd.DataFrame:
    """Parse an OpenMS design (one- or two-table) or an SDRF file into a design table.

    Args:
        source: a path, or the file's content as text or bytes.

    Raises:
        ValueError: if the content is neither format.
    """
    if isinstance(source, bytes):
        text = source.decode("utf-8-sig")
    elif isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and Path(source).is_file()):
        text = Path(source).read_text(encoding="utf-8-sig")
    else:
        text = source
    header = text.lstrip().split("\n", 1)[0].rstrip("\r").split("\t")
    if _is_sdrf(header):
        design = _from_sdrf(pd.read_csv(io.StringIO(text), sep="\t", dtype=str))
    else:
        design = _from_openms(text)
    return _normalize(design)


def to_openms_design(design: pd.DataFrame, paths: Union[List[str], None] = None) -> str:
    """The design as an OpenMS two-table ``design.tsv`` (label-free, so Label is 1).

    Each condition and biological replicate is one Sample. Each technical
    replicate of a sample is its own Fraction_Group, whose files are its fractions.

    Args:
        design: the design table.
        paths: full paths to write as Spectra_Filepath. When they are the
            design's files in row order (as for the selected input files),
            each row keeps its own path, even if two share a file name;
            otherwise they are matched by file name, and the bare file name
            is written for files not among them.
    """
    design = _normalize(design)
    paths = [str(p) for p in (paths or [])]
    if [_file_name(p) for p in paths] == list(design["file"]):
        spectra = paths
    else:
        by_name = {_file_name(p): p for p in paths}
        spectra = [by_name.get(f, f) for f in design["file"]]
    design["condition"] = design["condition"].replace("", "NA")
    design["technical"] = design.groupby(["condition", "replicate", "fraction"]).cumcount()
    design["Sample"] = design.groupby(["condition", "replicate"], sort=False).ngroup() + 1
    design["Fraction_Group"] = design.groupby(["condition", "replicate", "technical"], sort=False).ngroup() + 1
    file_section = pd.DataFrame({
        "Fraction_Group": design["Fraction_Group"],
        "Fraction": design["fraction"],
        "Spectra_Filepath": spectra,
        "Label": 1,
        "Sample": design["Sample"],
    }).sort_values(["Fraction_Group", "Fraction"], kind="stable")
    sample_section = (
        design.drop_duplicates("Sample")
        .rename(columns={"condition": "MSstats_Condition", "replicate": "MSstats_BioReplicate"})
        [_SAMPLE_SECTION]
        .sort_values("Sample")
    )
    return (
        file_section[_FILE_SECTION].to_csv(sep="\t", index=False, lineterminator="\n")
        + "\n"
        + sample_section.to_csv(sep="\t", index=False, lineterminator="\n")
    )


def check_design(design: pd.DataFrame) -> List[str]:
    """Notices about a design that is valid but probably not what was meant.

    None of these stop a run: a design with them still writes a loadable file.
    """
    design = _normalize(design)
    notices = []
    if design.empty:
        return notices
    unset = design.loc[design["condition"] == "", "file"].tolist()
    if unset:
        notices.append(f"{len(unset)} file(s) have no condition: {', '.join(unset[:3])}{' …' if len(unset) > 3 else ''}.")
    dup = design.loc[design["file"].duplicated(), "file"].unique().tolist()
    if dup:
        notices.append(f"Listed more than once: {', '.join(dup)}.")
    conditions = design.loc[design["condition"] != "", "condition"].nunique()
    if conditions == 1 and not unset:
        notices.append("All files are in one condition, so there is nothing to compare.")
    tech = design.groupby(["condition", "replicate", "fraction"]).size()
    if (tech > 1).any():
        notices.append(
            f"{int((tech > 1).sum())} condition/replicate/fraction combination(s) have more than one file; "
            "they are treated as technical replicates."
        )
    if design["fraction"].max() > 1:
        counts = {}
        for (cond, rep), grp in design.groupby(["condition", "replicate"]):
            fractions = sorted(set(grp["fraction"]))
            if fractions != list(range(1, fractions[-1] + 1)):
                missing = sorted(set(range(1, fractions[-1] + 1)) - set(fractions))
                notices.append(f"{cond or 'No condition'} replicate {rep} is missing fraction(s) {', '.join(map(str, missing))}.")
            counts[(cond, rep)] = len(fractions)
        if len(set(counts.values())) > 1:
            notices.append("Samples have different numbers of fractions.")
    return notices


def design_path(workflow_dir: Union[str, Path]) -> Path:
    """Where a workflow's experimental design is stored (an OpenMS design.tsv)."""
    return Path(workflow_dir, DESIGN_FILE)


def save_design(workflow_dir: Union[str, Path], design: pd.DataFrame, paths: Union[List[str], None] = None) -> Path:
    """Write the design to the workflow directory as an OpenMS design.tsv and return its path."""
    path = design_path(workflow_dir)
    path.write_text(to_openms_design(design, paths), encoding="utf-8")
    return path


def load_design(workflow_dir: Union[str, Path], files: Union[List[str], None] = None) -> pd.DataFrame:
    """The workflow's stored design, aligned to ``files`` when given.

    Returns the default design for ``files`` (or an empty table) when none is stored.
    """
    path = design_path(workflow_dir)
    design = read_design(path) if path.is_file() else pd.DataFrame(columns=COLUMNS)
    if files is None:
        return _normalize(design)
    return align_design(design, files)
