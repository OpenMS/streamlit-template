# Kubernetes Deployment

This guide covers deploying an OpenMS streamlit app to a Kubernetes cluster using the Kustomize-based manifests under `k8s/`. For the docker-compose deployment path, see the "Developers Guide: Deployment" page.

## 1. Overview

The template ships a full Kubernetes deployment stack designed for the de.NBI cluster (OpenStack + `cinder-csi` storage + Traefik ingress). The stack includes:

- A Streamlit Deployment serving the web UI
- A Redis Deployment as the job-queue backing store
- An RQ worker Deployment running background workflows
- A nightly cleanup CronJob for stale workspaces
- A shared PersistentVolumeClaim holding per-user workspace data
- A Traefik IngressRoute routing external traffic to the Streamlit service (with session affinity)

Every production OpenMS webapp (quantms-web, umetaflow, FLASHApp) deploys via this stack.

## 2. Architecture

```
                              ┌────────────────────────┐
                              │  Traefik IngressRoute  │
                              │  Host(<your-hostname>) │
                              │  (sticky cookie)       │
                              └───────────┬────────────┘
                                          │
                                          ▼
                              ┌────────────────────────┐
                              │   Streamlit Service    │
                              │     ClusterIP :8501    │
                              └───────────┬────────────┘
                                          │
                                          ▼
                ┌─────────────────────────────────────────┐
                │        Streamlit Deployment             │
                │        (N replicas, default 2)          │
                │                                         │
                │   [pod affinity: co-locate with         │
                │    rq-worker + cleanup-cronjob pods]    │
                └────────┬────────────────────────┬───────┘
                         │ REDIS_URL              │
                         │                        │ /workspaces-...
                         ▼                        │
            ┌────────────────────────┐            │
            │    Redis Deployment    │            │
            │      (1 replica)       │            ▼
            └────────────────────────┘   ┌────────────────────────┐
                         ▲               │    Workspace PVC       │
                         │               │   ReadWriteOnce 500Gi  │
                         │ REDIS_URL     │   (cinder-csi)         │
                         │               └────────────────────────┘
                         │                        ▲
                         │                        │
                ┌────────┴───────────────────────┴────────┐
                │          RQ Worker Deployment           │
                │             (1 replica)                 │
                │       rq worker openms-workflows        │
                └─────────────────────────────────────────┘

                ┌─────────────────────────────────────────┐
                │      Cleanup CronJob (nightly 3 UTC)    │
                │      python clean-up-workspaces.py      │
                │      (mounts same PVC)                  │
                └─────────────────────────────────────────┘
```

### Components

| Component | Purpose | Replicas | Shares PVC? |
|-----------|---------|----------|-------------|
| Streamlit Deployment | Serves the web UI | N (default 2) | Yes |
| Redis Deployment | Job-queue backing store | 1 | No |
| RQ Worker Deployment | Runs background workflows from the Redis queue | 1 | Yes |
| Cleanup CronJob | Removes stale workspaces nightly at 03:00 UTC | — | Yes |
| Workspace PVC | Shared `/workspaces-*` directory for session data | — | — |
| Traefik IngressRoute | External HTTP entrypoint with sticky sessions | — | — |
| nginx Ingress | Alternative HTTP entrypoint used by the CI kind cluster | — | — |

### Pod affinity

All workspace-using pods (Streamlit, RQ worker, Cleanup) carry a `volume-group: workspaces` label and a `requiredDuringSchedulingIgnoredDuringExecution` pod-affinity rule keyed on `kubernetes.io/hostname`. This forces every workspace-using pod onto the same node, so they can share the `ReadWriteOnce` PVC.

Co-location is a placement constraint, not a replica cap. The Streamlit deployment can scale to N replicas — they all land on the same node alongside the worker.

### Ingress

Production deployments use the Traefik `IngressRoute`. The nginx `Ingress` is kept in `k8s/base/` because the CI integration test (`.github/workflows/k8s-manifests-ci.yml`) uses a kind cluster with an nginx ingress controller and filters out Traefik CRDs at apply time.

## 3. Manifest reference (`k8s/base/`)

### `namespace.yaml`
Creates the `openms` namespace. All resources deploy into it.

### `configmap.yaml`
`streamlit-config` ConfigMap holding `settings-overrides.json`, merged into the app's `settings.json` at pod startup. Currently sets `online_deployment: true`.

### `redis.yaml`
Redis 7 Deployment (1 replica) + ClusterIP Service on port 6379. Backs the RQ job queue. Low resource requests (64Mi / 50m CPU).

### `workspace-pvc.yaml`
PersistentVolumeClaim `workspaces-pvc`:
- `accessModes: [ReadWriteOnce]`
- `storageClassName: cinder-csi`
- `resources.requests.storage: 500Gi`

### `streamlit-deployment.yaml`
Main Streamlit Deployment. Key fields:
- `replicas: 2` (scales to N)
- `image: openms-streamlit` — replaced per app via Kustomize image transformer
- Env: `REDIS_URL`, `WORKSPACES_DIR`
- Mounts the workspace PVC at `/workspaces-streamlit-template`
- Mounts `settings-overrides.json` from the ConfigMap as a `subPath`
- Readiness and liveness probes hit `/_stcore/health`
- Pod affinity: `volume-group: workspaces`

### `streamlit-service.yaml`
ClusterIP Service exposing Streamlit on port 8501.

