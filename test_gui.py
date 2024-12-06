from streamlit.testing.v1 import AppTest
import pytest


@pytest.fixture
def launch(request):
    test = AppTest.from_file(request.param)
    # disable online mode for testing
    test.session_state['settings'] = {'online_deployment':False, 'google_analytics':{'enabled':False}}
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


@pytest.mark.parametrize('launch,tab', [("content/file_upload.py", "File Upload"), 
                                        ("content/file_upload.py", "Example Data"), 
                                        ("content/file_upload.py", "Files from local folder")], indirect=['launch'])
def test_file_upload(launch, tab):
    launch.run()
    print(launch.tabs)
    for i in launch.tabs:
        print(i.label)
        if i.label == tab:
            if i.label == "Files from local folder":
                pass # This is a tkinter button so pass
            else:
                i.button[0].click().run()
                assert not launch.exception


##### IN PROGRESS
@pytest.mark.parametrize('launch,tab', [("content/raw_data_viewer.py", "Peak map (MS1)"), 
                                         ("content/raw_data_viewer.py", "Spectra (MS1 + MS2)"), 
                                         ("content/raw_data_viewer.py", "Chromatograms (MS1)")], indirect=['launch'])
def view_raw_ms_data(launch, tab):
    launch.run()
    for i in launch.tabs:
        if i.label == tab:
            i.button[0].click().run()
            assert not launch.exception

