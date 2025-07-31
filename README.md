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

> ⚠️ Note: The local version offers limited functionality. Features that depend on OpenMS are only available in the Docker setup.


## 🐳 Run with Docker (Full Feature Set)

1. **Install Docker (Ubuntu)**

   Install Docker from the [official Docker installation guide](https://docs.docker.com/engine/install/)  
   
   <details>
   <summary>Click to expand</summary>
   
   ```bash
   # Remove older Docker versions (if any)
   for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove -y $pkg; done
   
   # Install Docker’s GPG key and repository
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   sudo chmod a+r /etc/apt/keyrings/docker.asc
   echo   "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu   $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" |   sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```
   
   </details>

2. **Test Docker**
   
   Verify that Docker is working..
   ```bash
   docker run hello-world
   ```
   When running this command, you should see a hello world message from Docker.

3. **Build & Start the App**

   From the project root directory:
   
   ```bash
   docker compose up -d --build
   ```
   This will launch the app with full functionality.

## Documentation

Documentation for **users** and **developers** is included as pages in [this template app](https://abi-services.cs.uni-tuebingen.de/streamlit-template/), indicated by the 📖 icon.

## Citation

Please cite:
Müller, T. D., Siraj, A., et al. OpenMS WebApps: Building User-Friendly Solutions for MS Analysis. Journal of Proteome Research (2025). [https://doi.org/10.1021/acs.jproteome.4c00872](https://doi.org/10.1021/acs.jproteome.4c00872)

## References

- Pfeuffer, J., Bielow, C., Wein, S. et al. OpenMS 3 enables reproducible analysis of large-scale mass spectrometry data. Nat Methods 21, 365–367 (2024). [https://doi.org/10.1038/s41592-024-02197-7](https://doi.org/10.1038/s41592-024-02197-7)

- Röst HL, Schmitt U, Aebersold R, Malmström L. pyOpenMS: a Python-based interface to the OpenMS mass-spectrometry algorithm library. Proteomics. 2014 Jan;14(1):74-7. [https://doi.org/10.1002/pmic.201300246](https://doi.org/10.1002/pmic.201300246). PMID: [24420968](https://pubmed.ncbi.nlm.nih.gov/24420968/).


