# Makes `src` a regular package. As an implicit namespace package, Streamlit's
# file watcher dropped `src.workflow` from sys.modules while a page was still
# importing it on a fresh checkout (no __pycache__ yet), so the first visit to
# Documentation failed with KeyError: 'src.workflow'.
