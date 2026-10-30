# User Guide

Welcome to the OpenMS Streamlit Web Application! This guide will help you understand how to use our tools effectively.

## Advantages of OpenMS Web Apps

OpenMS web applications provide a user-friendly interface for accessing the powerful features of OpenMS. Here are a few advantages:
- **Accessibility**: Access powerful OpenMS algorithms and TOPP tools from any device with a web browser.
- **Ease of Use**: Simplified user interface makes it easy for both beginners and experts to perform complex analyses.
- **No Installation Required**: Use the tools without the need to install OpenMS locally, saving time and system resources.

## Workspaces

In the OpenMS web application, workspaces are designed to keep your analysis organized:
- **Workspace Specific Parameters and Files**: Each workspace stores parameters and files (uploaded input files and results from workflows).
- **Persistence**: Your workspaces and parameters are saved, so you can return to your analysis anytime and pick up where you left off. Simply bookmark the page!


### File Uploads
- **Online Mode**: You can upload only one file at a time. This helps manage server load and optimizes performance.

- **Local Mode**: Multiple file uploads are supported, giving you flexibility when working with large datasets. Additionally, the file size upload limit can be adjusted in the following ways:
  1. **Using `.streamlit/config.toml`**:
     - You can modify the `.streamlit/config.toml` file and set the `maxUploadSize` parameter to your desired value. By default, this is set to 200MB.
     - Example:
       ```toml
       [server]
       maxUploadSize = 500  # Set the upload limit to 500MB
       ```
  2. **Using CLI Command**:
     - You can customize the file size upload limit directly when running the application using the `--server.maxUploadSize` argument.
     - Example:
       ```bash
       python run_app.py --server.maxUploadSize 500
       ```
     - This sets the upload limit to 500MB for the current session.
     
- **Import from a link**: below the uploads of a workflow, paste a link instead of uploading. This is the way in for data that is too large for the browser upload or already sits in the cloud. Accepted links:
  - a file over HTTP(S), including presigned S3 links and Swift TempURLs to private objects;
  - a tar, tar.gz or zip archive (e.g. `https://a3s.fi/swift/v1/<bucket>/<name>.tar` on CSC Allas);
  - a public S3 or Swift folder (a link ending in `/`);
  - a Zenodo record or Figshare article (page link or DOI);
  - a OneDrive or SharePoint link shared with "Anyone with the link": files and folders from personal OneDrive, single files from SharePoint / OneDrive for Business (their folders can only be read with a sign-in).

  **Look up** lists the files; when the server allows it, the files inside an archive are listed too, and only the ones you select are downloaded. Each file is matched to the upload that takes its type (a Bruker `.d` folder as a whole), and you can change that in the table. The import runs in the background: you can leave the page, and a cancelled or interrupted import continues where it stopped when you start it again. Archives the server cannot send in parts are downloaded whole, unpacked, and their files sorted by type.

  Operators configure it in `settings.json` under `data_import`: `enabled`, `max_download_gb_online` (largest import on a public server, default 50 GB), `allowed_hosts` (if set, only links to these hosts and their subdomains) and `parallel_downloads` (default 4). On a public server, links to private or internal network addresses are refused.

- **Workspace Access**:
  - In online mode, workspaces are stored temporarily and will be cleared after seven days of inactivity.
  - In local mode, workspaces are saved on your local machine, allowing for persistent storage. Workspace directory can be specified in the `settings.json`. Defaults to `..` (parent directory).

## Downloading Results

You can download the results of your analyses, including data, figures and tables, directly from the application:
- **Figures**: Click the camera icon button, appearing while hovering on the top right corner of the figure. Set the desired image format in the settings panel in the side bar.
- **Tables**: Use the download button to save tables in *csv* format, appearing while hovering on the top right corner of the table.
- **Data**: Use the download section in the sidebar to download the raw results of your analysis.

### Keeping several runs

Workflows that keep their runs store every analysis you start as its own result set, so changing a parameter and running again does not overwrite the earlier results:
- **Run page**: give the run a name before you start it (optional; runs are numbered otherwise).
- **Results pages**: the *Run* picker at the top chooses which run is shown. The choice applies to all results pages.
- **Download page**: lists every run with its start time and status. 👁️ shows it on the results pages, ✏️ renames it, 📦 packs its results, parameters and logs into a ZIP to download, 🗑️ deletes it.

## Getting Started

To get started:
1. Select or create a new workspace.
2. Upload your data file.
3. Set the necessary parameters for your analysis.
4. Run the analysis.
5. View and download your results.

For more detailed information on each step, refer to the specific sections of this guide.

## Parameter Presets

Parameter presets allow you to quickly apply optimized parameter configurations for common analysis scenarios. When available, preset buttons appear on the parameter configuration page.

### Using Presets

1. Navigate to the parameter configuration page
2. Look for the **Parameter Presets** section below the "Show advanced parameters" toggle
3. Hover over a preset button to see its description
4. Click a preset to apply its optimized parameters
5. A confirmation message will appear when the preset is applied

### What Presets Do

- Presets override specific tool parameters with pre-configured values
- Only the parameters defined in the preset are changed; other parameters remain at their current values
- You can still modify individual parameters after applying a preset
- Use **Load default parameters** to reset all parameters to their original defaults

### Your Own Presets

Under **Your Presets** you can save the current settings and reuse them later:

1. Set the parameters the way you want them
2. Open **💾 Save or delete a preset**, enter a name (and optionally a description) and click **Save current settings**
3. Your preset appears as a button next to the built-in ones; click it to restore those settings

A saved preset holds every setting on this page except the selected input files and the number of threads, and applying it restores all of them. Presets are saved in the workspace, so they stay available in later sessions of the same workspace.

Below the buttons, a line tells you which preset the current settings come from, or that you changed settings since applying it.