from redis import Redis
from rq import get_current_job, Queue
from streamlit.delta_generator import DeltaGenerator
from streamlit.elements.lib.mutable_status_container import StatusContainer
import streamlit as st
from typing import Union

# retrieve last written log for the progress of workflow job from redis
# delete the message from the cache
def read_mzml_workflow_progress_log(job_id) -> str:
    r = Redis()
    log_key = f"mzml_workflow_progress_log_{job_id}"
    log = r.get(log_key)
    r.set(log_key, "")
    return log

# log the progress of workflow job into redis
# this runs inside queue worker
def log_mzml_workflow_progress(log):
    job = get_current_job()
    r = Redis()
    log_key = f"mzml_workflow_progress_log_{job.id}"
    r.set(log_key, log)

# retrieve last written status for the workflow job from redis
# delete the message from the cache
def read_mzml_workflow_status_log(job_id) -> str:
    r = Redis()
    log_key = f"mzml_workflow_status_log_{job_id}"
    log = r.get(log_key)
    r.set(log_key, "")
    return log

# log the status of workflow job into redis
# this runs inside queue worker
def log_mzml_workflow_status(log):
    job = get_current_job()
    r = Redis()
    log_key = f"mzml_workflow_status_log_{job.id}"
    r.set(log_key, log)

# monitor and notify status for workflow job
def monitor_mzml_workflow_job_status(streamlit_status_placeholder: DeltaGenerator, workflow_status: "StatusContainer"):
    if st.session_state['mzml_workflow_job_id'] == None:
        return
    queue = Queue('mzml_workflow_run', connection=Redis())
    job = queue.fetch_job(st.session_state['mzml_workflow_job_id'])
    with streamlit_status_placeholder.container():
        if not job.is_finished:
            log = read_mzml_workflow_progress_log(job.id)
            if log != None and len(log.decode('utf-8')):
                workflow_status.text(log.decode('utf-8'))

            status_log = read_mzml_workflow_status_log(job.id)
            if status_log != None and len(status_log.decode('utf-8')):
                workflow_status.update(label=status_log.decode('utf-8'))

        if job.is_finished:
            workflow_status.update(label="Complete!", expanded=False, state='complete')
            st.session_state['mzml_workflow_job_id'] = None
            st.session_state['mzml_workflow_last_read_log'] = 0
        elif job.is_stopped or job.is_canceled or job.is_canceled:
            workflow_status.update(label="Stopped!", expanded=False, state='error')
            st.session_state['mzml_workflow_job_id'] = None
            st.session_state['mzml_workflow_last_read_log'] = 0
