# Kubernetes Migration Plan — OpenMS Streamlit Template

## Goal

Transition from a single Docker container (where Streamlit, Redis, RQ workers, cron, and nginx all run together) to a Kubernetes deployment on **de.NBI Cloud Berlin** with separated, independently scalable services.

---

## Current Architecture (Single Container)

All services run inside one container, orchestrated by `entrypoint.sh`:

```
┌─────────────────────────────────────────────┐
│  Docker Container                           │
│                                             │
│  ┌──────────┐  ┌───────┐  ┌────────────┐   │
│  │ Streamlit │  │ Redis │  │ RQ Workers │   │
│  └──────────┘  └───────┘  └────────────┘   │
│  ┌───────┐  ┌──────┐                       │
│  │ Nginx │  │ Cron │                       │
│  └───────┘  └──────┘                       │
│                                             │
│  Volume: workspaces-streamlit-template      │
└─────────────────────────────────────────────┘
```

## Target Architecture (Kubernetes)

```
┌─ Kubernetes Cluster (de.NBI Berlin / Kubermatic) ──────────────┐
│                                                                 │
│  ┌──────────────────┐   ┌──────────────────┐                   │
│  │ Streamlit Deploy  │   │  Worker Deploy   │                   │
│  │ (N replicas)      │   │  (M replicas)    │                   │
│  │ image: app-web    │   │  image: app-worker│                  │
│  └────────┬─────────┘   └────────┬─────────┘                   │
│           │                      │                              │
│           ▼                      ▼                              │
│  ┌──────────────────────────────────────────┐                   │
│  │  Manila NFS Share (ReadWriteMany PVC)    │                   │
│  │  /app/workspaces-streamlit-template      │                   │
│  └──────────────────────────────────────────┘                   │
│           │                      │                              │
│           ▼                      ▼                              │
│  ┌──────────────────┐   ┌──────────────────┐                   │
│  │ Redis StatefulSet │   │  K8s CronJob     │                   │
│  │ (or single pod)   │   │  (cleanup)       │                   │
│  └──────────────────┘   └──────────────────┘                   │
│                                                                 │
│  ┌──────────────────┐                                           │
│  │  Ingress          │ ← sticky sessions + WebSocket support    │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Migration Steps

### Phase 1: Shared Storage Setup

**Create a Manila NFS share on de.NBI Cloud Berlin.**

1. Create an NFS share via the OpenStack dashboard or CLI using the `isilon-denbi` share type.
2. Configure IP-based access rules to allow your Kubernetes worker node subnet.
3. Define a static `PersistentVolume` and `PersistentVolumeClaim` with `ReadWriteMany` access mode pointing to the NFS share.

**Notes:**
- de.NBI Berlin supports NFSv3 only (no encryption in transit — acceptable within a private project network).
- Initial share size should not exceed 50 GB; shares > 250 GB may cause slow snapshots.
- Mount path must match the existing convention: `/app/workspaces-streamlit-template`.

---

### Phase 2: Externalize Redis

**Move Redis from an in-container daemon to its own pod.**

1. Create a Redis `Deployment` (single replica) or `StatefulSet` with a small `ReadWriteOnce` PVC for persistence.
2. Create a `Service` (ClusterIP) so other pods can reach it at e.g. `redis://redis:6379/0`.
3. No application code changes needed — `QueueManager` already reads `REDIS_URL` from the environment (`src/workflow/QueueManager.py`).

---

### Phase 3: Split Container Images

**Build two images from the existing Dockerfile.**

1. **`app-web`** — Streamlit server image.
   - Needs: Python, pyOpenMS, Streamlit, all UI dependencies.
   - Does NOT need: Full OpenMS TOPP tool binaries (unless pyOpenMS-only pages use them directly — verify).
   - Entrypoint: activate env + `streamlit run app.py`.

2. **`app-worker`** — RQ worker image.
   - Needs: Python, pyOpenMS, full OpenMS TOPP toolchain, RQ.
   - Does NOT need: Streamlit.
   - Entrypoint: activate env + `rq worker openms-workflows --url $REDIS_URL`.

**Alternatively**, use a single image for both (simpler to maintain, wastes some disk on the Streamlit pods). This is the recommended starting point — optimize later if image size becomes a concern.

---

### Phase 4: Decompose the Entrypoint

**Replace the monolithic `entrypoint.sh` with per-service entrypoints.**

| Service | Current (`entrypoint.sh`) | New Entrypoint |
|---|---|---|
| Streamlit | `streamlit run app.py` | `entrypoint-web.sh` |
| RQ Worker | `for` loop launching `rq worker` | `entrypoint-worker.sh` |
| Redis | `redis-server --daemonize yes` | Separate pod (Phase 2) |
| Cron | `service cron start` | K8s CronJob (Phase 6) |
| Nginx | Generated `nginx.conf` + `nginx` | K8s Ingress (Phase 5) |

