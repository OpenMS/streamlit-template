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
