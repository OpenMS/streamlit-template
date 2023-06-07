# base image
FROM python:3.9

# create workdir
WORKDIR /app

# install wget and cron
RUN apt-get update
RUN apt-get install -y wget cron && rm -rf /var/lib/apt/lists/*

# copying everything over
COPY . .

# install mamba (faster than conda)
ENV PATH="/root/mambaforge/bin:${PATH}"
RUN wget \
    https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-Linux-x86_64.sh \
    && bash Mambaforge-Linux-x86_64.sh -b \
    && rm -f Mambaforge-Linux-x86_64.sh
RUN mamba --version

# install packages
COPY environment.yml ./environment.yml

# creates the streamlit-env conda environment
RUN mamba env create -f environment.yml
# make sure that conda environment is used
SHELL ["conda", "run", "-n", "streamlit-env", "/bin/bash", "-c"]

# expose port
EXPOSE 8501

ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "streamlit-env", "streamlit", "run", "app.py"]

# hints:
# build image with: docker build --no-cache -t streamlitapp:latest . 2>&1 | tee build.log
# check if image was build: docker image ls
# run container: docker run -p 8501:8501 streamlitapp:latest
# debug container after build (comment out ENTRYPOINT) and run container with interactive /bin/bash shell
# prune build cache frees disc space (e.g. might be needed on gitpod): docker system prune --all --force
