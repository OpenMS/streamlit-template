import pyopenms as poms
import json
import shutil
import streamlit as st
from pathlib import Path

class ParameterManager:
    """
    Manages the parameters for a workflow, including saving parameters to a JSON file,
    loading parameters from the file, and resetting parameters to defaults. This class
    specifically handles parameters related to TOPP tools in a pyOpenMS context and
    general parameters stored in Streamlit's session state.

    Attributes:
        ini_dir (Path): Directory path where .ini files for TOPP tools are stored.
        params_file (Path): Path to the JSON file where parameters are saved.
        param_prefix (str): Prefix for general parameter keys in Streamlit's session state.
        topp_param_prefix (str): Prefix for TOPP tool parameter keys in Streamlit's session state.
    """
    # Methods related to parameter handling
    def __init__(self, workflow_dir: Path):
        self.ini_dir = Path(workflow_dir, "ini")
        self.ini_dir.mkdir(parents=True, exist_ok=True)
        self.params_file = Path(workflow_dir, "params.json")
        self.param_prefix = f"{workflow_dir.stem}-param-"
        self.topp_param_prefix = f"{workflow_dir.stem}-TOPP-"

    def save_parameters(self) -> None:
        """
        Saves the current parameters from Streamlit's session state to a JSON file.
        It handles both general parameters and parameters specific to TOPP tools,
        ensuring that only non-default values are stored.
        """
        # Everything in session state which begins with self.param_prefix is saved to a json file
        json_params = {
            k.replace(self.param_prefix, ""): v
            for k, v in st.session_state.items()
            if k.startswith(self.param_prefix)
        }
        # get a list of TOPP tools which are in session state
        current_topp_tools = list(
            set(
                [
                    k.replace(self.topp_param_prefix, "").split(":1:")[0]
                    for k in st.session_state.keys()
                    if k.startswith(f"{self.topp_param_prefix}")
                ]
            )
        )
        # for each TOPP tool, open the ini file
        for tool in current_topp_tools:
            json_params[tool] = {}
            # load the param object
            param = poms.Param()
            poms.ParamXMLFile().load(str(Path(self.ini_dir, f"{tool}.ini")), param)
            # get all session state param keys and values for this tool
            for key, value in st.session_state.items():
                if key.startswith(f"{self.topp_param_prefix}{tool}:1:"):
                    # get ini_key
                    ini_key = key.replace(self.topp_param_prefix, "").encode()
                    # get ini (default) value by ini_key
                    ini_value = param.getValue(ini_key)
                    # need to convert bool values to string values
                    if isinstance(value, bool):
                        value = "true" if value else "false"
                    # convert strings with newlines to list
                    if isinstance(value, str):
                        if "\n" in value:
                            value = [v.encode() for v in value.split("\n")]
                    # check if value is different from default
                    if ini_value != value:
                        # store non-default value
                        json_params[tool][key.split(":1:")[1]] = value
        # Save to json file
        with open(self.params_file, "w", encoding="utf-8") as f:
            json.dump(json_params, f, indent=4)

    def get_parameters_from_json(self) -> None:
        """
        Loads parameters from the JSON file if it exists and returns them as a dictionary.
        If the file does not exist, it returns an empty dictionary.

        Returns:
            dict: A dictionary containing the loaded parameters. Keys are parameter names,
                and values are parameter values.
        """
        # Check if parameter file exists
        if not Path(self.params_file).exists():
            return {}
        else:
            # Load parameters from json file
            with open(self.params_file, "r", encoding="utf-8") as f:
                return json.load(f)

    def reset_to_default_parameters(self) -> None:
        """
        Resets the parameters to their default values by deleting the custom parameters
        JSON file and the directory containing .ini files for TOPP tools. This method
        also triggers a Streamlit rerun to refresh the application state.
        """
        # Delete custom params json file
        self.params_file.unlink(missing_ok=True)
        shutil.rmtree(self.ini_dir)
        st.rerun()
