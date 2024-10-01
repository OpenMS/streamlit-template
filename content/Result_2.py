import streamlit as st
from src.common.common import *
from src.result_files import *
import plotly.graph_objects as go
from src.view import plot_ms2_spectrum, plot_ms2_spectrum_full
from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, ColumnsAutoSizeMode
from src.common.captcha_ import *
from pyopenms import *

params = page_setup()

# If run in hosted mode, show captcha as long as it has not been solved
if 'controllo' not in st.session_state or params["controllo"] == False:
    # Apply captcha by calling the captcha_control function
    captcha_control()


##################################

#TODO move to src folder
def process_mzML_file(filepath):
    """
    Loads an mzML file, extracts MS2 spectra, and normalizes the peak intensities.

    Parameters:
    filepath (str): The file path to the mzML file.

    Returns:
    MSExperiment: An MSExperiment object containing the normalized MS2 spectra.
    """

    try:
        # Initialize an MSExperiment object
        exp = MSExperiment()
        
        # Load the mzML file into the MSExperiment object
        MzMLFile().load(filepath, exp)

        # Create a new MSExperiment object to store MS2 spectra
        MS2 = MSExperiment()
        
        # Iterate over all spectra in the experiment
        for spec in exp:
            # Check if the spectrum is an MS2 spectrum
            if spec.getMSLevel() == 2:
                # Add the MS2 spectrum to the MS2 experiment object
                MS2.addSpectrum(spec)

        # Normalize peak intensities in the MS2 spectra
        normalizer = Normalizer()  # Create a Normalizer object
        param = normalizer.getParameters()  # Get the default parameters
        param.setValue("method", "to_one")  # Set normalization method to "to_one"
        normalizer.setParameters(param)  # Apply the parameters to the normalizer
        normalizer.filterPeakMap(MS2)  # Normalize the peaks in the MS2 spectra

        return MS2  # Return the MSExperiment object containing normalized MS2 spectra

    except Exception as e:
        return None  # Return None if any exception occurs

def get_mz_intensities_from_ms2(MS2_spectras, native_id):
    """
    Extracts m/z values and corresponding intensities from an MS2 spectrum with a specified native ID.

    Parameters:
    MS2_spectras (MSExperiment): An MSExperiment object containing MS2 spectra.
    native_id (str): The native ID of the desired MS2 spectrum.

    Returns:
    tuple: A tuple containing two arrays:
        - mz (list): List of m/z values.
        - intensities (list): List of corresponding intensity values.

    If the specified native ID is not found, the function returns None.
    """
    # Iterate through all spectra in the provided MS2_spectras object
    for spectrum in MS2_spectras.getSpectra():
        # Check if the current spectrum's native ID matches the specified native ID
        if spectrum.getNativeID() == native_id:
            # Extract m/z values and corresponding intensities from the spectrum
            mz, intensities = spectrum.get_peaks()
            # Return the m/z values and intensities as a tuple
            return mz, intensities
    
    # If the native ID is not found, return None
    return None

def remove_substrings(original_string, substrings_to_remove):
    modified_string = original_string
    for substring in substrings_to_remove:
        modified_string = modified_string.replace(substring, "")
    return modified_string

########################

### main content of page

# Make sure "selected-result-files" is in session state
if "selected-result-files" not in st.session_state:
    st.session_state["selected-result-files"] = params.get("selected-result-files", [])

# result directory path in current session state
result_dir: Path = Path(st.session_state.workspace, "result-files")

#title of page
st.title("📊 Result Viewer")

#tabs on page
tabs = ["View Results", "Result files", "Upload result files"]
tabs = st.tabs(tabs)

