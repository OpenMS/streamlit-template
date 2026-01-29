import pyopenms as poms
import json
import shutil
import subprocess
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

    def create_ini(self, tool: str) -> bool:
        """
        Create an ini file for a TOPP tool if it doesn't exist.

        Args:
            tool: Name of the TOPP tool (e.g., "CometAdapter")

        Returns:
            True if ini file exists (created or already existed), False if creation failed
        """
        ini_path = Path(self.ini_dir, tool + ".ini")
        if ini_path.exists():
            return True
        try:
            subprocess.call([tool, "-write_ini", str(ini_path)])
        except FileNotFoundError:
            return False
        return ini_path.exists()

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

        # Merge with parameters from json
        # Advanced parameters are only in session state if the view is active
        json_params = self.get_parameters_from_json() | json_params

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
            if not self.create_ini(tool):
                # Could not create ini file - skip this tool
                continue
            ini_path = Path(self.ini_dir, f"{tool}.ini")
            if tool not in json_params:
                json_params[tool] = {}
            # load the param object
            param = poms.Param()
            poms.ParamXMLFile().load(str(ini_path), param)
            # get all session state param keys and values for this tool
            for key, value in st.session_state.items():
                if key.startswith(f"{self.topp_param_prefix}{tool}:1:"):
                    # Skip display keys used by multiselect widgets
                    if key.endswith("_display"):
                        continue
                    # get ini_key
                    ini_key = key.replace(self.topp_param_prefix, "").encode()
                    # get ini (default) value by ini_key
                    ini_value = param.getValue(ini_key)
                    is_list_param = isinstance(ini_value, list)
                    # check if value is different from default OR is an empty list parameter
                    if (
                        (ini_value != value)
                        or (key.split(":1:")[1] in json_params[tool])
                        or (is_list_param and not value)  # Always save empty list params
                    ):
                        # store non-default value
                        json_params[tool][key.split(":1:")[1]] = value
        # Save to json file
        with open(self.params_file, "w", encoding="utf-8") as f:
            json.dump(json_params, f, indent=4)

    def get_parameters_from_json(self) -> dict:
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
            try:
                with open(self.params_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                st.error("**ERROR**: Attempting to load an invalid JSON parameter file. Reset to defaults.")
                return {}

    def get_topp_parameters(self, tool: str) -> dict:
        """
        Get all parameters for a TOPP tool, merging defaults with user values.

        Args:
            tool: Name of the TOPP tool (e.g., "CometAdapter")

        Returns:
            Dict with parameter names as keys (without tool prefix) and their values.
            Returns empty dict if ini file doesn't exist.
        """
        ini_path = Path(self.ini_dir, f"{tool}.ini")
        if not ini_path.exists():
            return {}

        # Load defaults from ini file
        param = poms.Param()
        poms.ParamXMLFile().load(str(ini_path), param)

        # Build dict from ini (extract short key names)
        prefix = f"{tool}:1:"
        full_params = {}
        for key in param.keys():
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            if prefix in key_str:
                short_key = key_str.split(prefix, 1)[1]
                full_params[short_key] = param.getValue(key)

        # Override with user-modified values from JSON
        user_params = self.get_parameters_from_json().get(tool, {})
        full_params.update(user_params)

        return full_params

    def reset_to_default_parameters(self) -> None:
        """
        Resets the parameters to their default values by deleting the custom parameters
        JSON file.
        """
        # Delete custom params json file
        self.params_file.unlink(missing_ok=True)