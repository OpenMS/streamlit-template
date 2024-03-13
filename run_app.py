from streamlit.web import cli

if __name__ == "__main__":
    cli._main_run_clExplicit(
        file="app.py", command_line="streamlit run", args=["local"]
    )  # run in local mode
    # we will create this function inside our streamlit framework
