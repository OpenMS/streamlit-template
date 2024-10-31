import streamlit as st
import json
import shutil
from .workflow.WorkflowManager import WorkflowManager
from src import view
from src import fileupload
from src.common.common import show_table
from pathlib import Path
from os.path import getsize

class Workflow(WorkflowManager):
    # Setup pages for upload, parameter, execution and results.
    # For layout use any streamlit components such as tabs (as shown in example), columns, or even expanders.
    def __init__(self) -> None:
        # Initialize the parent class with the workflow name.
        super().__init__("NASEWEIS", st.session_state["workspace"])

    def upload(self)-> None:
        t = st.tabs(["MS data", "Nucleotide sequences"])
        with t[0]:
            # Use the upload method from StreamlitUI to handle mzML file uploads.
            self.ui.upload_widget(key="mzML-files", name="MS data", file_type="mzML")
            if st.button("Load Example Data", type="primary", help="Import the example mzML files", key="example_mzml"):
                fileupload.load_example_files("mzML",Path(self.workflow_dir,"input-files"))
        with t[1]:
            # Example with fallback data (not used in workflow)
            self.ui.upload_widget(key="fasta-files", name="nucleotide sequence file", file_type="fasta")
            if st.button("Load Example Data", type="primary", help="Import the example mzML files", key="example_fasta" ):
                fileupload.load_example_files("fasta",Path(self.workflow_dir,"input-files"))

    def configure(self) -> None:
        # Allow users to select mzML files for the analysis.
        self.ui.select_input_file("mzML-files", multiple=False)
        self.ui.select_input_file("fasta-files", multiple=False)

        # Create tabs for different analysis steps.
        t = st.tabs(
            ["**Decoy generation**", "**Nucleic acid search engine**"]
        )
        with t[0]:
            # Parameters for DecoyDatabase TOPP tool.
            self.ui.input_widget("add-decoys", True, "Do FDR?", "Add decoys (required to calculate false discovery rate)")
            self.ui.input_widget("FDR_cutoff", 0.05, "FDR cutoff?", "What FDR cutoff should we use?", "number", min_value=0.0, max_value=1.0)
            self.ui.input_TOPP("DecoyDatabase", custom_defaults={"type" : "RNA", "method" : "shuffle" }, exclude_parameters=["decoy_string", "decoy_string_position", "enzyme", "only_decoy", "type", "non_shuffle_pattern", "method"])

        with t[1]:
            self.ui.input_widget("ms1_resolution", 60000.0, "MS1 approximate resolution?", "The approximate resolution at which MS1 scans were acquired", "number", min_value=1, max_value=10000000)
            self.ui.input_widget("ms2_resolution", 60000.0, "MS2 approximate resolution?", "The approximate resolution at which MS2 scans were acquired", "number", min_value=1, max_value=10000000)
            self.ui.input_TOPP("NucleicAcidSearchEngine", custom_defaults={"oligo:enzyme" : "RNase_T1"}, exclude_parameters=["variable", "precursor:mass_tolerance", "precursor:mass_tolerance_unit", "decharge_ms2", "include_unknown_charge" , "precursor:use_avg_mass", "precursor:isotopes", "precursor:min_charge", "precursor:max_charge", "precursor:use_adducts", "precursor:potential_adducts", "fragment:mass_tolerance", "fragment:mass_tolerance_unit", "fragment:ions", "resolve_ambiguities", "decoy_pattern", "max_size", "cutoff", "remove_decoys", "min_size"])


    def execution(self) -> None:
        # Any parameter checks, here simply checking if mzML files are selected
        if not self.params["mzML-files"]:
            self.logger.log("ERROR: No mzML files selected.")
            return
        # Any parameter checks, here simply checking if mzML files are selected
        if not self.params["fasta-files"]:
            self.logger.log("ERROR: No fasta file selected.")
            return
        
        # Get mzML files with FileManager
        in_mzML = self.file_manager.get_files(self.params["mzML-files"])

        # Get FASTA files with FileManager
        in_fasta = self.file_manager.get_files(self.params["fasta-files"])
        
        # Log any messages.
        self.logger.log(f"Number of input mzML files: {len(in_mzML)}")

        if self.params["add-decoys"]:
            # Prepare output files for feature detection.
            out_fasta = self.file_manager.get_files(in_mzML, "fasta", "with-decoys")

            # Run FeatureFinderMetabo tool with input and output files.
            self.executor.run_topp(
            "DecoyDatabase", input_output={"in": in_fasta, "out": out_fasta}
            )
            self.params["NucleicAcidSearchEngine"]["fdr:cutoff"] = self.params["FDR_cutoff"]
            self.params["NucleicAcidSearchEngine"]["fdr:decoy_pattern"] = "DECOY_"
        else:
            out_fasta = in_fasta # Use the un-decoyed fasta if we don't want decoys

        # Magic UX improving logic
        self.params["NucleicAcidSearchEngine"]["precursor:mass_tolerance"] = float(self.params["ms1_resolution"]) / 1000000

        if self.params["ms1_resolution"] <= 1500:
            #MS1 low-res
            self.params["NucleicAcidSearchEngine"]["precursor:mass_tolerance"] = 1500
            self.params["NucleicAcidSearchEngine"]["precursor:use_avg_mass"] = True
            self.params["NucleicAcidSearchEngine"]["precursor:include_unknown_charge"] = True
        elif self.params["ms1_resolution"] <= 30000:
            #MS1 medium-res
            self.params["NucleicAcidSearchEngine"]["precursor:mass_tolerance"] = 100
            self.params["NucleicAcidSearchEngine"]["precursor:use_avg_mass"] = False
            self.params["NucleicAcidSearchEngine"]["precursor:include_unknown_charge"] = True
        elif self.params["ms1_resolution"] <= 1000000:
            #MS1 high-res
            self.params["NucleicAcidSearchEngine"]["precursor:mass_tolerance"] = 10


        else:
            #I'm jealous
            self.params["NucleicAcidSearchEngine"]["precursor:mass_tolerance"] = 3
        
        if self.params["ms2_resolution"] <= 1500:
            #MS1 low-res
            self.params["NucleicAcidSearchEngine"]["fragment:mass_tolerance"] = 1500
        elif self.params["ms2_resolution"] <= 30000:
            #MS1 medium-res
            self.params["NucleicAcidSearchEngine"]["fragment:mass_tolerance"] = 100
        elif self.params["ms2_resolution"] <= 1000000:
            #MS1 high-res
            self.params["NucleicAcidSearchEngine"]["fragment:mass_tolerance"] = 10
        else:
            #I'm jealous
            self.params["NucleicAcidSearchEngine"]["fragment:mass_tolerance"] = 3

        # Store all of these carefully curated parameters
        self.parameter_manager.save_parameters()
        with open(self.parameter_manager.params_file, "w", encoding="utf-8") as f:
            json.dump(self.params, f, indent=4)      

        tab_out = self.file_manager.get_files("tab_out", set_results_dir="mztab_results")
        id_out = self.file_manager.get_files("id_out", set_results_dir="idxml_results")
        self.executor.run_topp("NucleicAcidSearchEngine", {"in": self.file_manager.get_files(in_mzML, collect=True),
                                                "database": self.file_manager.get_files(out_fasta, collect=True),
                                                "out": tab_out, "id_out": id_out})

    def results(self) -> None:
        # Check that results exists at all, that we have output id_xml and that mzML-files is set
        if Path(self.workflow_dir, "results" ).is_dir() and Path(self.file_manager.get_files("id_out", set_results_dir="idxml_results")[0]).is_file()  and  "mzML-files" in self.params:
            # Load the hits from the idXML file

            df_file = self.file_manager.get_files("id_out", set_results_dir="idxml_results")[0]
            # File_size is not a guarantee of no changes, but it's very unlikely that we see a collision.
            file_size = getsize(df_file)
            # Only do the actual loading from file if the file size has changed
            if "df_last_size" not in st.session_state or file_size != st.session_state['df_last_size']:
                st.session_state['df_last_size'] = file_size
                df = view.get_id_df( self.file_manager.get_files("id_out", set_results_dir="idxml_results")[0])
                if not df.empty:
                    # select a subset of the columns to display
                    formatted_df = df[['protein_accession','label','RT','mz','charge','hyperscore']]
                    # update column names
                    formatted_df = formatted_df.rename(columns={"protein_accession": "Accession", "label":"Sequence", "RT": "Retention Time (s)", "mz": "M/Z", "hyperscore": "Hyperscore"})
                    # if we have FDR data, add that
                    if self.params["add-decoys"]:
                      formatted_df['q-value %'] = df.loc[:,('PSM-level q-value')] * 100
                    # store the df to our session state
                    st.session_state['df'] = formatted_df
                else:
                    # Make sure that we store the empty df otherwise
                    st.session_state['df'] = None

            # We are using the cached DF. Just do the display
            if not st.session_state['df'].empty:
                # Tabley goodness
                show_table(st.session_state['df'], download_name="results")

                with open (self.file_manager.get_files("id_out", set_results_dir="idxml_results")[0]) as file:
                  st.download_button(
                    label = "Download idXML",
                    data = file,
                    file_name = Path(self.params["mzML-files"]).stem + '.idXML',
                    mime = "idXML"
                )
                  
                with open (self.file_manager.get_files("tab_out", set_results_dir="mztab_results")[0]) as file:
                  st.download_button(
                    label = "Download mztab",
                    data = file,
                    file_name = Path(self.params["mzML-files"]).stem + '.mztab',
                    mime = "mztab"
                )
            #It is possible that we cached an empty df if there were no results from the search
            else:
                st.warning("Search returned no results")