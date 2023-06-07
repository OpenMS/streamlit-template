# base image
FROM python:3.9

# create workdir
WORKDIR /app

# install conda
ENV PATH="/root/miniconda3/bin:${PATH}"
ARG PATH="/root/miniconda3/bin:${PATH}"
RUN apt-get update

RUN apt-get install -y wget && rm -rf /var/lib/apt/lists/*

RUN wget \
    https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
    && mkdir /root/.conda \
    && bash Miniconda3-latest-Linux-x86_64.sh -b \
    && rm -f Miniconda3-latest-Linux-x86_64.sh 
RUN conda --version

# copying everything over
COPY . .

# copy over and install packages.
COPY environment.yml ./environment.yml
RUN conda env create -f environment.yml
SHELL ["conda", "run", "-n", "condaenv", "/bin/bash", "-c"]

 #TODO add a default installation of OpenMS (e.g., 3.0) executables to docker file (e.g., from conda)
 #TODO add installation of OpenMS/Thirdparty tools to docker file
 #TODO add installation of mono to enable raw file conversion
 #TODO add cron job to docker file to automatically clean up data / delete data after a while

# expose port
EXPOSE 8501

ENTRYPOINT ["conda", "run", "--no-caputre-output", "-n" "streamlit-env", "streamlit", "run", "app.py"]

# build image with: docker build -t streamlitapp:latest .
# check if image was build: docker image ls
# run container: docker run -p 8501:8501 streamlitapp:latest
