# Installation

## Windows

The app is available as pre-packaged Windows executable, including all dependencies.

The Windows executable is built by a GitHub action and can be downloaded [here](https://github.com/OpenMS/streamlit-template/actions/workflows/build-windows-executable-app.yaml). Select the latest successful run and download the zip file from the artifacts section, while signed in to GitHub.

> ℹ️ A GitHub account is required to download artifacts.

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
  Make sure you can run `pip` commands.
  Install all dependencies with:
  ```bash
  pip install -r requirements.txt

  ```
3. **Launch the app**
  ```bash
  streamlit run app.py

  ```

> ⚠️ Note: The local version offers limited functionality. Features that depend on OpenMS are only available in the Docker setup.

## 🐳 Build with Docker

This repository contains two Dockerfiles.

1. `Dockerfile`: This Dockerfile builds all dependencies for the app including Python packages and the OpenMS TOPP tools. Recommended for more complex workflows where you want to use the OpenMS TOPP tools for instance with the **TOPP Workflow Framework**.
2. `Dockerfile_simple`: This Dockerfile builds only the Python packages. Recommended for simple apps using pyOpenMS only.
3. **Install Docker**
  Install Docker from the [official Docker installation guide](https://docs.docker.com/engine/install/)
   <details> <summary>Click to expand</summary> 
  ```bash
  # Remove older Docker versions (if any)
  for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove -y $pkg; done

  ```
   </details>
4. **Test Docker**
  Verify that Docker is working.
  ```bash
  docker run hello-world

  ```
  When running this command, you should see a hello world message from Docker.
5. **Clone the repository**
  ```bash
  git clone https://github.com/OpenMS/streamlit-template.git
  cd streamlit-template

  ```
6. **Specify GitHub token (to download Windows executables).**
  Create a temporary `.env` file with your Github token.
  It should contain only one line: `GITHUB_TOKEN=<your-github-token>`
  ℹ️ **Note:** This step is not strictly required, but skipping it will remove the option to download executables from the WebApp.
7. **Build & Launch the App**
  To build and start the containers. From the project root directory:
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

