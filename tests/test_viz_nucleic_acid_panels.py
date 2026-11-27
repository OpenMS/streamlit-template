"""The library's coverage, fragment, XIC and condition-scatter panels: their
row helpers and the Insight components their settings build."""
import pytest

# polars and openms_insight come with the apps, not with the template
pl = pytest.importorskip("polars")
insight = pytest.importorskip("openms_insight")

from src.viz.identification import fragment_spectrum, fragment_table, sequence_coverage
from src.viz.quantification import condition_scatter, feature_xic


def _build(cls_name, data, settings, tmp_path, cache_id):
    cls = getattr(insight, cls_name, None)
    if cls is None:
        pytest.skip(f"this openms-insight has no {cls_name}")
    return cls(cache_id=cache_id, data=data.lazy(), cache_path=str(tmp_path), **settings)


def test_ion_series_and_colors():
    assert fragment_spectrum.ion_series("a3-B") == "a-B"
    assert fragment_spectrum.ion_series("w2^2-") == "w"
    assert fragment_spectrum.ion_series("y1") == "y"
    assert fragment_spectrum.ion_series("") is None
    assert fragment_spectrum.ion_color("c4") == fragment_spectrum.ION_COLORS["c"]
    assert fragment_spectrum.ion_color("M-H2O") == fragment_spectrum.UNKNOWN_ION_COLOR


def test_fragment_spectrum_rows_and_component(tmp_path):
    rows = fragment_spectrum.rows([(100.0, 50.0), (200.0, 200.0), (300.0, 20.0)], 7, {1: "w2"})
    assert rows["intensity"].to_list() == [25.0, 100.0, 10.0]
    assert rows["matched"].to_list() == [False, True, False]
    assert rows["color"].to_list() == [None, fragment_spectrum.ION_COLORS["w"], None]
    plot = _build("LinePlot", rows, fragment_spectrum.settings(), tmp_path, "frag")
    args = plot._get_component_args()
    if "colorColumn" not in args:
        pytest.skip("this openms-insight's LinePlot has no color_column")
    assert args["colorColumn"] == "color"


def test_fragment_table_component(tmp_path):
    rows = pl.DataFrame({"fragment": [0], "spectrum": [7], "peak": [1], "ion": ["w2"], "series": ["w"],
                         "mz": [200.0], "expected_mz": [200.001], "error_ppm": [-5.0], "intensity": [100.0]})
    table = _build("Table", rows, fragment_table.settings(), tmp_path, "fragtable")
    fields = [c["field"] for c in fragment_table.columns()]
    assert set(fields) <= set(rows.columns)
    assert table._get_component_args()["componentType"] == "TabulatorTable"


def test_sequence_coverage_rows_and_component(tmp_path):
    hits = [{"sequence": "AUG", "start": 1, "end": 3, "count": 2,
             "modifications": [{"position": 2, "token": "m1A"}]},
            {"sequence": "GCU", "start": 3, "end": 5},
            {"sequence": "UGG", "start": 2, "end": 4, "count": 0}]
    rows = sequence_coverage.rows(hits, reference="tRNA1", track="ctrl")
    # A missing count is one match; an explicit zero stays zero.
    assert rows["count"].to_list() == [2, 1, 0]
    assert rows["mod_labels"].to_list() == [["m1A"], [], []]
    coverage = _build("SequenceCoverage", rows,
                      sequence_coverage.settings("AUGGCUACGU", reference_name="tRNA1"), tmp_path, "cov")
    model = coverage.build_model({"reference": "tRNA1"})
    assert model["covered"] == 5
    assert model["tracks"][0]["hits"][0]["values"] == {"match": 0}


def test_feature_xic_rows_and_component(tmp_path):
    rows = feature_xic.rows(3, [1.0, 2.0, 3.0, 4.0], [5.0, 9.0, 7.0, 1.0], start=2.0, end=3.0)
    assert rows.filter(pl.col("series") == "Feature")["rt"].to_list() == [2.0, 3.0]
    assert feature_xic.rows(3, [1.0], [2.0])["series"].to_list() == ["XIC"]
    _build("SeriesPlot", rows, feature_xic.settings(), tmp_path, "xic")


def test_condition_scatter_rows_and_component(tmp_path):
    entries = [{"entry": 0, "x": 10.0, "y": 100.0, "modified": False, "label": "AUG"},
               {"entry": 1, "x": 1000.0, "y": 100.0, "modified": True},
               {"entry": 2, "x": 0.0, "y": 5.0}]
    rows = condition_scatter.rows(entries, "drug/ctrl")
    assert rows.filter(pl.col("series") != "Equal")["x"].to_list() == [1.0, 3.0]
    line = rows.filter(pl.col("series") == "Equal")
    assert line["x"].to_list() == [1.0, 3.0] and line["y"].to_list() == [1.0, 3.0]
    linear = condition_scatter.rows(entries, "drug/ctrl", log=False)
    assert linear.filter(pl.col("entry") == 2)["x"].to_list() == [0.0]
    assert condition_scatter.rows([], "c").is_empty()
    settings = condition_scatter.settings("drug", "ctrl")
    assert settings["x_label"] == "log10 mean ctrl"
    _build("SeriesPlot", rows, settings, tmp_path, "scatter")
