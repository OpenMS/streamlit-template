from redis import Redis
from rq import get_current_job, job
import time
from streamlit.delta_generator import DeltaGenerator
from typing import List
import streamlit as st

# retrieve logs for the progress of workflow job from redis
def get_mzml_workflow_progress_logs(job_id) -> List[bytes]:
    r = Redis()
    return r.lrange(f"mzml_workflow_progress_logs:{job_id}", 0, -1)

# log the progress of workflow job into redis
def log_mzml_workflow_progress(message):
    job = get_current_job()
    log_key = f"mzml_workflow_progress_logs:{job.id}"
    r = Redis()
    r.rpush(log_key, message)

# monitor and notify status for workflow job
def monitor_mzml_workflow_job_status(job: job.Job, streamlit_status_placeholder: DeltaGenerator):
    with streamlit_status_placeholder.container():
        with st.status("Workflow in progress...", expanded=True) as status:
            last_len = 0
            while not job.is_finished:
                logs = get_mzml_workflow_progress_logs(job.id)

                if len(logs) > last_len:
                    # Read from the last read log and update the status message
                    for log in logs[last_len:]:
                        status.text(log.decode('utf-8'))
                    last_len = len(logs)

                time.sleep(1)

            if job.is_finished:
                status.update(label="Workflow complete!", expanded=False, state='complete')
            else:
                status.update(label="Workflow stopped!", expanded=False, state='error')
