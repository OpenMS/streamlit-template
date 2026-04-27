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
                              │ Host(.de) || Host(.org)│
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
                │   [co-located with rq-worker +          │
                │    cleanup pods via shared RWO PVC]     │
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

### Pod co-location via the RWO PVC

All workspace-using pods (Streamlit, RQ worker, Cleanup) of a given fork mount the same `<slug>-workspaces-pvc` (`ReadWriteOnce`, `cinder-csi`). Once the first pod schedules, the volume is attached to that node and the kube-scheduler's `VolumeBinding` plugin pins every subsequent pod that mounts the same PVC to the same node. NodeSelector (`openms.de/memory-tier`) picks which set of nodes the fork is eligible for; the RWO mount picks the specific node within that set.

There is no pod-affinity rule. Forks are isolated from each other — co-location applies within a fork (because they share a PVC), not across forks (each fork has its own PVC).

Co-location is a placement constraint, not a replica cap. The Streamlit deployment can scale to N replicas — they all land on the same node alongside the worker.

### Ingress

Production deployments use the Traefik `IngressRoute`. The nginx `Ingress` is kept in `k8s/base/` for forks deploying to nginx-only clusters and is exercised by the nginx-side kind integration test inside `.github/workflows/build-and-test.yml`. A separate `traefik-integration` job brings up Traefik in a second kind cluster and exercises the IngressRoute end-to-end.

#### Sticky cookie behaviour across hosts

Both Traefik and nginx attach a per-host `stroute` sticky cookie to bind a user to a specific Streamlit pod. Because cookies are scoped to the host that set them, a user who switches mid-session from `<app>.webapps.openms.de` to `<app>.webapps.openms.org` will be re-stuck to a (potentially different) pod. This is harmless: workspace and queue state live in Redis and the shared workspace PVC, so the new pod sees the same data. Pod affinity exists to keep the WebSocket warm and reuse Streamlit's in-process script cache, not for correctness.

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

