"""The visualization library's comparison panels: their data functions and the
Insight components they build, drawn with Streamlit mocked out."""
import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# polars and openms_insight come with the apps, not with the template
pl = pytest.importorskip("polars")

from src.viz import comparison_steps, heatmap, pca, plumbing, series, volcano


def _wide():
    rng = np.random.default_rng(0)
    values = rng.lognormal(10, 1, size=(30, 4))
    values[0, 1] = np.nan
    values[3, 2] = 0
    return pd.DataFrame(values, columns=["a1", "a2", "b1", "b2"]).assign(id=[f"P{i}" for i in range(30)])


SAMPLES = ["a1", "a2", "b1", "b2"]
GROUPS = {"a1": "A", "a2": "A", "b1": "B", "b2": "B"}


def test_fingerprint_follows_content_and_settings():
    frame = pl.DataFrame({"x": [1, 2]})
    assert plumbing.fingerprint(frame, "s") == plumbing.fingerprint(frame.to_pandas(), "s")
    assert plumbing.fingerprint(frame, "s") != plumbing.fingerprint(frame, "t")
    assert plumbing.fingerprint(frame) != plumbing.fingerprint(pl.DataFrame({"x": [1, 3]}))


def test_group_colors_are_by_sorted_name():
    assert plumbing.group_colors(["B", "A", None]) == {"A": plumbing.GROUP_PALETTE[0], "B": plumbing.GROUP_PALETTE[1]}


def test_zoom_args_only_for_a_class_that_takes_it():
    class Takes:
        def __init__(self, zoom_identifier=None):
            pass

    assert plumbing.zoom_args(Takes, "zoom@x") == {"zoom_identifier": "zoom@x"}
    assert plumbing.zoom_args(object, "zoom@x") == {}
    assert plumbing.zoom_args(Takes, None) == {}


def test_missingness_counts_entries_with_a_gap():
    table, gaps = comparison_steps.missingness_vs_intensity(_wide(), SAMPLES)
    assert gaps == 2
    assert set(table["series"]) == {"complete", "missing"}


def test_imputed_values_are_the_ones_filled_in():
    before = _wide()
    after = before.fillna(100.0).replace(0, 100.0)
    table = comparison_steps.imputed_value_preview(before, after, SAMPLES)
    assert table[table["series"] == "imputed"]["y"].sum() == 2


def test_sample_distributions_thin_each_box():
    wide = _wide()
    data = comparison_steps.sample_distributions(wide, np.log2(wide[SAMPLES]), SAMPLES, True, points=11)
    assert data.groupby(["Sample", "Stage"]).size().max() == 11


def test_pvalue_histogram_names_its_entries():
    table, expected = comparison_steps.pvalue_histogram(pd.DataFrame({"p-value": [0.01, 0.5, 0.99, None]}),
                                                        bins=10, noun="Proteoforms")
    assert list(table.columns) == ["p-value", "Proteoforms"]
    assert table["Proteoforms"].sum() == 3 and expected == pytest.approx(0.3)


def test_thin_keeps_the_extremes():
    frame = pl.DataFrame({"g": ["a"] * 1000, "v": np.arange(1000.0)})
    kept = series.thin(frame, ["g"], "v", points=5)
    assert kept["v"].to_list() == [0.0, 250.0, 500.0, 749.0, 999.0] or kept.height == 5
    assert kept["v"].min() == 0 and kept["v"].max() == 999


def test_volcano_settings_name_the_comparison():
    settings = volcano.volcano_settings(pvalue_column="p-adj", reference="A", compared="B",
                                        multi_select={"set": "id"})
    assert settings["title"] == "B vs. A"
    assert settings["preset_labels"]["up"] == "Higher in B"
    assert settings["y_label"] == "-log10(adjusted p-value)"
    assert settings["selection_presets"] is True
    assert volcano.short_label("sp|P05161|ISG15_HUMAN") == "ISG15_HUMAN"


def test_most_variable_and_metadata():
    top = pca.most_variable(_wide(), SAMPLES, top=5, id_column="id")
    assert top.height == 5 and top.columns == ["id", *SAMPLES]
    meta = pca.sample_metadata(GROUPS, ["b1", "x", "a1"])
    assert meta.rows() == [("b1", "B"), ("a1", "A")]
    assert pca.pca_settings(GROUPS)["group_colors"] == plumbing.group_colors(["A", "B"])


