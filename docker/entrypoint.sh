#!/bin/bash
# Container entrypoint for the OpenMS streamlit template.
#
# Works with both Docker (writable root FS, runs as root) and
# Apptainer/Singularity (read-only root FS, runs as the host user's UID).
# On HPC clusters apptainer is the dominant runtime; this script makes the
# image usable there without --writable-tmpfs.
set -e

# Force the app directory regardless of how the container was invoked.
# `apptainer instance start` does not always honor the Docker WORKDIR, so
# `streamlit run app.py` would otherwise resolve against the host's CWD.
cd /app

# Breadcrumbs — surfaced via apptainer instance .out/.err on failure, harmless
# in docker mode. Cheap to keep around for ongoing apptainer support.
echo "entrypoint: uid=$(id -u) gid=$(id -g) cwd=$(pwd) host=$(hostname) tty=$(tty 2>/dev/null || echo none)"
echo "entrypoint: APPTAINER_NAME=${APPTAINER_NAME:-unset} SINGULARITY_NAME=${SINGULARITY_NAME:-unset} APPTAINER_CONTAINER=${APPTAINER_CONTAINER:-unset}"

source /root/miniforge3/bin/activate streamlit-env
echo "entrypoint: conda env activated, streamlit=$(command -v streamlit || echo NOT_FOUND)"

# -----------------------------------------------------------------------------
# Apptainer / read-only root filesystem detection
# -----------------------------------------------------------------------------
# Apptainer sets APPTAINER_NAME (and SINGULARITY_NAME for backwards compat).
# As a fallback we probe /var/run for writability: docker = writable, apptainer
# default = read-only. Either signal flips us into "read-only mode".
if [ -n "${APPTAINER_NAME:-}" ] || [ -n "${SINGULARITY_NAME:-}" ] \
        || [ -n "${APPTAINER_CONTAINER:-}" ] || [ -n "${SINGULARITY_CONTAINER:-}" ] \
        || ! ( : > /var/run/.openms-rw-probe ) 2>/dev/null; then
    READONLY_ROOT=1
    echo "Detected read-only root filesystem (apptainer/singularity mode)"
else
    READONLY_ROOT=0
    rm -f /var/run/.openms-rw-probe 2>/dev/null || true
fi

# Pick state paths. In read-only mode we must use /tmp (always tmpfs in
# apptainer); in docker mode we keep the conventional /var paths so existing
# docker-compose / k8s deployments are unaffected.
if [ "$READONLY_ROOT" -eq 1 ]; then
    RUNTIME_DIR="${OPENMS_RUNTIME_DIR:-/tmp/openms-runtime-$$}"
    mkdir -p "$RUNTIME_DIR"
    REDIS_DATA_DIR="$RUNTIME_DIR/redis"
    REDIS_PID_FILE="$RUNTIME_DIR/redis.pid"
    # Apptainer/singularity share the host's network namespace by default. If
    # the host has anything listening on 6379 (a system redis-server, a docker
    # container, a previous singularity instance that didn't clean up), our
    # `redis-server --daemonize` silently fails with EADDRINUSE and the local
    # redis-cli ping happily connects to the host's redis instead — which
    # leaves stale `worker-1` records lying around and ultimately runs the
    # workflow's mkdir outside our mount namespace (no bind → EROFS). A unix
    # socket sidesteps the network stack entirely; the path is unambiguously
    # ours.
    REDIS_SOCKET="$RUNTIME_DIR/redis.sock"
    REDIS_URL="unix://${REDIS_SOCKET}"
    export REDIS_URL
    NGINX_CONF_DIR="$RUNTIME_DIR/nginx"
    NGINX_PID_FILE="$RUNTIME_DIR/nginx.pid"
    mkdir -p "$REDIS_DATA_DIR" "$NGINX_CONF_DIR"
    # Marker for out-of-band discovery (e.g. `apptainer exec ... redis-cli`
    # from CI). The entrypoint's exported env doesn't propagate to fresh
    # exec invocations, so write the resolved URL to a stable path.
    echo "$REDIS_URL" > /tmp/openms-redis-url 2>/dev/null || true
else
    RUNTIME_DIR="/var/run"
    REDIS_DATA_DIR="/var/lib/redis"
    REDIS_PID_FILE="/var/run/redis.pid"
    REDIS_SOCKET=""
    NGINX_CONF_DIR="/etc/nginx"
    NGINX_PID_FILE="/run/nginx.pid"
fi

# -----------------------------------------------------------------------------
# Workspace cleanup cron (best-effort)
# -----------------------------------------------------------------------------
# `service cron start` writes /var/run/crond.pid; it cannot work on a read-only
# root. The cleanup job is optional — workspaces just accumulate until the
# container is rebuilt, which is acceptable for HPC use cases where users
# manage their own workspace volumes.
if [ "$READONLY_ROOT" -eq 0 ]; then
    service cron start || echo "WARN: cron failed to start; workspace cleanup disabled"
else
    echo "Skipping cron (read-only root); run clean-up-workspaces.py manually if needed"
fi

