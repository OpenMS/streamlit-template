from streamlit.web import cli
import sys

if __name__ == "__main__":
    cli._main_run_clExplicit(
        file="app.py", 
        command_line="streamlit run"
    )
