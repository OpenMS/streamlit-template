import pytest
from streamlit.testing.v1 import AppTest

@pytest.fixture
def launch():
    """Launch the Streamlit page for testing."""
    return AppTest.from_file("content/run_subprocess.py")

# def test_file_selection(launch):
#     """Ensure a file is selectable from the dropdown."""
    
#     # Debugging: Print available selectboxes
#     print("Available select boxes:", launch.selectbox)
    
#     assert len(launch.selectbox) > 0, "No select box found!"
    
#     # Select the first file from the dropdown (if available)
#     if len(launch.selectbox[0].options) > 0:
#         file_name = launch.selectbox[0].options[0]
#         launch.selectbox[0].set_value(file_name)

#         assert launch.selectbox[0].value == file_name, "File selection failed!"
#     else:
#         pytest.skip("No files available for selection.")

def test_file_selection(launch):
    """Ensure a file is selectable from the dropdown."""

    # Debugging: Print available widgets
    print("Available select boxes:", launch.selectbox)

    # Ensure select box is available
    assert len(launch.selectbox) > 0, "No select box found!"

    # Check if there are any files to select
    if launch.selectbox[0].options:
        file_name = launch.selectbox[0].options[0]
        launch.selectbox[0].set_value(file_name)
        assert launch.selectbox[0].value == file_name, "File selection failed!"
    else:
        pytest.skip("No files available for selection.")


def test_extract_ids_button(launch):
    """Ensure clicking 'Extract ids' starts the process."""
    
    # Ensure the button exists
    assert len(launch.button) > 0, "Extract IDs button not found!"
    
    # Click the "Extract ids" button
    launch.button[0].click()

    # Ensure that the status message appears
    assert len(launch.status) > 0, "Process status message missing!"

# def test_command_execution(launch):
#     """Ensure the correct subprocess command is generated and executed."""
    
#     # Select a file first
#     if len(launch.selectbox[0].options) > 0:
#         file_name = launch.selectbox[0].options[0]
#         launch.selectbox[0].set_value(file_name)

#         # Click the button to start extraction
#         launch.button[0].click()

#         # Check if the command is displayed
#         assert len(launch.code) > 0, "Command output missing!"
#         command_text = launch.code[0].value
#         assert "findstr" in command_text or "grep" in command_text, "Invalid command format!"
#     else:
#         pytest.skip("No files available for selection.")

def test_command_execution(launch):
    """Ensure the correct subprocess command is generated and executed."""
    
    # Ensure at least one file exists
    if len(launch.selectbox) > 0 and launch.selectbox[0].options:
        file_name = launch.selectbox[0].options[0]
        launch.selectbox[0].set_value(file_name)

        # Click the "Extract ids" button
        launch.button[0].click()

        # Check if the command is displayed
        assert len(launch.code) > 0, "Command output missing!"
        command_text = launch.code[0].value
        assert "findstr" in command_text or "grep" in command_text, "Invalid command format!"
    else:
        pytest.skip("No files available for selection.")
