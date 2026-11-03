# Kubernetes Deployment

This guide covers deploying an OpenMS streamlit app to a Kubernetes cluster using the Kustomize-based manifests under `k8s/`. For the docker-compose deployment path, see the "Developers Guide: Deployment" page.

## 1. Overview

The template ships a full Kubernetes deployment stack designed for the de.NBI cluster (OpenStack, Manila shares for storage, Traefik ingress). The stack includes:

- A Streamlit Deployment serving the web UI
- A Redis Deployment as the job-queue backing store
- An RQ worker Deployment running background workflows
- A nightly cleanup CronJob for stale workspaces
- A shared `ReadWriteMany` PersistentVolumeClaim holding per-user workspace data
- A cluster-wide storage tier (`k8s/storage/`): the OpenStack Manila CSI driver and a `ReadWriteMany` StorageClass, so each app's workspace volume is a Manila NFS share and the pods above can be placed on any node
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
                │   [placed by the scheduler; the RWX     │
                │    volume constrains nothing]           │
                └────────┬────────────────────────┬───────┘
                         │ REDIS_URL              │
                         │                        │ /workspaces-...
                         ▼                        │
            ┌────────────────────────┐            │
            │    Redis Deployment    │            │
            │      (1 replica)       │            ▼
            └────────────────────────┘   ┌────────────────────────┐
                         ▲               │    Workspace PVC       │
                         │               │   ReadWriteMany 400Gi  │
                         │ REDIS_URL     │ (openms-manila-nfs: a  │
                         │               │  Manila NFS share)     │
                         │               └────────────────────────┘
                         │                        ▲
                         │                        │
                ┌────────┴───────────────────────┴────────┐
                │          RQ Worker Deployment           │
                │              (2 replicas)               │
                │       rq worker openms-workflows        │
                │                                         │
                │   [spread one per node, maxSkew 1       │
                │    over kubernetes.io/hostname]         │
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
| RQ Worker Deployment | Runs background workflows from the Redis queue | N (default 2) | Yes |
| Cleanup CronJob | Removes stale workspaces nightly at 03:00 UTC | — | Yes |
| Workspace PVC | Shared `/workspaces-*` directory for session data | — | — |
| Traefik IngressRoute | External HTTP entrypoint with sticky sessions | — | — |
| nginx Ingress | Alternative HTTP entrypoint used by the CI kind cluster | — | — |

### Pod placement and the shared workspace volume

All workspace-using pods (Streamlit, RQ worker, sync, Cleanup) of a given fork mount the same `<slug>-workspaces-manila-pvc`, which is `ReadWriteMany` on the `openms-manila-nfs` StorageClass published by the storage tier in `k8s/storage/`. Because it is RWX it imposes **no** placement constraint: any number of pods on any number of nodes can hold it at once, and the scheduler alone decides where they land.

That is what the storage tier is for. A Cinder volume (`cinder-csi`, `ReadWriteOnce`) attaches to exactly one node, so with it every workspace-using pod ended up on that node whether it fitted there or not. A Manila share is an NFS export served by OpenStack itself: there is no NFS server pod in the cluster, and losing a node costs only the pods on that node.

Nothing else constrains placement either. The `memory-tier-*` components are pure resource patches: they set the Streamlit and worker `requests`/`limits`, and a tier is now a **pod size**, not a set of nodes. No manifest in `k8s/` carries a `nodeSelector`, a `nodeName`, a `nodeAffinity` or an `openms.de/memory-tier` label, and CI fails the build if one reappears (`assert_no_node_pinning_anywhere`). Placement is the scheduler's decision alone; the manifests only tell it how big a worker is. See Step 4b below.

The workers go one step further and are actively spread. `rq-worker` runs a fixed replica count (2 by default) with a `topologySpreadConstraints` of `maxSkew: 1` over `kubernetes.io/hostname`, so the replicas land on different nodes before any node takes a second one. Two details make that work rather than merely look right:

- `maxSkew` is measured over **eligible** domains. While the `nodeSelector` was there, exactly one node was eligible, every distribution had skew 0, and a spread constraint written then would have passed while changing nothing. Deleting the selector is what gave the constraint something to measure.
- The constraint's `labelSelector` names `component: rq-worker` in the base, and kustomize copies the overlay's `commonLabels.app` into it. Topology spread counts pods per namespace and every fork deploys into `openms`, so without that label one fork's workers would be counted against another's skew.

