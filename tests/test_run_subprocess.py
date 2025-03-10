import pytest
from streamlit.testing.v1 import AppTest

@pytest.fixture
def launch():
    """Launch the Run Subprocess Streamlit page for testing."""
    return AppTest.from_file("content/run_subprocess.py")

def test_file_selection(launch):
    """Ensure a file can be selected from the dropdown."""
    launch.run()

    assert len(launch.selectbox) > 0, "No file selection dropdown found!"

    # Select a file if available
    if len(launch.selectbox[0].options) > 0:
        launch.selectbox[0].select(launch.selectbox[0].options[0])
        launch.run()

def test_extract_ids_button(launch):
    """Ensure clicking 'Extract IDs' starts the process."""
    launch.run()

    # Ensure the file selection dropdown exists
    assert len(launch.selectbox) > 0, "File selection dropdown not found!"
    
    if len(launch.selectbox[0].options) > 0:
        launch.selectbox[0].select(launch.selectbox[0].options[0])
        launch.run()
    else:
        pytest.skip("No files available for selection.")

    assert len(launch.button) > 0, "Extract IDs button not found!"

    # Click the Extract IDs button
    launch.button[0].click()
    launch.run()

    assert "result_dict" in launch.session_state, f"Subprocess result_dict missing! Current session state: {launch.session_state}"
    assert launch.session_state["result_dict"]["success"], "Subprocess did not complete successfully!"