Demo workspaces live under a hidden `.demos/` subdirectory of this PVC (see [Demo workspaces](#demo-workspaces) below). User workspaces live at the PVC root, one directory per session UUID.

### Demo workspaces
Demo workspaces are seeded onto the `workspaces-pvc` at `/workspaces-streamlit-template/.demos/` by the `seed-demos` initContainer on the Streamlit Deployment. The init runs `cp -rn /app/example-data/workspaces/. /workspaces-streamlit-template/.demos/` — new demos shipped in an image appear after redeploy, but existing entries on the PV (including admin-saved demos and edits) are preserved.

The ConfigMap override points `demo_workspaces.source_dirs` at `/workspaces-streamlit-template/.demos`, so both Streamlit pods and RQ workers read demos from the PV. The "Save as Demo" admin flow writes to the same path.

To force a re-seed of a specific demo, delete it on the PV and restart the Streamlit Deployment:
```
kubectl exec deploy/streamlit -- rm -rf /workspaces-streamlit-template/.demos/<name>
kubectl rollout restart deploy/streamlit
```

`clean-up-workspaces.py` skips any top-level directory whose name starts with `.`, so the nightly cleanup cron does not touch `.demos/`.

### `streamlit-deployment.yaml`
Main Streamlit Deployment. Key fields:
- `replicas: 2` (scales to N)
- `image: openms-streamlit` — replaced per app via Kustomize image transformer
- Env: `REDIS_URL`, `WORKSPACES_DIR`
- Mounts the workspace PVC at `/workspaces-streamlit-template`
- Mounts `settings-overrides.json` from the ConfigMap as a `subPath`
- Readiness and liveness probes hit `/_stcore/health`
- Co-located with the RQ worker (and any cleanup Job) on the node the RWO `workspaces-pvc` is attached to
- `seed-demos` initContainer merges image-shipped demos into `.demos/` on the PVC (see [Demo workspaces](#demo-workspaces))

### `streamlit-service.yaml`
ClusterIP Service exposing Streamlit on port 8501.

### `rq-worker-deployment.yaml`
RQ worker Deployment (1 replica). Runs `rq worker openms-workflows --url $REDIS_URL`. Shares the workspace PVC, so it co-locates onto the same node as the Streamlit pods via the RWO mount.

### `cleanup-cronjob.yaml`
CronJob that runs `python clean-up-workspaces.py` nightly at 03:00 UTC. Uses `concurrencyPolicy: Forbid`, retains 3 successful and 3 failed jobs. Shares the workspace PVC.

### `ingress.yaml`
nginx `Ingress` with:
- WebSocket support (required by Streamlit)
- Sticky sessions via the `stroute` cookie
- Unlimited upload body size
- Disabled proxy buffering

Ships with two parallel `rules[]` entries (`streamlit.openms.example.de` / `.org`) so forks deploying to nginx get the same dual-host shape as the Traefik production path. Used by the nginx-side kind CI integration test. Production overlays do not typically patch this.

### `traefik-ingressroute.yaml`
Traefik `IngressRoute` CRD. The default rule matches `PathPrefix('/')` (all paths) on the `web` entryPoint with a sticky `stroute` cookie. Overlays patch the match expression to gate the route by host. The template default is ``(Host(`<app>.webapps.openms.de`) || Host(`<app>.webapps.openms.org`)) && PathPrefix(`/`)`` — outer parens are required because Traefik's `&&` binds tighter than `||`. To serve only one TLD, drop the alternative `Host()` and the surrounding parens.

### `kustomization.yaml`
Lists all base resources under the `openms` namespace.

### `streamlit-secrets.yaml`
Ships with an empty admin password by default and is included in `k8s/base/kustomization.yaml`, so `kubectl apply -k` always creates the `streamlit-secrets` Secret. The Streamlit Deployment mounts it at `/app/admin-secrets/`, and `.streamlit/config.toml` registers that path under `[secrets].files` so `st.secrets` picks it up. The admin password gates the "Save as Demo" feature — when empty (default), that UI is hidden entirely; set a password to enable it. The volume mount keeps `optional: true` so forks that inject the Secret out-of-band (Vault, External Secrets Operator) or rename it still boot. See "Configuring the admin password" below.

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

Push your changes to `main` or create a tag. The workflow `.github/workflows/build-and-test.yml` builds both the full (`Dockerfile`) and lightweight (`Dockerfile_simple`) variants and pushes each to `ghcr.io/<your-org>/<your-repo>` with variant-suffixed tags: `<branch>-full` / `<branch>-simple`, `v<version>-full` / `v<version>-simple`, and `<sha>-full` / `<sha>-simple`. The unsuffixed `latest` tag tracks the full variant on `main`.

### Step 3 — Edit the production overlay

Each fork ships a single production overlay at `k8s/overlays/prod/`. Edit this file in place — the forked repository itself identifies the app, so no per-app overlay subdirectory is created.

### Step 4 — Edit `kustomization.yaml`

Open `k8s/overlays/prod/kustomization.yaml` and change the following fields:

| Field | Set to |
|-------|--------|
| `namePrefix` | `<your-app-name>-` (trailing dash) |
| `commonLabels.app` | `<your-app-name>` |
| `images[0].newName` | `ghcr.io/<your-org>/<your-repo>` |
| `images[0].newTag` | `main-full` for the latest `main` build, or `v<version>-full` / `v<version>-simple` to pin a release. Use `-simple` variants if your app does not need the full TOPP toolchain. |
| Both `Host(...)` hostnames inside the IngressRoute `match` expression | your deployment hostnames on both TLDs: `<app>.webapps.openms.de` and `<app>.webapps.openms.org` |
| IngressRoute service name reference (`template-app-streamlit`) | `<your-app-name>-streamlit` |
| Redis URL in both Deployment patches (`redis://template-app-redis:6379/0`) | `redis://<your-app-name>-redis:6379/0` |

The overlay leaves the nginx `Ingress` unpatched because Traefik is the production ingress. If you are deploying to an nginx-only cluster, add an overlay patch for both `rules[].host` entries in the base `Ingress` (same `.de` / `.org` pattern) instead of the IngressRoute patch.

### Step 4b — Select a memory tier

The overlay pulls in one of two Kustomize components under `components:`:

```yaml
components:
  - ../../components/memory-tier-low    # default: light app on low-mem node
  # OR
  - ../../components/memory-tier-high   # memory-intensive app on high-mem node
```

`memory-tier-low` is the right choice for most apps. Switch to `memory-tier-high` only if the workload genuinely needs tens of GB of RAM (DIA spectral-library + OpenSwath peak picking, DIA-LFQ). The tier component adds the matching `nodeSelector: openms.de/memory-tier=<tier>` plus `requests`/`limits` sized for that node, so cluster nodes must already be labelled `openms.de/memory-tier=low` / `...=high`.

### Step 5 — Configure the admin password (optional)

Skip this step if you don't need the "Save as Demo" feature. `k8s/base/streamlit-secrets.yaml` already ships the `streamlit-secrets` Secret with an empty password, so `kubectl apply -k` always creates it. While the password is empty, the Save-as-Demo UI is hidden entirely — no error, no button. Setting a non-empty password is what enables the feature.

The overlay's `namePrefix` rewrites the Secret's name and the Deployment's reference together, so both paths below target `<your-app-name>-streamlit-secrets`.

**Recommended — patch the live Secret, nothing on disk:**

```bash
kubectl -n openms patch secret <your-app-name>-streamlit-secrets \
  --type=merge -p '{"stringData":{"secrets.toml":"[admin]\npassword = \"<your-strong-password>\""}}'
kubectl -n openms rollout restart deployment/<your-app-name>-streamlit
```

Streamlit only re-reads `[secrets].files` at process start, so the rollout restart is required. Rotate the same way (same `patch` + `rollout restart`).

**Alternative — edit the committed file locally, tell git to ignore the change:**

```bash
git update-index --skip-worktree k8s/base/streamlit-secrets.yaml
# now edit password = "" to your real password, then:
kubectl apply -k k8s/overlays/prod
kubectl -n openms rollout restart deployment/<your-app-name>-streamlit
```

`skip-worktree` is a per-clone flag that makes git ignore further edits to that file; the password never shows up in `git status`, so you cannot accidentally commit it. Undo with `git update-index --no-skip-worktree k8s/base/streamlit-secrets.yaml`. A plain `.gitignore` entry would **not** work here — `.gitignore` only applies to untracked files, and this Secret is tracked.

### Step 6 — Deploy

```bash
kubectl apply -k k8s/overlays/prod/
```

### Step 7 — Verify

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

### `build-and-test.yml`

One unified workflow owns manifest lint, Docker build, push, and kind integration.

- **Trigger:** pull request to `main`, push to `main`, push of a `v*` tag, or manual workflow dispatch.
- **Job 1 — `lint-manifests`:**
  - `kubeconform` runs against `k8s/base/*.yaml` with strict mode and Kubernetes 1.28 schemas (excluding `kustomization.yaml` and the Traefik CRD `traefik-ingressroute.yaml`).
  - `kubectl kustomize k8s/overlays/prod/` must succeed; the kustomized output is re-validated through `kubeconform` (with `IngressRoute` skipped).
  - Takes ~30s. Fails fast so manifest typos never trigger the hours-long full Docker build.
- **Job 2 — `build`** (`needs: lint-manifests`, matrix over `[full, simple]`):
  - Builds `Dockerfile` (full, includes TOPP tools) or `Dockerfile_simple` (pyOpenMS only) depending on the matrix leg.
  - **Buildx registry cache** (`type=registry,…,mode=max`) stored at `ghcr.io/<repo>/cache:full` and `:simple`. A `cache-from` read is attempted on every event; `cache-to` write only on push/tag/workflow_dispatch (fork PRs can't write). Repeat builds with an unchanged Dockerfile finish in minutes.
  - **Push** on push/tag/workflow_dispatch events (not on PRs). Tags: `<branch>-full` / `<branch>-simple`, `v<version>-full` / `v<version>-simple`, `<sha>-full` / `<sha>-simple`. `latest` is emitted only for the full variant on push to `main`.
  - **Kind integration** runs per variant: creates a kind cluster, loads the just-built image, installs the nginx ingress controller, applies the kustomized `prod` overlay (filtering Traefik `IngressRoute`, forcing `imagePullPolicy: Never` and `storageClassName: standard`), asserts Redis + deployments become ready, and curls both `.de` and `.org` hostnames through the nginx ingress to verify dual-host routing.
- **Job 3 — `traefik-integration`** (`needs: lint-manifests`, runs once on `Dockerfile_simple`): builds the simple image, brings up a second kind cluster, installs Traefik via Helm (`service.type=ClusterIP`), applies the full kustomized overlay without filtering the `IngressRoute` (still patching `imagePullPolicy: Never` and `storageClassName: standard` for kind compatibility), and curls both hostnames through Traefik. Catches IngressRoute-syntax regressions that the nginx-side test cannot.
- **Auth:** uses the workflow's `GITHUB_TOKEN` for GHCR login and as a build argument for in-image private-resource access. Fork PRs skip login (their `GITHUB_TOKEN` is read-only) but can still read the public cache.
- **PR behavior:** all three jobs run on pull requests. No tags are pushed and no cache is written. The kind integration still runs, exercising manifests end-to-end. If branch protection requires these checks, a failure blocks merge.

### `ghcr-cleanup.yml`

Scheduled retention policy that keeps GHCR tidy.

- **Trigger:** Sundays 03:00 UTC (cron), plus manual `workflow_dispatch` with a `dry-run` input (default `false`; set to `true` to preview deletions without acting).
- **Policy (`ghcr.io/<repo>`):** delete `<sha>-full` / `<sha>-simple` tags older than 30 days. Preserve `v*-full` / `v*-simple`, `main-full` / `main-simple`, and `latest` indefinitely. Delete untagged manifests older than 7 days.
- **Policy (`ghcr.io/<repo>/cache`):** delete untagged cache manifests older than 7 days. The active `full` and `simple` cache tags are never deleted (buildx overwrites them in place).
- **Failure isolation:** not in `needs:` of any other workflow. Cleanup failures never block merges. The job uses `snok/container-retention-policy@v3`.
