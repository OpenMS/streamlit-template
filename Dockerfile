# This Dockerfile creates a container with pyOpenMS
# It also adds a basic streamlit server that serves a pyOpenMS-based app.
# hints:
# build image with: docker build -f Dockerfile --no-cache -t flashviewer:latest --build-arg GITHUB_TOKEN=<your-github-token> .
# check if image was build: docker image ls
# run container: docker run -p 8501:8501 flashviewer:latest
# debug container after build (comment out ENTRYPOINT) and run container with interactive /bin/bash shell
# prune unused images/etc. to free disc space (e.g. might be needed on gitpod). Use with care.: docker system prune --all --force

FROM python:3.10-slim as stage1
ARG OPENMS_REPO=https://github.com/OpenMS/OpenMS.git
ARG OPENMS_BRANCH=develop
ARG PORT=8501
# GitHub token to download latest OpenMS executable for Windows from Github action artifact.
ARG GITHUB_TOKEN
# Streamlit app Gihub user name (to download artifact from).
ARG GITHUB_USER=OpenMS
# Streamlit app Gihub repository name (to download artifact from).
ARG GITHUB_REPO=streamlit-template

# Step 1: set up a sane build system
USER root

RUN apt-get -y update
# note: streamlit in docker needs libgtk2.0-dev (see https://yugdamor.medium.com/importerror-libgthread-2-0-so-0-cannot-open-shared-object-file-no-such-file-or-directory-895b94a7827b)
RUN apt-get install -y --no-install-recommends --no-install-suggests wget ca-certificates libgtk2.0-dev curl jq
RUN update-ca-certificates

#################################### install streamlit
# install packages
COPY requirements.txt requirements.txt
RUN python -m pip install --upgrade pip
RUN python -m pip install -r requirements.txt

# create workdir and copy over all streamlit related files/folders
WORKDIR /app
# note: specifying folder with slash as suffix and repeating the folder name seems important to preserve directory structure
COPY FLASHViewer.py /app/FLASHViewer.py 
COPY src/ /app/src
COPY assets/ /app/assets
COPY example-data/ /app/example-data
COPY pages/ /app/pages
COPY dist/ /app/dist

# Download latest OpenMS App executable for Windows from Github actions workflow.
RUN WORKFLOW_ID=$(curl -s "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/actions/workflows" | jq -r '.workflows[] | select(.name == "Build executable for Windows") | .id') \
    && SUCCESSFUL_RUNS=$(curl -s "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/actions/runs?workflow_id=$WORKFLOW_ID&status=success" | jq -r '.workflow_runs[0].id') \
    && ARTIFACT_ID=$(curl -s "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/actions/runs/$SUCCESSFUL_RUNS/artifacts" | jq -r '.artifacts[] | select(.name == "OpenMS-App") | .id') \
    && curl -LJO -H "Authorization: Bearer $GITHUB_TOKEN" "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/actions/artifacts/$ARTIFACT_ID/zip" -o /app/OpenMS-App

EXPOSE $PORT
ENTRYPOINT ["python", "-m", "streamlit", "run", "FLASHViewer.py"]
