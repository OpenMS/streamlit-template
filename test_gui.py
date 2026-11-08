from streamlit.testing.v1 import AppTest
import pytest
from src import fileupload
import json
from pathlib import Path
import shutil


@pytest.fixture
def launch(request):
    test = AppTest.from_file(request.param)

    ## Initialize session state ##
    with open("settings.json", "r") as f:
        test.session_state.settings = json.load(f)
    test.session_state.settings["test"] = True
    test.secrets["workspace"] = "test"
    return test


# Test launching of all pages
@pytest.mark.parametrize(
    "launch",
    (
        # "content/quickstart.py", # NOTE: this page does not work due to streamlit.errors.StreamlitPageNotFoundError error
        "content/documentation.py",
        "content/topp_workflow_file_upload.py",
        "content/topp_workflow_parameter.py",
        "content/topp_workflow_execution.py",
        "content/topp_workflow_results.py",
        "content/topp_workflow_download.py",
        "content/workspace_sync.py",
        "content/file_upload.py",
        "content/raw_data_viewer.py",
        "content/run_example_workflow.py",
        "content/download_section.py",
        "content/simple_workflow.py",
        "content/run_subprocess.py",
    ),
    indirect=True,
)
def test_launch(launch):
    """Test if all pages can be launched without errors."""
    launch.run(timeout=30)  # Increased timeout from 10 to 30 seconds
    assert not launch.exception


########### PAGE SPECIFIC TESTS ############
@pytest.mark.parametrize(
    "launch,selection",
    [
        ("content/documentation.py", "User Guide"),
        ("content/documentation.py", "Installation"),
        (
            "content/documentation.py",
            "Developers Guide: How to build app based on this template",
        ),
        ("content/documentation.py", "Developers Guide: TOPP Workflow Framework"),
        ("content/documentation.py", "Developer Guide: Windows Executables"),
        ("content/documentation.py", "Developers Guide: From Notebook to Web App"),
        ("content/documentation.py", "Developers Guide: Deployment"),
        ("content/documentation.py", "Developers Guide: Kubernetes Deployment"),
    ],
    indirect=["launch"],
)
def test_documentation(launch, selection):
    launch.run()
    launch.selectbox[0].select(selection).run()
    assert not launch.exception


@pytest.mark.parametrize("launch", ["content/file_upload.py"], indirect=True)
def test_file_upload_load_example(launch):
    launch.run()
    for i in launch.tabs:
        if i.label == "Example Data":
            i.button[0].click().run()
            assert not launch.exception


# NOTE: All tabs are automatically checked
@pytest.mark.parametrize(
    "launch,example",
    [
        ("content/raw_data_viewer.py", "Blank.mzML"),
        ("content/raw_data_viewer.py", "Treatment.mzML"),
        ("content/raw_data_viewer.py", "Pool.mzML"),
        ("content/raw_data_viewer.py", "Control.mzML"),
    ],
    indirect=["launch"],
)
def test_view_raw_ms_data(launch, example):
    launch.run(timeout=30)  # Increased timeout from 10 to 30 seconds

    ## Load Example file, based on implementation of fileupload.load_example_mzML_files() ###
    mzML_dir = Path(launch.session_state.workspace, "mzML-files")

    # Copy files from example-data/mzML to workspace mzML directory, add to selected files
    for f in Path("example-data", "mzML").glob("*.mzML"):
        try:
            shutil.copy(f, mzML_dir)
        except shutil.SameFileError:
            pass  # File already exists as a symlink to the same source (on Linux)
    launch.run()

    ## TODO: Figure out a way to select a spectrum to be displayed
    launch.selectbox[0].select(example).run()
    assert not launch.exception


@pytest.mark.parametrize(
    "launch,example",
    [
        ("content/run_example_workflow.py", ["Blank"]),
        ("content/run_example_workflow.py", ["Treatment"]),
        ("content/run_example_workflow.py", ["Pool"]),
        ("content/run_example_workflow.py", ["Control"]),
        ("content/run_example_workflow.py", ["Control", "Blank"]),
    ],
    indirect=["launch"],
)
def test_run_workflow(launch, example):
    launch.run()
    ## Load Example file, based on implementation of fileupload.load_example_mzML_files() ###
    mzML_dir = Path(launch.session_state.workspace, "mzML-files")

    # Copy files from example-data/mzML to workspace mzML directory, add to selected files
    for f in Path("example-data", "mzML").glob("*.mzML"):
        try:
            shutil.copy(f, mzML_dir)
        except shutil.SameFileError:
            pass  # File already exists as a symlink to the same source (on Linux)
    launch.run()

    ## Select experiments to process
    for e in example:
        launch.multiselect[0].select(e)

    launch.run()
    assert not launch.exception

    # Press the "Run Workflow" button
    launch.button[1].click().run(timeout=60)
    assert not launch.exception


