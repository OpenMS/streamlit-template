#!/bin/bash
# Entrypoint for the streamlit-template container.
#
# Designed to run under both Docker and Apptainer/Singularity. Apptainer
# mounts the container filesystem read-only by default, so anything that
# needs to write at runtime (Redis dump, pidfiles, nginx temp dirs) must
# live under a writable path. /tmp is bind-mounted as tmpfs in both
# engines, so we route runtime state to $RUNTIME_DIR (default
# /tmp/opendiakiosk). Override RUNTIME_DIR to persist Redis dumps.
set -e
source /root/miniforge3/bin/activate streamlit-env

RUNTIME_DIR="${RUNTIME_DIR:-/tmp/opendiakiosk}"
mkdir -p "$RUNTIME_DIR/redis" "$RUNTIME_DIR/nginx" "$RUNTIME_DIR/nginx/tmp"

# cron writes /var/run/crond.pid, which is not writable on read-only
# container filesystems (Apptainer without --writable-tmpfs). Treat the
# failure as non-fatal: the rest of the app still works, the periodic
# workspace cleanup is just skipped. Run clean-up-workspaces.py from a
# host cron if you need it under Apptainer.
service cron start 2>/dev/null || echo "Note: cron not started (read-only filesystem?). Scheduled workspace cleanup disabled."

# Start Redis with an explicit runtime-generated config. This avoids the
# distro default /etc/redis/redis.conf which sets dir to /var/lib/redis,
# a path that is not writable on Apptainer's read-only rootfs.
echo "Starting Redis server..."
REDIS_CONF="$RUNTIME_DIR/redis/redis.conf"
cat > "$REDIS_CONF" <<EOF
port 6379
bind 127.0.0.1 -::1
dir $RUNTIME_DIR/redis
pidfile $RUNTIME_DIR/redis/redis.pid
logfile ""
appendonly no
daemonize yes
EOF
redis-server "$REDIS_CONF"

# Wait for Redis to be ready
until redis-cli ping > /dev/null 2>&1; do
    echo "Waiting for Redis..."
    sleep 1
done
echo "Redis is ready"

# Start RQ worker(s) in background
WORKER_COUNT=${RQ_WORKER_COUNT:-1}
echo "Starting $WORKER_COUNT RQ worker(s)..."
for i in $(seq 1 $WORKER_COUNT); do
    rq worker openms-workflows --url "$REDIS_URL" --name "worker-$i" &
done

# Load balancer setup
SERVER_COUNT=${STREAMLIT_SERVER_COUNT:-1}

if [ "$SERVER_COUNT" -gt 1 ]; then
    echo "Starting $SERVER_COUNT Streamlit instances with nginx load balancer..."

    BASE_PORT=8510
    UPSTREAM_LINES=""
    for i in $(seq 0 $((SERVER_COUNT - 1))); do
        PORT=$((BASE_PORT + i))
        UPSTREAM_LINES="${UPSTREAM_LINES}        server 127.0.0.1:${PORT};
"
    done

    # Write nginx config into the writable runtime dir and point pidfile,
    # logs, and all temp paths there too so nginx can run under Apptainer's
    # read-only rootfs (which makes the default /run, /var/log/nginx, and
    # /var/lib/nginx unwritable). Bash interpolates $RUNTIME_DIR and
    # $UPSTREAM_LINES; nginx-side variables are escaped with \$ so they
    # reach the file as literal $name for nginx to expand at request time.
    NGINX_CONF="$RUNTIME_DIR/nginx/nginx.conf"
    cat > "$NGINX_CONF" <<NGINX_EOF
worker_processes auto;
pid $RUNTIME_DIR/nginx/nginx.pid;
error_log $RUNTIME_DIR/nginx/error.log;

events {
    worker_connections 1024;
}

http {
    client_body_temp_path $RUNTIME_DIR/nginx/tmp/client_body;
    proxy_temp_path $RUNTIME_DIR/nginx/tmp/proxy;
    fastcgi_temp_path $RUNTIME_DIR/nginx/tmp/fastcgi;
    uwsgi_temp_path $RUNTIME_DIR/nginx/tmp/uwsgi;
    scgi_temp_path $RUNTIME_DIR/nginx/tmp/scgi;
    access_log $RUNTIME_DIR/nginx/access.log;

    client_max_body_size 0;

    map \$cookie_stroute \$route_key {
        ""      \$request_id;
        default \$cookie_stroute;
    }

    upstream streamlit_backend {
        hash \$route_key consistent;
${UPSTREAM_LINES}    }

    map \$http_upgrade \$connection_upgrade {
        default upgrade;
        '' close;
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

    # Start Streamlit instances on internal ports
    for i in $(seq 0 $((SERVER_COUNT - 1))); do
        PORT=$((BASE_PORT + i))
        echo "Starting Streamlit instance on port $PORT..."
        streamlit run app.py --server.port "$PORT" --server.address 0.0.0.0 &
    done

    sleep 2
    echo "Starting nginx load balancer on port 8501..."
    exec /usr/sbin/nginx -c "$NGINX_CONF" -g "daemon off;"
else
    # Single instance mode (default) - run Streamlit directly on port 8501
    echo "Starting Streamlit app..."
    exec streamlit run app.py --server.address 0.0.0.0
fi
