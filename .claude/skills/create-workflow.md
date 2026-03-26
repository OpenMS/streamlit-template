# Create a TOPP Workflow

Create a complete TOPP workflow: a WorkflowManager subclass and its 4 associated content pages.

## Instructions

1. **Ask the user** for:
   - Workflow name (e.g., "Metabolite Quantification")
   - TOPP tools to use in the pipeline (e.g., FeatureFinderMetabo, FeatureLinkerUnlabeledKD)
   - Input file type(s) (e.g., mzML, featureXML)
   - Any custom Python tools needed
   - What results to display

2. **Create the workflow class** at `src/<WorkflowName>.py`:

```python
import streamlit as st
from src.workflow.WorkflowManager import WorkflowManager
from pathlib import Path

class MyWorkflow(WorkflowManager):
    def __init__(self) -> None:
        super().__init__("My Workflow", st.session_state["workspace"])

    def upload(self) -> None:
        t = st.tabs(["MS data"])
        with t[0]:
            self.ui.upload_widget(
                key="mzML-files",
                name="MS data",
                file_types="mzML",
                fallback=[str(f) for f in Path("example-data", "mzML").glob("*.mzML")],
            )

    @st.fragment
    def configure(self) -> None:
        self.ui.select_input_file("mzML-files", multiple=True)
        t = st.tabs(["**Step 1**", "**Step 2**"])
        with t[0]:
            self.ui.input_TOPP("ToolName1")
        with t[1]:
            self.ui.input_TOPP("ToolName2")

    def execution(self) -> None:
        if not self.params["mzML-files"]:
            self.logger.log("ERROR: No input files selected.")
            return

        in_files = self.file_manager.get_files(self.params["mzML-files"])
        self.logger.log(f"Processing {len(in_files)} files...")

        # Step 1
        out_step1 = self.file_manager.get_files(in_files, "featureXML", "step1")
        self.executor.run_topp("ToolName1", input_output={"in": in_files, "out": out_step1})

        # Step 2
        in_step2 = self.file_manager.get_files(out_step1, collect=True)
        out_step2 = self.file_manager.get_files("result.consensusXML", set_results_dir="step2")
        self.executor.run_topp("ToolName2", input_output={"in": in_step2, "out": out_step2})

    @st.fragment
    def results(self) -> None:
        result_file = Path(self.workflow_dir, "results", "step2", "result.tsv")
        if result_file.exists():
            import pandas as pd
            df = pd.read_csv(result_file, sep="\t")
            st.dataframe(df)
        else:
            st.warning("No results found. Please run the workflow first.")
```

3. **Create 4 content pages** in `content/`. Each follows this minimal pattern:

```python
# content/<workflow_name>_file_upload.py
from src.common.common import page_setup
from src.<WorkflowName> import MyWorkflow
params = page_setup()
wf = MyWorkflow()
wf.show_file_upload_section()
```

The 4 pages call these methods respectively:
- `wf.show_file_upload_section()` — upload page
- `wf.show_parameter_section()` — configure page
- `wf.show_execution_section()` — run page
- `wf.show_results_section()` — results page

4. **Register all 4 pages** as a group in `app.py`:

```python
"My Workflow": [
    st.Page(Path("content", "my_workflow_file_upload.py"), title="File Upload", icon="📁"),
    st.Page(Path("content", "my_workflow_parameter.py"), title="Configure", icon="⚙️"),
    st.Page(Path("content", "my_workflow_execution.py"), title="Run", icon="🚀"),
    st.Page(Path("content", "my_workflow_results.py"), title="Results", icon="📊"),
],
```

5. **Add default parameters** to `default-parameters.json` if the workflow introduces new tracked widget keys.

## Key APIs

### File management
- `self.file_manager.get_files(input_files)` — resolve file paths in workspace
- `self.file_manager.get_files(in_files, "ext", "step-name")` — create output paths
- `self.file_manager.get_files(files, collect=True)` — collect multiple files into single list argument
- `self.file_manager.get_files("name.ext", set_results_dir="dir")` — single result file

### Execution
- `self.executor.run_topp("ToolName", input_output={"in": [...], "out": [...]})` — run a TOPP tool
- `self.executor.run_python("script_name", {"in": [...]})` — run a Python tool from `src/python-tools/`

### UI widgets
- `self.ui.upload_widget(key, name, file_types, fallback)` — file upload with example data fallback
- `self.ui.select_input_file(key, multiple)` — select from uploaded files
- `self.ui.input_TOPP("ToolName", custom_defaults={})` — auto-generated TOPP parameter UI
- `self.ui.input_python("script_name")` — auto-generated Python tool parameter UI
- `self.ui.input_widget(key, default, label)` — single custom widget

### Logging
- `self.logger.log("message")` — log progress during execution

## Reference Files

- Example workflow: `src/Workflow.py`
- Workflow base class: `src/workflow/WorkflowManager.py`
- UI widget library: `src/workflow/StreamlitUI.py`
- Example pages: `content/topp_workflow_file_upload.py`, `content/topp_workflow_parameter.py`, `content/topp_workflow_execution.py`, `content/topp_workflow_results.py`
- Command executor: `src/workflow/CommandExecutor.py`
- File manager: `src/workflow/FileManager.py`

## Real-World Examples

- **umetaflow** (OpenMS/umetaflow): multi-step metabolomics pipeline — feature detection, linking, annotation, statistics
- **quantms-web** (OpenMS/quantms-web): proteomics quantification pipeline with DDA-LFQ, DDA-ISO, DIA-LFQ modes

## Checklist

- [ ] Workflow class in `src/` subclassing `WorkflowManager`
- [ ] `__init__` calls `super().__init__("Name", st.session_state["workspace"])`
- [ ] `upload()`, `configure()`, `execution()`, `results()` implemented
- [ ] `@st.fragment` on `configure()` and `results()`
- [ ] 4 content pages created in `content/`
- [ ] All 4 pages registered as a group in `app.py`
- [ ] Default parameters added to `default-parameters.json` if needed