@pytest.mark.parametrize("launch", ["content/topp_workflow_parameter.py"], indirect=True)
def test_parameter_page_has_no_advanced_toggle(launch):
    """Advanced parameters are reached by search (TOPP) or an expander (python
    tools), not by a page-wide toggle."""
    launch.run(timeout=30)
    assert not launch.exception
    assert not [t for t in launch.toggle if t.label == "Show advanced parameters"]
    # src/python-tools/example.py has one advanced parameter
    # (an expander with an icon is listed as a status block by AppTest)
    blocks = list(launch.expander) + list(launch.status)
    assert [e for e in blocks if e.label == "1 advanced parameter"]


@pytest.mark.parametrize("launch", ["content/topp_workflow_parameter.py"], indirect=True)
def test_an_analysis_added_to_a_run_locks_its_files_and_kept_tools(launch):
    """Add the custom Python tool to a run: Configure shows the run's files
    locked and the feature steps as reused, in place of their settings."""
    launch.run(timeout=30)
    assert not launch.exception
    workflow_dir = Path(launch.session_state["workspace"], "topp-workflow")
    params_file = Path(workflow_dir, "params.json")
    params = json.loads(params_file.read_text()) if params_file.exists() else {}
    files = [str(f) for f in Path("example-data", "mzML").glob("*.mzML")][:1]
    params["_follow_up"] = {
        "run": "r1", "name": "Features", "note": "with the custom Python tool switched on",
        "same_files": "mzML-files", "files": files,
        "kept": ["FeatureFinderMetabo", "FeatureLinkerUnlabeledKD"], "reuses": ["r1"],
    }
    params["mzML-files"] = files
    params_file.write_text(json.dumps(params))
    try:
        launch.run(timeout=30)
        assert not launch.exception
        locked = [m for m in launch.multiselect if m.disabled and m.value == [Path(files[0]).name]]
        assert locked, [m.label for m in launch.multiselect]
        notes = " ".join(i.value for i in launch.info)
        assert "FeatureFinderMetabo** is not run again" in notes
        assert "FeatureLinkerUnlabeledKD** is not run again" in notes
        # The page's own run button starts it, saying what the start does,
        # and the note offers a new experiment instead
        assert any("Adds to Features" in c.value for c in launch.caption)
        assert [b for b in launch.button if b.label == "Start a new experiment instead"]
        assert not [b for b in launch.button if b.label == "Start analysis"]
    finally:
        params.pop("_follow_up", None)
        params_file.write_text(json.dumps(params))


@pytest.mark.parametrize("launch", ["content/topp_workflow_parameter.py"], indirect=True)
def test_a_new_experiment_instead_drops_the_earlier_run(launch):
    """Settings that add files to an experiment: the note's "Start a new
    experiment instead" keeps the settings and forgets the earlier run."""
    launch.run(timeout=30)
    assert not launch.exception
    workflow_dir = Path(launch.session_state["workspace"], "topp-workflow")
    params_file = Path(workflow_dir, "params.json")
    params = json.loads(params_file.read_text()) if params_file.exists() else {}
    files = [str(f) for f in Path("example-data", "mzML").glob("*.mzML")][:1]
    params["_follow_up"] = {"run": "r1", "name": "Features", "note": "to add more files",
                            "adds_to": "r1", "files_key": "mzML-files", "files": files}
    params["mzML-files"] = []
    params_file.write_text(json.dumps(params))
    try:
        launch.run(timeout=30)
        assert not launch.exception
        assert any("Adds the files picked above to Features" in c.value for c in launch.caption)
        [button] = [b for b in launch.button if b.label == "Start a new experiment instead"]
        button.click().run(timeout=30)
        assert not launch.exception
        assert "_follow_up" not in json.loads(params_file.read_text())
        launch.run(timeout=30)
        assert not [b for b in launch.button if b.label == "Start a new experiment instead"]
    finally:
        params = json.loads(params_file.read_text())
        params.pop("_follow_up", None)
        params_file.write_text(json.dumps(params))
