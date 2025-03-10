import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path
import json
import os
import time
import threading
import signal
import tornado.web
import tornado.ioloop
import pyopenms  # required import for Windows

# Keep settings at the very top
if "settings" not in st.session_state:
    with open("settings.json", "r") as f:
        st.session_state.settings = json.load(f)

# --- Global Session Counter ---
global_active_sessions = 0
last_heartbeat = 0   # Global heartbeat timestamp

def increment_active_sessions():
    global global_active_sessions
    global_active_sessions += 1
    print(f"Session connected, total active sessions: {global_active_sessions}")

def decrement_active_sessions():
    global global_active_sessions
    global_active_sessions -= 1
    print(f"Session disconnected, total active sessions: {global_active_sessions}")
    if global_active_sessions <= 0:
        shutdown()

def shutdown():
    print("🚨 No active users. Shutting down Streamlit server...")
    os.kill(os.getpid(), signal.SIGTERM)

# Register this session only once.
if "registered" not in st.session_state:
    st.session_state.registered = True
    increment_active_sessions()

# --- Tornado Endpoints ---

# This handler is called on browser unload (if it fires)
class CloseAppHandler(tornado.web.RequestHandler):
    def post(self):
        time.sleep(1)
        decrement_active_sessions()
        self.write("OK")

# This handler receives heartbeat pings
class HeartbeatHandler(tornado.web.RequestHandler):
    def post(self):
        global last_heartbeat
        last_heartbeat = time.time()
        self.write("OK")

def start_tornado_server():
    routes = [
        (r"/_closeapp", CloseAppHandler),
        (r"/heartbeat", HeartbeatHandler)
    ]
    app = tornado.web.Application(routes)
    app.listen(port=8501)  # Adjust if needed; matches Streamlit port.
    tornado.ioloop.IOLoop.current().start()

threading.Thread(target=start_tornado_server, daemon=True).start()

# Monitor for lost heartbeat and shutdown if no activity.
def heartbeat_monitor():
    global last_heartbeat
    # Initialize heartbeat time
    last_heartbeat = time.time()
    while True:
        time.sleep(5)
        # If no heartbeat received in 10 seconds and no sessions are active, shutdown
        if time.time() - last_heartbeat > 10 and global_active_sessions <= 0:
            shutdown()

threading.Thread(target=heartbeat_monitor, daemon=True).start()

# --- Client-side JavaScript injections ---
def insert_heartbeat_script():
    # Sends a heartbeat every 3 seconds.
    components.html(
        """
        <script>
        function sendHeartbeat() {
            fetch('/heartbeat', {method: 'POST'});
        }
        // Send an immediate heartbeat on load
        sendHeartbeat();
        // Then every 3 seconds
        setInterval(sendHeartbeat, 3000);
        </script>
        """,
        height=0,
    )

def insert_close_tab_script():
    # Fallback request on tab unload (may not always fire reliably)
    components.html(
        """
        <script>
        window.addEventListener('beforeunload', function(e) {
          navigator.sendBeacon('/_closeapp');
        });
        </script>
        """,
        height=0,
    )

if __name__ == '__main__':
    pages = {
        str(st.session_state.settings["app-name"]) : [
            st.Page(Path("content", "quickstart.py"), title="Quickstart", icon="👋"),
            st.Page(Path("content", "documentation.py"), title="Documentation", icon="📖"),
        ],
        "TOPP Workflow Framework": [
            st.Page(Path("content", "topp_workflow_file_upload.py"), title="File Upload", icon="📁"),
            st.Page(Path("content", "topp_workflow_parameter.py"), title="Configure", icon="⚙️"),
            st.Page(Path("content", "topp_workflow_execution.py"), title="Run", icon="🚀"),
            st.Page(Path("content", "topp_workflow_results.py"), title="Results", icon="📊"),
        ],
        "pyOpenMS Workflow" : [
            st.Page(Path("content", "file_upload.py"), title="File Upload", icon="📂"),
            st.Page(Path("content", "raw_data_viewer.py"), title="View MS data", icon="👀"),
            st.Page(Path("content", "run_example_workflow.py"), title="Run Workflow", icon="⚙️"),
            st.Page(Path("content", "download_section.py"), title="Download Results", icon="⬇️"),
        ],
        "Others Topics": [
            st.Page(Path("content", "simple_workflow.py"), title="Simple Workflow", icon="⚙️"),
            st.Page(Path("content", "run_subprocess.py"), title="Run Subprocess", icon="🖥️"),
        ]
    }

    pg = st.navigation(pages)
    pg.run()

    # Inject the heartbeat script first so the server sees regular pings.
    insert_heartbeat_script()
    # Also inject the close-tab script (as a fallback)
    insert_close_tab_script()