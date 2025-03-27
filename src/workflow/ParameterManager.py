import pyopenms as poms
import json
import shutil
import streamlit as st
from pathlib import Path
import xml.etree.ElementTree as ET

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

    def __init__(self, workflow_dir: Path):
        self.ini_dir = Path(workflow_dir, "ini")
        self.ini_dir.mkdir(parents=True, exist_ok=True)
        self.params_file = Path(workflow_dir, "params.json")
        self.param_prefix = f"{workflow_dir.stem}-param-"
        self.topp_param_prefix = f"{workflow_dir.stem}-TOPP-"

    def load_parameters_from_ini(self, ini_file):
        """Parse the .ini file and correctly handle boolean and string parameters."""
        ini_path = Path(ini_file)
        if not ini_path.exists():
            return {}  # Return empty dictionary if the file doesn't exist

        try:
            tree = ET.parse(ini_file)
            root = tree.getroot()
        except ET.ParseError:
            st.error(f"ERROR: Failed to parse {ini_file}. Invalid XML format.")
            return {}

        parameters = {}

        for item in root.findall(".//ITEM"):
            name = item.get("name")
            value = item.get("value")
            param_type = item.get("type")  # Get parameter type

            if param_type == "bool":
                parameters[name] = value.lower() == "true"  # Store as True/False
            elif param_type == "string":
                parameters[name] = value  # Store as a string
            else:
                parameters[name] = value  # Default case

        return parameters

    def save_parameters(self) -> None:
        """
        Saves the current parameters from Streamlit's session state to a JSON file.
        It handles both general parameters and parameters specific to TOPP tools,
        ensuring that only non-default values are stored.
        """
        json_params = {
            k.replace(self.param_prefix, ""): v if not isinstance(v, bool) else bool(v)
            for k, v in st.session_state.items()
            if k.startswith(self.param_prefix)
        }

        json_params = self.get_parameters_from_json() | json_params  # Merge with existing

        # Ensure TOPP tool boolean parameters are stored as actual booleans
        for tool, params in json_params.items():
            if isinstance(params, dict):  # Ensure we're dealing with a tool's parameters
                for key, value in params.items():
                    if isinstance(value, str) and value.lower() in ["true", "false"]:
                        json_params[tool][key] = value.lower() == "true"

        with open(self.params_file, "w", encoding="utf-8") as f:
            json.dump(json_params, f, indent=4)

    def get_parameters_from_json(self):
        """
        Loads parameters from the JSON file if it exists and returns them as a dictionary.
        If the file does not exist, it returns an empty dictionary.

        Returns:
            dict: A dictionary containing the loaded parameters. Keys are parameter names,
                and values are parameter values.
        """
        if not self.params_file.exists():
            return {}  
        try:
            with open(self.params_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            st.error("**ERROR**: Attempting to load an invalid JSON parameter file. Reset to defaults.")
            return {}

    def reset_to_default_parameters(self) -> None:
        """
         Resets the parameters to their default values by deleting the custom parameters
        JSON file.
        """
        if self.params_file.exists():  # Prevents errors if the file does not exist
            self.params_file.unlink()
    # def save_parameters_direct(self, params):#fucntion for testing purposes
    #   """
    #   Saves parameters directly to JSON without relying on Streamlit session state.
    #   """
    #   with open(self.params_file, "w", encoding="utf-8") as f:
    #      json.dump(params, f, indent=4)
