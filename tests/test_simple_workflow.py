import pytest
from streamlit.testing.v1 import AppTest

@pytest.fixture
def launch():
    """Launch the Simple Workflow page for testing."""
    return AppTest.from_file("content/simple_workflow.py") 

def test_number_inputs(launch):
    """Ensure x and y dimension inputs exist and update correctly."""
    launch.run()  

    assert len(launch.number_input) >= 2, f"Expected at least 2 number inputs, found {len(launch.number_input)}"

    # Set x and y dimensions
    launch.number_input[0].set_value(5)  
    launch.number_input[1].set_value(4)  
    launch.run()

    assert launch.session_state["example-x-dimension"] == 5, "X-dimension not updated in session state!"
    assert launch.session_state["example-y-dimension"] == 4, "Y-dimension not updated in session state!"

    assert len(launch.dataframe) > 0, "Table not generated!"
    
    df = launch.dataframe[0].value
    assert df.shape == (5, 4), f"Expected table size (5,4) but got {df.shape}"


def test_download_button(launch):
    """Ensure the 'Download Table' button appears after table generation."""
    launch.run()  

    # Set x and y dimensions
    launch.number_input[0].set_value(3)  
    launch.number_input[1].set_value(2) 
    launch.run()

    # Ensure a table is generated
    assert len(launch.dataframe) > 0, "Table not generated!"
    
    df = launch.dataframe[0].value
    assert df.shape == (3, 2), f"Expected table size (3,2) but got {df.shape}"

    # Check for "Download Table" text in markdown
    assert any(btn.label == "Download Table" for btn in launch.button), "Download Table button is missing!"