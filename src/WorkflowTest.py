import streamlit as st
from pathlib import Path
import pandas as pd
import plotly.express as px
from streamlit_plotly_events import plotly_events
from pyopenms import IdXMLFile

from src.workflow.WorkflowManager import WorkflowManager


class WorkflowTest(WorkflowManager):

    def __init__(self) -> None:
        super().__init__("TOPP Workflow", st.session_state["workspace"])

    def upload(self) -> None:
        t = st.tabs(["MS data (mzML)", "FASTA database"])

        with t[0]:
            self.ui.upload_widget(
                key="mzML-files",
                name="MS data",
                file_types="mzML",
                fallback=[str(f) for f in Path("example-data", "mzML").glob("*.mzML")],
            )

        with t[1]:
            self.ui.upload_widget(
                key="fasta-file",
                name="Protein FASTA database",
                file_types=("fasta", "fa"),
                fallback=[str(f) for f in Path("example-data", "db").glob("*.fasta")],
            )

    @st.fragment
    def configure(self) -> None:
        self.ui.select_input_file("mzML-files", multiple=True)
        self.ui.select_input_file("fasta-file", multiple=False)

        t = st.tabs(["**CometAdapter**", "**PercolatorAdapter**", "**IDFilter**", "**ProteomicsLFQ**"])

        with t[0]:
            self.ui.input_TOPP("CometAdapter")

        with t[1]:
            self.ui.input_TOPP("PercolatorAdapter")

        with t[2]:
            self.ui.input_TOPP("IDFilter")

        with t[3]:
            self.ui.input_TOPP("ProteomicsLFQ")

    def execution(self) -> None:
        """
        Refactored TOPP workflow execution:
        - Per-sample: CometAdapter -> PercolatorAdapter -> IDFilter
        - Cross-sample: ProteomicsLFQ (single combined output)
        """
        # ================================
        # 0️⃣ Input validation
        # ================================
        if not self.params.get("mzML-files"):
            st.error("No mzML files selected.")
            return

        if not self.params.get("fasta-file"):
            st.error("No FASTA file selected.")
            return

        in_mzML = self.file_manager.get_files(self.params["mzML-files"])
        fasta_file = self.file_manager.get_files([self.params["fasta-file"]])[0]

        if len(in_mzML) < 1:
            st.error("At least one mzML file is required.")
            return
        
        # ================================
        # 1️⃣ Directory setup
        # ================================
        results_dir = Path(self.workflow_dir, "results")
        comet_dir = results_dir / "comet_results"
        perc_dir = results_dir / "percolator_results"
        filter_dir = results_dir / "filter_results"
        quant_dir = results_dir / "quant_results"

        for d in [comet_dir, perc_dir, filter_dir, quant_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # ================================
        # 2️⃣ File path definitions (per sample)
        # ================================
        comet_results = []
        percolator_results = []
        filter_results = []

        for mz in in_mzML:
            stem = Path(mz).stem
            comet_results.append(str(comet_dir / f"{stem}_comet.idXML"))
            percolator_results.append(str(perc_dir / f"{stem}_per.idXML"))
            filter_results.append(str(filter_dir / f"{stem}_filter.idXML"))

        # ================================
        # 3️⃣ Per-file processing
        # ================================
        # for i, mz in enumerate(in_mzML):
        #     stem = Path(mz).stem
        #     st.info(f"Processing sample: {stem}")

            # --- CometAdapter ---
        with st.spinner(f"CometAdapter ({stem})"):
            self.executor.run_topp(
                "CometAdapter",
                {
                    "in": in_mzML,
                    "out": comet_results,
                },
                {"database": fasta_file},
            )

            # if not Path(comet_results[i]).exists():
            #     st.error(f"CometAdapter failed for {stem}")
            #     st.stop()

            # --- PercolatorAdapter ---
            with st.spinner(f"PercolatorAdapter ({stem})"):
                self.executor.run_topp(
                    "PercolatorAdapter",
                    {
                        "in": comet_results,
                        "out": percolator_results
                    }
                
                )
           
            # if not Path(percolator_results[i]).exists():
            #     st.error(f"PercolatorAdapter failed for {stem}")
            #     st.stop()

            # --- IDFilter ---
            with st.spinner(f"IDFilter ({stem})"):
                self.executor.run_topp(
                    "IDFilter",
                    {
                        "in": percolator_results,
                        "out": filter_results
                    },
                )

            # if not Path(filter_results[i]).exists():
            #     st.error(f"IDFilter failed for {stem}")
            #     st.stop()

            st.success(f"✓ {stem} identification completed")

        # # ================================
        # # 4️⃣ ProteomicsLFQ (cross-sample)
        # # ================================
        # st.info("Running ProteomicsLFQ (cross-sample quantification)")

        # quant_mztab = str(quant_dir / "openms_quant.mzTab")
        # quant_cxml = str(quant_dir / "openms.consensusXML")
        # quant_msstats = str(quant_dir / "openms_msstats.csv")

        # with st.spinner("ProteomicsLFQ"):
        #         combined_in = " ".join(in_mzML)
        #         combined_ids = " ".join(filter_results)
        #         self.logger.log(f"COMBINED_IN {combined_in}", 1)
        #         self.logger.log(f"COMBINED_IN_TYPE {type(combined_in).__name__}", 1)
        #         self.logger.log(f"FILTER_RESULTS = {filter_results}", 1)
        #         self.logger.log(f"FILTER_RESULTS_LEN = {len(filter_results)}", 1)

        #         self.executor.run_topp(
        #                 "ProteomicsLFQ",
        #                 {
        #                     "in": in_mzML,
        #                     "ids": filter_results,
        #                     "fasta": [fasta_file],
        #                     "out": [quant_mztab],
        #                     "out_cxml": [quant_cxml],
        #                     "out_msstats": [quant_msstats],
        #                     "psmFDR": 0.5,
        #                     "proteinFDR": 0.5,
        #                     "threads": 15,
        #                 },
        #             )

        # if not Path(quant_mztab).exists():
        #     st.error("ProteomicsLFQ failed: mzTab not created")
        #     st.stop()


        # ================================
        # 5️⃣ Final report
        # # ================================
        # st.success("🎉 TOPP workflow completed successfully")
        # st.write("📁 Results directory:")   
        # st.code(str(results_dir))


        # st.write("📄 Generated files:")
        # st.write(f"- mzTab: {quant_mztab}")
        # st.write(f"- consensusXML: {quant_cxml}")
        # st.write(f"- MSstats CSV: {quant_msstats}")

    @st.fragment
    def results(self) -> None:

        st.title("📊 Results")

        comet_tab, perc_tab, filter_tab, lfq_tab = st.tabs([
            "🔍 CometAdapter",
            "🔍 PercolatorAdapter",
            "🔍 IDFilter",
            "🔍 ProteomicsLFQ"
        ])

        # ================================
        # 🔍 CometAdapter
        # ================================
        with comet_tab:

            comet_dir = Path(self.workflow_dir, "results", "comet_results")
            comet_files = sorted(comet_dir.glob("*.idXML"))

            if not comet_files:
                st.warning("⚠ No CometAdapter output files found.")
                return

            selected_file = st.selectbox("📁 Select Comet result file", comet_files)

            def idxml_to_df(idxml_file):
                proteins, peptides = [], []
                IdXMLFile().load(str(idxml_file), proteins, peptides)

                records = []
                for pep in peptides:
                    rt = pep.getRT()
                    mz = pep.getMZ()
                    for h in pep.getHits():
                        protein_refs = [ev.getProteinAccession() for ev in h.getPeptideEvidences()]
                        records.append({
                            "RT": rt,
                            "m/z": mz,
                            "Sequence": h.getSequence().toString(),
                            "Charge": h.getCharge(),
                            "Score": h.getScore(),
                            "Proteins": ",".join(protein_refs) if protein_refs else None,
                        })

                df = pd.DataFrame(records)
                if not df.empty:
                    df["Charge"] = df["Charge"].astype(str)
                    df["Charge_num"] = df["Charge"].astype(int)
                return df

            df = idxml_to_df(selected_file)

            if df.empty:
                st.info("No peptide hits found.")
                return
                
            st.dataframe(df, use_container_width=True)

            df_plot = df.reset_index()

            fig = px.scatter(
                df_plot,
                x="RT",
                y="m/z",
                color="Score",
                custom_data=["index", "Sequence", "Proteins"],
                color_continuous_scale=["#a6cee3", "#1f78b4", "#08519c", "#08306b"],
            )
            fig.update_traces(
                marker=dict(size=6, opacity=0.8),
                hovertemplate='<b>Index: %{customdata[0]}</b><br>'
                            + 'RT: %{x:.2f}<br>'
                            + 'm/z: %{y:.4f}<br>'
                            + 'Score: %{marker.color:.3f}<br>'
                            + 'Sequence: %{customdata[1]}<br>'
                            + 'Proteins: %{customdata[2]}<br>'
                            + '<extra></extra>'
            )
            fig.update_layout(
                coloraxis_colorbar=dict(title="Score"),
                hovermode="closest"
            )

            clicked = plotly_events(fig, click_event=True, hover_event=False, override_height=550, key="comet_plot")

            if clicked:
                row_index = clicked[0]["pointNumber"]
                st.subheader("📌 Selected Peptide Match")
                st.dataframe(df.iloc[[row_index]], use_container_width=True)

        # ================================
        # 🔍 PercolatorAdapter RESULTS
        # ================================
        with perc_tab:

            perc_dir = Path(self.workflow_dir, "results", "percolator_results")
            perc_files = sorted(perc_dir.glob("*.idXML"))

            if not perc_files:
                st.warning("⚠ No PercolatorAdapter output files found.")
                return

            selected_perc = st.selectbox("📁 Select Percolator result file", perc_files)

            df_p = idxml_to_df(selected_perc)

            if df_p.empty:
                st.info("No peptide hits found in Percolator result.")
                return

            st.dataframe(df_p, use_container_width=True)

            df_plot_p = df_p.reset_index()

            fig2 = px.scatter(
                df_plot_p,
                x="RT",
                y="m/z",
                color="Score",
                custom_data=["index", "Sequence", "Proteins"],
                color_continuous_scale=["#a6cee3", "#1f78b4", "#08519c", "#08306b"],
            )
            fig2.update_traces(
                marker=dict(size=6, opacity=0.8),
                hovertemplate='<b>Index: %{customdata[0]}</b><br>'
                            + 'RT: %{x:.2f}<br>'
                            + 'm/z: %{y:.4f}<br>'
                            + 'Score: %{marker.color:.3f}<br>'
                            + 'Sequence: %{customdata[1]}<br>'
                            + 'Proteins: %{customdata[2]}<br>'
                            + '<extra></extra>'
            )
            fig2.update_layout(
                coloraxis_colorbar=dict(title="Score"),
                hovermode="closest"
            )

            clicked2 = plotly_events(fig2, click_event=True, hover_event=False, override_height=550, key="perc_plot")

            if clicked2:
                idx = clicked2[0]["pointNumber"]
                st.subheader("📌 Selected Percolator Peptide Match")
                st.dataframe(df_p.iloc[[idx]], use_container_width=True)

        # ================================
        # 🔍 IDFilter RESULTS
        # ================================
        with filter_tab:

            filter_dir = Path(self.workflow_dir, "results", "filter_results")
            filter_files = sorted(filter_dir.glob("*.idXML"))

            if not filter_files:
                st.warning("⚠ No IDFilter output files found.")
                return
            
            st.info("Here you can explore the PSM scatterplot along with the detailed PSM table.")

            selected_filter = st.selectbox("📁 Select IDFilter result file", filter_files)

            df_f = idxml_to_df(selected_filter)

            if df_f.empty:
                st.info("No peptide hits found in IDFilter result.")
                return

            st.dataframe(df_f, use_container_width=True)

            df_plot_f = df_f.reset_index()

            fig3 = px.scatter(
                df_plot_f,
                x="RT",
                y="m/z",
                color="Score",
                custom_data=["index", "Sequence", "Proteins"],
                color_continuous_scale=["#a6cee3", "#1f78b4", "#08519c", "#08306b"],
            )
            fig3.update_traces(
                marker=dict(size=6, opacity=0.8),
                hovertemplate='<b>Index: %{customdata[0]}</b><br>'
                            + 'RT: %{x:.2f}<br>'
                            + 'm/z: %{y:.4f}<br>'
                            + 'Score: %{marker.color:.3f}<br>'
                            + 'Sequence: %{customdata[1]}<br>'
                            + 'Proteins: %{customdata[2]}<br>'
                            + '<extra></extra>'
            )
            fig3.update_layout(
                coloraxis_colorbar=dict(title="Score"),
                hovermode="closest"
            )

            clicked3 = plotly_events(fig3, click_event=True, hover_event=False, override_height=550, key="filter_plot")

            if clicked3:
                idx3 = clicked3[0]["pointNumber"]
                st.subheader("📌 Selected IDFilter Peptide Match")
                st.dataframe(df_f.iloc[[idx3]], use_container_width=True)

        # ================================
        # 📊 ProteomicsLFQ RESULTS
        # ================================
        with lfq_tab:

            results_dir = Path(self.workflow_dir, "results")
            proteomicslfq_dir = results_dir / "quant_results"

            if not proteomicslfq_dir.exists():
                st.warning("❗ 'proteomicslfq' directory not found. Please run the analysis first.")
                return

            csv_files = sorted(proteomicslfq_dir.glob("*.csv"))

            if not csv_files:
                st.info("No CSV files found in the 'proteomicslfq' directory.")
                return

            csv_file = csv_files[0]

            # Protein / PSM table tab
            protein_tab, psm_tab = st.tabs(["🧬 Protein Table", "📄 PSM-level Quantification Table"])

            try:
                df = pd.read_csv(csv_file)

                if df.empty:
                    st.info("No data found in this file.")
                    return
                
                # PSM-level Table
                with psm_tab:
                    st.markdown(f"### 📄 PSM-level Quantification Table")
                    st.info("💡INFO \n\n This table shows the PSM-level quantification data, including protein IDs,peptide sequences, charge states, and intensities across samples.Each row represents one peptide-spectrum match detected from the MS/MS analysis.")
                    st.dataframe(df, use_container_width=True)

                # Protein-level Table
                with protein_tab:
                    st.markdown("### 🧬 Protein-Level Abundance Table")
                    st.info("💡INFO \n\n"
                        "This protein-level table is generated by grouping all PSMs that map to the "
                        "same protein and aggregating their intensities across samples.\n"
                        "It provides an overview of protein abundance rather than individual peptide measurements."
                    )

                    df['Sample'] = df['Reference'].str.replace('.mzML', '', regex=False)

                    all_samples = sorted(df['Sample'].unique())
                    pivot_list = []

                    for protein, group in df.groupby('ProteinName'):
                        peptides = ";".join(group['PeptideSequence'].unique())
                        intensity_dict = group.groupby('Sample')['Intensity'].sum().to_dict()

                        intensity_dict_complete = {
                            sample: intensity_dict.get(sample, 0)
                            for sample in all_samples
                        }

                        row = {
                            'ProteinName': protein,
                            **intensity_dict_complete,
                            'PeptideSequence': peptides
                        }
                        pivot_list.append(row)

                    pivot_df = pd.DataFrame(pivot_list)
                    pivot_df = pivot_df[['ProteinName'] + all_samples + ['PeptideSequence']]

                    st.dataframe(pivot_df, use_container_width=True)

            except Exception as e:
                st.error(f"Failed to load {csv_file.name}: {e}")