`whenUnsatisfiable: DoNotSchedule`, so a replica with nowhere to go stays `Pending` instead of quietly doubling up — including during a node drain, where the cordoned node still counts as a domain. That is visible in `kubectl get pods` and recoverable; a soft constraint that silently stops spreading is neither.

Recoverable is not free, though, and it is `strategy` that buys it. A Deployment is `Available` only when `replicas - maxUnavailable` pods are ready, and the RollingUpdate default of 25% rounds *down* to `maxUnavailable: 0` at two replicas — so one `Pending` worker during a drain, or one worker failing its storage readiness probe during an NFS failover, would take the whole Deployment out of `Available` and hang every subsequent `kubectl rollout status`. `rq-worker` therefore sets `maxUnavailable: 1` explicitly (and `maxSurge: 0`, because a surge replica needs a whole extra worker's worth of memory free somewhere, which a cluster sized for the steady-state count does not have). The pair is what makes a lost worker a queue running at half rate rather than a blocked rollout. That the *other* replica is genuinely up is asserted directly against `.spec.replicas`, by `assert_workers_spread_across_nodes` in CI, rather than being inferred from the `Available` condition.

Forks are isolated from each other: each PVC that claims the shared class gets a Manila share of its own, so apps share the StorageClass and the drivers, never the data.

### Ingress

Production deployments use the Traefik `IngressRoute`. The nginx `Ingress` is kept in `k8s/base/` for forks deploying to nginx-only clusters and is exercised by the nginx-side kind integration test inside `.github/workflows/build-and-test.yml`. A separate `traefik-integration` job brings up Traefik in a second kind cluster and exercises the IngressRoute end-to-end.

#### Sticky cookie behaviour across hosts

Both Traefik and nginx attach a per-host `stroute` sticky cookie to bind a user to a specific Streamlit pod. Because cookies are scoped to the host that set them, a user who switches mid-session from `<app>.webapps.openms.de` to `<app>.webapps.openms.org` will be re-stuck to a (potentially different) pod. This is harmless: workspace and queue state live in Redis and the shared workspace PVC, so the new pod sees the same data. Pod affinity exists to keep the WebSocket warm and reuse Streamlit's in-process script cache, not for correctness.

## 3. Manifest reference (`k8s/base/`)

### Namespace
All resources deploy into the shared `openms` namespace (`namespace: openms` in `k8s/base/kustomization.yaml`). The Namespace object itself is defined only in `k8s/overlays/prod/namespace.yaml` of the streamlit-template, so on a cluster with Argo CD exactly one Application (the template's) manages it. If several apps carried it, every sync would take it over from the previous app (labels and Argo CD tracking), and with self-heal on they would overwrite each other continuously. An app generated from the template deletes `namespace.yaml` and its line in `k8s/overlays/prod/kustomization.yaml`; on a cluster without the template, create the namespace once with `kubectl create namespace openms`.

### `configmap.yaml`
`streamlit-config` ConfigMap holding `settings-overrides.json`, merged into the app's `settings.json` at pod startup. Currently sets `online_deployment: true`.

### `redis.yaml`
Redis 7 Deployment (1 replica) + ClusterIP Service on port 6379. Backs the RQ job queue. Low resource requests (64Mi / 50m CPU).

### `workspace-pvc.yaml`
PersistentVolumeClaim `workspaces-manila-pvc`:
- `accessModes: [ReadWriteMany]`
- `storageClassName: openms-manila-nfs` — published once per cluster by `k8s/storage/`; the same for every app
- `resources.requests.storage: 400Gi` — the size of this app's Manila share, counted against the project's share quota. Manila grows a share in place, so raising the number and re-applying is enough.

This is a **different object** from the claims earlier releases used (`workspaces-pvc`, `ReadWriteOnce` on `cinder-csi`, and then `workspaces-nfs-pvc` on a per-app Ganesha server). A bound PVC's spec is immutable apart from `resources.requests`, so the class cannot be changed in place. The old claim is left alone, which is also what makes rollback a single re-apply of the previous manifests. Delete it by hand once the cutover has been stable for a week. Workspaces expire after 7 days, so nothing is migrated.

Demo workspaces live under a hidden `.demos/` subdirectory of this PVC (see [Demo workspaces](#demo-workspaces) below). User workspaces live at the PVC root, one directory per session UUID.

### Demo workspaces
Demo workspaces are seeded onto the workspace PVC at `/workspaces-streamlit-template/.demos/` by the `seed-demos` initContainer on the Streamlit Deployment. The init runs `docker/seed-demos.sh` — new demos shipped in an image appear after redeploy, but existing entries on the PV (including admin-saved demos and edits) are preserved. On an empty volume the whole tree is staged in a private directory and renamed into place, so `replicas: 2` cannot corrupt it and a pod killed mid-copy leaves nothing half-written; on a volume that already has `.demos/`, only the entries it is missing are copied in, one atomic rename each. The script bounds itself with `timeout` and always exits 0, so a slow or restarting NFS server degrades the demos instead of holding the pod in `Init`.

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
- Mounts the RWX workspace PVC, which places no constraint on which node the pod lands on
- `seed-demos` initContainer merges image-shipped demos into `.demos/` on the PVC (see [Demo workspaces](#demo-workspaces))

### `streamlit-service.yaml`
ClusterIP Service exposing Streamlit on port 8501.

### `rq-worker-deployment.yaml`
RQ worker Deployment, 2 replicas by default. Runs `rq worker openms-workflows --url $REDIS_URL`. Shares the workspace PVC over NFS, so it can run on any node, including one no Streamlit pod is on.

- `replicas: 2` — RQ takes one job per worker process, so this is exactly how many workflows the deployment can run at once. It was 1, which serialised every workflow in the deployment and was also the only thing keeping the queue path's concurrent-access bugs latent. `memory-tier-high` overrides it to 1, because a 180Gi worker fits on a high-memory node and nowhere else (see [Step 4b](#step-4b--choose-the-worker-size-and-how-many-workers)).
- `topologySpreadConstraints`, `maxSkew: 1` over `kubernetes.io/hostname`, `DoNotSchedule` — one worker per node before any node takes a second (see [Pod placement and the shared workspace volume](#pod-placement-and-the-shared-workspace-volume)).
- `strategy: RollingUpdate` with `maxSurge: 0`, `maxUnavailable: 1`, both explicit. The defaults resolve to `maxUnavailable: 0` at this replica count, which would make one `Pending` or `NotReady` worker enough to take the Deployment out of `Available`.
- Sized by the memory-tier component with `requests` equal to `limits`, which is what makes the pod Guaranteed QoS: `oom_score_adj` of −997 rather than the ~969 a 1Gi request against a 16Gi limit used to score. CI reads `.status.qosClass` off the **Running** worker pods (`assert_worker_qos_guaranteed`) — the class is assigned at admission and is populated on a `Pending` pod too, so a check that did not filter on phase would report a pass for workers that were never scheduled.
- Readiness probe only, never liveness: a liveness failure would SIGKILL the container mid-TOPP-job, and a restart cannot fix a wedged NFS mount.

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

## 3b. The storage tier (`k8s/storage/`)

**One per cluster, not one per app.** Everything in this root is cluster scoped or lives in `kube-system`, so it is applied once, by whoever operates the cluster, before the first app overlay. Every app on the cluster claims the same StorageClass and gets its own share.

| File | Purpose |
|------|---------|
| `storageclass.yaml` | `openms-manila-nfs`: provisioner `nfs.manila.csi.openstack.org`, `reclaimPolicy: Retain`, volume expansion on, mount options `hard`, `nfsvers=3` (the de.NBI Isilon serves no NFSv4), `nconnect=4`. Two values are **cluster-specific**: `type` (the NFS share type, `isilon-denbi` on de.NBI Berlin) and `nfs-shareClient` (the addresses that get the share's access rule: on de.NBI Berlin the floating-IP range `10.57.200.0/21`, because the nodes reach the Isilon through the router). Both are parameters of the StorageClass and cannot be changed in place: to change one, delete and re-apply the class while no PVC uses it. |
| `manila-csi-values.yaml` | Helm values for `openstack-manila-csi` 2.36.3: NFS only, forwarding mounts to the csi-driver-nfs node plugin. |
| `csi-driver-nfs-values.yaml` | Helm values for `csi-driver-nfs` 4.11.0, used only as the node plugin that does the mount. Its own controller is scaled to zero. |
| `kustomization.yaml` | Inflates both charts into `kube-system` and adds the StorageClass. |

How a volume comes about: the workspace PVC asks for `openms-manila-nfs`; the manila-csi controller creates an NFS share of that size through the Manila API and adds an IP access rule for `nfs-shareClient`; on every node that runs a pod using it, the csi-driver-nfs node plugin mounts the share's export.

**Credentials.** manila-csi talks to the Manila API with an OpenStack *application credential*, kept in the Secret `manila-csi-credentials` in `kube-system`. It is never committed. Create the credential in Horizon (*Identity → Application Credentials*, role `member`) and then:

```bash
kubectl -n kube-system create secret generic manila-csi-credentials \
  --from-literal=os-authURL=https://<keystone>/v3 \
  --from-literal=os-region=<region> \
  --from-literal=os-applicationCredentialID=<id> \
  --from-literal=os-applicationCredentialSecret=<secret>
```

Rendering this root needs Helm on `PATH`, because of the `helmCharts` block, and `kubectl apply -k` accepts no `--enable-helm` flag:

```bash
kubectl kustomize --enable-helm k8s/storage/            # inspect
kubectl kustomize --enable-helm k8s/storage/ | kubectl apply -f -
```

Rendering also writes the vendored charts into `k8s/storage/charts/`. That directory is gitignored and must never be committed.

`k8s/ci-storage/` is **not** for real clusters. It is what the kind jobs in CI apply instead: one NFS-Ganesha server inside the cluster, publishing a StorageClass with the same name and mount options, because a GitHub runner cannot reach Manila. `assert_storage_class_contract` keeps the two classes in step.

## 4. Fork-and-deploy guide

### Prerequisites

- `kubectl` configured for the target cluster
- OpenStack Manila with an NFS share type and share quota for the project (Horizon shows a *Share* section under *Project*), and the storage tier in `k8s/storage/` applied once on the cluster (section 3b)
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

### Step 4b — Choose the worker size, and how many workers

The overlay pulls in one of two Kustomize components under `components:`:

```yaml
components:
  - ../../components/memory-tier-low    # default: 16Gi / 4 cpu per worker
  # OR
  - ../../components/memory-tier-high   # 180Gi / 20 cpu per worker
```

A tier is a **pod size**, not a set of nodes. Each component patches the Streamlit and `rq-worker` `resources` and nothing else — no node label is involved, and none has to exist on the cluster. `memory-tier-low` is right for most apps; switch to `memory-tier-high` only if the workload genuinely needs tens of GB of RAM (DIA spectral-library + OpenSwath peak picking, DIA-LFQ).

Both components set `requests` **equal to** `limits` on memory and cpu, which is the exact condition for Guaranteed QoS. Keep it that way when retuning. Only the request enters the Burstable `oom_score_adj` formula, so a worker asking for 1Gi against a 16Gi ceiling is schedulable on every node in the cluster and sits near the top of that node's kill list once it fills up — which is what the old sizing did. The cluster-side maximum is the `LimitRange` in `k8s/base/limitrange.yaml`, at 200Gi / 20 cpu per container — note the high tier's `cpu: 20` sits exactly *on* that ceiling, so raising it without raising the `LimitRange` first is rejected at admission as a quota violation rather than showing up as a `Pending` pod.

How many workers is a separate decision, and the one that actually spends a second node. The base ships `replicas: 2`, one per node on the two-node OpenMS cluster, and `memory-tier-high` is the one place in `k8s/` that overrides it — down to 1, because a 180Gi Guaranteed request fits on a high-memory node and nowhere else. With `DoNotSchedule` forbidding the second replica from doubling up on the node that could hold it, an inherited `replicas: 2` there is a worker that is `Pending` for ever. A fork with N high-memory nodes raises it to N. Otherwise change the count in the overlay rather than the base, so a template rebase cannot revert it:

```yaml
patches:
  - target:
      kind: Deployment
      name: rq-worker
    patch: |
      - op: replace
        path: /spec/replicas
        value: 4
```

`replicas x worker size` is reserved cluster-wide for as long as the workers run, queue empty or not, so raise it only when there is somewhere for the extra workers to fit. One that does not fit stays `Pending`.

### Step 4c — Storage needs no per-fork renaming

The storage tier is shared by every app on the cluster and carries no app name, so a fork changes nothing in `k8s/storage/`. Its workspace claim gets the overlay's `namePrefix` like every other object, and with it a Manila share of its own. Size it with `resources.requests.storage` in `k8s/base/workspace-pvc.yaml` (and `deploy.k8s.storage` in `app.yaml`, which `python -m utils.app_spec` compares with it).

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

**The storage tier first, once per cluster.** If no other app on the cluster has applied it yet, set the two cluster-specific values in `k8s/storage/storageclass.yaml`, create the credentials Secret (section 3b) and apply the root. It publishes the StorageClass the workspace PVC claims; applied in the other order, every pod sits `Pending` on a class that does not exist yet:

```bash
kubectl kustomize --enable-helm k8s/storage/ | kubectl apply -f -
kubectl -n kube-system rollout status statefulset -l app=openstack-manila-csi --timeout=300s
kubectl get storageclass openms-manila-nfs
```

Then the app:

```bash
kubectl apply -k k8s/overlays/prod/
kubectl -n openms get pvc     # <slug>-workspaces-manila-pvc Bound, RWX; the share appears in Horizon
```

The first needs Helm on `PATH`. Both applies are idempotent, and on an upgrade the storage one is usually a no-op.

**Coming from the single Cinder volume** (`<slug>-workspaces-pvc`, `ReadWriteOnce` on `cinder-csi`, pods pinned to an `openms.de/memory-tier` node): install the storage tier first and check that a claim on `openms-manila-nfs` binds. Only then let the new overlay reach the cluster. Under Argo CD with automatic sync that is the moment the template sync merges into the app's deployed branch, so the storage tier must already be in place. The overlay's claim has a new name, so it binds a fresh Manila share and the pods move to it, unpinned. The old claim carries `Prune=false`, so Argo CD leaves it and its Cinder volume alone. Delete it by hand once the new deployment has been stable for a week. Running workspaces do not move with it (they expire after 7 days anyway), and demos are reseeded from the image.

### Step 7 — Verify

```bash
kubectl -n openms get pods -l app=<your-app-name>
kubectl -n openms rollout status deployment/<your-app-name>-streamlit --timeout=120s
```

Smoke-test the ingress URL in a browser — the app should load, a session cookie `stroute` should be set, and uploading a file should work.

### GitOps with Argo CD

Instead of running Step 6 by hand on every change, Argo CD can apply the overlay from git:

- One Application per app on `k8s/overlays/prod`, with automatic sync, prune and self-heal. Turn automatic sync on only after a first manual sync whose diff you have read.
- The storage root is one Application per cluster on `k8s/storage`, **without** automatic sync. It needs `kustomize.buildOptions: --enable-helm` in `argocd-cm`.
- The `openms` namespace, the workspace PVC and the StorageClass carry `argocd.argoproj.io/sync-options: Prune=false,Delete=false`. All apps share the namespace and the class, and the claim holds every workspace, so Argo CD must never remove them.
- Ignore the data of `<prefix>-streamlit-secrets` (`ignoreDifferences` plus `RespectIgnoreDifferences=true`). The admin password is patched live (Step 5), and self-heal would reset it.
- Argo CD rolls out changes in git. A rebuilt image under a moving tag (`main-full`, `latest`) is not one, so pin `images[0].newTag` to a release tag through a PR (the `release-app` skill).
- `k8s/argocd/` holds this app's `Application` and `ImageUpdater`, applied once with `kubectl apply -n argocd -f k8s/argocd/`. It is not part of the overlay (the overlay forces every resource into `openms`). Each app keeps its own copy (`k8s/argocd/*` is app-owned), with its own name, repo, branch, image and release-tag pattern.
- To deploy every new release without a PR per release, add [Argo CD Image Updater](https://argocd-image-updater.readthedocs.io/) with one `ImageUpdater` entry per app: `updateStrategy: newest-build`, `allowTags` a regular expression matching only that app's release images (here `regexp:^v[0-9]+(\.[0-9]+)*-full$`; an app with app-prefixed tags such as `OpenDDA-1.2.2` matches `^OpenDDA-...-full$`), `manifestTargets.kustomize.name: openms-streamlit`, and `writeBackConfig.method: argocd`. Keep `newTag` in git on the current release, so a re-created Application starts from it.

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
  - `kubectl kustomize k8s/overlays/ci/` — the overlay the kind jobs apply — must succeed and validate the same way. Because a `patches:` entry whose target matches nothing is not an error in kustomize, the step additionally checks that the rendered CI worker is actually *smaller* than prod's and still has `requests == limits`; otherwise a renamed patch target would hand the kind jobs a full-sized worker no runner can schedule, an hour before anything noticed.
  - `kubectl kustomize --enable-helm` on `k8s/storage/` (Manila) and on `k8s/ci-storage/` (the CI stand-in) must succeed and their output is validated the same way, so the charts' own rendered objects are covered too.
- **Job 1b — `assert-invariants`:** static assertions from `.github/scripts/ci-assertions.sh` over the manifests — that the workspace PVC, the Manila StorageClass and the CI stand-in agree on the class name, `Retain` and the mount options (`assert_storage_class_contract`), that the CI NFS server pins `device-based-fsids` off, and that nothing anywhere pins a pod to a node. It deliberately has no `needs:` and nothing needs it, so a red invariant cannot hide the build.
  - Takes ~30s. Fails fast so manifest typos never trigger the hours-long full Docker build.
- **Job 2 — `build`** (`needs: lint-manifests`, matrix over `[full, simple]`):
  - Builds `Dockerfile` (full, includes TOPP tools) or `Dockerfile_simple` (pyOpenMS only) depending on the matrix leg.
  - **Buildx registry cache** (`type=registry,…,mode=max`) stored at `ghcr.io/<repo>/cache:full` and `:simple`. A `cache-from` read is attempted on every event; `cache-to` write only on push/tag/workflow_dispatch (fork PRs can't write). Repeat builds with an unchanged Dockerfile finish in minutes.
  - **Push** on push/tag/workflow_dispatch events (not on PRs). Tags: `<branch>-full` / `<branch>-simple`, `v<version>-full` / `v<version>-simple`, `<sha>-full` / `<sha>-simple`. `latest` is emitted only for the full variant on push to `main`.
  - **Kind integration** runs per variant: creates a two-node kind cluster, loads the just-built image, installs the nginx ingress controller, applies the CI storage stand-in `k8s/ci-storage/` (an in-cluster Ganesha server publishing `openms-manila-nfs`), then applies the kustomized **`ci`** overlay (filtering Traefik `IngressRoute`, forcing `imagePullPolicy: Never`, and shrinking the workspaces claim to fit the runner's disk). It asserts Redis and every Deployment become ready, curls both `.de` and `.org` hostnames through the nginx ingress, and then runs the assertions from `.github/scripts/ci-assertions.sh`: that every worker replica is Running on more than one node within the declared `maxSkew` (`assert_workers_spread_across_nodes`), that the Running workers are `Guaranteed` QoS (`assert_worker_qos_guaranteed`), cross-node write visibility, the POSIX contract, a workflow surviving an NFS server restart, stable file-handle identity across that restart, and two pods on two nodes sharing the volume. The two placement assertions run first because they take seconds while the storage ones budget up to 45 minutes of deliberate timeouts.

The kind jobs apply `k8s/overlays/ci/`, which is `k8s/overlays/prod/` with the worker `resources` patched down and nothing else changed. Production sizes a worker at 16Gi / 4 cpu with requests equal to limits; a GitHub runner has 4 vCPU and ~15.6Gi in total, every kind node is a container on that one host advertising the whole of it, and both replicas would sit `Pending` for ever. Same replica count, same spread constraint, same labels, same images — and every static assertion still renders `k8s/overlays/prod/`, so the sizing is the only thing CI does not observe directly.
- **Job 3 — `traefik-integration`** (`needs: lint-manifests`, runs once on `Dockerfile_simple`): builds the simple image, brings up a second kind cluster, installs Traefik via Helm (`service.type=ClusterIP`), applies the CI storage stand-in and then the full kustomized `ci` overlay without filtering the `IngressRoute` (still patching `imagePullPolicy: Never` and the claim size for kind compatibility), and curls both hostnames through Traefik. Catches IngressRoute-syntax regressions that the nginx-side test cannot. It runs the same placement and storage assertions as the nginx job.
- **Auth:** uses the workflow's `GITHUB_TOKEN` for GHCR login and as a build argument for in-image private-resource access. Fork PRs skip login (their `GITHUB_TOKEN` is read-only) but can still read the public cache.
- **PR behavior:** all three jobs run on pull requests. No tags are pushed and no cache is written. The kind integration still runs, exercising manifests end-to-end. If branch protection requires these checks, a failure blocks merge.

### `ghcr-cleanup.yml`

Scheduled retention policy that keeps GHCR tidy.

- **Trigger:** Sundays 03:00 UTC (cron), plus manual `workflow_dispatch` with a `dry-run` input (default `false`; set to `true` to preview deletions without acting).
- **Policy (`ghcr.io/<repo>`):** delete `<sha>-full` / `<sha>-simple` tags older than 30 days. Preserve `v*-full` / `v*-simple`, `main-full` / `main-simple`, and `latest` indefinitely. Delete untagged manifests older than 7 days.
- **Policy (`ghcr.io/<repo>/cache`):** delete untagged cache manifests older than 7 days. The active `full` and `simple` cache tags are never deleted (buildx overwrites them in place).
- **Failure isolation:** not in `needs:` of any other workflow. Cleanup failures never block merges. The job uses `snok/container-retention-policy@v3`.
