# Implementation Plan: Kubernetes Support for streamlit-template

This document describes the concrete code changes needed in the template repository to support Kubernetes deployment alongside the existing Docker Compose workflow.

---

## Step 1: Create Per-Service Entrypoint Scripts

**New files:** `deployment/entrypoint-web.sh`, `deployment/entrypoint-worker.sh`

The current `Dockerfile` generates a monolithic `entrypoint.sh` (lines 162-220) that starts cron, Redis, RQ workers, nginx, and Streamlit all in one container. For Kubernetes, each pod runs exactly one process.

**`entrypoint-web.sh`** (Streamlit pod):
```bash
#!/bin/bash
set -e
source /root/miniforge3/bin/activate streamlit-env
exec streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

**`entrypoint-worker.sh`** (RQ worker pod):
```bash
#!/bin/bash
set -e
source /root/miniforge3/bin/activate streamlit-env
exec rq worker openms-workflows --url "$REDIS_URL"
```

These are intentionally minimal — one process, no backgrounding, `exec` for proper signal handling.

---

## Step 2: Add a Kubernetes-Oriented Dockerfile Variant

**New file:** `Dockerfile.k8s`

Reuses the existing multi-stage build (stages `setup-build-system` and `compile-openms` are unchanged) but replaces the `run-app` stage:

- Does NOT install Redis or nginx (those are separate pods).
- Does NOT generate `entrypoint.sh`, register cron, or start multiple services.
- Copies in the per-service entrypoint scripts from Step 1.
- Accepts a build arg (`ROLE=web|worker`) or simply ships both entrypoints and selects at runtime via the K8s manifest `command:` override.

This keeps the existing `Dockerfile` fully intact for the Docker Compose workflow.

---

## Step 3: Write Kubernetes Manifests

**New directory:** `deployment/k8s/`

### 3a. `deployment/k8s/redis.yaml`
- **Deployment**: 1 replica, `redis:7-alpine` image, port 6379.
- **PVC**: Small (1Gi) `ReadWriteOnce` volume at `/data`.
- **Service**: ClusterIP named `redis` on port 6379.
- Readiness probe: `redis-cli ping`.

### 3b. `deployment/k8s/web.yaml`
- **Deployment**: configurable replicas (default 1), using the app image.
- Command override: `/app/deployment/entrypoint-web.sh`.
- Environment: `REDIS_URL=redis://redis:6379/0`, `ONLINE_DEPLOYMENT=true`.
- Volume mount: NFS-backed PVC at `/workspaces-streamlit-template`.
- ConfigMap mount: `settings.json`, `default-parameters.json`, `presets.json`.
- Secret mount: `.streamlit/secrets.toml`.
- Readiness probe: HTTP GET `/_stcore/health` port 8501.
- **Service**: ClusterIP on port 8501.

