# This Dockerfile builds OpenMS, the TOPP tools, pyOpenMS and thidparty tools.
# It also adds a basic streamlit server that serves a pyOpenMS-based app.
# hints:
# build image and give it a name (here: streamlitapp) with: docker build --no-cache -t streamlitapp:latest . 2>&1 | tee build.log 
# check if image was build: docker image ls
# run container: docker run -p 8501:8501 streamlitappsimple:latest
# debug container after build (comment out ENTRYPOINT) and run container with interactive /bin/bash shell
# prune unused images/etc. to free disc space (e.g. might be needed on gitpod). Use with care.: docker system prune --all --force

FROM ubuntu:22.04 AS stage1
ARG OPENMS_REPO=https://github.com/OpenMS/OpenMS.git
ARG OPENMS_BRANCH=develop
ARG PORT=8501

# Step 1: set up a sane build system
USER root

RUN apt-get -y update
RUN apt-get install -y --no-install-recommends --no-install-suggests g++ autoconf automake patch libtool make git gpg wget ca-certificates curl libgtk2.0-dev
RUN update-ca-certificates

# Install mamba (faster than conda)
ENV PATH="/root/mambaforge/bin:${PATH}"
RUN wget -q \
    https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-Linux-x86_64.sh \
    && bash Mambaforge-Linux-x86_64.sh -b \
    && rm -f Mambaforge-Linux-x86_64.sh
RUN mamba --version

# Step 2: get an up-to date cmake (HEREDOC needs DOCKER_BUILDKIT=1 enabled or build with "docker buildx")
RUN <<-EOF
    cmake_ubuntu_version=$(lsb_release -cs)
    if ! wget -q --method=HEAD "https://apt.kitware.com/ubuntu/dists/$cmake_ubuntu_version/Release"; then
      bash -c "$(wget -O - https://apt.kitware.com/kitware-archive.sh)"
    else
      wget -qO - https://apt.kitware.com/kitware-archive.sh | bash -s -- --release $cmake_ubuntu_version
    fi
    apt-get -y update
    apt-get install -y cmake
EOF

# Step 3: dependencies for contrib etc.
RUN apt-get install -y --no-install-recommends --no-install-suggests libsvm-dev libglpk-dev libzip-dev zlib1g-dev libxerces-c-dev libbz2-dev libomp-dev libhdf5-dev
RUN apt-get install -y --no-install-recommends --no-install-suggests libboost-date-time1.74-dev \
                                                                     libboost-iostreams1.74-dev \
                                                                     libboost-regex1.74-dev \
                                                                     libboost-math1.74-dev \
                                                                     libboost-random1.74-dev
RUN apt-get install -y --no-install-recommends --no-install-suggests qtbase5-dev libqt5svg5-dev libqt5opengl5-dev

################################### clone OpenMS branch and the associcated contrib+thirdparties+pyOpenMS-doc submodules
RUN git clone --recursive --depth=1 -b ${OPENMS_BRANCH} --single-branch ${OPENMS_REPO} && cd /OpenMS
WORKDIR /OpenMS

###################################
# Step 4: Compile missing dependencies
RUN mkdir /OpenMS/contrib-build
WORKDIR /OpenMS/contrib-build

RUN cmake -DBUILD_TYPE=EIGEN /OpenMS/contrib && rm -rf archives src
RUN cmake -DBUILD_TYPE=COINOR /OpenMS/contrib && rm -rf archives src

#################################### compile OpenMS library
WORKDIR /

# pull Linux compatible third-party dependencies and store them 
# in directory thirdparty. Add path to them.
RUN apt-get install -y --no-install-recommends --no-install-suggests openjdk-8-jdk

WORKDIR /OpenMS
RUN mkdir /thirdparty && \
    git submodule update --init THIRDPARTY && \
    cp -r THIRDPARTY/All/* /thirdparty && \
    cp -r THIRDPARTY/Linux/64bit/* /thirdparty && \
    chmod -R +x /thirdparty
ENV PATH="/thirdparty/LuciPHOr2:/thirdparty/MSGFPlus:/thirdparty/Sirius:/thirdparty/ThermoRawFileParser:/thirdparty/Comet:/thirdparty/Fido:/thirdparty/MaRaCluster:/thirdparty/MyriMatch:/thirdparty/OMSSA:/thirdparty/Percolator:/thirdparty/SpectraST:/thirdparty/XTandem:/thirdparty/crux:${PATH}"

RUN mkdir /openms-build
WORKDIR /openms-build

# configure
RUN /bin/bash -c "cmake -DCMAKE_BUILD_TYPE='Release' -DCMAKE_PREFIX_PATH='/OpenMS/contrib-build/;/usr/;/usr/local' -DBOOST_USE_STATIC=OFF ../OpenMS"

# make OpenMS library and executables
RUN make -j4 TOPP && make -j4 UTILS && rm -rf src doc CMakeFiles 

ENV PATH="/openms-build/bin/:${PATH}"

#################################### build pyOpenMS
FROM stage1 AS stage2
SHELL ["/bin/bash", "-c"]
WORKDIR /openms-build

# Activate and configure the Conda environment to build pyOpenMS (needs extra libs)
RUN conda update -n base -c conda-forge conda && conda info && conda create -n py310 python=3.10
# note: activation of conda needs to go to bashrc because every RUN command spawns new bash
SHELL ["conda", "run", "-n", "py310", "/bin/bash", "-c"]
RUN echo "source activate py310" > ~/.bashrc
RUN conda install pip
RUN python -m pip install --upgrade pip && python -m pip install -U setuptools nose Cython autowrap pandas numpy pytest

RUN cmake -DCMAKE_PREFIX_PATH='/contrib-build/;/usr/;/usr/local' -DOPENMS_CONTRIB_LIBS='/contrib-build/' -DHAS_XSERVER=Off -DBOOST_USE_STATIC=OFF -DPYOPENMS=On ../OpenMS -DPY_MEMLEAK_DISABLE=On

# make and install pyOpenMS
RUN make -j4 pyopenms
WORKDIR /openms-build/pyOpenMS
RUN pip install dist/*.whl
ENV PATH="/openms-build/bin/:${PATH}"

### TODO: cleanup OpenMS source folder. Probably needs a make install to have share available
#RUN rm -rf /OpenMS

#################################### install streamlit
FROM stage2 AS stage3
# creates the streamlit-env conda environment
# install packages
COPY environment.yml ./environment.yml
RUN mamba env create -f environment.yml
RUN echo "conda activate streamlit-env" >> ~/.bashrc
SHELL ["/bin/bash", "--rcfile", "~/.bashrc"]

# create workdir and copy over all streamlit related files/folders
WORKDIR /app
# note: specifying folder with slash as suffix and repeating the folder name seems important to preserve directory structure
COPY app.py /app/app.py 
COPY src/ /app/src
COPY assets/ /app/assets
COPY example-data/ /app/example-data
COPY pages/ /app/pages

# install cron (TODO: think about automatic clean up of temporary files and workspaces)
# RUN apt-get install -y cron

# make sure that conda environment is used
SHELL ["conda", "run", "-n", "streamlit-env", "/bin/bash", "-c"]
EXPOSE $PORT
ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "streamlit-env", "streamlit", "run", "app.py"]
