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

        # Merge with parameters from json
        # Advanced parameters are only in session state if the view is active
        json_params = self.get_parameters_from_json() | json_params

        # get a list of TOPP tool instances (or tools) which are in session state
        current_topp_instances = list(
            set(
                [
                    k.replace(self.topp_param_prefix, "").split(":1:")[0]
                    for k in st.session_state.keys()
                    if k.startswith(f"{self.topp_param_prefix}")
                ]
            )
        )
        # for each TOPP tool instance, open the ini file
        for instance in current_topp_instances:
            if instance not in json_params:
                json_params[instance] = {}
            # Extract actual tool name from instance name (instance might be the tool name itself)
            # We need to check which ini file exists to determine the actual tool name
            tool_name = self._get_tool_name_from_instance(instance)
            if not tool_name:
                continue
            # load the param object
            param = poms.Param()
            poms.ParamXMLFile().load(str(Path(self.ini_dir, f"{tool_name}.ini")), param)
            # get all session state param keys and values for this tool instance
            for key, value in st.session_state.items():
                if key.startswith(f"{self.topp_param_prefix}{instance}:1:"):
                    # get ini_key by replacing instance with actual tool name
                    ini_key_str = key.replace(self.topp_param_prefix, "").replace(f"{instance}:1:", f"{tool_name}:1:")
                    ini_key = ini_key_str.encode()
                    # get ini (default) value by ini_key
                    ini_value = param.getValue(ini_key)
                    # check if value is different from default
                    if (
                        (ini_value != value) 
                        or (key.split(":1:")[1] in json_params[instance])
                    ):
                        # store non-default value
                        json_params[instance][key.split(":1:")[1]] = value
        # Save to json file
        with open(self.params_file, "w", encoding="utf-8") as f:
            json.dump(json_params, f, indent=4)

    def _get_tool_name_from_instance(self, instance: str) -> str:
        """
        Get the actual TOPP tool name from an instance identifier.
        If the instance name corresponds to an existing ini file, it's the tool name itself.
        Otherwise, extract from stored metadata in params.
        
        Args:
            instance (str): The tool instance identifier (could be tool name or custom name)
            
        Returns:
            str: The actual tool name, or None if not found
        """
        # Check if instance name corresponds to an existing ini file
        if Path(self.ini_dir, f"{instance}.ini").exists():
            return instance
        
        # Check if we have metadata about this instance in the params
        params = self.get_parameters_from_json()
        if instance in params and isinstance(params[instance], dict):
            # Check if there's a special metadata key for tool name
            if "_tool_name" in params[instance]:
                return params[instance]["_tool_name"]
        
        # Otherwise, find which ini file was used for this instance by checking session state
        for ini_file in Path(self.ini_dir).glob("*.ini"):
            tool_name = ini_file.stem
            # Check if any session state key matches the pattern for this instance and tool
            for key in st.session_state.keys():
                if key.startswith(f"{self.topp_param_prefix}{instance}:1:"):
                    # Try to see if this parameter exists in this tool's ini file
                    try:
                        param = poms.Param()
                        poms.ParamXMLFile().load(str(ini_file), param)
                        param_name = key.split(":1:")[1]
                        # Check if this parameter exists in the tool
                        test_key = f"{tool_name}:1:{param_name}".encode()
                        if test_key in param.keys():
                            # Store this mapping for future use
                            if instance in params:
                                params[instance]["_tool_name"] = tool_name
                            else:
                                params[instance] = {"_tool_name": tool_name}
                            with open(self.params_file, "w", encoding="utf-8") as f:
                                json.dump(params, f, indent=4)
                            return tool_name
                    except:
                        continue
        return None

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

    def get_topp_parameters(self, tool_or_instance: str) -> dict:
        """
        Get all parameters for a TOPP tool or tool instance, merging defaults with user values.

        Args:
            tool_or_instance: Name of the TOPP tool (e.g., "CometAdapter") or tool instance name (e.g., "IDFilter-first")

        Returns:
            Dict with parameter names as keys (without tool prefix) and their values.
            Returns empty dict if ini file doesn't exist.
        """
        # Determine if this is an instance name or actual tool name
        tool_name = self._get_tool_name_from_instance(tool_or_instance)
        if not tool_name:
            return {}
            
        ini_path = Path(self.ini_dir, f"{tool_name}.ini")
        if not ini_path.exists():
            return {}

        # Load defaults from ini file
        param = poms.Param()
        poms.ParamXMLFile().load(str(ini_path), param)

        # Build dict from ini (extract short key names)
        prefix = f"{tool_name}:1:"
        full_params = {}
        for key in param.keys():
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            if prefix in key_str:
                short_key = key_str.split(prefix, 1)[1]
                full_params[short_key] = param.getValue(key)

        # Override with user-modified values from JSON
        # Use tool_or_instance as key since that's what's stored in params
        user_params = self.get_parameters_from_json().get(tool_or_instance, {})
        full_params.update(user_params)

        return full_params

    def reset_to_default_parameters(self) -> None:
        """
        Resets the parameters to their default values by deleting the custom parameters
        JSON file.
        """
        # Delete custom params json file
        self.params_file.unlink(missing_ok=True)