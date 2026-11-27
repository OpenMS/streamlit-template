"""Where the files of a folder picked in the browser go (InputFolders.place_folder_upload)."""
from src.workflow.InputFolders import UploadPlacement, place_folder_upload


def test_subfolder_becomes_input_folder():
    assert place_folder_upload("study/ctrl/a.mzML", ["mzML"]) == UploadPlacement("a.mzML", "a.mzML", "ctrl")


def test_nested_subfolders_join():
    assert place_folder_upload("study/ctrl/day1/a.mzML", ["mzML"]).folder == "ctrl/day1"


def test_file_in_picked_folder_takes_its_name():
    assert place_folder_upload("study/a.mzML", ["mzML"]).folder == "study"


def test_bare_name_has_no_folder():
    assert place_folder_upload("a.mzML", ["mzML"]).folder == ""


def test_other_types_and_climbing_paths_left_out():
    assert place_folder_upload("study/notes.txt", ["mzML"]) is None
    assert place_folder_upload("study/../a.mzML", ["mzML"]) is None
    assert place_folder_upload("", ["mzML"]) is None


def test_extension_case_ignored_and_backslashes_split():
    assert place_folder_upload("study\\drug\\B.MZML", ["mzML"]) == UploadPlacement("B.MZML", "B.MZML", "drug")


def test_bruker_folder_keeps_its_files_together():
    placed = place_folder_upload("study/drug/x.d/analysis.tdf", ["mzML", "d"])
    assert placed == UploadPlacement("x.d/analysis.tdf", "x.d", "drug")
    assert place_folder_upload("study/drug/x.d/sub/y.bin", ["d"]).path == "x.d/sub/y.bin"


def test_bruker_files_ignored_without_d_type():
    assert place_folder_upload("study/x.d/analysis.tdf", ["mzML"]) is None
