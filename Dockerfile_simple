# This Dockerfile creates a container with pyOpenMS
# It also adds a basic streamlit server that serves a pyOpenMS-based app.
# hints:
# build image with: docker build -f Dockerfile_simple --no-cache -t streamlitapp:latest --build-arg GITHUB_TOKEN=<your-github-token> . 2>&1 | tee build.log
# check if image was build: docker image ls
# run container: docker run -p 8501:8501 streamlitapp:latest
# debug container after build (comment out ENTRYPOINT) and run container with interactive /bin/bash shell
# prune unused images/etc. to free disc space (e.g. might be needed on gitpod). Use with care.: docker system prune --all --force

FROM ubuntu:22.04 AS stage1
ARG OPENMS_REPO=https://github.com/OpenMS/OpenMS.git
ARG OPENMS_BRANCH=develop
ARG PORT=8501
# GitHub token to download latest OpenMS executable for Windows from Github action artifact.
ARG GITHUB_TOKEN
ENV GH_TOKEN=${GITHUB_TOKEN}
# Streamlit app Gihub user name (to download artifact from).
ARG GITHUB_USER=OpenMS
# Streamlit app Gihub repository name (to download artifact from).
ARG GITHUB_REPO=streamlit-template


# Step 1: set up a sane build system
USER root

RUN apt-get -y update
# note: streamlit in docker needs libgtk2.0-dev (see https://yugdamor.medium.com/importerror-libgthread-2-0-so-0-cannot-open-shared-object-file-no-such-file-or-directory-895b94a7827b)
RUN apt-get install -y --no-install-recommends --no-install-suggests wget ca-certificates libgtk2.0-dev curl jq cron
RUN update-ca-certificates

# Install Github CLI
RUN (type -p wget >/dev/null || (apt-get update && apt-get install wget -y)) \
	&& mkdir -p -m 755 /etc/apt/keyrings \
	&& wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
	&& chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
	&& echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
	&& apt-get update \
	&& apt-get install gh -y

# Download and install miniforge.
ENV PATH="/root/miniforge3/bin:${PATH}"
RUN wget -q \
    https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh \
    && bash Miniforge3-Linux-x86_64.sh -b \
    && rm -f Miniforge3-Linux-x86_64.sh
RUN mamba --version

# Activate and configure the mamba environment
RUN mamba update -n base -c conda-forge mamba && mamba info && mamba create -n streamlit-env python=3.10
# note: activation of mamba needs to go to bashrc because every RUN command spawns new bash
SHELL ["mamba", "run", "-n", "streamlit-env", "/bin/bash", "-c"]
RUN echo "source activate streamlit-env" > ~/.bashrc

#################################### install streamlit
# install packages
COPY requirements.txt requirements.txt
RUN mamba install pip
RUN python -m pip install --upgrade pip
RUN python -m pip install -r requirements.txt


# create workdir and copy over all streamlit related files/folders
WORKDIR /app
# note: specifying folder with slash as suffix and repeating the folder name seems important to preserve directory structure
WORKDIR /app
COPY assets/ /app/assets
COPY content/ /app/content
COPY docs/ /app/docs
COPY example-data/ /app/example-data
COPY gdpr_consent/ /app/gdpr_consent
COPY hooks/ /app/hooks
COPY src/ /app/src
COPY app.py /app/app.py
COPY settings.json /app/settings.json
COPY default-parameters.json /app/default-parameters.json

# For streamlit configuration
COPY .streamlit/config.toml /app/.streamlit/config.toml

COPY clean-up-workspaces.py /app/clean-up-workspaces.py

# add cron job to the crontab
RUN echo "0 3 * * * /root/miniforge3/envs/streamlit-env/bin/python /app/clean-up-workspaces.py >> /app/clean-up-workspaces.log 2>&1" | crontab -

# create entrypoint script to start cron service and launch streamlit app
RUN echo "#!/bin/bash" > /app/entrypoint.sh
RUN echo "service cron start" >> /app/entrypoint.sh
RUN echo "mamba run --no-capture-output -n streamlit-env streamlit run app.py" >> /app/entrypoint.sh
# make the script executable
RUN chmod +x /app/entrypoint.sh

# Patch Analytics
RUN mamba run -n streamlit-env python hooks/hook-analytics.py

# Set Online Deployment
RUN jq '.online_deployment = true' settings.json > tmp.json && mv tmp.json settings.json

# Download latest OpenMS App executable for Windows from Github actions workflow.
RUN if [ -n "$GH_TOKEN" ]; then \
        echo "GH_TOKEN is set, proceeding to download the release asset..."; \
        gh run download -R ${GITHUB_USER}/${GITHUB_REPO} $(gh run list -R ${GITHUB_USER}/${GITHUB_REPO} -b main -e push -s completed -w "Build executable for Windows" --json databaseId -q '.[0].databaseId') -n OpenMS-App --dir /app; \
    else \
        echo "GH_TOKEN is not set, skipping the release asset download."; \
    fi

# make sure that mamba environment is used
SHELL ["mamba", "run", "-n", "streamlit-env", "/bin/bash", "-c"]

EXPOSE $PORT
ENTRYPOINT ["/app/entrypoint.sh"]
