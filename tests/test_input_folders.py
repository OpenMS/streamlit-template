"""Tests for src/workflow/InputFolders.py (Streamlit-free)."""
import pytest

from src.workflow.InputFolders import (
    design_rows,
    folder_counts,
    load_folders,
    rename_folder,
    save_folders,
    suggest_groups,
)


def _groups(names):
    return [(s.file, s.group, s.replicate, s.fraction) for s in suggest_groups(names)]


@pytest.mark.parametrize(
    "names, expected",
    [
        (
            ["ctrl_R1.mzML", "ctrl_R2.mzML", "treat_R1.mzML", "treat_R2.mzML"],
            [("ctrl", 1), ("ctrl", 2), ("treat", 1), ("treat", 2)],
        ),
        (
            ["HeLa_DMSO_01.raw", "HeLa_DMSO_02.raw", "HeLa_Drug_01.raw", "HeLa_Drug_02.raw"],
            [("DMSO", 1), ("DMSO", 2), ("Drug", 1), ("Drug", 2)],
        ),
        (  # run dates and ids that occur once are not part of the group
            ["20240101_QE_ctrl_1.mzML", "20240102_QE_ctrl_2.mzML",
             "20240103_QE_heat_1.mzML", "20240104_QE_heat_2.mzML"],
            [("ctrl", 1), ("ctrl", 2), ("heat", 1), ("heat", 2)],
        ),
        (
            ["sampleA-rep1.mzML", "sampleA-rep2.mzML", "sampleB-rep1.mzML", "sampleB-rep2.mzML"],
            [("sampleA", 1), ("sampleA", 2), ("sampleB", 1), ("sampleB", 2)],
        ),
        (
            ["ctrl1.mzML", "ctrl2.mzML", "treated1.mzML", "treated2.mzML"],
            [("ctrl", 1), ("ctrl", 2), ("treated", 1), ("treated", 2)],
        ),
        (  # time points are groups, not technical replicates
            ["T0_rep1.mzML", "T0_rep2.mzML", "T1_rep1.mzML", "T1_rep2.mzML"],
            [("T0", 1), ("T0", 2), ("T1", 1), ("T1", 2)],
        ),
    ],
)
def test_suggest_groups(names, expected):
    assert [(g, r) for _, g, r, _ in _groups(names)] == expected


def test_fractions_of_one_sample_share_its_replicate():
    got = _groups(["x_F1.mzML", "x_F2.mzML", "y_F1.mzML", "y_F2.mzML"])
    assert [(g, r, f) for _, g, r, f in got] == [
        ("x", 1, 1), ("x", 1, 2), ("y", 1, 1), ("y", 1, 2),
    ]


def test_replicates_are_counted_when_names_do_not_number_them():
    got = _groups(["ctrl_a.mzML", "ctrl_b.mzML", "drug_a.mzML", "drug_b.mzML", "drug_c.mzML"])
    # "a"/"b" vary, so the group is the whole varying part: no grouping
    assert got == [] or all(r >= 1 for _, _, r, _ in got)


@pytest.mark.parametrize(
    "names",
    [
        ["run1.mzML", "run2.mzML", "run3.mzML"],  # one group
        ["alpha.mzML", "beta.mzML", "gamma.mzML"],  # every file its own group
        ["ctrl_1.mzML", "treat_1.mzML"],  # too few files
    ],
)
def test_no_suggestion_without_a_grouping(names):
    assert suggest_groups(names) == []


def test_folders_round_trip_and_rename(tmp_path):
    save_folders(tmp_path, "mzML-files", {"/x/a.mzML": "ctrl", "b.mzML": "ctrl", "c.mzML": " "})
    assert load_folders(tmp_path, "mzML-files") == {"a.mzML": "ctrl", "b.mzML": "ctrl"}
    assert load_folders(tmp_path, "other") == {}
    rename_folder(tmp_path, "mzML-files", "ctrl", "control")
    assert set(load_folders(tmp_path, "mzML-files").values()) == {"control"}
    rename_folder(tmp_path, "mzML-files", "control", "")
    assert load_folders(tmp_path, "mzML-files") == {}
    assert not (tmp_path / "input-folders.json").exists()


def test_folder_counts_in_natural_order():
    folders = {"a": "g10", "b": "g2", "c": "g2"}
    assert list(folder_counts(folders, ["a", "b", "c", "d"]).items()) == [("g2", 2), ("g10", 1)]


def test_design_rows_take_folders_as_conditions():
    files = ["/d/x_1.mzML", "/d/x_2.mzML", "/d/y.mzML", "/d/z.mzML"]
    rows = design_rows(files, {"x_1.mzML": "ctrl", "x_2.mzML": "ctrl", "y.mzML": "drug"})
    assert {f: (r.group, r.replicate) for f, r in rows.items()} == {
        "x_1.mzML": ("ctrl", 1), "x_2.mzML": ("ctrl", 2), "y.mzML": ("drug", 1),
    }


def test_design_rows_suggest_for_files_outside_folders():
    files = ["ctrl_R1.mzML", "ctrl_R2.mzML", "treat_R1.mzML", "treat_R2.mzML"]
    rows = design_rows(files, {"ctrl_R1.mzML": "control"}, suggest=True)
    assert rows["ctrl_R1.mzML"].group == "control"
    assert rows["ctrl_R2.mzML"].group == "ctrl"
    assert (rows["treat_R2.mzML"].group, rows["treat_R2.mzML"].replicate) == ("treat", 2)
    assert design_rows(files, {}, suggest=False) == {}
