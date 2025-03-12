import streamlit as st
from pathlib import Path
from ParameterManager import ParameterManager

def test_parameter_manager():
    # Set up a test workflow directory
    workflow_dir = Path("test_workflow")
    workflow_dir.mkdir(exist_ok=True)

    # Create an instance of ParameterManager
    param_manager = ParameterManager(workflow_dir)

    # Test loading parameters from a sample .ini file
    ini_file = workflow_dir / "test.ini"
    with open(ini_file, "w") as f:
        f.write("""<ROOT>
            <ITEM name="param1" value="true" type="bool"/>
            <ITEM name="param2" value="sample_value" type="string"/>
        </ROOT>""")

    loaded_params = param_manager.load_parameters_from_ini(ini_file)
    st.write("Loaded Parameters:", loaded_params)

    # Test saving parameters
    st.session_state["test-param-param1"] = True
    st.session_state["test-param-param2"] = "test_value"
    param_manager.save_parameters()

    # Verify saved parameters
    saved_params = param_manager.get_parameters_from_json()
    st.write("Saved Parameters:", saved_params)

# Run the test
if __name__ == "__main__":
    test_parameter_manager()
