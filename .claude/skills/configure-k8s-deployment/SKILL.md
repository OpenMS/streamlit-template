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
- OpenStack Manila with an NFS share type and enough share quota for one more share of the Q7 size.
- The `openms` namespace and the cluster's storage tier (once per cluster, shared by every app) already applied by the cluster's admin, publishing the `ReadWriteMany` StorageClass `openms-manila-nfs` the workspaces PVC names. Both are cluster configuration, not part of the app or the template (`docs/kubernetes-deployment.md` section 3b). Without them every pod sits `Pending`.
- **No node labels, of any kind.** Nothing under `k8s/` selects a node any more: the scheduler places pods and the manifests only declare how big a worker is. The `openms.de/memory-tier` labels the older components matched are gone, and CI fails any manifest that reintroduces a `nodeSelector`, `nodeName` or `nodeAffinity` (`assert_no_node_pinning_anywhere`).
- Room for `<replicas> x <worker size>` (Q5 and Q6) across the cluster's nodes. A worker is Guaranteed QoS, so its request is reserved for as long as the pod runs, queue empty or not.
- DNS for `*.webapps.openms.de` and `*.webapps.openms.org` pointing at the cluster's Traefik load balancer.

## Step 1 — Recon the fork

Before asking the user anything, read a small known set of files directly (do not delegate to a subagent — the surface area is fixed):

1. `git remote get-url origin` and the repo name → seeds the slug and GHCR ref defaults.
2. `k8s/overlays/prod/kustomization.yaml` — if anything has already been edited away from the template stub, treat those values as the user's prior choices to confirm rather than overwrite blindly.
3. `k8s/base/kustomization.yaml`, `k8s/base/streamlit-deployment.yaml`, `k8s/base/rq-worker-deployment.yaml`, `k8s/base/workspace-pvc.yaml` — confirm the layout still matches the template:
   - PVC `metadata.name` is `workspaces-manila-pvc`, `ReadWriteMany`, on `storageClassName: openms-manila-nfs`.
   - Deployments reference `image: openms-streamlit` (the placeholder Kustomize swaps).
   - `streamlit-deployment.yaml` and `rq-worker-deployment.yaml` both carry `claimName: workspaces-manila-pvc`. Being RWX, that claim constrains placement not at all: the workspace-using pods are placed independently by the scheduler, not co-located, and there is no pod-affinity rule pulling them together either.
   - `rq-worker-deployment.yaml` has a fixed `replicas` and a `topologySpreadConstraints` block over `kubernetes.io/hostname` with `maxSkew: 1`. Read the replica count from here — it is the default you propose in Q6.
4. `k8s/storage/` and `k8s/overlays/prod/namespace.yaml` — neither should exist (both are cluster configuration now). If either is still there, the fork predates that change: tell the user it needs a template sync first (`sync-from-template`) and stop.
5. `.github/workflows/build-and-test.yml` — confirm which tags CI publishes (the OpenMS template publishes `<branch>-full`, `<branch>-simple`, `<tag>-full`, `<tag>-simple`, plus `latest` on `main`-full pushes).

If any of those files are missing, renamed, or significantly restructured, stop and ask the user how to proceed. Do not pattern-match the standard answers onto an unknown layout.

## Step 2 — Interview the user

Ask the user the questions below in 3 batched `AskUserQuestion` turns rather than one long sequential interrogation. Group related questions together: slug + subdomain + GHCR ref + tag make a coherent identity batch, and worker size + replica count + storage size make a coherent capacity batch — they trade against each other and against the same cluster.

Each question must include:

- the **default** you are proposing (derived from Step 1),
- a one-line **"what this controls in the running deployment"** explanation,
- the **reasoning** for the default.

The user confirms or overrides each one. Do not omit the "what this controls" line — the user needs to understand the deployment effect of their answer before committing to it.

### Q1. App slug

- *What this controls:* every Kubernetes resource for this app gets prefixed with `<slug>-` (Pods, Services, PVCs, ConfigMaps), so the slug is what cluster operators see in `kubectl get pods/svc/pvc -n openms`. It also becomes the DNS name worker pods use to reach Redis (`<slug>-redis`), and the name of its workspace claim (`<slug>-workspaces-manila-pvc`).
- *Default:* repo name lowercased, with `streamlit-` / `-template` prefixes/suffixes stripped. Examples: `OpenDIAKiosk` → `opendiakiosk`; `umetaflow-gui` → `umetaflow-gui`; `streamlit-template` → `template-app`.
- *Format:* single lowercase token, no spaces.

### Q2. GHCR image reference

- *What this controls:* which container image the cluster pulls. A wrong value here means `ImagePullBackOff` and no app comes up.
- *Default:* `ghcr.io/<owner>/<repo>` lowercased, derived from the `origin` remote.

### Q3. Image tag

- *What this controls:* the release image a new deployment starts from. Under Argo CD the ImageUpdater in `k8s/argocd/` then deploys every later release (pre-releases included) by itself, so this tag never needs bumping; CI also loads its test image under it. Without Argo CD it is the deployed build: a release tag like `v1.2.3-full` pins it, `main-full` follows `main` whenever the operator re-applies.
- *Default:* the app's current release image (`<release-tag>-full`); `main-full` only if the app has no release yet. The `-simple` variant uses a lighter `Dockerfile_simple`; pick that only if the user explicitly wants the lightweight image.

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
- *Default:* **50 Gi** (matches the stock base, so the default needs zero file edits).
- *Note on naming (do not ask the user):* the PVC base name stays `workspaces-manila-pvc` for every fork. Kustomize's `namePrefix: <slug>-` automatically scopes it to `<slug>-workspaces-manila-pvc` in the cluster, so cross-fork name collisions are impossible. Override the size only — never rename the PVC.

