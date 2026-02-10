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
ARG OPENMS_BRANCH=release/3.5.0
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

# Install up-to-date cmake via mamba and packages for pyOpenMS build.
RUN mamba install cmake
RUN pip install --upgrade pip && python -m pip install -U setuptools nose cython "autowrap<=0.24" pandas numpy pytest

# Clone OpenMS branch and the associcated contrib+thirdparties+pyOpenMS-doc submodules.
RUN git clone --recursive --depth=1 -b ${OPENMS_BRANCH} --single-branch ${OPENMS_REPO} && cd /OpenMS

# Pull Linux compatible third-party dependencies and store them in directory thirdparty.
WORKDIR /OpenMS
RUN mkdir /thirdparty && \
    git submodule update --init THIRDPARTY && \
    cp -r THIRDPARTY/All/* /thirdparty && \
    cp -r THIRDPARTY/Linux/x86_64/* /thirdparty && \
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

# Install other dependencies (excluding pyopenms)
COPY requirements.txt ./requirements.txt 
RUN grep -Ev '^pyopenms([=<>!~].*)?$' requirements.txt > requirements_cleaned.txt && mv requirements_cleaned.txt requirements.txt
RUN pip install -r requirements.txt

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

# Install Redis server for job queue and nginx for load balancing
RUN apt-get update && apt-get install -y --no-install-recommends redis-server nginx \
    && rm -rf /var/lib/apt/lists/*

# Create Redis data directory
RUN mkdir -p /var/lib/redis && chown redis:redis /var/lib/redis

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
COPY presets.json /app/presets.json

# For streamlit configuration
COPY .streamlit/ /app/.streamlit/
COPY clean-up-workspaces.py /app/clean-up-workspaces.py

# add cron job to the crontab
RUN echo "0 3 * * * /root/miniforge3/envs/streamlit-env/bin/python /app/clean-up-workspaces.py >> /app/clean-up-workspaces.log 2>&1" | crontab -

# Set default worker count (can be overridden via environment variable)
ENV RQ_WORKER_COUNT=1
ENV REDIS_URL=redis://localhost:6379/0

# Number of Streamlit server instances for load balancing (default: 1 = no load balancer)
# Set to >1 to enable nginx load balancer with multiple Streamlit instances
ENV STREAMLIT_SERVER_COUNT=1

# create entrypoint script to start cron, Redis, RQ workers, and Streamlit
RUN echo -e '#!/bin/bash\n\
set -e\n\
source /root/miniforge3/bin/activate streamlit-env\n\
\n\
# Start cron for workspace cleanup\n\
service cron start\n\
\n\
# Start Redis server in background\n\
echo "Starting Redis server..."\n\
redis-server --daemonize yes --dir /var/lib/redis --appendonly no\n\
\n\
# Wait for Redis to be ready\n\
until redis-cli ping > /dev/null 2>&1; do\n\
    echo "Waiting for Redis..."\n\
    sleep 1\n\
done\n\
echo "Redis is ready"\n\
\n\
# Start RQ worker(s) in background\n\
WORKER_COUNT=${RQ_WORKER_COUNT:-1}\n\
echo "Starting $WORKER_COUNT RQ worker(s)..."\n\
for i in $(seq 1 $WORKER_COUNT); do\n\
    rq worker openms-workflows --url $REDIS_URL --name worker-$i &\n\
done\n\
\n\
# Load balancer setup\n\
SERVER_COUNT=${STREAMLIT_SERVER_COUNT:-1}\n\
\n\
if [ "$SERVER_COUNT" -gt 1 ]; then\n\
    echo "Starting $SERVER_COUNT Streamlit instances with nginx load balancer..."\n\
\n\
    # Generate nginx upstream block\n\
    UPSTREAM_SERVERS=""\n\
    BASE_PORT=8510\n\
    for i in $(seq 0 $((SERVER_COUNT - 1))); do\n\
        PORT=$((BASE_PORT + i))\n\
        UPSTREAM_SERVERS="${UPSTREAM_SERVERS}        server 127.0.0.1:${PORT};\\n"\n\
    done\n\
\n\
    # Write nginx config\n\
    mkdir -p /etc/nginx\n\
    echo -e "worker_processes auto;\\npid /run/nginx.pid;\\n\\nevents {\\n    worker_connections 1024;\\n}\\n\\nhttp {\\n    client_max_body_size 0;\\n\\n    map \\$cookie_stroute \\$route_key {\\n        \\x22\\x22      \\$request_id;\\n        default \\$cookie_stroute;\\n    }\\n\\n    upstream streamlit_backend {\\n        hash \\$route_key consistent;\\n${UPSTREAM_SERVERS}    }\\n\\n    map \\$http_upgrade \\$connection_upgrade {\\n        default upgrade;\\n        \\x27\\x27 close;\\n    }\\n\\n    server {\\n        listen 0.0.0.0:8501;\\n\\n        location / {\\n            proxy_pass http://streamlit_backend;\\n            proxy_http_version 1.1;\\n            proxy_set_header Upgrade \\$http_upgrade;\\n            proxy_set_header Connection \\$connection_upgrade;\\n            proxy_set_header Host \\$host;\\n            proxy_set_header X-Real-IP \\$remote_addr;\\n            proxy_set_header X-Forwarded-For \\$proxy_add_x_forwarded_for;\\n            proxy_set_header X-Forwarded-Proto \\$scheme;\\n            proxy_read_timeout 86400;\\n            proxy_send_timeout 86400;\\n            proxy_buffering off;\\n            add_header Set-Cookie \\x22stroute=\\$route_key; Path=/; HttpOnly; SameSite=Lax\\x22 always;\\n        }\\n    }\\n}" > /etc/nginx/nginx.conf\n\
\n\
    # Start Streamlit instances on internal ports\n\
    for i in $(seq 0 $((SERVER_COUNT - 1))); do\n\
        PORT=$((BASE_PORT + i))\n\
        echo "Starting Streamlit instance on port $PORT..."\n\
        streamlit run app.py --server.port $PORT --server.address 0.0.0.0 &\n\
    done\n\
\n\
    sleep 2\n\
    echo "Starting nginx load balancer on port 8501..."\n\
    exec /usr/sbin/nginx -g "daemon off;"\n\
else\n\
    # Single instance mode (default) - run Streamlit directly on port 8501\n\
    echo "Starting Streamlit app..."\n\
    exec streamlit run app.py --server.address 0.0.0.0\n\
fi\n\
' > /app/entrypoint.sh
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
