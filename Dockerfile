# This Dockerfile builds OpenMS, the TOPP tools, pyOpenMS and thidparty tools.
# It also adds a basic streamlit server that serves a pyOpenMS-based app.
# hints:
# build image with: docker build --no-cache -t streamlitapp:latest . 2>&1 | tee build.log
# check if image was build: docker image ls
# run container: docker run -p 8501:8501 streamlitapp:latest
# debug container after build (comment out ENTRYPOINT) and run container with interactive /bin/bash shell
# prune unused images/etc. to free disc space (e.g. might be needed on gitpod). Use with care.: docker system prune --all --force

FROM ubuntu:22.04
ARG OPENMS_BRANCH=develop

# Step 1: set up a sane build system
USER root

RUN apt-get -y update
RUN apt-get install -y --no-install-recommends --no-install-suggests g++ autoconf automake patch libtool make git gpg wget ca-certificates curl
RUN update-ca-certificates

# Install python and streamlit

# install mamba (faster than conda)
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
RUN git clone --recursive --depth=1 -b ${OPENMS_BRANCH} --single-branch https://github.com/OpenMS/OpenMS.git && cd /OpenMS
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
    cp -r THIRDPARTY/Linux/64bit/* /thirdparty
ENV PATH="/thirdparty/LuciPHOr2:/thirdparty/MSGFPlus:/thirdparty/Sirius:/thirdparty/ThermoRawFileParser:/thirdparty/Comet:/thirdparty/Fido:/thirdparty/MaRaCluster:/thirdparty/MyriMatch:/thirdparty/OMSSA:/thirdparty/Percolator:/thirdparty/SpectraST:/thirdparty/XTandem:/thirdparty/crux:${PATH}"

RUN mkdir /openms-build
WORKDIR /openms-build

# configure
RUN /bin/bash -c "cmake -DCMAKE_BUILD_TYPE='Release' -DCMAKE_PREFIX_PATH='/OpenMS/contrib-build/;/usr/;/usr/local' -DBOOST_USE_STATIC=OFF ../OpenMS"

# make OpenMS library and executables
RUN make -j4 && rm -rf src doc CMakeFiles 

ENV PATH="/openms-build/bin/:${PATH}"

#################################### make pyOpenMS

WORKDIR /openms-build

RUN echo "deb http://archive.ubuntu.com/ubuntu/ bionic main universe" >> /etc/apt/sources.list
RUN apt-get install -y software-properties-common dirmngr
RUN add-apt-repository "deb http://archive.ubuntu.com/ubuntu/ bionic main universe"
RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys 3B4FE6ACC0B21F32
RUN apt-get -y update
RUN apt-get install -y --no-install-recommends --no-install-suggests python3-pip python3-dev python3-numpy
RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install -U setuptools
RUN python3 -m pip install -U nose Cython autowrap pandas numpy pytest

RUN /bin/bash -c "cmake -DCMAKE_PREFIX_PATH='/usr/;/usr/local' -DOPENMS_CONTRIB_LIBS='/contrib-build/' -DHAS_XSERVER=Off -DBOOST_USE_STATIC=OFF -DPYOPENMS=On ../OpenMS -DPY_MEMLEAK_DISABLE=On"

# make OpenMS library
RUN make -j4 pyopenms

# install pyOpenMS
WORKDIR /openms-build/pyOpenMS
RUN pip install dist/*.whl
ENV PATH="/openms-build/bin/:${PATH}"

#################################### remove source folders
RUN rm -rf /OpenMS

#################################### install streamlit
# creates the streamlit-env conda environment
# install packages
COPY environment.yml ./environment.yml
RUN mamba env create -f environment.yml
RUN echo "conda activate streamlit-env" >> ~/.bashrc
SHELL ["/bin/bash", "--rcfile", "~/.bashrc"]

# create workdir
WORKDIR /app

# install wget and cron
RUN apt-get install -y wget cron && rm -rf /var/lib/apt/lists/*

# make sure that conda environment is used
SHELL ["conda", "run", "-n", "streamlit-env", "/bin/bash", "-c"]

# expose port
EXPOSE 8501

ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "streamlit-env", "streamlit", "run", "app.py"]

