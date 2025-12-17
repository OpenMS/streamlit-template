# This Dockerfile builds OpenMS, the TOPP tools, pyOpenMS and thidparty tools.
# It also adds a basic streamlit server that serves a pyOpenMS-based app.
# hints:
# build image and give it a name (here: streamlitapp) with: docker build --no-cache -t streamlitapp:latest --build-arg GITHUB_TOKEN=<your-github-token> . 2>&1 | tee build.log
# To install pyOpenMS from conda instead of building from source: docker build --no-cache -t streamlitapp:latest --build-arg BUILD_PYOPENMS=OFF --build-arg GITHUB_TOKEN=<your-github-token> . 2>&1 | tee build.log
# check if image was build: docker image ls
# run container: docker run -p 8501:8501 streamlitappsimple:latest
# debug container after build (comment out ENTRYPOINT) and run container with interactive /bin/bash shell
# prune unused images/etc. to free disc space (e.g. might be needed on gitpod). Use with care.: docker system prune --all --force

FROM ubuntu:22.04 AS setup-build-system
ARG OPENMS_REPO=https://github.com/OpenMS/OpenMS.git
ARG OPENMS_BRANCH=release/3.4.1
ARG PORT=8501
# Control whether to build pyOpenMS from source (ON) or install from conda (OFF). Default: ON
ARG BUILD_PYOPENMS=ON
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
RUN apt-get install -y --no-install-recommends --no-install-suggests qt6-base-dev libqt6svg6-dev libqt6opengl6-dev libqt6openglwidgets6 libgl-dev

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
RUN mamba create -n streamlit-env python=3.10
RUN echo "mamba activate streamlit-env" >> ~/.bashrc
SHELL ["/bin/bash", "--rcfile", "~/.bashrc"]
SHELL ["mamba", "run", "-n", "streamlit-env", "/bin/bash", "-c"]

# Install up-to-date cmake via mamba and packages for pyOpenMS build (if building from source).
RUN mamba install cmake
ARG BUILD_PYOPENMS
RUN if [ "$BUILD_PYOPENMS" = "ON" ]; then \
        pip install --upgrade pip && python -m pip install -U setuptools nose 'cython<3.1' 'autowrap<0.23' pandas numpy pytest; \
    fi

# Clone OpenMS branch and the associcated contrib+thirdparties+pyOpenMS-doc submodules.
RUN if [ "$BUILD_PYOPENMS" = "ON" ]; then \
        git clone --recursive --depth=1 -b ${OPENMS_BRANCH} --single-branch ${OPENMS_REPO} && cd /OpenMS; \
    fi