def test_zscores_center_each_row():
    scores = heatmap.zscores(np.log2(_wide().set_index("id")[SAMPLES]).dropna(), top=10)
    assert len(scores) == 10
    assert np.allclose(scores.mean(axis=1), 0)


def test_panels_build_their_components(tmp_path, monkeypatch):
    """Each panel builds an Insight component from the contract and calls it."""
    monkeypatch.setitem(sys.modules, "streamlit", MagicMock())
    calls = []

    def record(self, **kwargs):
        calls.append((type(self).__name__, kwargs))

    openms_insight = pytest.importorskip("openms_insight")
    from openms_insight.components import series_plot
    if "box" not in getattr(series_plot, "MODES", ()):
        pytest.skip("the installed openms-insight draws no box or bar series")
    for cls in (openms_insight.SeriesPlot, openms_insight.VolcanoPlot, openms_insight.ClusteredHeatmap):
        monkeypatch.setattr(cls, "__call__", record)
    wide = _wide()
    log = np.log2(wide[SAMPLES])
    comparison_steps.show_missing_values(wide, SAMPLES, cache_path=tmp_path, key="m")
    comparison_steps.show_imputed_values(wide, wide.fillna(1.0), SAMPLES, cache_path=tmp_path, key="i")
    comparison_steps.show_normalization(wide, log, SAMPLES, True, cache_path=tmp_path, key="n",
                                        labels={"a1": "first"})
    comparison_steps.show_pvalues(pd.DataFrame({"p-value": [0.1, 0.2]}), cache_path=tmp_path, key="p",
                                  noun="Proteins")
    stats = pd.DataFrame({"log2FC": [1.5, -2.0, 0.1], "p-value": [0.001, 0.01, 0.9], "label": ["x", "y", "z"]})
    volcano.show_volcano(stats, cache_path=tmp_path, key="v", fc_threshold=1, p_threshold=0.05,
                         reference="A", compared="B")
    scores = heatmap.zscores(np.log2(wide.set_index("id")[SAMPLES]).dropna(), top=10).reset_index()
    heatmap.show_clustered_heatmap(scores, GROUPS, "id", cache_path=tmp_path, key="h", title="Top")
    component = pca.pca_component(pca.most_variable(log.assign(id=wide["id"]).dropna(), SAMPLES, id_column="id"),
                                  GROUPS, cache_path=tmp_path)
    assert component.get_pc_columns()[0] == "PC1"
    assert [c[0] for c in calls] == ["SeriesPlot"] * 4 + ["VolcanoPlot", "ClusteredHeatmap"]
    assert [c[1]["key"] for c in calls] == ["m", "i", "n", "p", "v", "h"]
    # A rerun with the same table loads the cache rather than building again
    comparison_steps.show_pvalues(pd.DataFrame({"p-value": [0.1, 0.2]}), cache_path=tmp_path, key="p",
                                  noun="Proteins")
    assert len(list((tmp_path / "series").iterdir())) == 4


def test_fingerprint_follows_row_order():
    import polars as pl
    from src.viz.plumbing import fingerprint
    a = pl.DataFrame({"x": [0, 1, 2], "y": [0, 1, 0]})
    b = pl.DataFrame({"x": [0, 2, 1], "y": [0, 0, 1]})
    assert fingerprint(a) != fingerprint(b)
    assert fingerprint(a) == fingerprint(a.clone())


def _long():
    wide = _wide()
    long = wide.melt(id_vars="id", var_name="sample", value_name="value")
    long["group"] = long["sample"].map(GROUPS)
    return long


