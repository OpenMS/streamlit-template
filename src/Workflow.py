import streamlit as st
from .workflow.WorkflowManager import WorkflowManager

# for result section:
from pathlib import Path
import pandas as pd
import plotly.express as px
from .common import show_fig


class Workflow(WorkflowManager):
    # Setup pages for upload, parameter, execution and results.
    # For layout use any streamlit components such as tabs (as shown in example), columns, or even expanders.
    def __init__(self) -> None:
        # Initialize the parent class with the workflow name.
        super().__init__("TOPP Workflow", st.session_state["workspace"])

    def upload(self) -> None:
        t = st.tabs(["MS data"])
        with t[0]:
            # Use the upload method from StreamlitUI to handle mzML file uploads.
            self.ui.upload_widget(
                key="mzML-files",
                name="MS data",
                file_type="mzML",
                fallback=[str(f) for f in Path("example-data", "mzML").glob("*.mzML")],
            )

    @st.fragment
    def configure(self) -> None:
        # Allow users to select mzML files for the analysis.
        self.ui.select_input_file("mzML-files", multiple=True)

        # Create tabs for different analysis steps.
        t = st.tabs(
            ["**Feature Detection**", "**Feature Linking**", "**Python Custom Tool**"]
        )
        with t[0]:
            # Parameters for FeatureFinderMetabo TOPP tool.
            self.ui.input_TOPP(
                "FeatureFinderMetabo",
                custom_defaults={"algorithm:common:noise_threshold_int": 1000.0},
            )
        with t[1]:
            # Paramters for MetaboliteAdductDecharger TOPP tool.
            self.ui.input_TOPP("FeatureLinkerUnlabeledKD")
        with t[2]:
            # A single checkbox widget for workflow logic.
            self.ui.input_widget("run-python-script", False, "Run custom Python script")
            # Generate input widgets for a custom Python tool, located at src/python-tools.
            # Parameters are specified within the file in the DEFAULTS dictionary.
            self.ui.input_python("example")

    def execution(self) -> None:
        # Any parameter checks, here simply checking if mzML files are selected
        if not self.params["mzML-files"]:
            self.logger.log("ERROR: No mzML files selected.")
            return

        # Get mzML files with FileManager
        in_mzML = self.file_manager.get_files(self.params["mzML-files"])

        # Log any messages.
        self.logger.log(f"Number of input mzML files: {len(in_mzML)}")

        # Prepare output files for feature detection.
        out_ffm = self.file_manager.get_files(
            in_mzML, "featureXML", "feature-detection"
        )

        # Run FeatureFinderMetabo tool with input and output files.
        self.logger.log("Detecting features...")
        self.executor.run_topp(
            "FeatureFinderMetabo", input_output={"in": in_mzML, "out": out_ffm}
        )

        # Prepare input and output files for feature linking
        in_fl = self.file_manager.get_files(out_ffm, collect=True)
        out_fl = self.file_manager.get_files(
            "feature_matrix.consensusXML", set_results_dir="feature-linking"
        )

        # Run FeatureLinkerUnlabaeledKD with all feature maps passed at once
        self.logger.log("Linking features...")
        self.executor.run_topp(
            "FeatureLinkerUnlabeledKD", input_output={"in": in_fl, "out": out_fl}
        )
        self.logger.log("Exporting consensus features to pandas DataFrame...")
        self.executor.run_python(
            "export_consensus_feature_df", input_output={"in": out_fl[0]}
        )
        # Check if adduct detection should be run.
        if self.params["run-python-script"]:
            # Example for a custom Python tool, which is located in src/python-tools.
            self.executor.run_python("example", {"in": in_mzML})

    @st.fragment
    def results(self) -> None:
        @st.fragment
        def show_consensus_features():
            df = pd.read_csv(file, sep="\t", index_col=0)
            st.metric("number of consensus features", df.shape[0])
            c1, c2 = st.columns(2)
            rows = c1.dataframe(df, selection_mode="multi-row", on_select="rerun")[
                "selection"
            ]["rows"]
            if rows:
                df = df.iloc[rows, 4:]
                fig = px.bar(df, barmode="group", labels={"value": "intensity"})
                with c2:
                    show_fig(fig, "consensus-feature-intensities")
            else:
                st.info(
                    "💡 Select one ore more rows in the table to show a barplot with intensities."
                )

        file = Path(
            self.workflow_dir, "results", "feature-linking", "feature_matrix.tsv"
        )
        if file.exists():
            show_consensus_features()
        else:
            st.warning("No consensus feature file found. Please run workflow first.")
