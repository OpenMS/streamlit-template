import time
import os
import shutil
import subprocess
import threading
from pathlib import Path
from .Logger import Logger
from .ParameterManager import ParameterManager
import sys
import importlib.util
import json

class CommandExecutor:
    """
    Manages the execution of external shell commands such as OpenMS TOPP tools within a Streamlit application.

    This class provides a structured approach to executing shell commands, capturing
    their output, and handling errors. It is designed to facilitate running both single
    commands and batches of commands in parallel, leveraging Python's subprocess module
    for execution.
    """
    # Methods for running commands and logging
    def __init__(self, workflow_dir: Path, logger: Logger, parameter_manager: ParameterManager):
        self.pid_dir = Path(workflow_dir, "pids")
        self.logger = logger
        self.parameter_manager = parameter_manager

    def run_multiple_commands(
        self, commands: list[str]
    ) -> None:
        """
        Executes multiple shell commands concurrently in separate threads.

        This method leverages threading to run each command in parallel, improving
        efficiency for batch command execution. Execution time and command results are
        logged if specified.

        Args:
            commands (list[str]): A list where each element is a list representing
                                        a command and its arguments.
        """
        # Log the start of command execution
        self.logger.log(f"Running {len(commands)} commands in parallel...", 1)
        start_time = time.time()

        # Initialize a list to keep track of threads
        threads = []

        # Start a new thread for each command
        for cmd in commands:
            thread = threading.Thread(target=self.run_command, args=(cmd,))
            thread.start()
            threads.append(thread)

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Calculate and log the total execution time
        end_time = time.time()
        self.logger.log(f"Total time to run {len(commands)} commands: {end_time - start_time:.2f} seconds", 1)

    def run_command(self, command: list[str]) -> None:
        """
        Executes a specified shell command and logs its execution details.

        Args:
            command (list[str]): The shell command to execute, provided as a list of strings.

        Raises:
            Exception: If the command execution results in any errors.
        """
        # Ensure all command parts are strings
        command = [str(c) for c in command]

        # Log the execution start
        self.logger.log(f"Running command:\n"+' '.join(command)+"\nWaiting for command to finish...", 1)   
        start_time = time.time()
        
        # Execute the command
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        child_pid = process.pid
        
        # Record the PID to keep track of running processes associated with this workspace/workflow
        # User can close the Streamlit app and return to a running workflow later
        pid_file_path = self.pid_dir / str(child_pid)
        pid_file_path.touch()
        
        # Wait for command completion and capture output
        stdout, stderr = process.communicate()
        
        # Cleanup PID file
        pid_file_path.unlink()

        end_time = time.time()
        execution_time = end_time - start_time
        # Format the logging prefix
        self.logger.log(f"Process finished:\n"+' '.join(command)+f"\nTotal time to run command: {execution_time:.2f} seconds", 1)
        
        # Log stdout if present
        if stdout:
            self.logger.log(stdout.decode(), 2)
        
        # Log stderr and raise an exception if errors occurred
        if stderr or process.returncode != 0:
            error_message = stderr.decode().strip()
            self.logger.log(f"ERRORS OCCURRED:\n{error_message}", 2)
      

    
    

def format_boolean_flag(name, value, tool_name):
    """
    Formats boolean parameters correctly based on tool expectations.
    
    Some tools expect implicit flags (-flag), while others expect explicit values (-flag true/false).
    """
    tools_with_implicit_flags = {"FeatureFinderMetabo", "FileInfo", "XTandemAdapter"}  # Add tools that need implicit flags

    if isinstance(value, bool):  # Detect boolean parameters
        if tool_name in tools_with_implicit_flags:
            return f"-{name}" if value else ""  # Implicit flag (only include if True)
        return f"-{name} {str(value).lower()}"  # Explicit flag (true/false as string)

    return f"-{name} {value}"  # Default case for non-boolean parameters


