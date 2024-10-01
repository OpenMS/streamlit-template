import os
import streamlit as st
from streamlit_plotly_events import plotly_events
import subprocess
from src.common import *
from src.view import *
from src.fileupload import *
from src.result_files import *
from src.ini2dec import *
import threading
from src.common.captcha_ import *
from src.common.common import * 
from src.run_subprocess import *
from pyopenms import * 


params = page_setup()    

### main content of page

# title of page
st.title("⚙️ Run Analysis")

######################## Take NuXL configurations ini read #################################
# Define the sections you want to extract
# will capture automaticaly if add new section as decoy_factor 
sections = [
    "fixed",
    "variable",
    "presets",
    "enzyme",
    "scoring",
    "variable_max_per_peptide",
    "length",
    "mass_tolerance_right", # will store in config dict both precursor_mass_tolerance, and fragmant_mass_tolerance
    "mass_tolerance_left", 
    "mass_tolerance_unit", # will store in config dict both precursor_mass_tolerance_unit, and fragmant_mass_tolerance_unit
    "min_size",
    "max_size",
    "missed_cleavages", 
    "Test"
]

# current directory
current_dir = os.getcwd()
# take .ini config path
config_path = os.path.join(current_dir, 'assets', 'OpenMS_Init.ini')
Sage_Config=ini2dict(config_path, sections)

# make sure "selected-mzML-files" is in session state
if "selected-mzML-files" not in st.session_state:
    st.session_state["selected-mzML-files"] = params.get("selected-mzML-files", [])

# make sure "selected-fasta-files" is in session state
if "selected-fasta-files" not in st.session_state:
    st.session_state["selected-fasta-files"] = params.get("selected-fasta-files", [])

if st.session_state.location == "local":
    sage_exec = st.text_input(label = "Path to sage executable")
    SageAdapter_exec = st.text_input(label = "Path to SageAdapter executable")

# make sure mzML example files in current session state
load_example_mzML_files()

# take mzML files from current session file
mzML_files_ = [f.name for f in Path(st.session_state.workspace, "mzML-files").iterdir()]

# make sure fasta example files in current session state
load_example_fasta_files()

# take fasta files from current session file
fasta_files = [f.name for f in Path(st.session_state.workspace,"fasta-files").iterdir()]



show_options = st.selectbox("Show additional options?", ["No", "Yes"])

# put Trypsin as first enzyme
if 'Trypsin' in Sage_Config['enzyme']['restrictions']:
    Sage_Config['enzyme']['restrictions'].remove('Trypsin')
    Sage_Config['enzyme']['restrictions'].insert(0, 'Trypsin')

