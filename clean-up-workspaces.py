#!/usr/bin/env python
from pathlib import Path
import os
import json
import time
import shutil
from datetime import datetime

# Define the workspaces directory
workspaces_directory = Path(os.environ.get("WORKSPACES_DIR", "/workspaces-streamlit-template"))

# Get the current time in seconds
current_time = time.time()

# Define the time threshold (7 days ago) 86400 seconds in a day
threshold = current_time - (86400 * 7)

# Print current time
print(
    f"Current Time: {datetime.utcfromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
)

# Collect remaining dirctories to print out later
remaining_directories = []
# Iterate through directories in workspaces_directory
for directory in workspaces_directory.iterdir():
    # Skip hidden top-level directories (e.g. .demos/ holds seeded demo workspaces)
    if directory.name.startswith("."):
        continue
    # Check if it's a directory
    if directory.is_dir():
        # Get the directory's modification time
        modification_time = os.path.getmtime(directory)

        # Check if the modification time is less than the threshold
        if modification_time < threshold:
            # Calculate the time difference in seconds
            time_difference = current_time - modification_time

            # Print the directory name and the time difference in minutes
            print(
                f"Deleting directory: {directory.name}, Last Modified: {time_difference / 86400:.1f} days ago"
            )

            # Remove workspace
            shutil.rmtree(directory)
        else:
            remaining_directories.append(directory)

# Print info on remaining directories
if remaining_directories:
    print(f"\nRemaining directories in {workspaces_directory.name}:")
    for directory in remaining_directories:
        print(
            f"{directory.name}, Last Modified: {(current_time - os.path.getmtime(directory)) / 60:.2f} minutes ago"
        )
else:
    print(f"\n{workspaces_directory.name} is empty.")


# Workspace sync state lives in dot-directories, which the loop above skips:
# drop expired sync tokens, and partial uploads untouched for two days.
sync_tokens = workspaces_directory / ".sync-tokens"
if sync_tokens.is_dir():
    for entry in sync_tokens.glob("*.json"):
        try:
            expired = json.loads(entry.read_text()).get("expires", 0) < current_time
        except (OSError, ValueError):
            expired = True
        if expired:
            entry.unlink(missing_ok=True)
sync_uploads = workspaces_directory / ".sync-uploads"
if sync_uploads.is_dir():
    # An upload is <id>.json, <id>.part and <id>.lock, removed together. Its
    # age is that of its newest file (the .part grows while data arrives), and
    # one a request is writing holds the lock, so it is left alone.
    for upload_id in sorted({p.name.split(".")[0] for p in sync_uploads.iterdir()}):
        files = [sync_uploads / f"{upload_id}{ext}" for ext in (".json", ".part", ".lock")]
        ages = [os.path.getmtime(f) for f in files if f.exists()]
        if not ages or max(ages) >= current_time - 86400 * 2:
            continue
        lock = None
        try:
            import fcntl
            lock = os.open(files[2], os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            pass
        except OSError:
            if lock is not None:
                os.close(lock)
            continue        # still being written, or the lock cannot be taken
        print(f"Deleting stale partial upload: {upload_id}")
        for f in files:
            f.unlink(missing_ok=True)
        if lock is not None:
            os.close(lock)

# Print separator
print(100 * "-")
