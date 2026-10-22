"""Tests for src/workflow/ExperimentalDesign.py (Streamlit-free)."""
import pandas as pd
import pyopenms as poms

from src.workflow.ExperimentalDesign import (
    COLUMNS,
    align_design,
    check_design,
    default_design,
    load_design,
    read_design,
    save_design,
    to_openms_design,
)

FILES = ["/data/ctrl_1.mzML", "/data/ctrl_2.mzML", "/data/treat_1.mzML", "/data/treat_2.mzML"]


def _design():
    return pd.DataFrame({
        "file": ["ctrl_1.mzML", "ctrl_2.mzML", "treat_1.mzML", "treat_2.mzML"],
        "condition": ["ctrl", "ctrl", "treat", "treat"],
        "replicate": [1, 2, 1, 2],
        "fraction": [1, 1, 1, 1],
    })


def test_default_design_does_not_guess_conditions():
    design = default_design(FILES)
    assert list(design.columns) == COLUMNS
    assert list(design["file"]) == ["ctrl_1.mzML", "ctrl_2.mzML", "treat_1.mzML", "treat_2.mzML"]
    assert set(design["condition"]) == {""}
    assert list(design["replicate"]) == [1, 2, 3, 4]


def test_openms_design_round_trip_and_loads_in_pyopenms(tmp_path):
    text = to_openms_design(_design(), FILES)
    path = tmp_path / "design.tsv"
    path.write_text(text)
    ed = poms.ExperimentalDesignFile.load(str(path), False)
    assert ed.getNumberOfMSFiles() == 4
    assert ed.getNumberOfSamples() == 4
    assert "/data/ctrl_1.mzML" in text
    pd.testing.assert_frame_equal(read_design(path), _design())


def test_fractions_and_technical_replicates_map_to_fraction_groups(tmp_path):
    design = pd.DataFrame({
        "file": ["a_f1.mzML", "a_f2.mzML", "a_f1_tech.mzML", "a_f2_tech.mzML"],
        "condition": ["A"] * 4,
        "replicate": [1, 1, 1, 1],
        "fraction": [1, 2, 1, 2],
    })
    path = tmp_path / "design.tsv"
    path.write_text(to_openms_design(design))
    ed = poms.ExperimentalDesignFile.load(str(path), False)
    assert ed.isFractionated()
    assert ed.getNumberOfFractionGroups() == 2  # two technical replicates
    assert ed.getNumberOfSamples() == 1


def test_read_one_table_openms_design():
    text = (
        "Fraction_Group\tFraction\tSpectra_Filepath\tLabel\tSample\tMSstats_Condition\tMSstats_BioReplicate\n"
        "1\t1\t/x/ctrl_1.mzML\t1\t1\tctrl\t1\n"
        "2\t1\t/x/treat_1.mzML\t1\t2\ttreat\t1\n"
    )
    design = read_design(text)
    assert list(design["file"]) == ["ctrl_1.mzML", "treat_1.mzML"]
    assert list(design["condition"]) == ["ctrl", "treat"]


def test_read_sdrf_uses_factor_values_and_dedups_labels():
    text = (
        "source name\tcharacteristics[biological replicate]\tcomment[label]\tcomment[data file]"
        "\tcomment[fraction identifier]\tfactor value[treatment]\n"
        "s1\t1\tlabel free sample\tctrl_1.raw\t1\tcontrol\n"
        "s2\t2\tlabel free sample\tctrl_2.raw\t2\tcontrol\n"
        "s2\t2\tlabel free sample\tctrl_2.raw\t2\tcontrol\n"
    )
    design = read_design(text.encode())
    assert list(design["file"]) == ["ctrl_1.raw", "ctrl_2.raw"]
    assert list(design["condition"]) == ["control", "control"]
    assert list(design["replicate"]) == [1, 2]
    assert list(design["fraction"]) == [1, 2]


def test_align_design_matches_by_name_and_fills_defaults():
    imported = _design().iloc[:2].assign(file=lambda d: "/elsewhere/" + d["file"])
    aligned = align_design(imported, FILES[:3])
    assert list(aligned["file"]) == ["ctrl_1.mzML", "ctrl_2.mzML", "treat_1.mzML"]
    assert list(aligned["condition"]) == ["ctrl", "ctrl", ""]


def test_check_design_notices():
    assert check_design(_design()) == []
    notices = check_design(default_design(FILES))
    assert any("no condition" in n for n in notices)
    gaps = _design().assign(fraction=[1, 3, 1, 1], replicate=[1, 1, 1, 2])
    notices = check_design(gaps)
    assert any("missing fraction(s) 2" in n for n in notices)
    assert any("different numbers of fractions" in n for n in notices)


def test_save_and_load_design(tmp_path):
    save_design(tmp_path, _design(), FILES)
    loaded = load_design(tmp_path, FILES[::-1])
    assert list(loaded["file"]) == ["treat_2.mzML", "treat_1.mzML", "ctrl_2.mzML", "ctrl_1.mzML"]
    assert list(loaded["condition"]) == ["treat", "treat", "ctrl", "ctrl"]
    assert load_design(tmp_path / "missing", FILES)["condition"].eq("").all()