#with View Results tab
with tabs[0]:  

    tabs_ = st.tabs(["Sage Output Table", "PTMs Table"])
    

    ## selected .idXML file
    
        #with CSMs Table
    with tabs_[0]:
        load_example_result_files()
        # take all .idXML files in current session files; .idXML is CSMs 
        session_files = [f.name for f in Path(st.session_state.workspace,"result-files").iterdir() if (f.name.endswith(".idXML"))]
        mzML_files = [f2.name for f2 in Path(st.session_state.workspace,"mzML-files").iterdir() if (f2.name.endswith(".mzML"))]
        # select box to select .idXML file to see the results
        selected_file = st.selectbox("choose a currently protocol file to view",session_files)
        selected_mzML_file = st.selectbox("choose a currently protocol file to view",mzML_files)

        #current workspace session path
        workspace_path = Path(st.session_state.workspace)
        #tabs on page to show different results
        
        if selected_file:
            #st.write("CSMs Table")
            #take all CSMs as dataframe
            CSM_= readAndProcessIdXML(workspace_path / "result-files" /f"{selected_file}")
            #st.write(selected_file)

            ##TODO setup more better/effiecient
            # Remove the out pattern of idxml
            #file_name_wout_out = remove_substrings(selected_file, nuxl_out_pattern)

            if (selected_file.find("Example") != -1): 
               file_name_wout_out = "Example_RNA_UV_XL"
            else: 
                file_name_wout_out = selected_file.replace(".idXML", "")

            #st.write( os.path.join(Path.cwd().parent ,  str(st.session_state.workspace)[3:] , "mzML-files" ,f"{file_name_wout_out}.mzML"))

            #if os.path.isfile(os.path.join(Path.cwd().parent ,  str(st.session_state.workspace)[3:] , "mzML-files" ,f"{file_name_wout_out}.mzML")): 
                #st.write("File found")
            if selected_mzML_file: 
                MS2 = process_mzML_file(os.path.join(Path.cwd().parent ,  str(st.session_state.workspace)[3:] , "mzML-files" ,selected_mzML_file))
                if MS2 is None:
                    st.warning("The corresponding " +  ".mzML file could not be found. Please re-upload the mzML file to visualize all peaks.")
                                
                if CSM_ is None: 
                    st.warning("No CSMs found in selected idXML file")
                else:
                    
                    #if CSM_['NuXL:NA'].str.contains('none').any():
                    #    st.warning("nonXL CSMs found")  
                    #else:
                    
                        # provide dataframe
                        #st.write(list(CSM_.columns.values))
                        
                        gb = GridOptionsBuilder.from_dataframe(CSM_[list(CSM_.columns.values)])

                        # configure selection
                        gb.configure_selection(selection_mode="single", use_checkbox=True)
                        gb.configure_side_bar()
                        gb.configure_pagination(enabled=True, paginationAutoPageSize=False, paginationPageSize=10)
                        gridOptions = gb.build()


                        
                        data = AgGrid(CSM_,
                                    gridOptions=gridOptions,
                                    enable_enterprise_modules=True,
                                    allow_unsafe_jscode=True,
                                    update_mode=GridUpdateMode.SELECTION_CHANGED,
                                    columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS)

                        #download table
                        show_table(CSM_, f"{os.path.splitext(selected_file)[0]}")
                        #select row by user
                        selected_row = data["selected_rows"]

                    

                        #st.write(selected_row)
                        
                        #st.write(type(selected_row))
                        #st.write(selected_row.get(0))
                        #st.write(selected_row["Label"])
                        #st.write( selected_row[ "Label"] )
                        #st.write(selected_row['intensities'])

                        if not(selected_row is None):
                            # Create a dictionary of annotation features
                            annotation_data_idxml = {'intarray': [float(value) for value in {selected_row['intensities'][0]}.pop().split(',')],
                                    'mzarray': [float(value) for value in {selected_row['mz_values'][0]}.pop().split(',')],
                                    'anotarray': [str(value) for value in {selected_row['ions'][0]}.pop().split(',')]
                                }
                            
                            #annotation_data_idxml_df = pd.DataFrame(annotation_data_idxml)
                            #annotation_data_idxml_df.to_csv(str(selected_row[0]['ScanNr']) + "_idxml_annot.csv")
                            #st.write("ANOT:", annotation_data_idxml["anotarray"])
                            #st.write("MZ:",annotation_data_idxml["mzarray"])
                            #st.write("INT:",annotation_data_idxml["intarray"])


                            if MS2 is not None:
                                # Extract m/z and intensity data from the selected MS2 spectrum
                                mz_full, inten_full = get_mz_intensities_from_ms2(MS2_spectras=MS2, native_id=selected_row['SpecId'][0])
                                #st.write("MZFULL: ",list(mz_full) )
                                #st.write("INTENFULL: ",list(inten_full) )
                                scaled = []
                                for i in annotation_data_idxml['intarray']: 
                                    scaled.append(i/max(annotation_data_idxml['intarray']))
                                
                                #st.write("scaled", scaled)
                                # Convert annotation_data into a dictionary for efficient matching
                                annotation_dict = {(round(mz, 2)): (anot, i) for i, mz, anot in zip(scaled, annotation_data_idxml['mzarray'], annotation_data_idxml['anotarray'])}

                                #st.write(list(zip(scaled, annotation_data_idxml['mzarray'], annotation_data_idxml['anotarray'])))
                                #st.write(annotation_dict.keys())
                                #st.write(annotation_dict.values())

                                # Annotate the data
                                annotation_data = []
                                for intensity, mz in zip(inten_full, mz_full):
                                    mz_r = round(float(mz), 2)
                                    int_r = round(float(intensity), 2)
                                    #st.write(mz_r)
                                    annotation = annotation_dict.get(mz_r, (' ', int_r))
                                    #st.write(annotation)
                                    annotation_data.append({
                                        'mzarray': mz_r,
                                        'intarray': annotation[1],
                                        'anotarray': annotation[0]
                                    }) 
                            
                            if MS2 is None:
                                annotation_data = annotation_data_idxml # just provide the annotated peaks
                                st.write("MS2 was none")
    
                            # Check if the lists are not empty
                            if annotation_data:
                                #st.write("Gets to annotation data")
                                # Create the DataFrame
                                annotation_df = pd.DataFrame(annotation_data)
                                #st.write(annotation_df)
                                # title of spectra #Maybe remove NuXL:na
                                spectra_name = os.path.splitext(selected_file)[0] +" Scan# " + str({selected_row['ScanNr'][0]}).strip('{}') + " Pep: " + str({selected_row['Peptide'][0]}).strip('{}\'') 
                                # generate ms2 spectra
                                fig = plot_ms2_spectrum_full(annotation_df, spectra_name, "black")
                                #show figure
                                show_fig(fig,  f"{os.path.splitext(selected_file)[0]}_scan_{str({selected_row['ScanNr'][0]}).strip('{}')}")

                            else:
                                # if any list empty
                                st.warning("Annotation not available for this peptide")
                                    
        #with PRTs Table
    with tabs_[1]:
            
            #Make bar plots for various Output files 

            ptm_output_files = [f.name for f in Path(st.session_state.workspace,"result-files").iterdir() if (f.name.find("OutputTable.tsv")) != -1]
            selected_ptm_files = st.multiselect("choose a PTM-output file to view",ptm_output_files)
            # Creating the new filename as same as selected idXML file
            #new_filename = ""#f"{}_proteins{}_XLs.tsv"

            ptm_paths = []

            #path of corresponding protein file
            for p in selected_ptm_files: 
                ptm_paths.append(workspace_path / "result-files" /f"{p}")

            #if file exist
            if ptm_paths:
                combined_df_list = []
                for p in ptm_paths: 
                    dfPTMraw = pd.read_csv(p, sep= "\t")
                    dfPTM = dfPTMraw.head(30)
                    show_table(dfPTM, f"{os.path.splitext(p)[0]}")
                    combined_df_list.append(dfPTM)

                    
                    PTM_fig = go.Figure(data=[go.Bar(x=dfPTM["Name"], y=dfPTM["Modified Peptides"], marker_color='rgb(55, 83, 109)')])
                    #update the layout of plot
                    PTM_fig.update_layout(
                        title='PTM list',
                        xaxis_title='Modifications',
                            yaxis_title='Frequency',
                            font=dict(family='Arial', size=12, color='rgb(0,0,0)'),
                            paper_bgcolor='rgb(255, 255, 255)',
                            plot_bgcolor='rgb(255, 255, 255)'
                        )
                    #show figure, with download
                    show_fig(PTM_fig, f"{os.path.splitext(p)[0]}")
                    #show button of download table from where above plot came
                combined_df = pd.DataFrame()
                for df in combined_df_list: 
                    combined_df = pd.concat([combined_df, df])
                
                if len(combined_df_list) > 1 : 
                    st.write("Combined Table")
                    result_df = combined_df.groupby(['Name'], as_index=False).agg({
                        'Modified Peptides': 'sum',     # Sum the 'amount' for matching names
                        'Modified Peptides (incl. charge variants)': 'sum', 
                        'Mass': 'first'  # Keep the first occurrence for other columns
                        })
                    result_df = result_df.sort_values(by='Modified Peptides', ascending=False)
                    result_df = result_df.head(30)
                    
                    PTM_fig_combo = go.Figure(data=[go.Bar(x=result_df["Name"], y=result_df["Modified Peptides"], marker_color='rgb(55, 83, 109)')])
                    #update the layout of plot
                    PTM_fig_combo.update_layout(
                        title='PTM list',
                        xaxis_title='Modifications',
                            yaxis_title='Count',
                            font=dict(family='Arial', size=12, color='rgb(0,0,0)'),
                            paper_bgcolor='rgb(255, 255, 255)',
                            plot_bgcolor='rgb(255, 255, 255)'
                        )
                    #show figure, with download
                    show_fig(PTM_fig_combo, f"{os.path.splitext(p)[0]}")
                
                    show_table(result_df)

            #if the same protein file not available
            else:
                st.warning(f"{ptm_paths} file not exist in current workspace") 

            