# -----------------------------------------------------------------------------
# Redis + RQ workers (only present in the full image)
# -----------------------------------------------------------------------------
# The simple image does not install redis-server. Skip the whole queue section
# when the binary is missing, so this entrypoint can be shared by both images.
if command -v redis-server >/dev/null 2>&1; then
    if [ -n "$REDIS_SOCKET" ]; then
        echo "Starting Redis server (data=$REDIS_DATA_DIR, socket=$REDIS_SOCKET)..."
        # --port 0 disables the TCP listener entirely — we only accept the
        # unix socket. This is the whole point of switching to a socket in
        # apptainer mode: the host's network namespace (shared by default)
        # cannot conflict with us, and there is no fall-through to a stray
        # host redis-server.
        redis-server --daemonize yes \
            --dir "$REDIS_DATA_DIR" \
            --pidfile "$REDIS_PID_FILE" \
            --unixsocket "$REDIS_SOCKET" \
            --unixsocketperm 700 \
            --port 0 \
            --appendonly no
        REDIS_CLI_ARGS=(-s "$REDIS_SOCKET")
    else
        echo "Starting Redis server (data=$REDIS_DATA_DIR)..."
        redis-server --daemonize yes \
            --dir "$REDIS_DATA_DIR" \
            --pidfile "$REDIS_PID_FILE" \
            --appendonly no
        REDIS_CLI_ARGS=()
    fi

    # Bounded wait so a broken redis-server (e.g. socket can't be created or
    # an unexpected fork failure) fails the container fast instead of hanging
    # forever and never serving /_stcore/health.
    REDIS_STARTUP_RETRIES="${REDIS_STARTUP_RETRIES:-30}"
    for i in $(seq 1 "$REDIS_STARTUP_RETRIES"); do
        if redis-cli "${REDIS_CLI_ARGS[@]}" ping >/dev/null 2>&1; then
            echo "Redis is ready"
            break
        fi
        echo "Waiting for Redis... attempt $i/$REDIS_STARTUP_RETRIES"
        sleep 1
    done
    if ! redis-cli "${REDIS_CLI_ARGS[@]}" ping >/dev/null 2>&1; then
        echo "ERROR: Redis failed to become ready within ${REDIS_STARTUP_RETRIES}s" >&2
        exit 1
    fi

    WORKER_COUNT="${RQ_WORKER_COUNT:-1}"
    echo "Starting $WORKER_COUNT RQ worker(s)..."
    for i in $(seq 1 "$WORKER_COUNT"); do
        rq worker openms-workflows --url "$REDIS_URL" --name "worker-$i" &
    done
fi

# -----------------------------------------------------------------------------
# Streamlit (single instance or behind nginx load balancer)
# -----------------------------------------------------------------------------
SERVER_COUNT="${STREAMLIT_SERVER_COUNT:-1}"

# Surface a misconfigured opt-in to load balancing — silently downgrading to a
# single instance has bitten users on the simple image variant where nginx
# isn't installed.
if [ "$SERVER_COUNT" -gt 1 ] && ! command -v nginx >/dev/null 2>&1; then
    echo "WARN: STREAMLIT_SERVER_COUNT=$SERVER_COUNT requested but nginx is not installed (simple image?); falling back to a single instance" >&2
fi

if [ "$SERVER_COUNT" -gt 1 ] && command -v nginx >/dev/null 2>&1; then
    echo "Starting $SERVER_COUNT Streamlit instances with nginx load balancer..."

    UPSTREAM_SERVERS=""
    BASE_PORT=8510
    for i in $(seq 0 $((SERVER_COUNT - 1))); do
        PORT=$((BASE_PORT + i))
        UPSTREAM_SERVERS="${UPSTREAM_SERVERS}        server 127.0.0.1:${PORT};
"
    done

    NGINX_CONF_FILE="$NGINX_CONF_DIR/nginx.conf"
    cat > "$NGINX_CONF_FILE" <<NGINX_EOF
worker_processes auto;
pid $NGINX_PID_FILE;

events {
    worker_connections 1024;
}

http {
    client_max_body_size 0;

    map \$cookie_stroute \$route_key {
        ""      \$request_id;
        default \$cookie_stroute;
    }

    upstream streamlit_backend {
        hash \$route_key consistent;
${UPSTREAM_SERVERS}    }

    map \$http_upgrade \$connection_upgrade {
        default upgrade;
        ''      close;
    }

    server {
        listen 0.0.0.0:8501;

        location / {
            proxy_pass http://streamlit_backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection \$connection_upgrade;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_read_timeout 86400;
            proxy_send_timeout 86400;
            proxy_buffering off;
            add_header Set-Cookie "stroute=\$route_key; Path=/; HttpOnly; SameSite=Lax" always;
        }
    }
}
NGINX_EOF

    for i in $(seq 0 $((SERVER_COUNT - 1))); do
        PORT=$((BASE_PORT + i))
        echo "Starting Streamlit instance on port $PORT..."
        streamlit run app.py --server.port "$PORT" --server.address 0.0.0.0 &
    done

    sleep 2
    echo "Starting nginx load balancer on port 8501..."
    exec /usr/sbin/nginx -c "$NGINX_CONF_FILE" -g "daemon off;"
else
    echo "Starting Streamlit app (cwd=$(pwd), uid=$(id -u))..."
    exec streamlit run app.py --server.address 0.0.0.0
fi