Each entrypoint should:
1. Activate the mamba/conda environment.
2. Run exactly one process (no backgrounding).

---

### Phase 5: Kubernetes Manifests

**Create the core K8s resources.**

#### 5a. Streamlit Deployment + Service

- Deployment with N replicas (start with 1, scale up later).
- Environment: `REDIS_URL`, `online_deployment=true`.
- Volume mount: the NFS-backed PVC at `/app/workspaces-streamlit-template`.
- Service: ClusterIP on port 8501.
- Readiness probe: HTTP GET on `/_stcore/health` (Streamlit's built-in health endpoint).

#### 5b. Worker Deployment

- Deployment with M replicas (each pod runs one `rq worker` process).
- Same environment and volume mount as Streamlit.
- No Service needed (workers don't serve HTTP).
- Liveness probe: check if the `rq worker` process is alive.

#### 5c. Redis Deployment + Service

- Single-replica Deployment or StatefulSet.
- Small PVC for optional persistence.
- Service: ClusterIP, port 6379.
- Readiness probe: `redis-cli ping`.

#### 5d. Ingress

- Replace nginx load balancer.
- Must support:
  - **Sticky sessions** (cookie-based affinity) — Streamlit requires each browser tab to consistently reach the same pod due to WebSocket state.
  - **WebSocket upgrades** — Streamlit communicates via WebSocket after initial HTTP.
- Most ingress controllers (nginx-ingress, Traefik) support both via annotations.

Example (nginx-ingress):
```yaml
metadata:
  annotations:
    nginx.ingress.kubernetes.io/affinity: "cookie"
    nginx.ingress.kubernetes.io/session-cookie-name: "streamlit-route"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "86400"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "86400"
```

#### 5e. ConfigMap + Secret

- `ConfigMap`: `settings.json`, `default-parameters.json`, `presets.json`.
- `Secret`: `.streamlit/secrets.toml` (admin password), any other credentials.
- Mount or inject as environment variables depending on how each file is consumed.

---

### Phase 6: Workspace Cleanup CronJob

**Replace the in-container cron with a K8s CronJob.**

1. Create a `CronJob` that runs `clean-up-workspaces.py` on schedule (e.g. `0 3 * * *`).
2. Mount the same NFS PVC so it can access and delete stale workspaces.
3. Use a minimal image (just Python + the script).

---

### Phase 7: Force Online Mode

**Ensure the app always uses the RQ queue path, never local `multiprocessing`.**

1. Set `online_deployment: true` in `settings.json` (or via ConfigMap).
2. Verify all workflow execution goes through `QueueManager.submit_job()` → Redis → RQ worker.
3. The local process spawning path (`WorkflowManager._start_workflow_local()`) with PID files is incompatible with multi-pod architecture — it must not be used.
4. Test that job submission, status polling, and result retrieval all work across pods.

---

### Phase 8: Testing and Validation

1. **Single-replica smoke test**: Deploy one Streamlit pod, one worker pod, one Redis pod. Upload files, run a workflow, verify results appear.
2. **Multi-replica test**: Scale Streamlit to 2+ pods. Verify sticky sessions work — refreshing the page should keep the user on the same pod.
3. **Worker scaling test**: Scale workers to 2+. Submit multiple workflows concurrently. Verify jobs are distributed and results are correct.
4. **Pod failure test**: Kill a worker pod mid-workflow. Verify the job is marked as failed (not stuck). Kill a Streamlit pod — verify the user can reconnect (workspace state survives via `params.json` on NFS).
5. **Cleanup test**: Verify the CronJob runs and correctly removes stale workspaces from the NFS share.

---

## Risk Summary

| Risk | Severity | Mitigation |
|---|---|---|
| NFS performance for large files | Medium | Benchmark with real mzML files; consider object storage for bulk data if needed |
| Streamlit session loss on pod restart | Medium | Accepted trade-off; `params.json` persistence provides partial recovery |
| NFSv3 no encryption in transit | Low | Acceptable within de.NBI private project network |
| Image build times (OpenMS from source) | Low | Use CI/CD caching; consider pre-built base image |
| Manila share size limits | Low | Monitor usage; request quota increase if needed |

---

## de.NBI-Specific References

- **Kubernetes**: Managed via [Kubermatic](https://cloud.denbi.de/wiki/Tutorials/Kubermatic/), control plane >= 1.29
- **NFS shares**: Via [OpenStack Manila](https://cloud.denbi.de/wiki/Compute_Center/Berlin/), `isilon-denbi` share type, NFSv3
- **Support**: denbi-cloud@bih-charite.de
