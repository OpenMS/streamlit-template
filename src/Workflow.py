import streamlit as st
from .workflow.WorkflowManager import WorkflowManager
from pages.FileUpload import handleInputFiles
from pages.FileUpload import parseUploadedFiles
from pages.FileUpload import initializeWorkspace, showUploadedFilesTable

from os.path import join, splitext, basename, exists, dirname
from os import makedirs
from shutil import copyfile

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




class TagWorkflow(WorkflowManager):

    def __init__(self) -> None:
        # Initialize the parent class with the workflow name.
        super().__init__("Workflow", st.session_state["workspace"])


    def upload(self)-> None:
        t = st.tabs(["MS data", "Database"])
        with t[0]:
            # Use the upload method from StreamlitUI to handle mzML file uploads.
            self.ui.upload_widget(key="mzML-files", name="MS data", file_type="mzML")
        with t[1]:
            # Example with fallback data (not used in workflow)
            self.ui.upload_widget(key="fasta-file", name="Database", file_type="fasta", enable_directory=False, accept_multiple_files=False)


    def configure(self) -> None:
        # Allow users to select mzML files for the analysis.
        self.ui.select_input_file("mzML-files", multiple=True)
        self.ui.select_input_file("fasta-file", multiple=False)

        # Create tabs for different analysis steps.
        t = st.tabs(
            ["**FLASHDeconv**", "**FLASHTagger**"]
        )
        with t[0]:
            # Parameters for FeatureFinderMetabo TOPP tool.
            self.ui.input_TOPP(
                'FLASHDeconv',
                exclude_parameters = [
                    'max_tag_count', 'min_length', 'max_length', 
                    'flanking_mass_tol', 'max_iso_error_count', 
                    'min_matched_aa', 'fdr', 'keep_decoy', 'ida_log',
                    'write_detail', 'report_FDR', 'quant_method'
                ]
            )
        with t[1]:
            # Parameters for FeatureFinderMetabo TOPP tool.
            self.ui.input_TOPP(
                'FLASHTagger', 
                exclude_parameters = [
                    'min_mz', 'max_mz', 'min_rt', 'max_rt', 'max_ms_level',
                    'use_RNA_averagine', 'tol', 'min_mass', 'max_mass',
                    'min_charge', 'max_charge', 'precursor_charge',
                    'precursor_mz', 'min_cos', 'min_snr'
                ]
            )

    def pp(self) -> None:
        st.session_state['progress_bar_space'] = st.container()

        in_mzMLs = self.file_manager.get_files(self.params["mzML-files"])

        base_path = join('..', 'workspaces-streamlit-template', 'default')

        uploaded_files = []
        for in_mzML in in_mzMLs:
            current_base = splitext(basename(in_mzML))[0]

            #out_db = join(base_path, 'db-fasta', f'{current_base}_db.fasta')
            out_anno = join(base_path, 'anno-mzMLs', f'{current_base}_annotated.mzML')
            out_deconv = join(base_path, 'deconv-mzMLs', f'{current_base}_deconv.mzML')
            out_tag = join(base_path, 'tags-tsv', f'{current_base}_tagged.tsv')
            out_protein = join(base_path, 'proteins-tsv', f'{current_base}_protein.tsv')

            if not exists(out_tag):
                continue

            #uploaded_files.append(out_db)
            uploaded_files.append(out_anno)
            uploaded_files.append(out_deconv)
            uploaded_files.append(out_tag)
            uploaded_files.append(out_protein)


        # make directory to store deconv and anno mzML files & initialize data storage
        input_types = ["deconv-mzMLs", "anno-mzMLs", "tags-tsv", "proteins-tsv"]
        parsed_df_types = ["deconv_dfs", "anno_dfs", "tag_dfs", "protein_dfs"]
        initializeWorkspace(input_types, parsed_df_types)
        handleInputFiles(uploaded_files)
        parseUploadedFiles(reparse=True)
        showUploadedFilesTable()



    
    def execution(self) -> None:
        # Get mzML input files from self.params.
        # Can be done without file manager, however, it ensures everything is correct.
        in_mzMLs = self.file_manager.get_files(self.params["mzML-files"])
        database = self.file_manager.get_files(self.params["fasta-file"])
        temp_path = self.file_manager._create_results_sub_dir()
        
        # TODO: Dont like
        base_path = join('..', 'workspaces-streamlit-template', 'default')
        base_path = dirname(self.workflow_dir)

        if not exists(join(base_path, 'db-fasta')):
            makedirs(join(base_path, 'db-fasta'))
        if not exists(join(base_path, 'anno-mzMLs')):
            makedirs(join(base_path, 'anno-mzMLs'))
        if not exists(join(base_path, 'deconv-mzMLs')):
            makedirs(join(base_path, 'deconv-mzMLs'))
        if not exists(join(base_path, 'tags-tsv')):
            makedirs(join(base_path, 'tags-tsv'))
        if not exists(join(base_path, 'proteins-tsv')):
            makedirs(join(base_path, 'proteins-tsv'))
            
        # # Log any messages.
        self.logger.log(f"Number of input mzML files: {in_mzMLs}")
        self.logger.log(f"Number of input mzML files: {database}")

        self.logger.log(self.file_manager.workflow_dir)


        uploaded_files = []
        for in_mzML in in_mzMLs:
            current_base = splitext(basename(in_mzML))[0]


            out_db = join(base_path, 'db-fasta', f'{current_base}_db.fasta')
            out_anno = join(base_path, 'anno-mzMLs', f'{current_base}_annotated.mzML')
            out_deconv = join(base_path, 'deconv-mzMLs', f'{current_base}_deconv.mzML')
            out_tag = join(base_path, 'tags-tsv', f'{current_base}_tagged.tsv')
            out_protein = join(base_path, 'proteins-tsv', f'{current_base}_protein.tsv')
            #decoy_db = join(temp_path, f'{current_base}_db.fasta')

            self.executor.run_topp(
                'DecoyDatabase',
                {
                    'in' : [database[0]],
                    'out' : [out_db],
                },
                params_manual = {
                    'method' : 'shuffle',
                    'shuffle_decoy_ratio' : 100,
                    'enzyme' : 'no cleavage',
                }
            )

            #copyfile(decoy_db, out_db)
            # TODO: Parallelize
            self.executor.run_topp(
                'FLASHDeconv',
                input_output={
                    'in' : [in_mzML],
                    'out' : ['_.tsv'],
                    'out_annotated_mzml' :  [out_anno],
                    'out_mzml' :  [out_deconv],
                }
            )

            self.executor.run_topp(
                'FLASHTagger',
                input_output={
                    'in' : [out_deconv],
                    'fasta' : [out_db],
                    'out_tag' :  [out_tag],
                    'out_protein' :  [out_protein]
                },
            )

            uploaded_files.append(out_db)
            uploaded_files.append(out_anno)
            uploaded_files.append(out_deconv)
            uploaded_files.append(out_tag)
            uploaded_files.append(out_protein)


        # make directory to store deconv and anno mzML files & initialize data storage
        # input_types = ["deconv-mzMLs", "anno-mzMLs", "tags-tsv", "db-fasta"]
        # parsed_df_types = ["deconv_dfs", "anno_dfs", "tag_dfs", "protein_db"]
        # initializeWorkspace(input_types, parsed_df_types)
        
        # handleInputFiles(uploaded_files)
        # parseUploadedFiles()



        # # Prepare output files for feature detection.
        # out_ffm = self.file_manager.get_files(in_mzML, "featureXML", "feature-detection")

        # # Run FeatureFinderMetabo tool with input and output files.
        # self.executor.run_topp(
        #     "FeatureFinderMetabo", input_output={"in": in_mzML, "out": out_ffm}
        # )

        # # Check if adduct detection should be run.
        # if self.params["run-adduct-detection"]:
        
        #     # Run MetaboliteAdductDecharger for adduct detection, with disabled logs.
        #     # Without a new file list for output, the input files will be overwritten in this case.
        #     self.executor.run_topp(
        #         "MetaboliteAdductDecharger", {"in": out_ffm, "out_fm": out_ffm}, write_log=False
        #     )

        # # Example for a custom Python tool, which is located in src/python-tools.
        # self.executor.run_python("example", {"in": in_mzML})

        # # Prepare output file for SiriusExport.
        # out_se = self.file_manager.get_files("sirius.ms", set_results_dir="sirius-export")
        # self.executor.run_topp("SiriusExport", {"in": self.file_manager.get_files(in_mzML, collect=True),
        #                                         "in_featureinfo": self.file_manager.get_files(out_ffm, collect=True),
        #                                         "out": out_se})

