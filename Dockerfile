# This Dockerfile builds OpenMS, the TOPP tools, pyOpenMS and thidparty tools.
# It also adds a basic streamlit server that serves a pyOpenMS-based app.
# hints:
# build image and give it a name (here: streamlitapp) with: docker build --no-cache -t streamlitapp:latest --build-arg GITHUB_TOKEN=<your-github-token> . 2>&1 | tee build.log
# check if image was build: docker image ls
# run container: docker run -p 8501:8501 streamlitappsimple:latest
# debug container after build (comment out ENTRYPOINT) and run container with interactive /bin/bash shell
# prune unused images/etc. to free disc space (e.g. might be needed on gitpod). Use with care.: docker system prune --all --force

FROM ubuntu:22.04 AS setup-build-system
ARG OPENMS_REPO=https://github.com/OpenMS/OpenMS.git
ARG OPENMS_BRANCH=release/3.2.0
ARG PORT=8501
# GitHub token to download latest OpenMS executable for Windows from Github action artifact.
ARG GITHUB_TOKEN
ENV GH_TOKEN=${GITHUB_TOKEN}
# Streamlit app Gihub user name (to download artifact from).
ARG GITHUB_USER=OpenMS
# Streamlit app Gihub repository name (to download artifact from).
ARG GITHUB_REPO=streamlit-template

USER root

# Install required Ubuntu packages.
RUN apt-get -y update
RUN apt-get install -y --no-install-recommends --no-install-suggests g++ autoconf automake patch libtool make git gpg wget ca-certificates curl jq libgtk2.0-dev openjdk-8-jdk cron
RUN update-ca-certificates
RUN apt-get install -y --no-install-recommends --no-install-suggests libsvm-dev libeigen3-dev coinor-libcbc-dev libglpk-dev libzip-dev zlib1g-dev libxerces-c-dev libbz2-dev libomp-dev libhdf5-dev
RUN apt-get install -y --no-install-recommends --no-install-suggests libboost-date-time1.74-dev \
                                                                     libboost-iostreams1.74-dev \
                                                                     libboost-regex1.74-dev \
                                                                     libboost-math1.74-dev \
                                                                     libboost-random1.74-dev
RUN apt-get install -y --no-install-recommends --no-install-suggests qtbase5-dev libqt5svg5-dev libqt5opengl5-dev

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

# Setup mamba environment.
COPY environment.yml ./environment.yml
RUN mamba env create -f environment.yml
RUN echo "mamba activate streamlit-env" >> ~/.bashrc
SHELL ["/bin/bash", "--rcfile", "~/.bashrc"]
SHELL ["mamba", "run", "-n", "streamlit-env", "/bin/bash", "-c"]

# Install up-to-date cmake via mamba and packages for pyOpenMS build.
RUN mamba install cmake
RUN pip install --upgrade pip && python -m pip install -U setuptools nose Cython autowrap pandas numpy pytest

# Clone OpenMS branch and the associcated contrib+thirdparties+pyOpenMS-doc submodules.
RUN git clone --recursive --depth=1 -b ${OPENMS_BRANCH} --single-branch ${OPENMS_REPO} && cd /OpenMS

# Pull Linux compatible third-party dependencies and store them in directory thirdparty.
WORKDIR /OpenMS
RUN mkdir /thirdparty && \
    git submodule update --init THIRDPARTY && \
    cp -r THIRDPARTY/All/* /thirdparty && \
    cp -r THIRDPARTY/Linux/64bit/* /thirdparty && \
    chmod -R +x /thirdparty
ENV PATH="/thirdparty/LuciPHOr2:/thirdparty/MSGFPlus:/thirdparty/Sirius:/thirdparty/ThermoRawFileParser:/thirdparty/Comet:/thirdparty/Fido:/thirdparty/MaRaCluster:/thirdparty/MyriMatch:/thirdparty/OMSSA:/thirdparty/Percolator:/thirdparty/SpectraST:/thirdparty/XTandem:/thirdparty/crux:${PATH}"

# Build OpenMS and pyOpenMS.
FROM setup-build-system AS compile-openms
WORKDIR /

# Set up build directory.
RUN mkdir /openms-build
WORKDIR /openms-build

# Configure.
RUN /bin/bash -c "cmake -DCMAKE_BUILD_TYPE='Release' -DCMAKE_PREFIX_PATH='/OpenMS/contrib-build/;/usr/;/usr/local' -DHAS_XSERVER=OFF -DBOOST_USE_STATIC=OFF -DPYOPENMS=ON ../OpenMS -DPY_MEMLEAK_DISABLE=On"

# Build TOPP tools and clean up.
RUN make -j4 TOPP
RUN rm -rf src doc CMakeFiles

# Build pyOpenMS wheels and install via pip.
RUN make -j4 pyopenms
WORKDIR /openms-build/pyOpenMS
RUN pip install dist/*.whl


WORKDIR /
RUN mkdir openms

# Copy TOPP tools bin directory, add to PATH.
RUN cp -r openms-build/bin /openms/bin
ENV PATH="/openms/bin/:${PATH}"

# Copy TOPP tools bin directory, add to PATH.
RUN cp -r openms-build/lib /openms/lib
ENV LD_LIBRARY_PATH="/openms/lib/:${LD_LIBRARY_PATH}"

# Copy share folder, add to PATH, remove source directory.
RUN cp -r OpenMS/share/OpenMS /openms/share
RUN rm -rf OpenMS
ENV OPENMS_DATA_PATH="/openms/share/"

# Remove build directory.
RUN rm -rf openms-build

# Prepare and run streamlit app.
FROM compile-openms AS run-app
# Create workdir and copy over all streamlit related files/folders.

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

# Run app as container entrypoint.
EXPOSE $PORT
ENTRYPOINT ["/app/entrypoint.sh"]