### 3c. `deployment/k8s/worker.yaml`
- **Deployment**: configurable replicas (default 1), same app image.
- Command override: `/app/deployment/entrypoint-worker.sh`.
- Same environment and NFS volume mount as web.
- No Service (workers don't serve HTTP).
- Liveness probe: exec `pgrep -f "rq worker"`.

### 3d. `deployment/k8s/ingress.yaml`
- Ingress resource with annotations for:
  - **Sticky sessions**: `nginx.ingress.kubernetes.io/affinity: cookie`
  - **WebSocket**: `proxy-read-timeout: 86400`, `proxy-send-timeout: 86400`
- Routes `/` to the web Service on port 8501.
- TLS section left as a placeholder (user provides cert/secret name).

### 3e. `deployment/k8s/cronjob.yaml`
- **CronJob**: runs `clean-up-workspaces.py` daily at 03:00.
- Uses a minimal image (or the same app image).
- Mounts the same NFS PVC.
- `restartPolicy: OnFailure`.

### 3f. `deployment/k8s/configmap.yaml`
- Contains `settings.json` with `online_deployment: true`.
- Contains `default-parameters.json` and `presets.json`.

### 3g. `deployment/k8s/pvc.yaml`
- PersistentVolumeClaim for workspaces:
  - `ReadWriteMany` access mode (required for multi-pod NFS).
  - Storage class left as a placeholder (`nfs` or `manila-nfs`) for the user to fill in based on their cluster.
- Includes comments for de.NBI Berlin Manila NFS setup.

---

## Step 4: Make `clean-up-workspaces.py` Configurable

**Modify:** `clean-up-workspaces.py`

Currently the workspace path is hardcoded to `/workspaces-streamlit-template` (line 9). Change to:

```python
workspaces_directory = Path(
    os.environ.get("WORKSPACES_DIR", "/workspaces-streamlit-template")
)
```

Also make the retention period configurable:

```python
retention_days = int(os.environ.get("CLEANUP_RETENTION_DAYS", "7"))
threshold = current_time - (86400 * retention_days)
```

This works for both the existing cron-in-container setup and the new K8s CronJob (environment variables are set in the CronJob manifest).

---

## Step 5: Make `QueueManager.py` Comment Accurate

**Modify:** `src/workflow/QueueManager.py`

The class docstring (line 49) says "Redis runs on localhost within the same container." This is no longer universally true. Update to:

```python
"""
Manages Redis Queue operations for workflow execution.

Only active in online mode. Falls back to direct execution in local mode.
Redis location is configured via the REDIS_URL environment variable
(defaults to redis://localhost:6379/0 for single-container deployments).
"""
```

No functional code changes — the `REDIS_URL` env var override already works correctly.

---

## Step 6: Remove Local-Execution Fallback in `WorkflowManager.py` for Online Mode

**Modify:** `src/workflow/WorkflowManager.py`

Currently `_start_workflow_queued()` (line 79) silently falls back to `_start_workflow_local()` if the queue submission fails. In a Kubernetes deployment, this fallback is harmful — `multiprocessing.Process` spawned on a Streamlit pod can't access worker-pod toolchains and won't be visible to the status-polling mechanism on other pods.

Change:

```python
if submitted_id:
    self._queue_manager.store_job_id(self.workflow_dir, submitted_id)
else:
    if self._is_online_mode():
        st.error("Queue submission failed. Please try again or contact an administrator.")
    else:
        self._start_workflow_local()
```

This makes the failure explicit in online mode instead of silently doing something that can't work in a multi-pod setup.

---

## Step 7: Add `settings.json` Environment Variable Override

**Modify:** The settings loading code (wherever `settings.json` is read at startup — likely `app.py` or a common init path).

Add support for overriding `online_deployment` via an environment variable so that the K8s ConfigMap or pod env can control it without rebuilding the image or modifying `settings.json` at build time:

```python
if os.environ.get("ONLINE_DEPLOYMENT", "").lower() in ("true", "1", "yes"):
    settings["online_deployment"] = True
```

This makes the `jq` patching in the Dockerfile (line 228) optional — the K8s deployment sets it via environment instead.

---

## Step 8: Add Deployment Documentation

**Modify:** `docs/kubernetes-migration-plan.md` (already created)

Add a practical "Quick Start" section at the top with:

1. Build the image: `docker build -f Dockerfile.k8s -t myregistry/openms-app:latest .`
2. Push to registry: `docker push myregistry/openms-app:latest`
3. Update `deployment/k8s/*.yaml` with your image, NFS details, and domain.
4. Apply: `kubectl apply -f deployment/k8s/`
5. Verify: `kubectl get pods`, check logs, test the Ingress URL.

---

## What Does NOT Change

- **`Dockerfile`** — untouched, Docker Compose workflow continues to work as-is.
- **`docker-compose.yml`** — untouched.
- **`QueueManager.py` logic** — already supports external Redis via `REDIS_URL`.
- **`WorkflowManager.py` local mode** — still works for development / Docker Compose.
- **`CommandExecutor.py`** — thread pool is pod-local, works fine.
- **CI/CD** (`ci.yml`, `build-docker-images.yml`) — no changes needed for the template itself.

---

## File Summary

| Action | Path | Description |
|--------|------|-------------|
| **Create** | `deployment/entrypoint-web.sh` | Single-process Streamlit entrypoint |
| **Create** | `deployment/entrypoint-worker.sh` | Single-process RQ worker entrypoint |
| **Create** | `Dockerfile.k8s` | K8s-oriented image (no Redis/nginx/cron) |
| **Create** | `deployment/k8s/redis.yaml` | Redis Deployment + Service + PVC |
| **Create** | `deployment/k8s/web.yaml` | Streamlit Deployment + Service |
| **Create** | `deployment/k8s/worker.yaml` | RQ Worker Deployment |
| **Create** | `deployment/k8s/ingress.yaml` | Ingress with sticky sessions + WebSocket |
| **Create** | `deployment/k8s/cronjob.yaml` | Workspace cleanup CronJob |
| **Create** | `deployment/k8s/configmap.yaml` | App configuration ConfigMap |
| **Create** | `deployment/k8s/pvc.yaml` | NFS PersistentVolumeClaim |
| **Modify** | `clean-up-workspaces.py` | Make paths + retention configurable via env |
| **Modify** | `src/workflow/QueueManager.py` | Update docstring |
| **Modify** | `src/workflow/WorkflowManager.py` | Error instead of silent fallback in online mode |
| **Modify** | Settings loading code | Add env var override for `online_deployment` |
| **Modify** | `docs/kubernetes-migration-plan.md` | Add quick-start section |