with st.form("fasta-upload", clear_on_submit=False):

    # selected mzML file from mzML files list
    selected_mzML_file = st.multiselect(
        "choose mzML file",
        [item for item in mzML_files_ if not item.endswith(".csv")]
        ,
        help="If file not here, please upload at File Upload"
    )

    # select fasta file from mzML files list
    selected_fasta_file = st.selectbox(
        "choose fasta file",
        [f.name for f in Path(st.session_state.workspace,
                            "fasta-files").iterdir()],
        help="If file not here, please upload at File Upload"
    )
    # take full path of mzML file
    mzML_file_paths = []
    for mzml in selected_mzML_file:
        mzML_file_paths.append(str(Path(st.session_state.workspace, "mzML-files", mzml)))

    # take full path of fasta file
    if selected_fasta_file:
        database_file_path = str(Path(st.session_state.workspace, "fasta-files", selected_fasta_file))


    if show_options == "Yes":
        with st.expander("Additional Options"):
            # take all variables settings from config dictionary/ take all user configuration
            cols=st.columns(2)
            with cols[0]:
                cols_=st.columns(2)
                with cols_[0]:
                    Enzyme = st.selectbox('enzyme', Sage_Config['enzyme']['restrictions'], help="Sage_Config['enzyme']['description']")
                with cols_[1]:
                    Missed_cleavages = str(st.number_input("missed cleavages",value=int(Sage_Config['missed_cleavages']['default']), help=Sage_Config['missed_cleavages']['description'] + " default: "+ Sage_Config['missed_cleavages']['default']))
                    if int(Missed_cleavages) <= 0:
                        st.error("Length must be a positive integer greater than 0")

            with cols[1]:
                cols_=st.columns(2)
                with cols_[0]:
                    peptide_min = str(st.number_input('peptide min length', value=int(Sage_Config['min_size']['default']), help=Sage_Config['min_size']['description'] + " default: "+ Sage_Config['min_size']['default']))
                    if int(peptide_min) < 1:
                            st.error("Length must be a positive integer greater than 0")

                with cols_[1]:
                    peptide_max= str(st.number_input('peptide max length', value=int(Sage_Config['max_size']['default']), help=Sage_Config['max_size']['description'] + " default: "+ Sage_Config['max_size']['default']))
                    if int(peptide_max) < 1:
                            st.error("Length must be a positive integer greater than 1")

            cols=st.columns(2)
            with cols[0]:
                cols_=st.columns(2)
                with cols_[0]:
                    Precursor_MT_right = str(st.number_input("precursor mass tolerance right",value=float(Sage_Config['precursor_mass_tolerance_right']['default']), help=Sage_Config['precursor_mass_tolerance_right']['description'] + " default: "+ Sage_Config['precursor_mass_tolerance_right']['default']))
                    if float(Precursor_MT_right) <= 0:
                        st.error("Precursor mass tolerance must be a positive integer")

                with cols_[1]:
                    Precursor_MT_left = str(st.number_input("precursor mass tolerance left",value=float(Sage_Config['precursor_mass_tolerance_left']['default']), help=Sage_Config['precursor_mass_tolerance_left']['description'] + " default: "+ Sage_Config['precursor_mass_tolerance_left']['default']))
                    if float(Precursor_MT_left) >= 0:
                        st.error("Precursor mass tolerance must be a negative integer")
                    #Precursor_MT_unit= st.selectbox('precursor mass tolerance unit',Sage_Config['precursor_mass_tolerance_unit']['restrictions'], help=Sage_Config['precursor_mass_tolerance_unit']['description'] + " default: "+ Sage_Config['precursor_mass_tolerance_unit']['default'])
                    
            with cols[1]:
                cols_=st.columns(2)
                with cols_[0]:
                    Fragment_MT_right = str(st.number_input("fragment mass tolerance right",value=float(Sage_Config['fragment_mass_tolerance_right']['default']), help=Sage_Config['fragment_mass_tolerance_right']['description'] + " default: "+ Sage_Config['fragment_mass_tolerance_right']['default']))
                    if float(Fragment_MT_right) <= 0:
                        st.error("Fragment mass tolerance must be a positive integer")
                with cols_[1]: 
                    Fragment_MT_left = str(st.number_input("fragment mass tolerance left",value=float(Sage_Config['fragment_mass_tolerance_left']['default']), help=Sage_Config['fragment_mass_tolerance_left']['description'] + " default: "+ Sage_Config['fragment_mass_tolerance_left']['default']))
                    if float(Fragment_MT_left) >= 0:
                        st.error("Fragment mass tolerance must be a negative integer")

            cols=st.columns(2)
            with cols[0]: 
                Precursor_MT_unit = cols[0].radio(
                "precursor mass tolerance unit",
                Sage_Config['precursor_mass_tolerance_unit']['restrictions'], 
                help=Sage_Config['precursor_mass_tolerance_unit']['description']  + " default: "+ Sage_Config['precursor_mass_tolerance_unit']['default'],
                key="Precursor_MT_unit", index = 1
                )

            with cols[1]: 
                #Fragment_MT_unit= st.selectbox('fragment mass tolerance unit', Sage_Config['precursor_mass_tolerance_unit']['restrictions'], help=Sage_Config['fragment_mass_tolerance_unit']['description'] + " default: "+ Sage_Config['fragment_mass_tolerance_unit']['default'])
                Fragment_MT_unit = cols[1].radio(
                "fragment mass tolerance unit",
                Sage_Config['precursor_mass_tolerance_unit']['restrictions'], 
                help=Sage_Config['fragment_mass_tolerance_unit']['description']+ " default: "+ Sage_Config['fragment_mass_tolerance_unit']['default'],
                key="Fragment_MT_unit"
                )
            
            cols=st.columns(2)
            with cols[0]:
                fixed_modification = st.multiselect('select fixed modifications:', Sage_Config['fixed']['restrictions'], help=Sage_Config['fixed']['description'] + " default: "+ Sage_Config['fixed']['default'], default = "Carbamidomethyl (C)")

            with cols[1]: 
                variable_modification = st.multiselect('select variable modifications:', Sage_Config['variable']['restrictions'], help=Sage_Config['variable']['description'] + " default: "+ Sage_Config['variable']['default'], default = "Oxidation (M)")
                
            cols=st.columns(2)
            with cols[0]:
                Variable_max_per_peptide  = str(st.number_input("variable modification max per peptide",value=int(Sage_Config['variable_max_per_peptide']['default']), help=Sage_Config['variable_max_per_peptide']['description'] + " default: "+ Sage_Config['variable_max_per_peptide']['default']))
                if int(Variable_max_per_peptide) <= -1:
                    st.error("variable modification max per peptide must be a positive integer")

            with cols[1]:
                #scoring  = st.selectbox('select the scoring method',Sage_Config['scoring']['restrictions'], help=Sage_Config['scoring']['description'] + " default: "+ Sage_Config['scoring']['default'])
                psm_scores = str(st.number_input('Report PSMs', value = 2))
                if int(peptide_min) < 1:
                    st.error("Length must be a positive integer greater than 0")

            cols=st.columns(2)

            with cols[0]: 
                cols_=st.columns(2)
                with cols_[0]:
                    Wide_window_mode = bool(st.checkbox(label = "Wide Window", help = "Click if wide window mode should be enabled, leave unchecked if not (Warning: only check if absolutely sure!)"))
                with cols_[1]:
                    Predict_rt = bool(st.checkbox(label = "Predict RT", help= "Check if retention time should be predicted, leave unchecked if not"))
            with cols[1]: 
                cols_=st.columns(3)
                with cols_[0]:
                    Annotate_TF = bool(st.checkbox(label = "Annotation", help = "Check if annotation should be produced, leave unchecked if not"))
                with cols_[1]:
                    Deisotope = bool(st.checkbox(label = "Deisotope", help = "Check if deisotoping should be done, leave unchecked if not"))
                with cols_[2]:
                    Chimera = bool(st.checkbox(label = "Chimera", help = "Check if chimera mode should be enabled, leave unchecked if not"))
            
            cols=st.columns(2)

            with cols[0]: 
                FDR_Var = str(st.number_input("False Discovery Rate filtering threshhold",value=float(0.01), help="False Discovery Rate filter for peptides, default: 0.01"))
            with cols[1]:
                cols_=st.columns(3)
                with cols_[0]: 
                    smoothing =  bool(st.checkbox(label = "Smoothing", help = "Check if smoothing + local maxima picking should be done, leave unchecked if not"))
                with cols_[1]: 
                    rerun = bool(st.checkbox(label = "Localization-Rerun", help = "Check if Sage should be rerun with top PTMs found"))

    else:
        Enzyme = Sage_Config['enzyme']['restrictions'] 
        Missed_cleavages = str(Sage_Config['missed_cleavages']['default'])
        peptide_min = str(Sage_Config['min_size']['default'])
        peptide_max = str(int(Sage_Config['max_size']['default']))
        Precursor_MT_right = str(float(Sage_Config['precursor_mass_tolerance_right']['default']))
        Precursor_MT_left = str(float(Sage_Config['precursor_mass_tolerance_left']['default']))
        Fragment_MT_right = str(float(Sage_Config['fragment_mass_tolerance_right']['default']))
        Fragment_MT_left = str(float(Sage_Config['fragment_mass_tolerance_left']['default']))       
        Precursor_MT_unit = Sage_Config['precursor_mass_tolerance_unit']['default']
        Fragment_MT_unit = Sage_Config['fragment_mass_tolerance_unit']['default']
        # Replace multiselect with default values
        fixed_modification = "Carbamidomethyl (C)"
        variable_modification = "Oxidation (M)"
        Variable_max_per_peptide = str(int(Sage_Config['variable_max_per_peptide']['default']))
        psm_scores = str(2)
        Not_in_docker = False
        Wide_window_mode = False
        Predict_rt = False
        Annotate_TF = False
        Deisotope = False
        Chimera = False
        FDR_Var = str(float(0.01))
        smoothing = False
        rerun = False
        st.write("Additional options are currently hidden. Using default configuration for open searches.")
        cols=st.columns(2)
