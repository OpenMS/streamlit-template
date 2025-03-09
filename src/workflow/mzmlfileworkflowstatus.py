from redis import Redis
from rq import job, get_current_job, Queue
from streamlit.delta_generator import DeltaGenerator
from typing import List
import streamlit as st

# retrieve logs for the progress of workflow job from redis
def get_mzml_workflow_progress_logs(job_id) -> List[bytes]:
    r = Redis()
    return r.lrange(f"mzml_workflow_progress_logs:{job_id}", 0, -1)

# log the progress of workflow job into redis
# this runs inside queue worker
def log_mzml_workflow_progress(message):
    job = get_current_job()
    log_key = f"mzml_workflow_progress_logs:{job.id}"
    r = Redis()
    r.rpush(log_key, message)

# monitor and notify status for workflow job
def monitor_mzml_workflow_job_status(streamlit_status_placeholder: DeltaGenerator, workflow_status: DeltaGenerator):
    if st.session_state['mzml_workflow_job_id'] == None:
        return
    queue = Queue('mzml_workflow_run', connection=Redis())
    job = queue.fetch_job(st.session_state['mzml_workflow_job_id'])
    with streamlit_status_placeholder.container():
        last_len = st.session_state['mzml_workflow_last_read_log']
        if not job.is_finished:
            logs = get_mzml_workflow_progress_logs(job.id)

            if len(logs) > last_len:
                # Read from the last read log and update the status message
                workflow_status.text(logs[last_len].decode('utf-8'))
                st.session_state['mzml_workflow_last_read_log'] = len(logs)

        if job.is_finished:
            workflow_status.update(label="Complete!", expanded=False, state='complete')
            st.session_state['mzml_workflow_job_id'] = None
            st.session_state['mzml_workflow_last_read_log'] = 0
        elif job.is_stopped or job.is_canceled or job.is_canceled:
            workflow_status.update(label="Stopped!", expanded=False, state='error')
            st.session_state['mzml_workflow_job_id'] = None
            st.session_state['mzml_workflow_last_read_log'] = 0
