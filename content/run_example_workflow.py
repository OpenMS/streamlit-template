import streamlit as st

from pathlib import Path

from src.common.common import page_setup, save_params
from src import mzmlfileworkflow
from rq import Queue
from redis import Redis
from src.workflow.mzmlfileworkflowstatus import monitor_mzml_workflow_job_status
from src.cpustats import monitor_cpu_ram_stats

# Page name "workflow" will show mzML file selector in sidebar
params = page_setup()

st.title("Workflow")
st.markdown(
    """
More complex workflow with mzML files and input form.
             
Changing widgets within the form will not trigger the execution of the script immediatly.
This is great for large parameter sections.
"""
)

with st.form("workflow-with-mzML-form"):
    st.markdown("**Parameters**")
    
    file_options = [f.stem for f in Path(st.session_state.workspace, "mzML-files").glob("*.mzML") if "external_files.txt" not in f.name]
    
    # Check if local files are available
    external_files = Path(Path(st.session_state.workspace, "mzML-files"), "external_files.txt")
    if external_files.exists():
        with open(external_files, "r") as f_handle:
            external_files = f_handle.readlines()
            external_files = [str(Path(f.strip()).with_suffix('')) for f in external_files]
            file_options += external_files

    st.multiselect(
        "**input mzML files**",
        file_options,
        params["example-workflow-selected-mzML-files"],
        key="example-workflow-selected-mzML-files",
    )

    c1, _, c3 = st.columns(3)
    if c1.form_submit_button(
        "Save Parameters", help="Save changes made to parameter section."
    ):
        params = save_params(params)
    run_workflow_button = c3.form_submit_button("Run Workflow", type="primary")

result_dir = Path(st.session_state["workspace"], "mzML-workflow-results")

# placeholder to display workflow status and run progress
mzml_workflow_status_placeholder = st.empty()
st.session_state['mzml_workflow_job_id'] = None
workflow_status = None

if run_workflow_button:
    params = save_params(params)
    if params["example-workflow-selected-mzML-files"]:
        queue = Queue('mzml_workflow_run', connection=Redis())
        job = queue.enqueue(mzmlfileworkflow.run_workflow, params, result_dir, st.session_state["workspace"])
        st.session_state['mzml_workflow_job_id'] = job.id
    else:
        st.warning("Select some mzML files.")

if st.session_state['mzml_workflow_job_id'] != None:
    # start showing the status when a job is found
    workflow_status = st.status("Workflow in progress ...", expanded=True)

results_section_placholder = st.empty()
with results_section_placholder:
    # don't show table if workflow is in running state as it'll be shown once the workflow ends
    if st.session_state['mzml_workflow_job_id'] == None:
        mzmlfileworkflow.result_section(result_dir)

st.write("## Hardware utilization")
cpu_ram_stats_placeholder = st.empty()

# in this continuous loop we measure CPU/RAM metrics and
# monitor the state of the active workflow job
while True:
    # monitor if active job exists
    if st.session_state['mzml_workflow_job_id'] != None:
        monitor_mzml_workflow_job_status(mzml_workflow_status_placeholder, workflow_status, results_section_placholder, result_dir)
    monitor_cpu_ram_stats(cpu_ram_stats_placeholder)
    