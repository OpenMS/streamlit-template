"""Charge states and missed cleavages: shares per file and the components' settings."""
import pandas as pd
import pytest

pl = pytest.importorskip("polars")

from src.viz.identification import charge_cleavage as cc


def _psms():
    return pd.DataFrame({
        "file": ["a", "a", "a", "a", "b", "b"],
        "charge": [1, 2, 2, 5, 3, 3],
        "sequence": ["PEPK", "PEPK", "PEKPEPR", "AAK", "KRAAK", "AAK"],
        "missed_cleavages": [0, 0, 1, 0, 2, 0],
    })


def test_shares_per_file_and_all_files():
    per_file, charges, missed = cc.summary(_psms())
    assert list(per_file["File"]) == [cc.ALL_FILES, "a", "b"]
    assert list(per_file["file_id"]) == [0, 1, 2]
    a = per_file.set_index("File").loc["a"]
    assert a["Target PSMs"] == 4
    assert a["Charge 1 (%)"] == 25.0 and a["Charge 2 (%)"] == 50.0 and a["Charge 4+ (%)"] == 25.0
    # PEPK counts once: three distinct peptides, one with a missed cleavage
    assert a["1 missed (%)"] == pytest.approx(33.3)
    assert a["Mean missed"] == pytest.approx(0.33)
    b = charges[charges["file"] == "b"].set_index("bin")
    assert b.loc["3", "share"] == 100.0 and b.loc["3", "count"] == 2
    assert set(missed["bin"]) == set(cc.MISSED_BINS)


def test_no_enzyme_leaves_missed_cleavages_out():
    psms = _psms().assign(missed_cleavages=None)
    per_file, _, missed = cc.summary(psms)
    assert missed.empty
    assert "Mean missed" not in per_file.columns


def test_settings_build_table_and_bars():
    per_file, charges, missed = cc.summary(pl.from_pandas(_psms()))
    table = cc.table_settings(per_file)
    titles = {c["field"]: c["title"] for c in table["column_definitions"]}
    assert titles["Charge 4+ (%)"] == "≥4+" and titles["2+ missed (%)"] == "≥2 MC"
    assert table["index_field"] == "file_id"
    bars = cc.charge_settings(charges)
    assert bars["mode"] == "bars" and bars["series_column"] == "bin"
    assert set(bars["series_colors"]) == set(cc.CHARGE_BINS)
    assert "Charge 1:" in bars["data"]["hover"][0]
    assert len(set(cc.cleavage_settings(missed)["series_colors"].values())) == len(cc.MISSED_BINS)


def test_short_names_on_the_axis():
    long = "B000248_Ap_6883_EXT-765_DIA_Yeast_UPS2_ratio01_DDA.mzML"
    assert cc.short_name("a.mzML") == "a"
    short = cc.short_name(long)
    assert len(short) == 28 and short.startswith("B000248_Ap") and short.endswith("ratio01_DDA")
    _, charges, _ = cc.summary(pd.DataFrame({
        "file": [long], "charge": [2], "sequence": ["PEPTIDEK"], "missed_cleavages": [0]}))
    frame = cc.charge_settings(charges)["data"]
    assert short in frame["file"].to_list() and any(long in h for h in frame["hover"])