# Pull Linux compatible third-party dependencies and store them in directory thirdparty.
WORKDIR /OpenMS
ARG BUILD_PYOPENMS
RUN if [ "$BUILD_PYOPENMS" = "ON" ]; then \
        mkdir /thirdparty && \
        git submodule update --init THIRDPARTY && \
        cp -r THIRDPARTY/All/* /thirdparty && \
        cp -r THIRDPARTY/Linux/x86_64/* /thirdparty && \
        chmod -R +x /thirdparty; \
    fi
ENV PATH="/thirdparty/LuciPHOr2:/thirdparty/MSGFPlus:/thirdparty/Sirius:/thirdparty/ThermoRawFileParser:/thirdparty/Comet:/thirdparty/Fido:/thirdparty/MaRaCluster:/thirdparty/MyriMatch:/thirdparty/OMSSA:/thirdparty/Percolator:/thirdparty/SpectraST:/thirdparty/XTandem:/thirdparty/crux:${PATH}"

# Build OpenMS and pyOpenMS.
FROM setup-build-system AS compile-openms
WORKDIR /

ARG BUILD_PYOPENMS
# Set up build directory and build pyOpenMS from source if enabled.
RUN if [ "$BUILD_PYOPENMS" = "ON" ]; then \
        mkdir /openms-build && \
        cd /openms-build && \
        /bin/bash -c "cmake -DCMAKE_BUILD_TYPE='Release' -DCMAKE_PREFIX_PATH='/OpenMS/contrib-build/;/usr/;/usr/local' -DHAS_XSERVER=OFF -DBOOST_USE_STATIC=OFF -DPYOPENMS=ON ../OpenMS -DPY_MEMLEAK_DISABLE=On" && \
        make -j4 TOPP && \
        rm -rf src doc CMakeFiles && \
        make -j4 pyopenms && \
        cd /openms-build/pyOpenMS && \
        pip install dist/*.whl; \
    fi

# Install dependencies.
COPY requirements.txt ./requirements.txt 
RUN if [ "$BUILD_PYOPENMS" = "ON" ]; then \
        # If building from source, exclude pyopenms from requirements.txt \
        grep -Ev '^pyopenms([=<>!~].*)?$' requirements.txt > requirements_cleaned.txt && mv requirements_cleaned.txt requirements.txt; \
    fi
RUN pip install -r requirements.txt

WORKDIR /
RUN mkdir openms

ARG BUILD_PYOPENMS
# Copy TOPP tools bin directory, add to PATH (only if built from source).
RUN if [ "$BUILD_PYOPENMS" = "ON" ]; then \
        cp -r openms-build/bin /openms/bin; \
    fi
ENV PATH="/openms/bin/:${PATH}"

# Copy TOPP tools lib directory, add to LD_LIBRARY_PATH (only if built from source).
RUN if [ "$BUILD_PYOPENMS" = "ON" ]; then \
        cp -r openms-build/lib /openms/lib; \
    fi
ENV LD_LIBRARY_PATH="/openms/lib/:${LD_LIBRARY_PATH}"

# Copy share folder, add to PATH, remove source directory (only if built from source).
RUN if [ "$BUILD_PYOPENMS" = "ON" ]; then \
        cp -r OpenMS/share/OpenMS /openms/share && \
        rm -rf OpenMS; \
    fi
ENV OPENMS_DATA_PATH="/openms/share/"

# Remove build directory (only if built from source).
RUN if [ "$BUILD_PYOPENMS" = "ON" ]; then \
        rm -rf openms-build; \
    fi

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
COPY utils/ /app/utils
COPY app.py /app/app.py
COPY settings.json /app/settings.json
COPY default-parameters.json /app/default-parameters.json

# For streamlit configuration
COPY .streamlit/config.toml /app/.streamlit/config.toml
COPY clean-up-workspaces.py /app/clean-up-workspaces.py

# add cron job to the crontab
RUN echo "0 3 * * * /root/miniforge3/envs/streamlit-env/bin/python /app/clean-up-workspaces.py >> /app/clean-up-workspaces.log 2>&1" | crontab -

# create entrypoint script to start cron service and launch streamlit app
RUN echo "#!/bin/bash" > /app/entrypoint.sh && \
    echo "source /root/miniforge3/bin/activate streamlit-env" >> /app/entrypoint.sh && \
    echo "service cron start" >> /app/entrypoint.sh && \
    echo "streamlit run app.py" >> /app/entrypoint.sh
# make the script executable
RUN chmod +x /app/entrypoint.sh

# Patch Analytics
RUN mamba run -n streamlit-env python hooks/hook-analytics.py

# Set Online Deployment
RUN jq '.online_deployment = true' settings.json > tmp.json && mv tmp.json settings.json

# Download latest OpenMS App executable as a ZIP file
RUN if [ -n "$GH_TOKEN" ]; then \
        echo "GH_TOKEN is set, proceeding to download the release asset..."; \
        gh release download -R ${GITHUB_USER}/${GITHUB_REPO} -p "OpenMS-App.zip" -D /app; \
    else \
        echo "GH_TOKEN is not set, skipping the release asset download."; \
    fi


# Run app as container entrypoint.
EXPOSE $PORT
ENTRYPOINT ["/app/entrypoint.sh"]
