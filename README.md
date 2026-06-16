# OpenMS streamlit template 

[![Open Template!](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://abi-services.cs.uni-tuebingen.de/streamlit-template/)

This repository contains a template app for OpenMS workflows in a web application using the **streamlit** framework. It serves as a foundation for apps ranging from simple workflows with **pyOpenMS** to complex workflows utilizing **OpenMS TOPP tools** with parallel execution. It includes solutions for handling user data and parameters in workspaces as well as deployment with docker-compose.

## Features

- Workspaces for user data with unique shareable IDs
- Persistent parameters and input files within a workspace
- local and online mode
- Captcha control
- Packaged executables for Windows
- framework for workflows with OpenMS TOPP tools
- Deployment [with docker-compose](https://github.com/OpenMS/streamlit-deployment)

## 🔗 Try the Online Demo

Explore the hosted version here:  👉 [Live App](https://abi-services.cs.uni-tuebingen.de/streamlit-template/)

## 💻 Run Locally

To run the app locally:

1. **Clone the repository**
   ```bash
   git clone https://github.com/OpenMS/streamlit-template.git
   cd streamlit-template
   ```

2. **Install dependencies**
   
   Make sure you can run ```pip``` commands.
   
   Install all dependencies with:
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the app**
   ```bash
   streamlit run app.py
   ```

> ⚠️ Note: The local version offers limited functionality. Features that depend on OpenMS TOPP tools are only available out of the box in the Docker setup. For the local version [OpenMS Command Line Tools](https://openms.readthedocs.io/en/latest/about/installation.html) must be installed separately.


## 🐳 Build with Docker

This repository contains two Dockerfiles.

1. `Dockerfile`: This Dockerfile builds all dependencies for the app including Python packages and the OpenMS TOPP tools. Recommended for more complex workflows where you want to use the OpenMS TOPP tools for instance with the **TOPP Workflow Framework**.
2. `Dockerfile_simple`: This Dockerfile builds only the Python packages. Recommended for simple apps using pyOpenMS only.

1. **Install Docker**

   Install Docker from the [official Docker installation guide](https://docs.docker.com/engine/install/)  
   
   <details>
   <summary>Click to expand</summary>
   
   ```bash
   # Remove older Docker versions (if any)
   for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove -y $pkg; done
   ```
   
   </details>

2. **Test Docker**
   
   Verify that Docker is working.
   ```bash
   docker run hello-world
   ```
   When running this command, you should see a hello world message from Docker.
   
3. **Clone the repository**
   ```bash
   git clone https://github.com/OpenMS/streamlit-template.git
   cd streamlit-template
   ```
   
4. **Specify GitHub token (to download Windows executables).**
   
   Create a temporary `.env` file with your Github token.
   
   It should contain only one line:
   `GITHUB_TOKEN=<your-github-token>`

   ℹ️ **Note:** This step is not strictly required, but skipping it will remove the option to download executables from the WebApp.
   
3. **Build & Launch the App**

   To build and start the containers.
   From the project root directory:
   
   ```bash
   docker-compose up -d --build
   ```
     At the end, you should see this:
      ```
      [+] Running 2/2
       ✔ openms-streamlit-template            Built      
       ✔ Container openms-streamlit-template  Started  
      ```
      
      To make sure server started successfully, run `docker compose ps`. You should see `Up` status:
      ```
      CONTAINER ID   IMAGE                       COMMAND                  CREATED         STATUS                 PORTS                                           NAMES
      4abe0603e521   openms_streamlit_template   "/app/entrypoint.sh …"   7 minutes ago   Up 7 minutes           0.0.0.0:8501->8501/tcp, :::8501->8501/tcp       openms-streamlit-template
      ```
   
      To map the port to default streamlit port `8501` and launch.
      
      ```
      docker run -p 8505:8501 openms_streamlit_template
      ```

   ### Mount a local data directory

   To make a directory of MS files on the host available to the running app
   without uploading or copying them, bind-mount it into the container at
   the path configured by `local_data_dir` in `settings.json` (the Docker
   image defaults this to `/mounted-data`):

   ```
   docker run -p 8501:8501 \
     -v /path/on/host:/mounted-data:ro \
     openms_streamlit_template
   ```

   The upload widget auto-detects the mount: when the directory exists at
   runtime it shows an in-app tree browser; selected files are referenced
   in place via `external_files.txt` (no copy into the workspace volume),
   so the mount can safely be read-only. Omitting `-v` hides the browser
   and falls back to the standard upload UI. To use a different container
   path, change `local_data_dir` in `settings.json` before building.

## 🛰️ Run with Apptainer / Singularity (HPC)

Apptainer (formerly Singularity) is the dominant container runtime on HPC
clusters. CI publishes prebuilt SIFs to GHCR via ORAS, so you can pull a
ready-to-run image with no on-the-fly OCI→SIF conversion and run it as your
user — no root, no `--writable-tmpfs` required:

```bash
apptainer pull --name openms-streamlit-template.sif \
  oras://ghcr.io/openms/streamlit-template/sif:latest
apptainer run \
  --bind /path/to/data:/mounted-data:ro \
  --bind /path/to/workspaces:/workspaces-streamlit-template \
  openms-streamlit-template.sif
```

Available tags follow the same scheme as the Docker images: `latest`,
`main-full`, `main-simple`, `v*-full`, `v*-simple`, and per-commit SHAs.
If a tag hasn't been prebuilt yet (e.g. a PR branch), fall back to on-the-fly
conversion: `apptainer pull docker://ghcr.io/openms/streamlit-template:<tag>`.
Requires apptainer 1.1+ or singularity-ce 3.10+ for the `oras://` transport.

The entrypoint auto-detects the read-only root filesystem (set by apptainer's
default isolation) and switches its runtime state — Redis data directory,
nginx config, PID files — to `/tmp/openms-runtime-$$`, which is always
writable inside an apptainer container. The workspace cleanup cron job is
skipped in this mode; rerun `clean-up-workspaces.py` manually if needed.

## ⚖️ Legal pages (Impressum, Privacy Policy, Terms of Use)

Every page shows **Impressum**, **Privacy Policy** and **Terms of Use** links at
the bottom of the sidebar, and the GDPR consent banner links to the privacy
policy. By default these point to the centrally maintained official OpenMS pages
(`https://openms.de/impressum`, `/privacy`, `/terms`).

If you self-host a fork, override them in `settings.json` — an Impressum must
name the **actual operator**, not OpenMS:

```json
"legal_links": {
    "impressum": "https://your-domain.example/impressum",
    "privacy": "https://your-domain.example/privacy",
    "terms": "https://your-domain.example/terms"
}
```

Any link you omit falls back to its OpenMS default. The `privacy` URL is reused
for the consent banner's privacy-policy link, so consent and policy stay in sync.

## Documentation

Documentation for **users** and **developers** is included as pages in [this template app](https://abi-services.cs.uni-tuebingen.de/streamlit-template/), indicated by the 📖 icon.

## Citation

Please cite:
Müller, T. D., Siraj, A., et al. OpenMS WebApps: Building User-Friendly Solutions for MS Analysis. Journal of Proteome Research (2025). [https://doi.org/10.1021/acs.jproteome.4c00872](https://doi.org/10.1021/acs.jproteome.4c00872)

## References

- Pfeuffer, J., Bielow, C., Wein, S. et al. OpenMS 3 enables reproducible analysis of large-scale mass spectrometry data. Nat Methods 21, 365–367 (2024). [https://doi.org/10.1038/s41592-024-02197-7](https://doi.org/10.1038/s41592-024-02197-7)

- Röst HL, Schmitt U, Aebersold R, Malmström L. pyOpenMS: a Python-based interface to the OpenMS mass-spectrometry algorithm library. Proteomics. 2014 Jan;14(1):74-7. [https://doi.org/10.1002/pmic.201300246](https://doi.org/10.1002/pmic.201300246). PMID: [24420968](https://pubmed.ncbi.nlm.nih.gov/24420968/).


