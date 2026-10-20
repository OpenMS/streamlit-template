"""
Local backend of the Svelte web app.

The Svelte frontend (``frontend/``) talks to this FastAPI server over
``/api``. Both run on the user's machine: the server binds to 127.0.0.1,
drives the same TOPP tools and pyOpenMS code as the Streamlit app, and reads
and writes the same workspace layout, so a workspace opened in one app can be
opened in the other.
"""
