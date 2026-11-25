"""Library: the PSM table over the PSMs of several files."""
from src.viz.identification import psm_table


def test_file_column_comes_first_and_numbers_are_rounded():
    columns = psm_table.all_files_columns(psm_table.columns())
    assert columns[0]["field"] == psm_table.FILE_FIELD
    mz = next(c for c in columns if c["field"] == "mz")
    assert mz["formatterParams"]["precision"] == 4


def test_settings_pick_the_merged_row_and_search_the_file():
    fields = ["psm_row", "file_name", "sequence", "protein_accession", "not_contaminant"]
    settings = psm_table.all_files_settings(psm_table.columns(), fields, page_size=50)
    assert settings["interactivity"] == {"psm_all": "psm_row"}
    assert settings["index_field"] == "psm_row"
    assert settings["search"] == ["file_name", "sequence", "protein_accession"]
    assert settings["page_size"] == 50
