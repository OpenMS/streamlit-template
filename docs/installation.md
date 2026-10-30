# Installation

## Windows

The app is available as a Windows installer (`<APP_NAME>-Setup.exe`) that includes all dependencies. It installs per user and needs no admin rights.

Download it from the latest [release](https://github.com/OpenMS/streamlit-template/releases), or build it with the [GitHub action](https://github.com/OpenMS/streamlit-template/actions/workflows/build-desktop-app.yaml): select the latest successful run and download the `OpenMS-App-Electron` artifact while signed in to GitHub.

## macOS (Apple Silicon)

`<APP_NAME>-macOS-arm64.dmg` holds the app for Macs with Apple Silicon (M1 and later); Intel Macs are not supported. Open the dmg and drag the app to Applications. Builds made without the OpenMS signing certificate (for example from a fork) are unsigned, and macOS refuses to open them; run `xattr -dr com.apple.quarantine /Applications/<APP_NAME>.app` once to allow it.

## Linux (x86_64)

Two packages contain the same app; both need glibc 2.35 or newer (Ubuntu 22.04, Debian 12, Fedora 36 or newer):

- `<APP_NAME>-Linux-x86_64.AppImage` runs without installation: `chmod +x` it and start it. It needs `libfuse2` (`sudo apt install libfuse2`, on Ubuntu 24.04 `libfuse2t64`).
- `<APP_NAME>-Linux-amd64.deb` installs to `/opt/<APP_NAME>` with a menu entry: `sudo apt install ./<APP_NAME>-Linux-amd64.deb`.

Both are built by the [GitHub action](https://github.com/OpenMS/streamlit-template/actions/workflows/build-desktop-app.yaml) and attached to each release.

## Python

Clone the [streamlit-template repository](https://github.com/OpenMS/streamlit-template). It includes files to install dependencies via pip or conda.

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

> ⚠️ Note: The local version offers limited functionality. Features that depend on OpenMS are only available in the Docker setup.


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
