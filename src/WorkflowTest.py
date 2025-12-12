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

        if not self.params.get("mzML-files"):
            st.error("No mzML files selected.")
            return

        if not self.params.get("fasta-file"):
            st.error("No FASTA file selected.")
            return

        in_mzML = self.file_manager.get_files(self.params["mzML-files"])
        fasta_file = self.file_manager.get_files([self.params["fasta-file"]])[0]

        comet_results = [
            str(Path(self.workflow_dir, "results", "comet_results", Path(f).stem + "_comet.idXML"))
            for f in in_mzML
        ]

        percolator_results = [
            str(Path(self.workflow_dir, "results", "percolator_results", Path(f).stem + "_per.idXML"))
            for f in in_mzML
        ]

        filter_results = [
            str(Path(self.workflow_dir, "results", "filter_results", Path(f).stem + "_filter.idXML"))
            for f in in_mzML
        ]

        quantified = [
            str(Path(self.workflow_dir, "results", "quant_results", Path(f).stem + "_openms.mzTab"))
            for f in in_mzML
        ]

        out_cxml_file = [
            str(Path(self.workflow_dir, "results", "quant_results", Path(f).stem + "_openms.consensusXML"))
            for f in in_mzML
        ]

        out_msstats = [
            str(Path(self.workflow_dir, "results", "quant_results", Path(f).stem + "_openms.csv"))
            for f in in_mzML
        ]

        # Create folders
        Path(self.workflow_dir, "results", "comet_results").mkdir(parents=True, exist_ok=True)
        Path(self.workflow_dir, "results", "percolator_results").mkdir(parents=True, exist_ok=True)
        Path(self.workflow_dir, "results", "filter_results").mkdir(parents=True, exist_ok=True)
        Path(self.workflow_dir, "results", "quant_results").mkdir(parents=True, exist_ok=True)

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
        
        st.info("📊 **Detailed file list overview:**")
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
        
        # Run CometAdapter
        self.executor.run_topp(
            "CometAdapter",
            {
                "in": in_mzML, 
                "out": comet_results, 
                "database": [fasta_file], 
                "missed_cleavages": ["2"],
                "min_peptide_length": ["6"],
                "max_peptide_length": ["40"],
                "num_hits": ["1"],
                "num_enzyme_termini": ["fully"],
                "enzyme": ["Trypsin"],
                "precursor_charge": ["2:4"],
                "max_variable_mods_in_peptide": ["3"],
                "minimum_peaks": ["10"],
                "PeptideIndexing:unmatched_action": ["warn"],
                # "force": [],
             }
        )

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

        # Run PercolatorAdapter
        self.executor.run_topp(
            "PercolatorAdapter", 
            {
                "in": comet_results, 
                "out": percolator_results,
                "subset_max_train": ["300000"],
                "decoy_pattern": ["DECOY_"],
                "score_type": ["pep"]
            }
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
        # 3️⃣ IDFilter
        # ----------------------------
        self.logger.log("Running IDFilter...")
        self.logger.log(f"IDFilter inputs:")
        self.logger.log(f"  - in: {percolator_results}")
        self.logger.log(f"  - in: {comet_results}")
        self.logger.log(f"  - out: {filter_results}")

        # Run IDFilter
        self.executor.run_topp(
            "IDFilter", 
            {
                "in": percolator_results, 
                "out": filter_results, 
            }
        )

        # 🔍 Check if IDFilter output exists
        if Path(filter_results[0]).exists():
            self.logger.log(f"✓ IDFilter output created: {filter_results[0]}")
            st.success("✓ IDFilter completed")
        else:
            self.logger.log(f"✗ IDFilter output NOT found: {filter_results[0]}")
            st.error("✗ IDFilter failed - output file not created.")
            st.info("💡 Check log for detailed error messages.")
            st.stop()        

        # ----------------------------
        # 4️⃣ ProteomicsLFQ
        # ----------------------------
        self.logger.log("Running ProteomicsLFQ...")
        self.logger.log(f"ProteomicsLFQ inputs:")
        self.logger.log(f"  - in: {in_mzML}")
        self.logger.log(f"  - ids: {filter_results}")
        self.logger.log(f"  - out: {quantified}")

        # Run ProteomicsLFQ
        self.executor.run_topp(
            "ProteomicsLFQ", 
            {
                "in": in_mzML, 
                "ids": filter_results, 
                "fasta": [fasta_file],
                "protein_inference": ["aggregation"],
                "quantification_method": ["feature_intensity"],
                "targeted_only": ["true"],
                "feature_with_id_min_score": ["0.10"],
                "feature_without_id_min_score": ["0.75"],
                "mass_recalibration": ["false"],
                "Seeding:intThreshold": ["1000"],
                "protein_quantification": ["unique_peptides"],
                "alignment_order": ["star"],
                "psmFDR": ["0.1"],
                "proteinFDR": ["0.1"],
                "picked_proteinFDR": ["true"],
                "out_msstats": out_msstats,
                "out_cxml": out_cxml_file,
                "out": quantified
            }
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