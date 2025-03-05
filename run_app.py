import argparse
import json
import subprocess

# Default upload size (MB) if settings.json is missing/invalid
DEFAULT_MAX_SIZE = 200

def get_upload_limit():
    """Read max upload size from settings.json or use default."""
    try:
        with open("settings.json") as f:
            return json.load(f).get("maximum_file_upload_size", DEFAULT_MAX_SIZE)
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_MAX_SIZE

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-upload', type=int, help='Override upload size (MB)')
    args, unknown = parser.parse_known_args()
    
    # Priority: Command-line > settings.json > default
    size = args.max_upload or get_upload_limit()
    
    # Run Streamlit with the configured upload size
    subprocess.run([
        "streamlit", "run", "app.py",
        "--server.maxUploadSize", str(size)
    ] + unknown)  # Pass through additional arguments