def test_profile_places_samples_by_group_with_mean_lines():
    from src.viz import profile
    long = _long()
    # Samples listed out of group order are still placed group by group
    table = profile.profile_table(long, "id", log2=True, samples=["b1", "a1", "b2", "a2"])
    p0 = table[table["id"] == "P0"]
    points = p0[~p0["series"].str.endswith(" mean")]
    # a2 of P0 is missing and left out
    assert dict(zip(points["sample"], points["x"])) == {"a1": 1.0, "b1": 3.0, "b2": 4.0}
    mean_b = p0[p0["series"] == "B mean"]
    assert list(mean_b["x"]) == [3.0, 4.0]
    assert np.allclose(mean_b["y"], points[points["series"] == "B"]["y"].mean())
    # P3's b1 is 0: left out on a log scale
    assert "b1" not in set(table[(table["id"] == "P3") & (table["series"] == "B")]["sample"])
    assert not profile.profile_table(long, "id", means=False)["series"].str.endswith(" mean").any()
    colors = profile.profile_colors(["B", "A"])
    assert colors["A"] == colors["A mean"] == plumbing.group_colors(["A", "B"])["A"]


def test_picked_set_needs_several_entries():
    from src.viz import profile
    state = MagicMock()
    state.get_selection.return_value = ["P1"]
    assert profile.picked_set(state, "set") == []
    state.get_selection.return_value = ["P1", None, "P2"]
    assert profile.picked_set(state, "set") == ["P1", "P2"]
    assert profile.picked_set(None, "set") == []


def test_comparison_table_calls_changes_and_sorts():
    from src.viz import comparison_table as ct
    stats = pd.DataFrame({"Protein": ["x", "y", "z", "w"], "log2FC": [1.5, -2.0, 0.1, 3.0],
                          "p-adj": [0.01, 0.001, 0.9, None], "p-value": [0.001, 0.0001, 0.5, None]})
    table = ct.comparison_table(stats, "B", 1.0, 0.05).to_pandas()
    assert list(table["Protein"]) == ["y", "x", "z", "w"]
    assert list(table["Change"]) == ["lower in B", "higher in B", "–", "–"]
    assert ct.comparison_table(pl.from_pandas(stats).lazy(), None, 1.0, 0.05).collect()["Change"].unique().to_list() == ["–"]
    columns = ct.comparison_columns("Proteoform", "Proteoform", after_entity=[{"field": "residues"}], p_value=False)
    assert [c["field"] for c in columns] == ["Proteoform", "residues", "Change", "log2FC", "p-adj"]
    assert ct.comparison_title("A", "B") == "B vs. A"


def test_zscore_long_and_heatmap_settings():
    matrix = np.log2(_wide().set_index("id")[SAMPLES]).dropna()
    long = heatmap.zscore_long(matrix, "Protein", top=5, groups=GROUPS)
    assert list(long.columns) == ["Protein", "Sample", "Z_score", "Group"]
    assert long["Protein"].nunique() == 5 and len(long) == 20
    settings = heatmap.heatmap_settings("Protein", toolbar_settings=[heatmap.top_setting()])
    assert settings["y_column"] == "Protein" and settings["toolbar_settings"][0]["default"] == 50