# out file path
result_dir: Path = Path(st.session_state.workspace, "result-files")

# create same output file path name as input file path
mzML_file_paths_abs = []
for mzmlfp in mzML_file_paths: 
    mzML_file_paths_abs.append(os.path.abspath(mzmlfp))

mzML_file_names = []
for mzmlfp in mzML_file_paths_abs: 
    os.path.basename(mzmlfp)
    mzML_file_names.append(os.path.basename(mzmlfp))
    

protocol_names = []
for mzmlfn in mzML_file_names: 
    protocol_names.append(os.path.splitext(mzmlfn)[0])

protocol_name = ''.join(protocol_names)

# result dictionary to capture output of subprocess
result_dict = {}
result_dict["success"] = False
result_dict["log"] = " "

# create terminate flag from even function
terminate_flag = threading.Event()
terminate_flag.set()

# terminate subprocess by terminate flag
def terminate_subprocess():
    global terminate_flag
    terminate_flag.set()

# run analysis 
if cols[0].form_submit_button("Run-analysis", type="primary"):
    #st.write("Button reached")
    # To terminate subprocess and clear form
    if st.button("Terminate/Clear", key="terminate-button", type="secondary"):
        #terminate subprocess
        terminate_subprocess()
        st.warning("Process terminated. The analysis may not be complete.")
        #clear form
        st.rerun() 

    # with st.spinner("Running analysis... Please wait until analysis done 😑"): #without status/ just spinner button
    with st.status("Running analysis... Please wait until analysis done 😑"):
        for mzML_file_path in mzML_file_paths: 

            mzMLfilepath = [mzML_file_path]
            base_name = os.path.basename(mzML_file_path)
            base = base_name.removesuffix(".mzML")
            result_path = os.path.join(result_dir, base + "Output" + ".idXML")

            result_dict["success"] = False
            # If session state is local
            if st.session_state.location == "local":
                args = [SageAdapter_exec, "-in"]
                args.extend((mzMLfilepath))
                args.extend([ "-database", database_file_path, "-out", result_path,
                            "-precursor_tol_left",  Precursor_MT_left, "-precursor_tol_right", Precursor_MT_right, "-precursor_tol_unit",  Precursor_MT_unit,
                            "-fragment_tol_left",  Fragment_MT_left, "-fragment_tol_right", Fragment_MT_right , "-fragment_tol_unit",  Fragment_MT_unit,
                            "-min_len", peptide_min, "-max_len",peptide_max, "-missed_cleavages",Missed_cleavages, "-enzyme", Enzyme,
                            "-max_variable_mods", Variable_max_per_peptide,"-annotate_matches",str(Annotate_TF).lower(), "-report_psms",str(psm_scores).lower(),"-deisotope", str(Deisotope).lower(), "-chimera", str(Chimera).lower(),"-predict_rt",str(Predict_rt).lower(), 
                            "-wide_window", str(Wide_window_mode).lower(), "-smoothing", str(smoothing).lower(), "-q_value_threshold", FDR_Var , "-sage_executable", sage_exec
                            ])
    
            # If session state is online/docker
            else:     

                # In docker it executable on path   
                #st.write("In docker")
                #sage_exec = "/usr/local/bin/sage"
                args = ["SageAdapter", "-in"]
                args.extend((mzMLfilepath))
                args.extend([ "-database", database_file_path, "-out", result_path,
                        "-precursor_tol_left",  Precursor_MT_left, "-precursor_tol_right", Precursor_MT_right, "-precursor_tol_unit",  Precursor_MT_unit,
                        "-fragment_tol_left",  Fragment_MT_left, "-fragment_tol_right", Fragment_MT_right , "-fragment_tol_unit",  Fragment_MT_unit,
                        "-min_len", peptide_min, "-max_len",peptide_max, "-missed_cleavages",Missed_cleavages, "-enzyme", Enzyme,
                        "-max_variable_mods", Variable_max_per_peptide,"-annotate_matches",str(Annotate_TF).lower(), "-report_psms",str(psm_scores).lower(),"-deisotope", str(Deisotope).lower(), "-chimera", str(Chimera).lower(),"-predict_rt",str(Predict_rt).lower(), 
                        "-wide_window", str(Wide_window_mode).lower(),"-smoothing", str(smoothing).lower(), "-q_value_threshold", FDR_Var ,  "-sage_executable", "sage"
                        ])

            
            # If variable modification provided
            if variable_modification: 
                args.extend(["-variable_modifications"])
                args.extend(variable_modification)

            # If fixed modification provided
            if fixed_modification: 
                args.extend(["-fixed_modifications"])
                args.extend(fixed_modification)
            
            # Add any additional variables needed for the subprocess (if any)
            variables = []  

            # run subprocess command
            #st.write(st.session_state.location)
            run_subprocess(args, result_dict)

    # if run_subprocess success (no need if not success because error will show/display in run_subprocess command)
    if result_dict["success"]:
        st.write("Success")

        # Save the log to a text file in the result_dir
        log_file_path = result_dir / f"log.txt"
        with open(log_file_path, "w") as log_file:
            log_file.write(result_dict["log"])

        # all result files in result-dir
        All_files = [f.name for f in sorted(result_dir.iterdir())]
        #st.write(All_files)

        # filtered out all current run file from all resul-dir files
        #current_analysis_files = [s for s in All_files if protocol_name in s]
        current_analysis_files = [s for s in All_files]

        # add list of files to dataframe
        df = pd.DataFrame({"output files ": current_analysis_files})

        # show table of all list files of current protocol
        show_table(df)

        outfiles = [s for s in current_analysis_files if ("OutputTable.tsv" in s and base in s)]

        names = []

        combined_df_list=[]

        for file in outfiles: 
            outfile_val = pd.read_csv( (str(result_dir) + "/" + file), sep = "\t")
            show_table(outfile_val)
            combined_df_list.append(outfile_val)

    
        listofmods = Sage_Config['variable']['restrictions']

        research_list = []

        combined_df = pd.DataFrame()

        for df in combined_df_list: 
                combined_df = pd.concat([combined_df, df])
                
        result_df = combined_df.groupby(['Name'], as_index=False).agg({
                    'Modified Peptides': 'sum',     # Sum the 'amount' for matching names
                    'Modified Peptides (incl. charge variants)': 'sum', 
                    'Mass': 'first'  # Keep the first occurrence for other columns
                    })
        result_df = result_df.sort_values(by='Modified Peptides', ascending=False)
                
        mod_name_top = result_df["Name"].iloc[0]
        i = 1
        while("//" in mod_name_top and i < len(result_df["Name"])): 
            mod_name_top = result_df["Name"].iloc[i]
            i = i +1 

        top_mod = ModificationsDB().getModification(mod_name_top).getFullId()

        research_list.append(top_mod)
        

        if rerun: 
            for mzML_file_path in mzML_file_paths: 

                mzMLfilepath = [mzML_file_path]
                base_name = os.path.basename(mzML_file_path)
                base = base_name.removesuffix(".mzML")
                st.write(base)
                result_path = os.path.join(result_dir, base + "Output-Rerun" + ".idXML")
                # If session state is local
                if st.session_state.location == "local":
                    args = [SageAdapter_exec, "-in"]
                    args.extend((mzMLfilepath))
                    args.extend([ "-database", database_file_path, "-out", result_path,
                                "-precursor_tol_left",  Precursor_MT_left, "-precursor_tol_right", Precursor_MT_right, "-precursor_tol_unit",  Precursor_MT_unit,
                                "-fragment_tol_left",  Fragment_MT_left, "-fragment_tol_right", Fragment_MT_right , "-fragment_tol_unit",  Fragment_MT_unit,
                                "-min_len", peptide_min, "-max_len",peptide_max, "-missed_cleavages",Missed_cleavages, "-enzyme", Enzyme,
                                "-max_variable_mods", Variable_max_per_peptide,"-annotate_matches",str(Annotate_TF).lower(), "-report_psms",str(psm_scores).lower(),"-deisotope", str(Deisotope).lower(), "-chimera", str(Chimera).lower(),"-predict_rt",str(Predict_rt).lower(), 
                                "-wide_window", str(Wide_window_mode).lower(), "-smoothing", str(smoothing).lower(), "-q_value_threshold", FDR_Var , "-sage_executable", sage_exec
                                ])
        
                # If session state is online/docker
                else:     
                    args = ["SageAdapter", "-in"]
                    args.extend(mzMLfilepath)
                    args.extend([ "-database", database_file_path, "-out", result_path,
                            "-precursor_tol_left",  Precursor_MT_left, "-precursor_tol_right", Precursor_MT_right, "-precursor_tol_unit",  Precursor_MT_unit,
                            "-fragment_tol_left",  Fragment_MT_left, "-fragment_tol_right", Fragment_MT_right , "-fragment_tol_unit",  Fragment_MT_unit,
                            "-min_len", peptide_min, "-max_len",peptide_max, "-missed_cleavages",Missed_cleavages, "-enzyme", Enzyme,
                            "-max_variable_mods", Variable_max_per_peptide,"-annotate_matches",str(Annotate_TF).lower(), "-report_psms",str(psm_scores).lower(),"-deisotope", str(Deisotope).lower(), "-chimera", str(Chimera).lower(),"-predict_rt",str(Predict_rt).lower(), 
                            "-wide_window", str(Wide_window_mode).lower(),"-smoothing", str(smoothing).lower(), "-q_value_threshold", FDR_Var ,  "-sage_executable", "sage"
                            ])
                # If variable modification provided
                if variable_modification: 
                    args.extend(["-variable_modifications"])
                    args.extend(variable_modification)
                    args.extend(research_list)

                # If fixed modification provided
                if fixed_modification: 
                    args.extend(["-fixed_modifications"])
                    args.extend(fixed_modification)
                
                # Add any additional variables needed for the subprocess (if any)
                variables = []  

                # run subprocess command
                #st.write(st.session_state.location)
                st.write(args)
                run_subprocess(args, result_dict)

    # if run_subprocess success (no need if not success because error will show/display in run_subprocess command)
        if result_dict["success"]:
            st.write("Great Success! ")

            # Save the log to a text file in the result_dir
            log_file_path = result_dir / f"log.txt"
            with open(log_file_path, "w") as log_file:
                log_file.write(result_dict["log"])

            # all result files in result-dir
            All_files = [f.name for f in sorted(result_dir.iterdir())]
            #st.write(All_files)

            # filtered out all current run file from all resul-dir files
            current_analysis_files = [s for s in All_files]

            # add list of files to dataframe
            df = pd.DataFrame({"output files ": current_analysis_files})

            # show table of all list files of current protocol
            show_table(df)

save_params(params)