"""
Main page for the OpenMS SageAdapter App.

This module sets up and displays the Streamlit app for the OpenMS Template App.
It includes:
- Setting the app title.
- Displaying a description.
- Providing a download button for the Windows version of the app.

Usage:
Run this script to launch the OpenMS Template App.

Note:
- If run in local mode, the CAPTCHA control is not applied.
- If not in local mode, CAPTCHA control is applied to verify the user.

Returns:
    None
"""

from pathlib import Path
import streamlit as st

from src.common.common import page_setup, v_space

page_setup(page="main")

st.markdown(
        """
        # PTMScanner
        ### SageAdapter: Integrating the proteomics search engine into the OpenMS framework.
        Welcome to the PTMScanner app, a web application for the SageAdapter tool from OpenMS built using [OpenMS](https://openms.de/) and [pyOpenMS](https://pyopenms.readthedocs.io/en/latest/).
        """
)

st.image("assets/SagePTMScanner.png")
    #st.image("assets/NuXL_image.png")
st.markdown(
        """
        In this web-app the Sage search engine is presented in a simple and easy-to-use graphical interface. Sage is a fast and reliable proteomics search engine for the anaylsis of MS data, for more see: [Sage](https://lazear.github.io/sage/). 
        This tool allows for annotation of various ions, fast discovery of PTMs, and FDR-filtering of results! 
        """
    )
    #In docker, OpenMS-app (executable) can be downloadable from github
    #TODO: make zip possible 
    
st.markdown("""
        ## Quickstart 

        You can start right away analyzing your data by following the steps below:

        ### 1. Create a workspace
        On the left side of this page a workspace  defined where all your data including uploaded files will be stored. In the web app, you can share your results via the unique workspace ID. Be careful with sensitive data, anyone with access to this ID can view your data.

        ⚠️ Note: In the web app, all users with a unique workspace ID have the same rights.
                
        ### 2. 📁 Upload your files
        Upload `mzML` and `fasta` files via the **File Upload** tab. The data will be stored in your workspace. With the web app you can upload only one file at a time.
        Locally there is no limit in files. However, it is recommended to upload large number of files by specifying the path to a directory containing the files.

        Your uploaded files will be shown on the same **File Upload** page. Also you can remove the files from workspace.

        ### 3. ⚙️ Analyze your uploaded data

        Select the `mzML` and `fasta` files for analysis, configure user settings, and start the analysis using the **Run-analysis** button.
        You can terminate the analysis immediately using the **Terminate/Clear** button and you can review the search engine log on the page.
        Once the analysis completed successfully, the output table will be displayed on the page, along with downloadable links for crosslink identification files.

        #### 4. 📊 View your results
        Here, you can visualize and explore the output of the search engine. All crosslink output files in the workspace are available on the **View Results** tab.
        After selecting any file, you can view the "Sage Output Table" and the "PTMs table".

        Note: Every table and plot can be downloaded, as indicated in the side-bar under ⚙️ Settings.

        #### How to accessing previously analysed results?
        Under the **Result Files** tab, you can manage your results. You can `remove` or `download` files from the output files list.

        #### How to upload result files (e.g., from external sources/collaborator) for manual inspection and visualization?
        At **Upload result files** tab, user can  `upload` the results files and can visualize in **View Results** tab.
        In the web app, collaborators can visualize files by sharing a unique workspace ID.
        
        #### Contact
        For any inquiries or assistance, please feel free to reach out to us.  
        [![Discord Shield](https://img.shields.io/discord/832282841836159006?style=flat-square&message=Discord&color=5865F2&logo=Discord&logoColor=FFFFFF&label=Discord)](https://discord.gg/4TAGhqJ7s5) [![Gitter](https://img.shields.io/static/v1?style=flat-square&message=on%20Gitter&color=ED1965&logo=Gitter&logoColor=FFFFFF&label=Chat)](https://gitter.im/OpenMS/OpenMS?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge)

    """)