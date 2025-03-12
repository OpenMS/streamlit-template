import pytest
import time
from streamlit.testing.v1 import AppTest

@pytest.fixture
def launch():
    """Launch the Run Subprocess Streamlit page for testing."""

    app = AppTest.from_file("content/run_subprocess.py")
    app.run(timeout=10)  
    return app

def test_file_selection(launch):
    """Ensure a file can be selected from the dropdown."""
    launch.run()

    assert len(launch.selectbox) > 0, "No file selection dropdown found!"

    if len(launch.selectbox[0].options) > 0:
        launch.selectbox[0].select(launch.selectbox[0].options[0])
        launch.run()


def test_extract_ids_button(launch):
    """Ensure clicking 'Extract IDs' triggers process and UI updates accordingly."""
    launch.run(timeout=10)
    time.sleep(3)

    # Ensure 'Extract ids' button exists
    extract_button = next((btn for btn in launch.button if "Extract ids" in btn.label), None)
    assert extract_button is not None, "Extract ids button not found!"

    # Click the 'Extract ids' button
    extract_button.click()
    launch.run(timeout=10)

    print("Extract ids button was clicked successfully!")