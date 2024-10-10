from pathlib import Path
from .Logger import Logger
from .ParameterManager import ParameterManager
from .CommandExecutor import CommandExecutor
from .StreamlitUI import StreamlitUI
from .FileManager import FileManager
import multiprocessing
import streamlit as st
import shutil
import time

class WorkflowManager:
    # Core workflow logic using the above classes
    def __init__(self, name: str, workspace: str):
        self.name = name
        self.workflow_dir = Path(workspace, name.replace(" ", "-").lower())
        self.file_manager = FileManager(self.workflow_dir)
        self.logger = Logger(self.workflow_dir)
        self.parameter_manager = ParameterManager(self.workflow_dir)
        self.executor = CommandExecutor(self.workflow_dir, self.logger, self.parameter_manager)
        self.params = self.parameter_manager.get_parameters_from_json()
        self.ui = StreamlitUI(self.workflow_dir, self.logger, self.executor, self.parameter_manager)

    def start_workflow(self) -> None:
        """
        Starts the workflow process and adds its process id to the pid directory.
        The workflow itself needs to be a process, otherwise streamlit will wait for everything to finish before updating the UI again.
        """
        # Delete the log file if it already exists
        shutil.rmtree(Path(self.workflow_dir, "logs"), ignore_errors=True)
        # Start workflow process
        workflow_process = multiprocessing.Process(target=self.workflow_process)
        workflow_process.start()
        # Add workflow process id to pid dir
        self.executor.pid_dir.mkdir()
        Path(self.executor.pid_dir, str(workflow_process.pid)).touch()
        time.sleep(3)
        st.rerun()

    def workflow_process(self) -> None:
        """
        Workflow process. Logs start and end of the workflow and calls the execution method where all steps are defined.
        """
        try:
            self.logger.log("STARTING WORKFLOW")
            results_dir = Path(self.workflow_dir, "results")
            if results_dir.exists():
                shutil.rmtree(results_dir)
            results_dir.mkdir(parents=True)
            self.execution()
            self.logger.log("WORKFLOW FINISHED")
        except Exception as e:
            self.logger.log(f"ERROR: {e}")
        # Delete pid dir path to indicate workflow is done
        shutil.rmtree(self.executor.pid_dir, ignore_errors=True)

    def show_file_upload_section(self) -> None:
        """
        Shows the file upload section of the UI with content defined in self.upload().
        """
        self.ui.file_upload_section(self.upload)
        
    def show_parameter_section(self) -> None:
        """
        Shows the parameter section of the UI with content defined in self.configure().
        """
        self.ui.parameter_section(self.configure)

    def show_execution_section(self) -> None:
        """
        Shows the execution section of the UI with content defined in self.execution().
        """
        self.ui.execution_section(self.start_workflow)
        
    def show_results_section(self) -> None:
        """
        Shows the results section of the UI with content defined in self.results().
        """
        self.ui.results_section(self.results)

    def upload(self) -> None:
        """
        Add your file upload widgets here
        """
        ###################################
        # Add your file upload widgets here
        ###################################
        pass

    def configure(self) -> None:
        """
        Add your input widgets here
        """
        ###################################
        # Add your input widgets here
        ###################################
        pass

    def execution(self) -> None:
        """
        Add your workflow steps here
        """
        ###################################
        # Add your workflow steps here
        ###################################
        pass

    def results(self) -> None:
        """
        Display results here
        """
        ###################################
        # Display results here
        ###################################
        pass