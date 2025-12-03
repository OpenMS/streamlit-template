import streamlit as st
from src.Workflow import Workflow
from src.workflow.StreamlitUI import StreamlitUI
from src.workflow.FileManager import FileManager
from src.workflow.CommandExecutor import CommandExecutor
from inspect import getsource

def content():
    st.title("TOPP Workflow Framework Documentation")

    st.markdown(
        """
## Features

- streamlined methods for uploading files, setting parameters, and executing workflows
- automatic parameter handling
- quickly build parameter interface for TOPP tools with all parameters from *ini* files
- automatically create a log file for each workflow run with stdout and stderr
- workflow output updates automatically in short intervalls
- user can leave the app and return to the running workflow at any time
- quickly build a workflow with multiple steps channelling files between steps
"""
    )

    st.markdown(
        """
## Quickstart

This repository contains a module in `src/workflow` that provides a framework for building and running analysis workflows.

The `WorkflowManager` class provides the core workflow logic. It uses the `Logger`, `FileManager`, `ParameterManager`, and `CommandExecutor` classes to setup a complete workflow logic.

To build your own workflow edit the file `src/TOPPWorkflow.py`. Use any streamlit components such as tabs (as shown in example), columns, or even expanders to organize the helper functions for displaying file upload and parameter widgets.

> 💡 Simply set a name for the workflow and overwrite the **`upload`**, **`configure`**, **`execution`** and **`results`** methods in your **`Workflow`** class.

The file `content/6_TOPP-Workflow.py` displays the workflow content and can, but does not have to be modified.

The `Workflow` class contains four important members, which you can use to build your own workflow:

> **`self.params`:** dictionary of parameters stored in a JSON file in the workflow directory. Parameter handling is done automatically. Default values are defined in input widgets and non-default values are stored in the JSON file.

> **`self.ui`:** object of type `StreamlitUI` contains helper functions for building the parameter and file upload widgets.

> **`self.executor`:** object of type `CommandExecutor` can be used to run any command line tool alone or in parallel and includes a convenient method for running TOPP tools.

> **`self.logger`:** object of type `Logger` to write any output to a log file during workflow execution.

> **`self.file_manager`:** object of type `FileManager` to handle file types and creation of output directories.
"""
    )

    with st.expander("**Complete example for custom Workflow class**", expanded=False):
        st.code(getsource(Workflow))

    st.markdown(
        """
## File Upload

All input files for the workflow will be stored within the workflow directory in the subdirectory `input-files` within it's own subdirectory for the file type.

The subdirectory name will be determined by a **key** that is defined in the `self.ui.upload_widget` method. The uploaded files are available by the specific key for parameter input widgets and accessible while building the workflow.

Calling this method will create a complete file upload page with the following components:

- file uploader
- list of currently uploaded files with this key (or a warning if there are none)
- button to delete all files

Fallback files(s) can be specified, which will be used if the user doesn't upload any files. This can be useful for example for database files where a default is provided.
"""
    )

    st.code(getsource(Workflow.upload))

    st.info(
        "💡 Use the same **key** for parameter widgets, to select which of the uploaded files to use for analysis."
    )

    with st.expander("**Code documentation:**", expanded=True):
        st.help(StreamlitUI.upload_widget)

    st.markdown(
        """
## Parameter Input

The parameter page is already pre-defined as a form with buttons to **save parameters** and **load defaults** and a toggle to show TOPP tool parameters marked as advanced.

Generating parameter input widgets is done with the `self.ui.input` method for any parameter and the `self.ui.input_TOPP` method for TOPP tools.

**1. Choose `self.ui.input_widget` for any parameter not-related to a TOPP tool or `self.ui.select_input_file` for any input file:**

It takes the obligatory **key** parameter. The key is used to access the parameter value in the workflow parameters dictionary `self.params`. Default values do not need to be specified in a separate file. Instead they are determined from the widgets default value automatically. Widget types can be specified or automatically determined from **default** and **options** parameters. It's suggested to add a **help** text and other parameters for numerical input.

Make sure to match the **key** of the upload widget when calling `self.ui.input_TOPP`.

**2. Choose `self.ui.input_TOPP` to automatically generate complete input sections for a TOPP tool:**

It takes the obligatory **topp_tool_name** parameter and generates input widgets for each parameter present in the **ini** file (automatically created) except for input and output file parameters. For all input file parameters a widget needs to be created with `self.ui.select_input_file` with an appropriate **key**. For TOPP tool parameters only non-default values are stored.

**3. Choose `self.ui.input_python` to automatically generate complete input sections for a custom Python tool:**

Takes the obligatory **script_file** argument. The default location for the Python script files is in `src/python-tools` (in this case the `.py` file extension is optional in the **script_file** argument), however, any other path can be specified as well. Parameters need to be specified in the Python script in the **DEFAULTS** variable with the mandatory **key** and **value** parameters.
"""
    )

    with st.expander(
        "Options to use as dictionary keys for parameter definitions (see `src/python-tools/example.py` for an example)"
    ):
        st.markdown(
            """
**Mandatory** keys for each parameter
- *key:* a unique identifier
- *value:* the default value

**Optional** keys for each parameter
- *name:* the name of the parameter
- *hide:* don't show the parameter in the parameter section (e.g. for **input/output files**)
- *options:* a list of valid options for the parameter
- *min:* the minimum value for the parameter (int and float)
- *max:* the maximum value for the parameter (int and float)
- *step_size:* the step size for the parameter (int and float)
- *help:* a description of the parameter
- *widget_type:* the type of widget to use for the parameter (default: auto)
- *advanced:* whether or not the parameter is advanced (default: False)
"""
        )

    st.code(getsource(Workflow.configure))
    st.info(
        "💡 Access parameter widget values by their **key** in the `self.params` object, e.g. `self.params['mzML-files']` will give all selected mzML files."
    )

    with st.expander("**Code documentation**", expanded=True):
        st.help(StreamlitUI.input_widget)
        st.help(StreamlitUI.select_input_file)
        st.help(StreamlitUI.input_TOPP)
        st.help(StreamlitUI.input_python)
    st.markdown(
        """
## Building the Workflow

Building the workflow involves **calling all (TOPP) tools** using **`self.executor`** with **input and output files** based on the **`FileManager`** class. For TOPP tools non-input-output parameters are handled automatically. Parameters for other processes and workflow logic can be accessed via widget keys (set on the parameter page) in the **`self.params`** dictionary.

### FileManager

The `FileManager` class serves as an interface for unified input and output files with useful functionality specific to building workflows, such as **setting a (new) file type** and **subdirectory in the workflows result directory**.

Use the **`get_files`** method to get a list of all file paths as strings.

Optionally set the following parameters modify the files:

- **set_file_type** (str): set new file types and result subdirectory. 
- **set_results_dir** (str): set a new subdirectory in the workflows result directory.
- **collect** (bool): collect all files into a single list. Will return a list with a single entry, which is a list of all files. Useful to pass to tools which can handle multiple input files at once.
"""
    )

    st.code(
        """
# Get all file paths as strings from self.param entry.
mzML_files = self.file_manager.get_files(self.params["mzML-files])
# mzML_files = ['../workspaces-streamlit-template/default/topp-workflow/input-files/mzML-files/Control.mzML', '../workspaces-streamlit-template/default/topp-workflow/input-files/mzML-files/Treatment.mzML']

# Creating output files for a TOPP tool, setting a new file type and result subdirectory name.
feature_detection_out = self.file_manager.get_files(mzML_files, set_file_type="featureXML", set_results_dir="feature-detection")
# feature_detection_out = ['../workspaces-streamlit-template/default/topp-workflow/results/feature-detection/Control.featureXML', '../workspaces-streamlit-template/default/topp-workflow/results/feature-detection/Treatment.featureXML']

# Setting a name for the output directory automatically (useful if you never plan to access these files within the results page).
feature_detection_out = self.file_manager.get_files(mzML_files, set_file_type="featureXML", set_results_dir="auto")
# feature_detection_out = ['../workspaces-streamlit-template/default/topp-workflow/results/6DUd/Control.featureXML', '../workspaces-streamlit-template/default/topp-workflow/results/6DUd/Treatment.featureXML']

# Combining all mzML files to be passed to a TOPP tool in a single run. Using "collected" files as argument for self.file_manager.get_files will "un-collect" them.
mzML_files = self.file_manager.get_files(mzML_files, collect=True)
# mzML_files = [['../workspaces-streamlit-template/default/topp-workflow/input-files/mzML-files/Control.mzML', '../workspaces-streamlit-template/default/topp-workflow/input-files/mzML-files/Treatment.mzML']]
    """
    )

    with st.expander("**Code documentation**", expanded=True):
        st.help(FileManager.get_files)

    st.markdown(
        """
### Running commands

It is possible to execute any command line command using the **`self.executor`** object, either a single command or a list of commands in parallel. Furthermore a method to run TOPP tools is included.

**1. Single command**

The `self.executor.run_command` method takes a single command as input and optionally logs stdout and stderr to the workflow log (default True).
"""
    )

    st.code(
        """
self.executor.run_command(["command", "arg1", "arg2", ...])
"""
    )

    st.markdown(
        """
**2. Run multiple commands in parallel**

The `self.executor.run_multiple_commands` method takes a list of commands as inputs.

**3. Run TOPP tools**

The `self.executor.run_topp` method takes a TOPP tool name as input and a dictionary of input and output files as input. The **keys** need to match the actual input and output parameter names of the TOPP tool. The **values** should be of type `FileManager`. All other **non-default parameters (from input widgets)** will be passed to the TOPP tool automatically.

Depending on the number of input files, the TOPP tool will be run either in parallel or in a single run (using **`FileManager.collect`**).
"""
    )

    st.info(
        """💡 **Input and output file order**
        
In many tools, a single input file is processed to produce a single output file.
When dealing with lists of input or output files, the convention is that
files are paired based on their order. For instance, the n-th input file is
assumed to correspond to the n-th output file, maintaining a structured
relationship between input and output data.       
"""
    )
    st.code(
        """
# e.g. FeatureFinderMetabo takes single input files
in_files = self.file_manager.get_files(["sample1.mzML", "sample2.mzML"])
out_files = self.file_manager.get_files(in_files, set_file_type="featureXML", set_results_dir="feature-detection")

# Run FeatureFinderMetabo tool with input and output files in parallel for each pair of input/output files.
self.executor.run_topp("FeatureFinderMetabo", input_output={"in": in_files, "out": out_files})
# FeaturFinderMetabo -in sample1.mzML -out workspace-dir/results/feature-detection/sample1.featureXML
# FeaturFinderMetabo -in sample2.mzML -out workspace-dir/results/feature-detection/sample2.featureXML

# Run SiriusExport tool with mutliple input and output files.
out = self.file_manager.get_files("sirius.ms", set_results_dir="sirius-export")
self.executor.run_topp("SiriusExport", {"in": self.file_manager.get_files(in_files, collect=True),
                                        "in_featureinfo": self.file_manager.get_files(out_files, collect=True),
                                        "out": out_se})
# SiriusExport -in sample1.mzML sample2.mzML -in_featureinfo sample1.featureXML sample2.featureXML -out sirius.ms
        """
    )

    st.markdown(
        """
**4. Run custom Python scripts**

Sometimes it is useful to run custom Python scripts, for example for extra functionality which is not included in a TOPP tool.

`self.executor.run_python` works similar to `self.executor.run_topp`, but takes a single Python script as input instead of a TOPP tool name. The default location for the Python script files is in `src/python-tools` (in this case the `.py` file extension is optional in the **script_file** argument), however, any other path can be specified as well. Input and output file parameters need to be specified in the **input_output** dictionary.
"""
    )

    st.code(
        """
# e.g. example Python tool which modifies mzML files in place based on experimental design
self.ui.input_python(script_file="example", input_output={"in": in_mzML, "in_experimantal_design": FileManager(["path/to/experimantal-design.tsv"])})       
        """
    )

    st.markdown("**Example for a complete workflow:**")

    st.code(getsource(Workflow.execution))

    with st.expander("**Code documentation**", expanded=True):
        st.help(CommandExecutor.run_command)
        st.help(CommandExecutor.run_multiple_commands)
        st.help(CommandExecutor.run_topp)
        st.help(CommandExecutor.run_python)