import streamlit as st
from .workflow.WorkflowManager import WorkflowManager

class Workflow(WorkflowManager):
    # Setup pages for upload, parameter, execution and results.
    # For layout use any streamlit components such as tabs (as shown in example), columns, or even expanders.
    def __init__(self) -> None:
        # Initialize the parent class with the workflow name.
        super().__init__("TOPP Workflow", st.session_state["workspace"])

    def upload(self)-> None:
        t = st.tabs(["MS data", "Example with fallback data"])
        with t[0]:
            # Use the upload method from StreamlitUI to handle mzML file uploads.
            self.ui.upload_widget(key="mzML-files", name="MS data", file_type="mzML")
        with t[1]:
            # Example with fallback data (not used in workflow)
            self.ui.upload_widget(key="image", file_type="png", fallback="assets/OpenMS.png")

    def configure(self) -> None:
        # Allow users to select mzML files for the analysis.
        self.ui.select_input_file("mzML-files", multiple=True)

        # Create tabs for different analysis steps.
        t = st.tabs(
            ["**Feature Detection**", "**Adduct Detection**", "**SIRIUS Export**", "**Python Custom Tool**"]
        )
        with t[0]:
            # Parameters for FeatureFinderMetabo TOPP tool.
            self.ui.input_TOPP("FeatureFinderMetabo")
        with t[1]:
            # A single checkbox widget for workflow logic.
            self.ui.input_widget("run-adduct-detection", False, "Adduct Detection")
            # Paramters for MetaboliteAdductDecharger TOPP tool.
            self.ui.input_TOPP("MetaboliteAdductDecharger")
        with t[2]:
            # Paramters for SiriusExport TOPP tool
            self.ui.input_TOPP("SiriusExport")
        with t[3]:
            # Generate input widgets for a custom Python tool, located at src/python-tools.
            # Parameters are specified within the file in the DEFAULTS dictionary.
            self.ui.input_python("example")

    def execution(self) -> None:
        # Get mzML input files from self.params.
        # Can be done without file manager, however, it ensures everything is correct.
        in_mzML = self.file_manager.get_files(self.params["mzML-files"])
        
        # Log any messages.
        self.logger.log(f"Number of input mzML files: {len(in_mzML)}")

        # Prepare output files for feature detection.
        out_ffm = self.file_manager.get_files(in_mzML, "featureXML", "feature-detection")

        # Run FeatureFinderMetabo tool with input and output files.
        self.executor.run_topp(
            "FeatureFinderMetabo", input_output={"in": in_mzML, "out": out_ffm}
        )

        # Check if adduct detection should be run.
        if self.params["run-adduct-detection"]:
        
            # Run MetaboliteAdductDecharger for adduct detection, with disabled logs.
            # Without a new file list for output, the input files will be overwritten in this case.
            self.executor.run_topp(
                "MetaboliteAdductDecharger", {"in": out_ffm, "out_fm": out_ffm}, write_log=False
            )

        # Example for a custom Python tool, which is located in src/python-tools.
        self.executor.run_python("example", {"in": in_mzML})

        # Prepare output file for SiriusExport.
        out_se = self.file_manager.get_files("sirius.ms", set_results_dir="sirius-export")
        self.executor.run_topp("SiriusExport", {"in": self.file_manager.get_files(in_mzML, collect=True),
                                                "in_featureinfo": self.file_manager.get_files(out_ffm, collect=True),
                                                "out": out_se})

    def results(self) -> None:
        st.warning("Not implemented yet.")