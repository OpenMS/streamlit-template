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
                name="MS data",
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
        with t[1]:
            self.ui.input_TOPP("ProteomicsLFQ")

    def execution(self) -> None:
        comet_exe = "C:/Users/admin/Desktop/comet_2021010/comet.2021010.win64.exe"

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

        # Prepare output filenames - 입력 파일 개수만큼만 생성
        comet_results = [
            str(Path(self.workflow_dir, "results", "comet_results", Path(f).stem + ".idXML"))
            for f in in_mzML
        ]
        percolator_results = [
            str(Path(self.workflow_dir, "results", "percolator_results", Path(f).stem + ".idXML"))
            for f in comet_results
        ]
        quantified = [
            str(Path(self.workflow_dir, "results", "quant_results", Path(f).stem + ".tsv"))
            for f in percolator_results
        ]

        # 출력 디렉토리 생성
        Path(self.workflow_dir, "results", "comet_results").mkdir(parents=True, exist_ok=True)
        Path(self.workflow_dir, "results", "percolator_results").mkdir(parents=True, exist_ok=True)
        Path(self.workflow_dir, "results", "quant_results").mkdir(parents=True, exist_ok=True)

        # 🔍 파일 리스트 길이 및 내용 확인
        self.logger.log("=" * 50)
        self.logger.log("FILE LIST LENGTH CHECK:")
        self.logger.log(f"in_mzML: {len(in_mzML)} files")
        self.logger.log(f"in_mzML type: {type(in_mzML)}")
        self.logger.log(f"in_mzML content: {in_mzML}")
        
        self.logger.log(f"fasta_file type: {type(fasta_file)}")
        self.logger.log(f"fasta_file content: {fasta_file}")
        
        self.logger.log(f"comet_results: {len(comet_results)} files")
        self.logger.log(f"comet_results type: {type(comet_results)}")
        self.logger.log(f"comet_results content: {comet_results}")
        
        self.logger.log(f"percolator_results: {len(percolator_results)} files")
        self.logger.log(f"quantified: {len(quantified)} files")
        self.logger.log("=" * 50)
        
        # Streamlit에도 표시
        st.info("📊 **파일 리스트 상세 확인:**")
        st.write(f"- in_mzML: **{len(in_mzML)}** files")
        st.code(f"Type: {type(in_mzML)}\nContent: {in_mzML}")
        
        st.write(f"- fasta_file: **1** file")
        st.code(f"Type: {type(fasta_file)}\nContent: {fasta_file}")
        
        st.write(f"- comet_results: **{len(comet_results)}** files")
        st.code(f"Type: {type(comet_results)}\nContent: {comet_results}")

        # ----------------------------
        # 1️⃣ CometAdapter
        # ----------------------------
        self.logger.log("Running CometAdapter...")
        self.logger.log(f"CometAdapter inputs:")
        self.logger.log(f"  - in: {in_mzML}")
        self.logger.log(f"  - database: {[fasta_file]}")
        self.logger.log(f"  - out: {comet_results}")
        self.logger.log(f"  - executable: {[comet_exe]}")
        
        # Check if executable exists
        if not Path(comet_exe).exists():
            error_msg = f"ERROR: Comet executable not found at: {comet_exe}"
            self.logger.log(error_msg)
            st.error(error_msg)
            st.stop()
        
        try:
            self.executor.run_topp(
                "CometAdapter",
                {"in": in_mzML, "database": [fasta_file], "out": comet_results, "comet_executable": [comet_exe]},
            )
        except Exception as e:
            self.logger.log(f"ERROR in CometAdapter: {str(e)}")
            st.error(f"CometAdapter failed: {str(e)}")
            st.stop()
        
        # Check if output was created
        if Path(comet_results[0]).exists():
            self.logger.log(f"✓ CometAdapter output created: {comet_results[0]}")
            st.success(f"✓ CometAdapter completed")
        else:
            self.logger.log(f"✗ CometAdapter output NOT found: {comet_results[0]}")
            st.error(f"✗ CometAdapter failed - output file not created. Check if CometAdapter ran successfully.")
            st.info("💡 Possible issues:\n- Comet executable path incorrect\n- Input mzML file format issue\n- FASTA database format issue\n- Check log files for detailed error messages")
            st.stop()

        # ----------------------------
        # 2️⃣ PercolatorAdapter
        # ----------------------------
        self.logger.log("Running PercolatorAdapter...")
        self.logger.log(f"PercolatorAdapter inputs:")
        self.logger.log(f"  - in: {comet_results}")
        self.logger.log(f"  - out: {percolator_results}")
        
        self.executor.run_topp(
            "PercolatorAdapter",
            {"in": comet_results, "out": percolator_results}
        )
        
        # Check if output was created
        if Path(percolator_results[0]).exists():
            self.logger.log(f"✓ PercolatorAdapter output created: {percolator_results[0]}")
            st.success(f"✓ PercolatorAdapter completed")
        else:
            self.logger.log(f"✗ PercolatorAdapter output NOT found: {percolator_results[0]}")
            st.error(f"✗ PercolatorAdapter failed - output file not created")
            st.stop()

        # ----------------------------
        # 3️⃣ ProteomicsLFQ
        # ----------------------------
        self.logger.log("Running ProteomicsLFQ...")
        self.logger.log(f"ProteomicsLFQ inputs:")
        self.logger.log(f"  - in: {percolator_results}")
        self.logger.log(f"  - in: {comet_results}")
        self.logger.log(f"  - out: {quantified}")
        
        self.executor.run_topp(
            "ProteomicsLFQ",
            {"in": percolator_results, "out": quantified}
        )
        
        # Check if output was created
        if Path(quantified[0]).exists():
            self.logger.log(f"✓ ProteomicsLFQ output created: {quantified[0]}")
            st.success(f"✓ ProteomicsLFQ completed")
        else:
            self.logger.log(f"✗ ProteomicsLFQ output NOT found: {quantified[0]}")
            st.error(f"✗ ProteomicsLFQ failed - output file not created")

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

        # Look for output in quant_results directory
        file = Path(
            self.workflow_dir, "results", "quant_results", "protein_abundances.tsv"
        )
        if not file.exists():
            # Try alternative output file
            result_dir = Path(self.workflow_dir, "results", "quant_results")
            if result_dir.exists():
                tsv_files = list(result_dir.glob("*.tsv"))
                if tsv_files:
                    file = tsv_files[0]
        
        if file.exists():
            show_consensus_features()
        else:
            st.warning("No quantification results found. Please run workflow first.")