### `rq-worker-deployment.yaml`
RQ worker Deployment (1 replica). Runs `rq worker openms-workflows --url $REDIS_URL`. Shares the workspace PVC via the same `volume-group: workspaces` affinity rule.

### `cleanup-cronjob.yaml`
CronJob that runs `python clean-up-workspaces.py` nightly at 03:00 UTC. Uses `concurrencyPolicy: Forbid`, retains 3 successful and 3 failed jobs. Shares the workspace PVC.

### `ingress.yaml`
nginx `Ingress` with:
- WebSocket support (required by Streamlit)
- Sticky sessions via the `stroute` cookie
- Unlimited upload body size
- Disabled proxy buffering

Used by the kind CI integration test. Production overlays do not typically patch this.

### `traefik-ingressroute.yaml`
Traefik `IngressRoute` CRD. The default rule matches `PathPrefix('/')` (all paths) on the `web` entryPoint with a sticky `stroute` cookie. Overlays patch the `Host()` match expression and the service name to scope the route to a particular app.

### `kustomization.yaml`
Lists all base resources under the `openms` namespace.

## 4. Fork-and-deploy guide

### Prerequisites

- `kubectl` configured for the target cluster
- A storage class that supports `ReadWriteOnce` volumes (de.NBI uses `cinder-csi`)
- An ingress controller (Traefik, or nginx if you patch the nginx Ingress instead)
- Read access to GHCR for pulling the app image
- A DNS record pointing to the cluster's ingress load balancer

### Step 1 — App-level configuration

Update `settings.json`, choose a Dockerfile, and update `README.md`. If you are using Claude Code, the `configure-app-settings` skill automates these steps.

### Step 2 — Let CI build the image

Push your changes to `main` or create a tag. The workflow `.github/workflows/build-and-push-image.yml` builds the image from `Dockerfile` and pushes it to `ghcr.io/<your-org>/<your-repo>` with tags derived from the branch, semver, and commit SHA.

### Step 3 — Create your overlay

```bash
cp -r k8s/overlays/template-app k8s/overlays/<your-app-name>
```

### Step 4 — Edit `kustomization.yaml`

Open `k8s/overlays/<your-app-name>/kustomization.yaml` and change the following fields:

| Field | Set to |
|-------|--------|
| `namePrefix` | `<your-app-name>-` (trailing dash) |
| `commonLabels.app` | `<your-app-name>` |
| `images[0].newName` | `ghcr.io/<your-org>/<your-repo>` |
| `images[0].newTag` | `main` or a specific version tag |
| Hostname inside the IngressRoute `match` expression's `Host(...)` | your deployment hostname (e.g. `myapp.webapps.openms.de`) |
| IngressRoute service name reference (`template-app-streamlit`) | `<your-app-name>-streamlit` |
| Redis URL in both Deployment patches (`redis://template-app-redis:6379/0`) | `redis://<your-app-name>-redis:6379/0` |

The overlay leaves the nginx `Ingress` unpatched because Traefik is the production ingress. If you are deploying to an nginx-only cluster, substitute an Ingress host patch for the IngressRoute patch.

### Step 5 — Deploy

```bash
kubectl apply -k k8s/overlays/<your-app-name>/
```

### Step 6 — Verify

```bash
kubectl -n openms get pods -l app=<your-app-name>
kubectl -n openms rollout status deployment/<your-app-name>-streamlit --timeout=120s
```

Smoke-test the ingress URL in a browser — the app should load, a session cookie `stroute` should be set, and uploading a file should work.

### Automation with Claude skills

If you are using Claude Code, two skills automate this entire flow end-to-end:

- `configure-app-settings` — `settings.json`, Dockerfile, README.
- `configure-k8s-deployment` — the overlay + `kubectl apply` steps above.

## 5. CI/CD pipeline

### `build-and-push-image.yml`

- **Trigger:** push to `main`, push of a `v*` tag, or manual workflow dispatch.
- **Image name:** `ghcr.io/${{ github.repository }}`.
- **Dockerfile:** `Dockerfile` (full build with TOPP tools).
- **Tags:** branch name, semver (when a tag is pushed), short commit SHA.
- **Auth:** uses the workflow's `GITHUB_TOKEN` for GHCR login; also passes it as a build argument for in-image private-resource access.

### `k8s-manifests-ci.yml`

- **Trigger:** any push or pull request that touches `k8s/**`.
- **Job 1 — `validate-manifests`:**
  - `kubeconform` runs against `k8s/base/*.yaml` with strict mode and Kubernetes 1.28 schemas (excluding `kustomization.yaml` and the Traefik CRD `traefik-ingressroute.yaml`).
  - `kubectl kustomize k8s/overlays/template-app/` must succeed.
  - The kustomized output is re-validated through `kubeconform` (with `IngressRoute` skipped, since it is a CRD).
- **Job 2 — `integration-test`** (matrix over the two Dockerfile variants):
  - Builds the image from `Dockerfile` or `Dockerfile_simple`.
  - Creates a kind cluster, loads the image, installs the nginx ingress controller.
  - Applies the kustomized manifests with the Traefik IngressRoute filtered out (the kind cluster does not have Traefik CRDs).
  - Waits for Redis and the deployments to become available.
- **PR behavior:** both jobs run on pull requests. If branch protection requires these checks, a failure will block merge; otherwise the check failure is surfaced but non-blocking.
