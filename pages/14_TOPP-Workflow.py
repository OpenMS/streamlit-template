import streamlit as st
from src.common import page_setup
from src.Workflow import Workflow

# The rest of the page can, but does not have to be changed
if __name__ == "__main__":
    
    params = page_setup()

    wf = Workflow()

    st.title(wf.name)

    t = st.tabs(["**How to use NASE-Weis**", "📁 **File Upload**", "⚙️ **Configure**", "🚀 **Run**", "📊 **Results**"])
    with t[0]:
        st.markdown("""
                      # Quick start
                                        
                      1. Load the example MzMl (raw data) by clicking the "Load Example Data" button under the "MS data" tab of "📁File Upload".
                    
                      2. Load the example RNA sequence file by clicking the "Load Example Data" button under the "Nucleotide sequences" tab of "📁File Upload".
                    
                      3. Go to the ⚙️ Configure tab and Select the example files in the "mzML-files" and "fasta-files" entries.
                    
                      4. Click on the 🚀 **Run** tab and hit "Run" and click "Start Workflow"
                    
                      5. Go to the📊 **Results** tab and scroll through the results table. You can also download the table, a mzTab formatted version of the results, and a TOPPView idXML set of results.
                    
                      # More leisurely start

                      ## What is NASE-Weis

                      NASE-Weis (short for NucleicAcidSearchEngine Web execution in streamlit). Is a Web-app version of the [NucleicAcidSearchEngine](https://doi.org/10.1038/s41467-020-14665-7). 
                      It is a tool to search for (potentially modified) oligonucleotides in mass spectrometry data. The goal of NASE-Weis is to be easy to use for scientists who want to try out
                      searching oligonucleotide data. It does not have all of the features of the full NASE application. We are working on added as many of them as possible, but for the time being
                      if you need options that are not available here, please download the [whole OpenMS package](https://openms.readthedocs.io/en/latest/about/installation.html), or install the
                      [OpenMS extension for KNIME](https://hub.knime.com/openms-team/extensions/de.openms.feature/latest).

                      In addition to being able to run NASE-Weis in the cloud there is also a Windows version that you can [download](example.com/SPWFIXME) and install locally to search larger files.
                    

                      ## How to use NASE-Weis
                    
                      ### Prerequisites 
                    
                      In order to search your own data 

                      Clone the [streamlit-template repository](https://github.com/OpenMS/streamlit-template). It includes files to install dependencies via pip or conda.

                      ### via pip in an existing Python environment

                      To install all required depdencies via pip in an already existing Python environment, run the following command in the terminal:

                      `pip install -r requirements.txt`

                      ### create new environment via conda/mamba

                      Create and activate the conda environment:

                      `conda env create -f environment.yml`

                      `conda activate streamlit-env`

                      ### run the app

                      Run the app via streamlit command in the terminal with or without *local* mode (default is *online* mode). Learn more about *local* and *online* mode in the documentation page 📖 **OpenMS Template App**.

                      `streamlit run app.py [local]`

                      ## Docker

                      This repository contains two Dockerfiles.

                      1. `Dockerfile`: This Dockerfile builds all dependencies for the app including Python packages and the OpenMS TOPP tools. Recommended for more complex workflows where you want to use the OpenMS TOPP tools for instance with the **TOPP Workflow Framework**.
                      2. `Dockerfile_simple`: This Dockerfile builds only the Python packages. Recommended for simple apps using pyOpenMS only.

                      """)
    with t[1]:
        wf.show_file_upload_section()

    with t[2]:
        wf.show_parameter_section()

    with t[3]:
        wf.show_execution_section()
        
    with t[4]:
        wf.show_results_section()

