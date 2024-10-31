import streamlit as st
from src.common.common import page_setup
from src.Workflow import Workflow

# The rest of the page can, but does not have to be changed
if __name__ == "__main__":
    
    params = page_setup()

    wf = Workflow()

    st.title(wf.name)

    t = st.tabs(["**How to use NASEWEIS**", "📁 **File Upload**", "⚙️ **Configure**", "🚀 **Run**", "📊 **Results**"])
    with t[0]:
        st.markdown("""
                      ## What is NASEWEIS

                      NASEWEIS (short for NucleicAcidSearchEngine Web execution in streamlit). Is a Web-app version of the [NucleicAcidSearchEngine](https://doi.org/10.1038/s41467-020-14665-7). 
                      It is a tool to search for (potentially modified) oligonucleotides in mass spectrometry data. The goal of NASEWEIS is to be easy to use for scientists who want to try out
                      searching oligonucleotide data. It does not have all of the features of the full NASE application. We are working on added as many of them as possible, but for the time being
                      if you need options that are not available here, please download the [whole OpenMS package](https://openms.readthedocs.io/en/latest/about/installation.html), or install the
                      [OpenMS extension for KNIME](https://hub.knime.com/openms-team/extensions/de.openms.feature/latest).

                      In addition to being able to run NASEWEIS in the cloud there is also a Windows version that you can [download](example.com/SPWFIXME) and install locally to search larger files.
                    

                      ## How to use NASEWEIS
                    
                      ### Prerequisites 
                    
                      In order to search your own data you need two things: Output from a MS experiment formatted as an [mzML file](https://doi.org/10.1007%2F978-1-60761-444-9_22),
                      and a set of sequences to search formatted as a [FASTA file](https://en.wikipedia.org/wiki/FASTA_format). You can convert the raw files produced by your instrument to mzML
                      using [MSConvert](https://proteowizard.sourceforge.io/). Search sequences are formatted as a standard FASTA entries with sequences including the canonical RNA bases (A,U,C,G),
                      as well as "short name" representations of modified residues from [Modomics](https://genesilico.pl/modomics/modifications) surrounded by square brackets (see below for an example)
                    
                      > **_Example:_** RNA sequence: AUCCCUGGACAUA[Am]CU[P]AAA - Includes 2'-O-methyladenosine and Pseudouridine, in addition to cannoncial bases
                    
                      Note that the FASTA file can contain many sequences, if you are searching for multiple forms or RNAs.
                    
                      ### Uploading your files
                    
                      Navigate to the "📁File Upload" tab in NASEWEIS. There are two sub-tabs "MS data" and "Nucleotide sequences". You can upload your mzML file under the MS-data sub-tab, and your FASTA file under the "Nucleotide sequences" sub-tab by clicking "Browse files" and
                      selecting your file. After uploading the files, you should see a "Current files" box showing the files that you have uploaded. Alternatively, you can use the supplied example data by clicking the "Load Example Data" button.
                    
                      ### Configuring NASEWEIS

                      Navigate to the "⚙️ **Configure**" tab in NASEWEIS. Select the files that you uploaded in the previous step in the mzML-files and fasta-files boxes. If you don't want to do FDR calculations click on the "do FDR?" checkbox. You can also adjust the FDR cutoff below.
                      Once you are satisfied with the FDR settings, click the "Nucleic acid search engine" tab above the "Do FDR?" box. Here you will see options for the search engine itself. The search engine automatically selects internal tolerance, and mass options based on the resolution of the data
                      make sure that the settings for "MS1 approximate resolution?" and "MS2 approximate resolution?" **roughly** match those for your data. If the RNA was digested with an enzyme before the experiment, select your enzyme in the "enzyme box", and select the number of missed cleavages
                      to allow. After you are happy with these settings, click the "Save Parameters" button above.
                    
                      ### Running NASEWEIS
                    
                      Navigate to the "🚀 **Run**" tab in NASEWEIS. Click the "Start Workflow" button. You will get a "WORKFLOW FINISHED" message below when the workflow is done. If you want to see more details, you can configure the "log details" above the start button.
                    
                      ### Viewing the results

                      Navigate to the 📊 **Results** tab. There you will see a table of the results of your search, showing RNA's were matched, what digestion fragment matched, the retention time and mass to charge ratio of the match, its charge, the search engine score, and (if FDR is enabled) the q-value in %.
                      Below the table is a button to download it as a CSV. There are also buttons to download the idXML formatted hits (for use with pyOpenMS or TOPPView), and mztab formatted output.


                      """)
    with t[1]:
        wf.show_file_upload_section()

    with t[2]:
        wf.show_parameter_section()

    with t[3]:
        wf.show_execution_section()
        
    with t[4]:
        wf.show_results_section()