def run_topp(self, tool: str, input_output: dict, custom_params: dict = {}):
    """
    Constructs and executes commands for the specified tool OpenMS TOPP tool based on the given
        input and output configurations. Ensures that all input/output file lists
        are of the same length, or single strings, to maintain consistency in command
        execution.
        In many tools, a single input file is processed to produce a single output file.
        When dealing with lists of input or output files, the convention is that
        files are paired based on their order. For instance, the n-th input file is
        assumed to correspond to the n-th output file, maintaining a structured
        relationship between input and output data.
        Supports executing commands either as single or multiple processes
        based on the input size.
    
    Args:
        tool (str): Name of the TOPP tool to execute.
        input_output (dict): Dictionary specifying input/output file paths.
        custom_params (dict): Dictionary of additional parameters.
    """
    # Validate input/output file list lengths
    io_lengths = [len(v) for v in input_output.values() if isinstance(v, list) and len(v) > 1]
    
    if len(set(io_lengths)) > 1:
        raise ValueError(f"ERROR in {tool} input/output. File list lengths must be 1 and/or the same. Found: {io_lengths}")

    n_processes = max(io_lengths) if io_lengths else 1  # Determine the number of parallel processes
    commands = []

    # Load non-default parameters from JSON
    params = self.parameter_manager.get_parameters_from_json()

    # Construct command(s)
    for i in range(n_processes):
        command = [tool]  # Start with tool name
        
        # Add input/output file parameters
        for param_name, param_value in input_output.items():
            command.append(f"-{param_name}")  # Always add parameter name
            
            if isinstance(param_value, list):  # Multi-file inputs
                command.append(param_value[min(i, len(param_value) - 1)])  # Handle single-file case
            else:
                command.append(param_value)  # Single file input

        # Add non-default parameters
        if tool in params:
            for param_name, param_value in params[tool].items():
                formatted_param = format_boolean_flag(param_name, param_value, tool)
                if formatted_param:  # Avoid empty flags
                    command.append(formatted_param)

        # Add custom parameters
        for param_name, param_value in custom_params.items():
            formatted_param = format_boolean_flag(param_name, param_value, tool)
            if formatted_param:
                command.append(formatted_param)

        # Include INI file if available
        ini_path = Path(self.parameter_manager.ini_dir, f"{tool}.ini")
        if ini_path.exists():
            command += ["-ini", str(ini_path)]

        commands.append(command)

    # Execute commands
    if len(commands) == 1:
        self.run_command(commands[0])
    elif len(commands) > 1:
        self.run_multiple_commands(commands)
    else:
        raise Exception("No commands to execute.")
def stop(self) -> None:
        """
        Terminates all processes initiated by this executor by killing them based on stored PIDs.
        """
        self.logger.log("Stopping all running processes...")
        pids = [Path(f).stem for f in self.pid_dir.iterdir()]
        
        for pid in pids:
            try:
                os.kill(int(pid), 9)
            except OSError as e:
                self.logger.log(f"Failed to kill process {pid}: {e}")
        
        shutil.rmtree(self.pid_dir, ignore_errors=True)
        self.logger.log("Workflow stopped.")

def run_python(self, script_file: str, input_output: dict = {}) -> None:
        """
        Executes a specified Python script with dynamic input and output parameters,
        optionally logging the execution process. The method identifies and loads
        parameter defaults from the script, updates them with any user-specified
        parameters and file paths, and then executes the script via a subprocess
        call.

        This method facilitates the integration of standalone Python scripts into
        a larger application or workflow, allowing for the execution of these scripts
        with varying inputs and outputs without modifying the scripts themselves.

        Args:
            script_file (str):  The name or path of the Python script to be executed.
                                If the path is omitted, the method looks for the script in 'src/python-tools/'.
                                The '.py' extension is appended if not present.
            input_output (dict, optional): A dictionary specifying the input/output parameter names (as key) and their corresponding file paths (as value). Defaults to {}.
        """
        # Check if script file exists (can be specified without path and extension)
        # default location: src/python-tools/script_file
        if not script_file.endswith(".py"):
            script_file += ".py"
        path = Path(script_file)
        if not path.exists():
            path = Path("src", "python-tools", script_file)
            if not path.exists():
                self.logger.log(f"Script file not found: {script_file}")
                
        # load DEFAULTS
        if path.parent not in sys.path:
            sys.path.append(str(path.parent))
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        defaults = getattr(module, "DEFAULTS", None)
        if defaults is None:
            self.logger.log(f"WARNING: No DEFAULTS found in {path.name}")
            # run command without params
            self.run_command(["python", str(path)])
        elif isinstance(defaults, list):
            defaults = {entry["key"]: entry["value"] for entry in defaults}
            # load paramters from JSON file
            params = {k: v for k, v in self.parameter_manager.get_parameters_from_json().items() if path.name in k}
            # update defaults
            for k, v in params.items():
                defaults[k.replace(f"{path.name}:", "")] = v
            for k, v in input_output.items():
                defaults[k] = v
            # save parameters to temporary JSON file
            tmp_params_file = Path(self.pid_dir.parent, f"{path.stem}.json")
            with open(tmp_params_file, "w", encoding="utf-8") as f:
                json.dump(defaults, f, indent=4)
            # run command
            self.run_command(["python", str(path), str(tmp_params_file)])
            # remove tmp params file
            tmp_params_file.unlink()
