import streamlit as st
from src.workflow.WorkflowManager import WorkflowManager

# for result section:
from pathlib import Path
import pandas as pd
import plotly.express as px
from src.common.common import show_fig


class WorkflowTest(WorkflowManager):
    # Setup pages for upload, parameter, execution and results.
    # For layout use any streamlit components such as tabs (as shown in example), columns, or even expanders.
    def __init__(self) -> None:
        # Initialize the parent class with the workflow name.
        super().__init__("TOPP Workflow", st.session_state["workspace"])

    def upload(self) -> None:
        t = st.tabs(["MS data (mzML)", "FASTA database"])
        # mzML Upload
        with t[0]:
            self.ui.upload_widget(
                key="mzML-files",
                name="MS spectra files",
                file_types="mzML",
                fallback=[str(f) for f in Path("example-data", "mzML").glob("*.mzML")],
            )

        # FASTA Upload
        with t[1]:
            self.ui.upload_widget(
                key="fasta-file",
                name="Protein FASTA database",
                file_types=("fasta", "fa"),
                fallback=[str(f) for f in Path("example-data", "db").glob("*.fasta")],
            )

    @st.fragment
    def configure(self) -> None:
        # Allow users to select mzML files for the analysis.
        self.ui.select_input_file("mzML-files", multiple=True)
        self.ui.select_input_file("fasta-file", multiple=False)

        # Create tabs for different analysis steps.
        t = st.tabs(
            ["**CometAdapter**", "**PercolatorAdapter**", "**ProteomicsLFQ**"]
            )
        with t[0]:
            # Parameters for FeatureFinderMetabo TOPP tool.
            self.ui.input_TOPP(
                "CometAdapter"
            )
        with t[1]:
            # Parameters for MetaboliteAdductDecharger TOPP tool.
            self.ui.input_TOPP(
                "PercolatorAdapter"
            )
        with t[2]:
            self.ui.input_TOPP("ProteomicsLFQ")

    def execution(self) -> None:
        comet_exe = "C:/Users/admin/Desktop/comet_2021010/comet.2021010.win64"

        # Check input mzML
        if not self.params.get("mzML-files"):
            self.logger.log("ERROR: No mzML files selected.")
            st.error("No mzML files selected.")
            return

        # Check FASTA
        if not self.params.get("fasta-file"):
            self.logger.log("ERROR: No FASTA file selected.")
            st.error("No FASTA file selected.")
            return

        # Load input files
        in_mzML = self.file_manager.get_files(self.params["mzML-files"])
        fasta_file = self.file_manager.get_files([self.params["fasta-file"]])[0]

        self.logger.log(f"Input mzML files: {len(in_mzML)}")
        self.logger.log(f"FASTA: {fasta_file}")

        # Prepare output filenames
        comet_results = self.file_manager.get_files(in_mzML, set_file_type="idXML", set_results_dir="comet_results")
        percolator_results = self.file_manager.get_files(comet_results, set_file_type="idXML", set_results_dir="percolator_results")
        quantified = self.file_manager.get_files(percolator_results, set_file_type="tsv", set_results_dir="quant_results")

        # ----------------------------
        # 1️⃣ CometAdapter
        # ----------------------------
        self.logger.log("Running CometAdapter...")
        self.executor.run_topp(
            "CometAdapter",
            {"in": in_mzML, "database": fasta_file, "out": comet_results, "executable": comet_exe},
        )

        # ----------------------------
        # 2️⃣ PercolatorAdapter
        # ----------------------------
        self.logger.log("Running PercolatorAdapter...")
        self.executor.run_topp(
            "PercolatorAdapter",
            {"in": comet_results, "out": percolator_results}
        )

        # ----------------------------
        # 3️⃣ ProteomicsLFQ
        # ----------------------------
        self.logger.log("Running ProteomicsLFQ...")
        self.executor.run_topp(
            "ProteomicsLFQ",
            {"in": percolator_results, "out": quantified}
        )

        self.logger.log("Pipeline Completed Successfully.")
        st.success("🎉 Processing complete!")
        st.write(f"📁 Output files saved in: `{quantified}`")


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
