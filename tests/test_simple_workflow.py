import pytest
from streamlit.testing.v1 import AppTest

"""
Tests for the Simple Workflow page functionality.

These tests verify:
- Number input widgets function correctly
- Session state updates properly
- Table generation with correct dimensions
- Download button presence
"""

@pytest.fixture
def launch():
    """Launch the Simple Workflow page for testing."""
    app = AppTest.from_file("content/simple_workflow.py")
    app.run(timeout=10)  
    return app

def test_number_inputs(launch):
    """Ensure x and y dimension inputs exist and update correctly."""
    launch.run(timeout=10)  

    # Ensure at least 2 number input widgets exist
    assert len(launch.number_input) >= 2, f"Expected at least 2 number inputs, found {len(launch.number_input)}"

    # Set x and y dimensions
    launch.number_input[0].set_value(5)  
    launch.number_input[1].set_value(4)  
    launch.run(timeout=10)

    # Validate session state updates
    assert "example-x-dimension" in launch.session_state, "X-dimension key missing in session state!"
    assert "example-y-dimension" in launch.session_state, "Y-dimension key missing in session state!"
    assert launch.session_state["example-x-dimension"] == 5, "X-dimension not updated!"
    assert launch.session_state["example-y-dimension"] == 4, "Y-dimension not updated!"

    assert len(launch.dataframe) > 0, "Table not generated!"
    
    df = launch.dataframe[0].value
    assert df.shape == (5, 4), f"Expected table size (5,4) but got {df.shape}"

def test_download_button(launch):
    """Ensure the 'Download Table' button appears after table generation."""
    launch.run(timeout=10)

    # Set x and y dimensions
    launch.number_input[0].set_value(3)
    launch.number_input[1].set_value(2)
    launch.run(timeout=10)

    # Ensure table exists before checking download button
    assert len(launch.dataframe) > 0, "Table not generated!"

    df = launch.dataframe[0].value
    assert df.shape == (3, 2), f"Expected table size (3,2) but got {df.shape}"

    print("Available downloads:", [dl.label for dl in launch.download])

    # Check if "Download Table" is found inside `launch.download`
    download_button = next((dl for dl in launch.download if dl.label == "Download Table"), None)
    assert download_button, "Download Table button is missing!"