"""The GO panel's tables and charts, built from the contract frames (no Streamlit run)."""
import pandas as pd
import pytest

# polars comes with the apps (openms-insight), not with the template
pl = pytest.importorskip("polars")

from src.viz import go_panel


def _enriched():
    return {
        "BP": pd.DataFrame({
            "GO_Term": ["late", "early"], "p_adj": [0.04, 1e-5], "p_value": [0.01, 1e-6], "Count": [2, 5],
            "Background": [10, 12], "GeneRatio": ["2/10", "5/10"], "BgRatio": ["10/100", "12/100"],
            "FoldEnrichment": [1.5, 3.0], "Proteins": ["P1;P2", "P1;P3"],
        }),
        "MF": pd.DataFrame({
            "GO_Term": ["binding"], "p_adj": [0.01], "p_value": [0.005], "Count": [3], "Background": [9],
            "GeneRatio": ["3/10"], "BgRatio": ["9/100"], "FoldEnrichment": [2.0], "Proteins": ["P2"],
        }),
        "CC": None,
    }


def test_term_chart_puts_the_most_significant_term_first_per_category():
    data = go_panel.term_chart(_enriched())
    assert data.filter(pl.col("category") == "BP")["term"].to_list() == ["early", "late"]
    assert data.filter(pl.col("category") == "MF")["term"].to_list() == ["binding"]
    assert data["score"][0] == 5.0


def test_count_chart_reports_the_share_of_annotated_proteins():
    tables = {"CC": pl.DataFrame({"term": ["a", "b"], "count": [4, 1], "accessions": ["P1", "P2"]}), "BP": None}
    data = go_panel.count_chart(tables, 8)
    assert data["proteins"].to_list() == [4, 1]
    assert data["category"].to_list() == ["CC", "CC"]
    assert "50.0% of annotated" in data["hover"][0]


def test_term_frame_names_the_proteins_and_ranks_by_adjusted_p():
    frame = go_panel.term_frame(_enriched()["BP"], {"P1": "ALBU_HUMAN"})
    assert frame["term"].to_list() == ["early", "late"]
    assert frame["rank"].to_list() == [1, 2]
    assert frame["proteins"][0] == "ALBU_HUMAN, P3"
    assert go_panel.term_frame(None, {}).columns == list(go_panel._TERM_SCHEMA)


def test_count_frame_accepts_pandas_and_polars():
    table = pd.DataFrame({"term": ["a"], "count": [2], "accessions": ["P1;P2"]})
    frame = go_panel.count_frame(table, {}, 4)
    assert frame["share"].to_list() == [50.0]
    assert frame["proteins"].to_list() == ["P1, P2"]
    assert go_panel.count_frame(None, {}, 0).height == 0


def test_empty_charts_keep_their_columns():
    assert "category" in go_panel.term_chart({}).columns
    assert "category" in go_panel.count_chart({}, 0).columns


def test_info_text_joins_the_parts_that_are_set():
    assert go_panel.info_text("Picked: 3 proteins.", None, "Select proteins …") == "Picked: 3 proteins.\n\nSelect proteins …"
    assert go_panel.info_text(None, "") is None
    assert go_panel.info_text("**4 selected.**") == "4 selected."


def test_the_mode_switch_has_its_own_identifier():
    assert go_panel.mode_identifier("go") == "go_mode@go"
    assert set(go_panel.MODES) == {"selection", "all"}
