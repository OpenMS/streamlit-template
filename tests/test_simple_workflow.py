import pytest
import time
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
    app.run(timeout=15)  
    return app

def test_number_inputs(launch):
    """Ensure x and y dimension inputs exist and update correctly."""

    assert len(launch.number_input) >= 2, f"Expected at least 2 number inputs, found {len(launch.number_input)}"

    # Set x and y dimensions
    x_input = next((ni for ni in launch.number_input if ni.key == "example-x-dimension"), None)
    y_input = next((ni for ni in launch.number_input if ni.key == "example-y-dimension"), None)
    
    assert x_input is not None, "X-dimension input not found!"
    assert y_input is not None, "Y-dimension input not found!"
    
    x_input.set_value(5)
    y_input.set_value(4) 
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
    """Ensure 'Download Table' button appears after table generation."""

    # Locate number inputs by key
    x_input = next((ni for ni in launch.number_input if ni.key == "example-x-dimension"), None)
    y_input = next((ni for ni in launch.number_input if ni.key == "example-y-dimension"), None)

    assert x_input is not None, "X-dimension input not found!"
    assert y_input is not None, "Y-dimension input not found!"

    # Set values and trigger app update
    x_input.set_value(3)
    y_input.set_value(2)
    launch.run(timeout=15)  
    time.sleep(5)  

    assert len(launch.dataframe) > 0, "Table not generated!"

    # Find the "Download Table" button correctly
    download_elements = [comp for comp in launch.main if hasattr(comp, "label") and "Download" in comp.label]    
    assert len(download_elements) > 0, "Download Table button is missing!"
