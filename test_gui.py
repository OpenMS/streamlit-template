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
    test.session_state.settings['test'] = True 
    test.secrets['workspace'] = 'test'
    return test



# Test launching of all pages
@pytest.mark.parametrize('launch', (
                       #"content/quickstart.py", # NOTE: this page does not work due to streamlit.errors.StreamlitPageNotFoundError error
                       "content/documentation.py",
                       "content/topp_workflow_file_upload.py",
                       "content/topp_workflow_parameter.py",
                       "content/topp_workflow_execution.py",
                       "content/topp_workflow_results.py",
                       "content/file_upload.py",
                       "content/raw_data_viewer.py",
                       "content/run_example_workflow.py",
                       "content/download_section.py",
                       "content/simple_workflow.py",
                       "content/run_subprocess.py"), indirect=True)
def test_launch(launch):
    launch.run()
    assert not launch.exception



########### PAGE SPECIFIC TESTS ############
@pytest.mark.parametrize('launch,selection', [("content/documentation.py", 'User Guide'),
                                              ("content/documentation.py", 'Installation'),
                                              ("content/documentation.py", 'Developers Guide: How to build app based on this template'),
                                              ("content/documentation.py", 'Developers Guide: TOPP Workflow Framework'),
                                              ("content/documentation.py", 'Developer Guide: Windows Executables'),
                                              ("content/documentation.py", 'Developers Guide: Deployment')], indirect=['launch'])
def test_documentation(launch, selection):
    launch.run()
    launch.selectbox[0].select(selection).run()
    assert not launch.exception


@pytest.mark.parametrize('launch', ["content/file_upload.py"], indirect=True)
def test_file_upload_load_example(launch):
    launch.run()
    for i in launch.tabs:
        if i.label == "Example Data":
            i.button[0].click().run()
            assert not launch.exception


# NOTE: All tabs are automatically checked
@pytest.mark.parametrize('launch,example', [("content/raw_data_viewer.py", 'Blank.mzML'),
                                            ("content/raw_data_viewer.py", 'Treatment.mzML'),
                                            ("content/raw_data_viewer.py", 'Pool.mzML'),
                                            ("content/raw_data_viewer.py", 'Control.mzML')], indirect=['launch'])
def test_view_raw_ms_data(launch, example):
    launch.run(timeout=10)

    ## Load Example file, based on implementation of fileupload.load_example_mzML_files() ###
    mzML_dir = Path(launch.session_state.workspace, "mzML-files")

    # Copy files from example-data/mzML to workspace mzML directory, add to selected files
    for f in Path("example-data", "mzML").glob("*.mzML"):
        shutil.copy(f, mzML_dir)
    launch.run()

    ## TODO: Figure out a way to select a spectrum to be displayed 
    launch.selectbox[0].select(example).run()
    assert not launch.exception


@pytest.mark.parametrize('launch,example', [("content/run_example_workflow.py", ['Blank']),
                                            ("content/run_example_workflow.py", ['Treatment']),
                                            ("content/run_example_workflow.py", ['Pool']),
                                            ("content/run_example_workflow.py", ['Control']),
                                            ("content/run_example_workflow.py", ['Control', 'Blank'])], indirect=['launch'])
def test_run_workflow(launch, example):
    launch.run()
    ## Load Example file, based on implementation of fileupload.load_example_mzML_files() ###
    mzML_dir = Path(launch.session_state.workspace, "mzML-files")

    # Copy files from example-data/mzML to workspace mzML directory, add to selected files
    for f in Path("example-data", "mzML").glob("*.mzML"):
        shutil.copy(f, mzML_dir)
    launch.run()

    ## Select experiments to process 
    for e in example:
        launch.multiselect[0].select(e)
    
    launch.run()
    assert not launch.exception
    
    # Press the "Run Workflow" button
    launch.button[1].click().run(timeout=60)
    assert not launch.exception