## Step 3 — Apply the answers to `k8s/overlays/prod/kustomization.yaml`

Edit the file in place. The overlay never lists a Namespace: the shared `openms` namespace is cluster configuration. The full templated shape is:

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

## Step 4 — Storage tier (nothing to edit)

The storage tier is shared by every app on the cluster and carries no app name: one Manila CSI driver, one StorageClass `openms-manila-nfs`, kept in the cluster's own configuration. Each fork's workspace PVC gets the overlay's `namePrefix` and, with it, a Manila share of its own.

## Step 5 — Optional storage resize

Skip this step if the user accepted the 50 Gi default.

Otherwise change one number, the size of this app's Manila share, in the claim patch of the prod overlay (never in `k8s/base/`, which is template-owned):

```yaml
# k8s/overlays/prod/kustomization.yaml
patches:
  - target:
      kind: PersistentVolumeClaim
      name: workspaces-manila-pvc
    patch: |
      - op: replace
        path: /spec/resources/requests/storage
        value: <size>     # Q7: e.g. 100Gi, 1Ti, 3Ti
```

and `deploy.k8s.storage` in `app.yaml` to the same value (`python -m utils.app_spec` compares them). The share counts against the project's Manila share quota; mention that in the handoff.

Do **not** rename the PVC, the base `kustomization.yaml` resource list, or the `claimName`s. Kustomize's `namePrefix` already gives the in-cluster workspaces PVC a unique per-fork name.

The StorageClass allows volume expansion, so growing an already-deployed share later is the same edit plus a re-apply. Shrinking a deployed share is not possible in place (Kubernetes rejects it and Argo CD then stops syncing that commit): the claim, its PV and the share in Horizon have to be deleted and the claim created again, empty. The steps are in `docs/kubernetes-deployment.md`, section on the workspace PVC.

## Step 6 — Handoff

After committing the edits, tell the user the next steps belong to a human operator (or CI) and are out of scope for you:

1. Open a PR with the overlay edits and have it reviewed.
2. Merge to `main`. CI (`build-and-test.yml`) rebuilds and pushes the image to GHCR with the tag from Q3. The kind integration jobs (`test-nginx`, `test-traefik`) auto-discover slug and Traefik hostnames from the overlay output, so no workflow edits are needed for fork-specific values.
3. The cluster's admin makes sure the `openms` namespace and the storage tier exist (cluster configuration, once per cluster), then the operator runs `kubectl apply -k k8s/overlays/prod/` (or hands the app to Argo CD). That order matters — the overlay's PVC names a StorageClass the storage tier publishes.
4. Operator verifies with `kubectl -n openms rollout status deployment/<slug>-streamlit` and a browser check on `https://<sub>.webapps.openms.de`, then `kubectl -n openms get pods -o wide -l component=rq-worker` to confirm the workers came up on **different** nodes, each with `.status.qosClass` of `Guaranteed`.

## Reference files

- Overlay: `k8s/overlays/prod/kustomization.yaml`
- Worker/Streamlit sizing components: `k8s/components/memory-tier-{low,high}/` — `worker-resources.yaml` + `streamlit-resources.yaml`, pod sizes only, no node selection
- Base manifests: `k8s/base/*.yaml`
- Storage tier: cluster configuration (OpenStack Manila CSI and the shared `openms-manila-nfs` StorageClass, once per cluster); `k8s/ci-storage/` is CI's in-cluster stand-in
- CI workflow: `.github/workflows/build-and-test.yml` (build + lint + kind integration)
- In-app reference: the "Developers Guide: Kubernetes Deployment" Documentation page in the running Streamlit app.

## Checklist

- [ ] Step 1 recon done; fork's `k8s/` layout matches expectations (or the user was asked because it didn't)
- [ ] Interview completed; defaults shown to the user and confirmed/overridden
- [ ] No Namespace in the overlay (the `openms` namespace is cluster configuration)
- [ ] `namePrefix`, `commonLabels.app`, `images[0].newName`, `images[0].newTag` written in the overlay
- [ ] IngressRoute patch written: both `.de` and `.org` hostnames, plus the `<slug>-streamlit` service reference
- [ ] Redis URL written in both Deployment patches (`streamlit` and `rq-worker`)
- [ ] Worker size component selected (Q5)
- [ ] Worker replica count (Q6) patched into the overlay only if it differs from the base default; the base Deployment left untouched
- [ ] No `nodeSelector`, `nodeName`, `nodeAffinity` or `openms.de/memory-tier` anywhere in the overlay or the components — `assert_no_node_pinning_anywhere` fails the PR on any of them
- [ ] Workspace size changed in `k8s/base/workspace-pvc.yaml` and `app.yaml` together, only if the user picked a non-default size; PVC names and `claimName`s untouched
- [ ] `.github/workflows/build-and-test.yml` uses dynamic overlay discovery (no `template-app` / `template.webapps.openms.*` literals); patched in if the fork's workflow was on the old hardcoded shape
- [ ] Changes committed on a feature branch (no PR opened unless the user asked for one)
