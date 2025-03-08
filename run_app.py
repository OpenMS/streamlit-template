import subprocess
import sys
from streamlit.logger import get_logger

# Initialize a logger for this module
logger = get_logger(__name__)

if __name__ == "__main__":
    try:
        # Construct the command to run the Streamlit app, including any additional command-line arguments
        cmd = ["streamlit", "run", "app.py"] + sys.argv[1:]
        
        # Log the constructed command at the debug level
        logger.debug(f"Running command: {' '.join(cmd)}")
        
        # Execute the command and check for errors
        subprocess.run(cmd, check=True)
        
    except subprocess.CalledProcessError as e:
        # Log an error message if the Streamlit command fails
        logger.error(f"Streamlit failed to run (error code {e.returncode})")
        sys.exit(1)
    except Exception as e:
        # Log any unexpected errors that occur during execution
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)