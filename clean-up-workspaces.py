#!/usr/bin/env python
from pathlib import Path
import os
import time
import shutil
from datetime import datetime

# Define the workspaces directory
workspaces_directory = Path("/workspaces-streamlit-template")

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


# Print separator
print(100 * "-")
