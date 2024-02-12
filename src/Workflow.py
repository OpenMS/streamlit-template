import streamlit as st
from .workflow.WorkflowManager import WorkflowManager
from .workflow.Files import Files

class Workflow(WorkflowManager):
    # Setup pages for upload, parameter, execution and results.
    # For layout use any streamlit components such as tabs (as shown in example), columns, or even expanders.
    def __init__(self):
        # Initialize the parent class with the workflow name.
        super().__init__("TOPP Workflow")

    def upload(self):
        t = st.tabs(["MS data", "Example with fallback data"])
        with t[0]:
            # Use the upload method from StreamlitUI to handle mzML file uploads.
            self.ui.upload(key="mzML-files", name="MS data", file_type="mzML")
        with t[1]:
            # Example with fallback data (not used in workflow)
            self.ui.upload(key="image", file_type="png", fallback="assets/OpenMS.png")

    def parameter(self) -> None:
        # Allow users to select mzML files for the analysis.
        self.ui.select_input_file("mzML-files", multiple=True)

        # Create tabs for different analysis steps.
        t = st.tabs(
            ["**Feature Detection**", "**Adduct Detection**", "**SIRIUS Export**"]
        )
        with t[0]:
            self.ui.input_TOPP("FeatureFinderMetabo")
        with t[1]:
            self.ui.input("run-adduct-detection", False, "Adduct Detection")
            self.ui.input_TOPP("MetaboliteAdductDecharger")
        with t[2]:
            self.ui.input_TOPP("SiriusExport")

    def execution(self) -> None:
        # Wrap mzML files into a Files object for processing.
        in_mzML = Files(self.params["mzML-files"], "mzML")
        
        # Log any messages.
        self.logger.log(f"Number of input mzML files: {len(in_mzML)}")

        # Prepare output files for feature detection.
        out_ffm = Files(in_mzML, "featureXML", "feature-detection")

        # Run FeatureFinderMetabo tool with input and output files.
        self.executor.run_topp(
            "FeatureFinderMetabo", input_output={"in": in_mzML, "out": out_ffm}
        )

        # Check if adduct detection should be run.
        if self.params["run-adduct-detection"]:
        
            # Run MetaboliteAdductDecharger for adduct detection, with disabled logs.
            # Without a new Files object for output, the input files will be overwritten in this case.
            self.executor.run_topp(
                "MetaboliteAdductDecharger", {"in": out_ffm, "out_fm": out_ffm}, write_log=False
            )

        # Combine input files for SiriusExport (can process multiple files at once).
        in_mzML.combine()
        out_ffm.combine()

        # Prepare output file for SiriusExport.
        out_se = Files(["sirius-export.ms"], "ms", "sirius-export")

        # Run SiriusExport tool with the combined files.
        self.executor.run_topp("SiriusExport", {"in": in_mzML, "in_featureinfo": out_ffm, "out": out_se})

    def results(self) -> None:
        st.warning("Not implemented yet.")