#with "Result files" 
with tabs[1]:
    #make sure to load all results example files
    load_example_result_files()

    if any(Path(result_dir).iterdir()):
        v_space(2)
        #  all result files currently in workspace
        df = pd.DataFrame(
            {"file name": [f.name for f in Path(result_dir).iterdir()]})
        st.markdown("##### result files in current workspace:")

        show_table(df)
        v_space(1)
        # Remove files
        copy_local_result_files_from_directory(result_dir)
        with st.expander("🗑️ Remove result files"):
            #take all example result files name
            list_result_examples = list_result_example_files()
            #take all session result files
            session_files = [f.name for f in sorted(result_dir.iterdir())]
            #filter out the example result files
            Final_list = [item for item in session_files if item not in list_result_examples]

            #multiselect for result files selection
            to_remove = st.multiselect("select result files", options=Final_list)

            c1, c2 = st.columns(2)
            ### remove selected files from workspace
            if c2.button("Remove **selected**", type="primary", disabled=not any(to_remove)):
                remove_selected_result_files(to_remove)
                st.rerun() 

            ### remove all files from workspace
            if c1.button("⚠️ Remove **all**", disabled=not any(result_dir.iterdir())):
                remove_all_result_files() 
                st.rerun()


        with st.expander("⬇️ Download result files"):
            #multiselect for result files selection
            to_download = st.multiselect("select result files for download",
                                    options=[f.name for f in sorted(result_dir.iterdir())])
            
            c1, c2 = st.columns(2)
            if c2.button("Download **selected**", type="primary", disabled=not any(to_download)):
                #download selected files will display download hyperlink
                download_selected_result_files(to_download, "selected_result_files")
                #st.experimental_rerun()

            ### afraid if there are many files in workspace? should we removed this option?
            if c1.button("⚠️ Download **all**", disabled=not any(result_dir.iterdir())):
                #create the zip content of all result files in workspace
                b64_zip_content = create_zip_and_get_base64_()
                #display the download hyperlink
                href = f'<a href="data:application/zip;base64,{b64_zip_content}" download="all_result_files.zip">Download All Files</a>'
                st.markdown(href, unsafe_allow_html=True)

#with "Upload result files"
with tabs[2]:
    #form to upload file
    with st.form("Upload .idXML and .tsv", clear_on_submit=True):
        files = st.file_uploader(
            "Result files", accept_multiple_files=(st.session_state.location == "local"), type=['.idXML', '.tsv'], help="Input file (Valid formats: 'idXML', 'tsv')")
        cols = st.columns(3)
        if cols[1].form_submit_button("Add files to workspace", type="primary"):
            if not files:
                st.warning("Upload some files first.")
            else:
                save_uploaded_result(files)
            st.rerun()

# At the end of each page, always save parameters (including any changes via widgets with key)
save_params(params)