def test_new_panels_build_their_components(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", MagicMock())
    openms_insight = pytest.importorskip("openms_insight")
    from src.viz import comparison_table as ct, profile
    calls = []

    def record(self, **kwargs):
        calls.append((type(self).__name__, kwargs["key"]))

    for cls in (openms_insight.SeriesPlot, openms_insight.Table, openms_insight.Heatmap):
        monkeypatch.setattr(cls, "__call__", record)
    profile.show_profile(_long(), "id", "protein", cache_path=tmp_path, key="pr",
                         table_args={"log2": True}, y_label="log2 abundance")
    profile.show_profile(_long(), "id", "set", cache_path=tmp_path, key="prs", several=True)
    stats = pd.DataFrame({"Protein": ["x", "y"], "log2FC": [1.5, -2.0], "p-adj": [0.01, 0.2]})
    ct.show_comparison_table(stats, "Protein", "Protein", cache_path=tmp_path, key="t",
                             reference="A", compared="B", fc=1.0, padj=0.05,
                             interactivity={"protein": "Protein"})
    matrix = np.log2(_wide().set_index("id")[SAMPLES]).dropna()
    state = MagicMock()
    state.get_selection.return_value = None
    heatmap.show_zscore_heatmap(matrix, "id", cache_path=tmp_path, key="z", top=10, groups=GROUPS)
    assert calls == [("SeriesPlot", "pr"), ("SeriesPlot", "prs"), ("Table", "t"), ("Heatmap", "z")]


def test_profile_colours_keep_a_group_whose_values_are_all_missing():
    pytest.importorskip("openms_insight")
    from src.viz import plumbing, profile

    long = pd.DataFrame({"id": ["p"] * 4, "sample": ["a1", "a2", "b1", "b2"],
                         "group": ["A", "A", "B", "B"], "value": [None, None, 3.0, 4.0]})
    table = profile.profile_table(long, "id")
    assert "A" not in set(table["series"])
    colors = plumbing.group_colors(["A", "B"])
    settings = profile.profile_settings(table, "id", "protein", groups=["A", "B"])
    assert settings["series_colors"]["B"] == colors["B"]
    assert settings["series_colors"]["B mean"] == colors["B"]


def test_comparison_table_uses_renamed_columns():
    import polars as pl
    from src.viz.quantification.comparison_table import comparison_table
    data = pl.DataFrame({"Protein": ["a", "b"], "fc": [2.0, -0.1], "q": [0.001, 0.5]})
    frame = comparison_table(data, "drug", 1.0, 0.05, log2fc_column="fc", padj_column="q")
    assert frame["Change"].to_list() == ["higher in drug", "–"]


def test_show_comparison_table_forwards_renamed_columns(monkeypatch):
    import sys, types
    import polars as pl
    from src.viz.quantification import comparison_table as module
    seen = {}

    class Table:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def __call__(self, **kwargs):
            pass

    monkeypatch.setitem(sys.modules, "openms_insight", types.SimpleNamespace(Table=Table))
    data = pl.DataFrame({"Protein": ["a"], "fc": [2.0], "q": [0.001]})
    module.show_comparison_table(data, "Protein", "Protein", cache_path="/tmp", key="k",
                                 reference="ctrl", compared="drug", fc=1.0, padj=0.05,
                                 log2fc_column="fc", padj_column="q")
    frame = seen["data"].collect()
    assert frame["Change"].to_list() == ["higher in drug"]


def test_show_zscore_heatmap_forwards_column_names(monkeypatch):
    import sys, types
    import pandas as pd
    from src.viz.quantification import zscore_heatmap as module
    seen = {}

    class Heatmap:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def __call__(self, **kwargs):
            pass

    monkeypatch.setitem(sys.modules, "openms_insight", types.SimpleNamespace(Heatmap=Heatmap))
    matrix = pd.DataFrame({"s1": [1.0, 5.0], "s2": [3.0, 2.0]}, index=["p1", "p2"])
    module.show_zscore_heatmap(matrix, "Protein", cache_path="/tmp", key="k",
                               sample_column="Run", value_column="Z")
    columns = seen["data"].collect().columns
    assert {"Run", "Z"} <= set(columns)
    assert seen["x_column"] == "Run" and seen["intensity_column"] == "Z"


def test_show_series_takes_rows_as_dicts(monkeypatch, tmp_path):
    """filter_threshold.rows() returns a list of dicts; the filter step's plot draws it."""
    import sys, types
    from src.viz import series
    from src.viz.quantification import filter_threshold
    seen = {}

    class SeriesPlot:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def __call__(self, **kwargs):
            pass

    monkeypatch.setitem(sys.modules, "openms_insight", types.SimpleNamespace(SeriesPlot=SeriesPlot))
    rows = filter_threshold.rows([0.0, 50.0, 100.0], [10, 6, 0], 10, 50.0, 6)
    series.show_series(rows, "filter-threshold", cache_path=tmp_path, key="k",
                       **filter_threshold.settings("Threshold percentile (%)"))
    frame = seen["data"].collect()
    assert frame.height == 6 and set(frame["series"]) == {"Kept", "All", "Current"}


def test_scan_table_counts_peaks_of_a_run_not_deconvolved():
    from src.viz.ms_data import scan_table, spectrum

    fields = [c["field"] for c in scan_table.settings(peaks=True)["column_definitions"]]
    assert fields[-1] == "#Peaks" and "#Masses" not in fields
    assert scan_table.settings()["column_definitions"][-1]["field"] == "#Masses"
    # A spectrum without masses: the raw spectrum shows its peaks only
    raw = spectrum.settings("scan", signal_column=None)
    assert raw["filters"] == {"scan": "index"} and raw["signal_column"] is None
