---
name: configure-k8s-deployment
description: Use when deploying an OpenMS Streamlit app to Kubernetes, or when working with the kustomize base, overlays or the separate storage root.
---

# Configure Kubernetes Deployment

Conduct a short interview, then edit the Kustomize overlay (and optionally the workspace PVC) so a forked OpenMS Streamlit app is ready to deploy to the OpenMS Kubernetes cluster.

## Prerequisite

Run `configure-app-settings` first. This skill assumes `settings.json`, the Dockerfile, and app metadata are already configured.

## Scope

You — Claude — only edit YAML files in this repo. You do **not** run `kubectl`, render manifests with `kubectl kustomize`, or verify cluster state. A human operator (or CI on merge to `main`) applies the manifests after this skill commits the overlay edits. The skill targets the Traefik-based OpenMS production cluster only; nginx fallback paths are out of scope.

## Cluster prerequisites (informational)

These are facts about the target cluster, not steps for you to execute. Mention them in the handoff so the operator can confirm they hold:

- Traefik ingress controller installed in the cluster (handles `IngressRoute` CRDs).
- Cluster has read access to GHCR for pulling the app image.
- A storage class that provisions `ReadWriteOnce` volumes (de.NBI: `cinder-csi`). That is the **backing** volume for the storage tier, not the claim the app mounts. For live grows of it, the class needs `allowVolumeExpansion: true`.
- The fork's storage tier (`k8s/storage/`) already applied, publishing the `ReadWriteMany` StorageClass the workspaces PVC names, and `mount.nfs` present on every node. Applied in the other order, every pod sits `Pending` on a class that does not exist yet.
- **No node labels, of any kind.** Nothing under `k8s/` selects a node any more: the scheduler places pods and the manifests only declare how big a worker is. The `openms.de/memory-tier` labels the older components matched are gone, and CI fails any manifest that reintroduces a `nodeSelector`, `nodeName` or `nodeAffinity` (`assert_no_node_pinning_anywhere`).
- Room for `<replicas> x <worker size>` (Q5 and Q6) across the cluster's nodes. A worker is Guaranteed QoS, so its request is reserved for as long as the pod runs, queue empty or not.
- DNS for `*.webapps.openms.de` and `*.webapps.openms.org` pointing at the cluster's Traefik load balancer.

## Step 1 — Recon the fork

Before asking the user anything, read a small known set of files directly (do not delegate to a subagent — the surface area is fixed):

1. `git remote get-url origin` and the repo name → seeds the slug and GHCR ref defaults.
2. `k8s/overlays/prod/kustomization.yaml` — if anything has already been edited away from the template stub, treat those values as the user's prior choices to confirm rather than overwrite blindly.
3. `k8s/base/kustomization.yaml`, `k8s/base/streamlit-deployment.yaml`, `k8s/base/rq-worker-deployment.yaml`, `k8s/base/workspace-pvc.yaml` — confirm the layout still matches the template:
   - PVC `metadata.name` is `workspaces-nfs-pvc`, `ReadWriteMany`, on a `storageClassName` this fork's `k8s/storage/` publishes.
   - Deployments reference `image: openms-streamlit` (the placeholder Kustomize swaps).
   - `streamlit-deployment.yaml` and `rq-worker-deployment.yaml` both carry `claimName: workspaces-nfs-pvc`. Being RWX, that claim constrains placement not at all: the workspace-using pods are placed independently by the scheduler, not co-located, and there is no pod-affinity rule pulling them together either.
   - `rq-worker-deployment.yaml` has a fixed `replicas` and a `topologySpreadConstraints` block over `kubernetes.io/hostname` with `maxSkew: 1`. Read the replica count from here — it is the default you propose in Q6.
4. `.github/workflows/build-and-test.yml` — confirm which tags CI publishes (the OpenMS template publishes `<branch>-full`, `<branch>-simple`, `<tag>-full`, `<tag>-simple`, plus `latest` on `main`-full pushes).

If any of those files are missing, renamed, or significantly restructured, stop and ask the user how to proceed. Do not pattern-match the standard answers onto an unknown layout.

## Step 2 — Interview the user

Ask the user the questions below in 3 batched `AskUserQuestion` turns rather than one long sequential interrogation. Group related questions together: slug + subdomain + GHCR ref + tag make a coherent identity batch, and worker size + replica count + storage size make a coherent capacity batch — they trade against each other and against the same cluster.

Each question must include:

- the **default** you are proposing (derived from Step 1),
- a one-line **"what this controls in the running deployment"** explanation,
- the **reasoning** for the default.

The user confirms or overrides each one. Do not omit the "what this controls" line — the user needs to understand the deployment effect of their answer before committing to it.

### Q1. App slug

- *What this controls:* every Kubernetes resource for this app gets prefixed with `<slug>-` (Pods, Services, PVCs, ConfigMaps), so the slug is what cluster operators see in `kubectl get pods/svc/pvc -n openms`. It also becomes the DNS name worker pods use to reach Redis (`<slug>-redis`).
- *Default:* repo name lowercased, with `streamlit-` / `-template` prefixes/suffixes stripped. Examples: `OpenDIAKiosk` → `opendiakiosk`; `umetaflow-gui` → `umetaflow-gui`; `streamlit-template` → `template-app`.
- *Format:* single lowercase token, no spaces.

### Q2. GHCR image reference

- *What this controls:* which container image the cluster pulls. A wrong value here means `ImagePullBackOff` and no app comes up.
- *Default:* `ghcr.io/<owner>/<repo>` lowercased, derived from the `origin` remote.

### Q3. Image tag

- *What this controls:* which build of the image is deployed. `main-full` follows the `main` branch (auto-updates whenever a merge rebuilds + the operator re-applies); a release tag like `v1.2.3-full` pins to a specific build (won't drift, requires deliberate bumps).
- *Default:* `main-full` if the workflow publishes branch-suffixed tags (the standard template setup), otherwise whatever pattern Step 1 found in `build-and-test.yml`. The `-simple` variant uses a lighter `Dockerfile_simple`; pick that only if the user explicitly wants the lightweight image.

### Q4. Ingress subdomain

- *What this controls:* the public URL users type into a browser. The IngressRoute always wires up **both** `<sub>.webapps.openms.de` and `<sub>.webapps.openms.org` (one IngressRoute, two `Host(...)` matchers OR-ed together), so users land on the same app regardless of which TLD they remember.
- *Default:* the slug. But ask — `OpenDIAKiosk` chose subdomain `opendia` (different from its slug `opendiakiosk`) for a shorter URL, so this is not always identical to the slug.

### Q5. Worker size

- *What this controls:* how much memory and CPU **one RQ worker** reserves. This is a pod size, not a node selection — the component sets `requests` equal to `limits`, so the number is simultaneously what the scheduler reserves and the hard ceiling the kernel enforces, and Kubernetes then places the pod wherever it fits. Too small and TOPP tools are OOMKilled mid-workflow; too large and the worker either sits `Pending` or reserves most of a node it never uses.
- *Default:* `memory-tier-low` — 16Gi / 4 cpu per worker, correct for ~90% of template forks.
- *Override prompt:* "Does this app run DIA spectral-library construction, OpenSwath peak picking, DIA-LFQ, or comparable heavy OpenMS workloads?" If yes → `memory-tier-high`, 180Gi / 20 cpu, which is most of a high-memory node held for as long as the worker lives.
- *If neither number fits:* edit `k8s/components/memory-tier-<tier>/worker-resources.yaml` and keep `requests` **equal to** `limits` on both memory and cpu. Splitting them drops the pod to Burstable QoS and back near the top of the node's OOM-kill list; CI fails that (`assert_worker_qos_guaranteed`). The cluster-side ceiling is the `LimitRange` in `k8s/base/limitrange.yaml`.
- *What it no longer controls:* placement. Nothing schedules by node label any more — a tier is a size. A fork that needs one specific machine has to take that up with the cluster operator, not encode it here.

### Q6. Worker replica count

- *What this controls:* how many workflows the deployment runs at once — RQ takes one job per worker process, so N workers is N concurrent workflows and nothing else. It is also what actually spends a second node: the workers carry `topologySpreadConstraints` with `maxSkew: 1` over `kubernetes.io/hostname`, so replicas are placed one per node before any node takes a second.
- *Default:* whatever `k8s/base/rq-worker-deployment.yaml` already says (2 — one per node on the two-node OpenMS cluster). Propose a different number only when the answer to "how many nodes can hold a worker of the Q5 size" is not 2.
- *Cost of raising it:* `replicas x Q5 size` is reserved cluster-wide for as long as the workers run, queued jobs or not. A replica with nowhere to fit stays `Pending` rather than doubling up on a node — `whenUnsatisfiable: DoNotSchedule` — so over-provisioning is visible in `kubectl get pods` rather than silent.
- *Do not answer 1* unless serialized workflows are genuinely wanted: a single worker leaves every other node with nothing to run, which is the state this deployment was in before.

### Q7. Workspace storage size

- *What this controls:* the persistent disk allocated for Streamlit session workspaces, uploaded files, intermediate analysis outputs, and any reference data the app seeds at startup. Too small → users hit "no space left" mid-analysis; too large → wasted cluster storage budget.
- *Default:* **400 Gi** (matches the stock base, so the default needs zero file edits).
- *Note on naming (do not ask the user):* the PVC base name stays `workspaces-nfs-pvc` for every fork. Kustomize's `namePrefix: <slug>-` automatically scopes it to `<slug>-workspaces-nfs-pvc` in the cluster, so cross-fork name collisions are impossible. Override the size only — never rename the PVC.

## Step 3 — Apply the answers to `k8s/overlays/prod/kustomization.yaml`

Edit the file in place. The full templated shape is:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base

components:
  - ../../components/memory-tier-<tier>          # Q5: low | high — worker SIZE, not node selection

namePrefix: <slug>-                              # Q1

commonLabels:
  app: <slug>                                    # Q1

images:
  - name: openms-streamlit                       # match key — DO NOT CHANGE
    newName: <ghcr-ref>                          # Q2
    newTag: <tag>                                # Q3

patches:
  - target:
      kind: IngressRoute
      name: streamlit-traefik
    patch: |
      - op: replace
        path: /spec/routes/0/match
        value: (Host(`<sub>.webapps.openms.de`) || Host(`<sub>.webapps.openms.org`)) && PathPrefix(`/`)
      - op: replace
        path: /spec/routes/0/services/0/name
        value: <slug>-streamlit
  - target:
      kind: Deployment
      name: streamlit
    patch: |
      - op: replace
        path: /spec/template/spec/containers/0/env/0/value
        value: "redis://<slug>-redis:6379/0"
  - target:
      kind: Deployment
      name: rq-worker
    patch: |
      - op: replace
        path: /spec/template/spec/containers/0/env/0/value
        value: "redis://<slug>-redis:6379/0"
```

Substitution map:

- `<slug>` → Q1 answer.
- `<ghcr-ref>` → Q2 answer.
- `<tag>` → Q3 answer.
- `<sub>` → Q4 answer (note: `<sub>` is independent of `<slug>`).
- `<tier>` → `low` or `high` from Q5.

Q6 needs a file edit **only if the answer differs from the base default**. If it does, add one more patch to the same `patches:` list. Patch the overlay, never `k8s/base/rq-worker-deployment.yaml`, so the fork's capacity choice stays in the one file this skill owns and a template rebase cannot quietly revert it:

```yaml
  - target:
      kind: Deployment
      name: rq-worker
    patch: |
      - op: replace
        path: /spec/replicas
        value: <N>                                 # Q6
```

Leave the `topologySpreadConstraints` in the base alone either way. It is what puts those replicas on different nodes, and it is scoped to this fork only because kustomize copies `commonLabels.app` into the constraint's `labelSelector` — dropping `commonLabels` from the overlay silently widens it to every fork's workers in the namespace.

About `images[0].name: openms-streamlit` — **this is the match key, not a value the user picks.** Kustomize's `images:` transformer is find-and-replace: `name` is the literal image string Kustomize searches for in the rendered manifests, and `newName`/`newTag` are what it substitutes. Both base Deployments (`streamlit-deployment.yaml`, `rq-worker-deployment.yaml`) reference `image: openms-streamlit`; the overlay's `name: openms-streamlit` matches that literal and rewrites it to `<ghcr-ref>:<tag>`. If you change this field, no rewrite happens and the cluster pulls a non-existent `openms-streamlit:latest` and gets `ImagePullBackOff`. Leave it alone.

About the `||` in the IngressRoute match — both TLDs always go in. The OpenMS infra publishes apps on both `.de` and `.org` so users land on the same app no matter which they remember. One IngressRoute, two `Host(...)` matchers OR-ed together is the right shape; do not split into two IngressRoute objects.

## Step 4 — Optional storage resize

Skip this step if the user accepted the 400 Gi default.

Otherwise **two** claims move together, because the app no longer mounts a volume directly — it claims space out of the one the NFS server exports:

```yaml
# 1. k8s/storage/nfs-backing-pvc.yaml — the Cinder volume Ganesha exports
spec:
  resources:
    requests:
      storage: <backing size>

# 2. k8s/base/workspace-pvc.yaml — what the app claims out of it
spec:
  resources:
    requests:
      storage: <size>     # Q7: e.g. 100Gi, 1Ti, 3Ti
```

The app's claim must stay **materially below** the backing volume, and the backing volume grows first. nfs-provisioner `statfs()`es the export on every provision and refuses outright any claim larger than the *free* space it finds there — unconditionally, not gated on quotas — and a fresh filesystem never reports its full nominal size. The stock pair is 400Gi against 500Gi; keep a comparable margin, or the claim never binds and every pod stays `Pending` behind it.

Do **not** rename either PVC, the base `kustomization.yaml` resource list, or the `claimName` in `streamlit-deployment.yaml` / `rq-worker-deployment.yaml`. Kustomize's `namePrefix` already gives the in-cluster workspaces PVC a unique per-fork name; renaming the base creates a multi-file cascade for no benefit.

Operator caveat (mention in handoff, not your job to verify): in-place expansion of an *already-deployed* PVC requires the StorageClass to have `allowVolumeExpansion: true`, and that applies to the backing `cinder-csi` claim. If the class does not allow expansion, growing a live volume requires recreation, not a manifest edit. Sizing on first deploy is unaffected.

## Step 5 — Handoff

After committing the edits, tell the user the next steps belong to a human operator (or CI) and are out of scope for you:

1. Open a PR with the overlay edits and have it reviewed.
2. Merge to `main`. CI (`build-and-test.yml`) rebuilds and pushes the image to GHCR with the tag from Q3. The kind integration jobs (`test-nginx`, `test-traefik`) auto-discover slug and Traefik hostnames from the overlay output, so no workflow edits are needed for fork-specific values.
3. Cluster operator applies the fork's storage tier first (`kubectl kustomize --enable-helm k8s/storage/ | kubectl apply -f -`), then `kubectl apply -k k8s/overlays/prod/`. That order matters — the overlay's PVC names a StorageClass the storage tier publishes.
4. Operator verifies with `kubectl -n openms rollout status deployment/<slug>-streamlit` and a browser check on `https://<sub>.webapps.openms.de`, then `kubectl -n openms get pods -o wide -l component=rq-worker` to confirm the workers came up on **different** nodes, each with `.status.qosClass` of `Guaranteed`.

## Reference files

- Overlay: `k8s/overlays/prod/kustomization.yaml`
- Worker/Streamlit sizing components: `k8s/components/memory-tier-{low,high}/` — `worker-resources.yaml` + `streamlit-resources.yaml`, pod sizes only, no node selection
- Base manifests: `k8s/base/*.yaml`
- Storage tier: `k8s/storage/` — NFS-Ganesha serving the RWX workspace volume
- CI workflow: `.github/workflows/build-and-test.yml` (build + lint + kind integration)
- In-app reference: the "Developers Guide: Kubernetes Deployment" Documentation page in the running Streamlit app.

## Checklist

- [ ] Step 1 recon done; fork's `k8s/` layout matches expectations (or the user was asked because it didn't)
- [ ] Interview completed; defaults shown to the user and confirmed/overridden
- [ ] `namePrefix`, `commonLabels.app`, `images[0].newName`, `images[0].newTag` written in the overlay
- [ ] IngressRoute patch written: both `.de` and `.org` hostnames, plus the `<slug>-streamlit` service reference
- [ ] Redis URL written in both Deployment patches (`streamlit` and `rq-worker`)
- [ ] Worker size component selected (Q5)
- [ ] Worker replica count (Q6) patched into the overlay only if it differs from the base default; the base Deployment left untouched
- [ ] No `nodeSelector`, `nodeName`, `nodeAffinity` or `openms.de/memory-tier` anywhere in the overlay or the components — `assert_no_node_pinning_anywhere` fails the PR on any of them
- [ ] Storage sizes in `k8s/storage/nfs-backing-pvc.yaml` and `k8s/base/workspace-pvc.yaml` changed together, backing volume materially larger, and only if the user picked a non-default size; PVC names and `claimName`s untouched
- [ ] `.github/workflows/build-and-test.yml` uses dynamic overlay discovery (no `template-app` / `template.webapps.openms.*` literals); patched in if the fork's workflow was on the old hardcoded shape
- [ ] Changes committed on a feature branch (no PR opened unless the user asked for one)
