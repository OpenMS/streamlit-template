---
name: configure-k8s-deployment
description: Use when deploying an OpenMS Streamlit app to Kubernetes, or when working with the kustomize base, components or overlays.
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
- A storage class that provisions `ReadWriteOnce` volumes (de.NBI: `cinder-csi`) for the workspaces PVC. For live grows of it, the class needs `allowVolumeExpansion: true`.
- Nodes labelled `openms.de/memory-tier=low` and `openms.de/memory-tier=high`. The memory-tier component (Q5) puts a matching `nodeSelector` on every Deployment and the cleanup CronJob, so all of the app's pods land on one node and share the single `ReadWriteOnce` workspace volume.
- Room on that node for the worker's requests (Q5) next to the Streamlit, Redis and sync pods.
- DNS for `*.webapps.openms.de` and `*.webapps.openms.org` pointing at the cluster's Traefik load balancer.

## Step 1 — Recon the fork

Before asking the user anything, read a small known set of files directly (do not delegate to a subagent — the surface area is fixed):

1. `git remote get-url origin` and the repo name → seeds the slug and GHCR ref defaults.
2. `k8s/overlays/prod/kustomization.yaml` — if anything has already been edited away from the template stub, treat those values as the user's prior choices to confirm rather than overwrite blindly.
3. `k8s/base/kustomization.yaml`, `k8s/base/streamlit-deployment.yaml`, `k8s/base/rq-worker-deployment.yaml`, `k8s/base/workspace-pvc.yaml` — confirm the layout still matches the template:
   - PVC `metadata.name` is `workspaces-pvc`, `ReadWriteOnce`, `storageClassName: cinder-csi`.
   - Deployments reference `image: openms-streamlit` (the placeholder Kustomize swaps).
   - `streamlit-deployment.yaml`, `rq-worker-deployment.yaml`, `sync-deployment.yaml` and `cleanup-cronjob.yaml` all carry `claimName: workspaces-pvc`. The claim is `ReadWriteOnce`, so every pod that mounts it has to run on the same node; the memory-tier component's `nodeSelector` is what keeps them there.
   - `rq-worker-deployment.yaml` has `replicas: 1` and a `RollingUpdate` strategy with `maxSurge: 0`.
4. `.github/workflows/build-and-test.yml` — confirm which tags CI publishes (the OpenMS template publishes `<branch>-full`, `<branch>-simple`, `<tag>-full`, `<tag>-simple`, plus `latest` on `main`-full pushes).

If any of those files are missing, renamed, or significantly restructured, stop and ask the user how to proceed. Do not pattern-match the standard answers onto an unknown layout.

## Step 2 — Interview the user

Ask the user the questions below in 3 batched `AskUserQuestion` turns rather than one long sequential interrogation. Group related questions together: slug + subdomain + GHCR ref + tag make a coherent identity batch, and memory tier + storage size make a coherent capacity batch.

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

### Q5. Memory tier

- *What this controls:* which node the app runs on and how much memory and CPU **the RQ worker** may use. The component sets a `nodeSelector` (`openms.de/memory-tier: <tier>`) on every Deployment and the cleanup CronJob, and sizes the worker. Too small and TOPP tools are OOMKilled mid-workflow.
- *Default:* `memory-tier-low` — worker requests 1Gi / 500m, limited to 16Gi / 4 cpu, correct for ~90% of template forks.
- *Override prompt:* "Does this app run DIA spectral-library construction, OpenSwath peak picking, DIA-LFQ, or comparable heavy OpenMS workloads?" If yes → `memory-tier-high`: requests 2Gi / 2 cpu, limited to 180Gi / 20 cpu, on the high-memory node.
- *If neither number fits:* edit `k8s/components/memory-tier-<tier>/worker-resources.yaml`. The cluster-side ceiling is the `LimitRange` in `k8s/base/limitrange.yaml`.

### Q6. Workspace storage size

- *What this controls:* the persistent disk allocated for Streamlit session workspaces, uploaded files, intermediate analysis outputs, and any reference data the app seeds at startup. Too small → users hit "no space left" mid-analysis; too large → wasted cluster storage budget.
- *Default:* **500 Gi** (matches the stock base, so the default needs zero file edits).
- *Note on naming (do not ask the user):* the PVC base name stays `workspaces-pvc` for every fork. Kustomize's `namePrefix: <slug>-` automatically scopes it to `<slug>-workspaces-pvc` in the cluster, so cross-fork name collisions are impossible. Override the size only — never rename the PVC.

## Step 3 — Apply the answers to `k8s/overlays/prod/kustomization.yaml`

Edit the file in place. First delete `k8s/overlays/prod/namespace.yaml` and its `- namespace.yaml` entry under `resources:`: the shared `openms` namespace is managed only by the template's own deployment, and two Argo CD Applications carrying it would keep taking it over from each other. The full templated shape is:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - ../../base

