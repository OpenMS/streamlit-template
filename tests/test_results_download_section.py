"""Tests for StreamlitUI.results_download_section (the workflow Download page)."""

import zipfile
from pathlib import Path

from streamlit.testing.v1 import AppTest


def _script(workflow_dir: str, exclude: list, location: str = "online"):
    from pathlib import Path

    import streamlit as st

    from src.workflow.StreamlitUI import StreamlitUI

    st.session_state.location = location
    st.session_state.settings = {"app-name": "TestApp"}

    ui = StreamlitUI.__new__(StreamlitUI)
    ui.workflow_dir = Path(workflow_dir)
    ui.results_download_section(exclude=exclude)


def _run(workflow_dir: Path, exclude=None, location="online") -> AppTest:
    at = AppTest.from_function(
        _script, args=(str(workflow_dir), exclude or [], location)
    )
    return at.run(timeout=30)


def _populate(workflow_dir: Path) -> None:
    for rel in [
        "quant/proteins.csv",
        "quant/nested/peptides.csv",
        "ids/run1.idXML",
        "insight_cache/table/data.parquet",
        "summary.txt",
    ]:
        path = Path(workflow_dir, "results", rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel)


def test_no_results_shows_info(tmp_path):
    at = _run(tmp_path)
    assert not at.exception
    assert "No results yet" in at.info[0].value


def test_lists_files_and_honours_exclude(tmp_path):
    _populate(tmp_path)
    at = _run(tmp_path, exclude=["insight_cache"])
    assert not at.exception

    listed = at.dataframe[0].value
    assert sorted(zip(listed["Folder"], listed["File"])) == [
        (".", "summary.txt"),
        ("ids", "run1.idXML"),
        ("quant", "nested/peptides.csv"),
        ("quant", "proteins.csv"),
    ]
    assert "insight_cache" not in set(listed["Folder"])
    assert sorted(at.multiselect[0].value) == [".", "ids", "quant"]


def test_zip_contains_chosen_folders(tmp_path):
    _populate(tmp_path)
    at = _run(tmp_path, exclude=["insight_cache"])
    at.multiselect[0].set_value(["quant"]).run()
    at.button[0].click().run()
    assert not at.exception

    with zipfile.ZipFile(tmp_path / "downloads" / "results.zip") as zf:
        assert sorted(zf.namelist()) == [
            "results/quant/nested/peptides.csv",
            "results/quant/proteins.csv",
        ]


def test_local_exports_every_listed_file_to_the_chosen_folder(tmp_path):
    workflow_dir = tmp_path / "my-workflow"
    _populate(workflow_dir)
    export_dir = tmp_path / "Documents" / "TestApp"
    at = _run(workflow_dir, exclude=["insight_cache"], location="local")
    assert not at.exception
    # One folder field and one Export button replace the download widgets.
    assert not at.multiselect and not at.selectbox
    at.text_input[0].set_value(str(export_dir)).run()
    next(b for b in at.button if "Export" in b.label).click().run()
    assert not at.exception

    exported = export_dir / "my-workflow-results"
    assert sorted(
        str(p.relative_to(exported)) for p in exported.rglob("*") if p.is_file()
    ) == ["ids/run1.idXML", "quant/nested/peptides.csv", "quant/proteins.csv", "summary.txt"]
    assert "Exported 4 files" in at.success[0].value


def test_local_export_folder_defaults_to_documents_app_name(tmp_path):
    _populate(tmp_path)
    at = _run(tmp_path, location="local")
    assert at.text_input[0].value == str(Path.home() / "Documents" / "TestApp")