components:
  - ../../components/memory-tier-<tier>          # Q5: low | high — node and worker size

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

About `images[0].name: openms-streamlit` — **this is the match key, not a value the user picks.** Kustomize's `images:` transformer is find-and-replace: `name` is the literal image string Kustomize searches for in the rendered manifests, and `newName`/`newTag` are what it substitutes. Both base Deployments (`streamlit-deployment.yaml`, `rq-worker-deployment.yaml`) reference `image: openms-streamlit`; the overlay's `name: openms-streamlit` matches that literal and rewrites it to `<ghcr-ref>:<tag>`. If you change this field, no rewrite happens and the cluster pulls a non-existent `openms-streamlit:latest` and gets `ImagePullBackOff`. Leave it alone.

About the `||` in the IngressRoute match — both TLDs always go in. The OpenMS infra publishes apps on both `.de` and `.org` so users land on the same app no matter which they remember. One IngressRoute, two `Host(...)` matchers OR-ed together is the right shape; do not split into two IngressRoute objects.

## Step 4 — Optional storage resize

Skip this step if the user accepted the 500 Gi default. Otherwise edit the size in `k8s/base/workspace-pvc.yaml`:

```yaml
spec:
  resources:
    requests:
      storage: <size>     # Q6: e.g. 100Gi, 1Ti, 3Ti
```

Do **not** rename the PVC, the base `kustomization.yaml` resource list, or the `claimName`s. Kustomize's `namePrefix` already gives the in-cluster workspaces PVC a unique per-fork name; renaming the base creates a multi-file cascade for no benefit.

Operator caveat (mention in handoff, not your job to verify): in-place expansion of an *already-deployed* PVC requires the StorageClass (`cinder-csi`) to have `allowVolumeExpansion: true`. If the class does not allow expansion, growing a live volume requires recreation, not a manifest edit. Sizing on first deploy is unaffected.

## Step 5 — Handoff

After committing the edits, tell the user the next steps belong to a human operator (or CI) and are out of scope for you:

1. Open a PR with the overlay edits and have it reviewed.
2. Merge to `main`. CI (`build-and-test.yml`) rebuilds and pushes the image to GHCR with the tag from Q3. The kind integration jobs (`test-nginx`, `test-traefik`) auto-discover slug and Traefik hostnames from the overlay output, so no workflow edits are needed for fork-specific values.
3. On a cluster where the template's deployment does not run (so nothing has created the shared namespace yet), the operator first runs `kubectl create namespace openms --dry-run=client -o yaml | kubectl apply -f -`; it is a no-op where the namespace exists. Then the cluster operator runs `kubectl apply -k k8s/overlays/prod/` (or registers the Argo CD Application in `k8s/argocd/`).
4. Operator verifies with `kubectl -n openms rollout status deployment/<slug>-streamlit` and a browser check on `https://<sub>.webapps.openms.de`, then `kubectl -n openms get pods -o wide -l app=<slug>` to confirm every pod runs on the node of the chosen memory tier.

## Reference files

- Overlay: `k8s/overlays/prod/kustomization.yaml`
- Memory-tier components: `k8s/components/memory-tier-{low,high}/` — `nodeselector.yaml` + `cronjob-nodeselector.yaml` (node), `worker-resources.yaml` + `streamlit-resources.yaml` (sizes)
- Base manifests: `k8s/base/*.yaml`
- CI workflow: `.github/workflows/build-and-test.yml` (build + lint + kind integration)
- In-app reference: the "Developers Guide: Kubernetes Deployment" Documentation page in the running Streamlit app.

## Checklist

- [ ] Step 1 recon done; fork's `k8s/` layout matches expectations (or the user was asked because it didn't)
- [ ] Interview completed; defaults shown to the user and confirmed/overridden
- [ ] `k8s/overlays/prod/namespace.yaml` and its `resources:` entry deleted (only the template's deployment manages the `openms` namespace)
- [ ] `namePrefix`, `commonLabels.app`, `images[0].newName`, `images[0].newTag` written in the overlay
- [ ] IngressRoute patch written: both `.de` and `.org` hostnames, plus the `<slug>-streamlit` service reference
- [ ] Redis URL written in both Deployment patches (`streamlit` and `rq-worker`)
- [ ] Memory-tier component selected (Q5)
- [ ] Storage size in `k8s/base/workspace-pvc.yaml` changed only if the user picked a non-default size; PVC name and `claimName`s untouched
- [ ] `.github/workflows/build-and-test.yml` uses dynamic overlay discovery (no `template-app` / `template.webapps.openms.*` literals); patched in if the fork's workflow was on the old hardcoded shape
- [ ] Changes committed on a feature branch (no PR opened unless the user asked for one)
