> **What this is.** The operational runbook for the NFS-Ganesha storage tier
> that makes the workspace volume ReadWriteMany, so the app can run on more than
> one Kubernetes node. It covers the cutover, the verification matrix and the
> rollback, and it is the authority several manifests in `k8s/` point at by name.
>
> It records the design as of the multi-node work on the de.NBI Berlin cluster.
> Cluster-specific values (node CIDRs, volume sizes, node names) are examples,
> not settings to copy. See `docs/kubernetes-deployment.md` for the general
> deployment guide.

# A16 cutover runbook — PR 2

Companion to `docs/a16-storage-decisions.md`. That file records *what* was decided; this one
records *how to do it and how to undo it*.

Closes open items 3, 4, 5 and 6. Items 1 (`mount.nfs` probe) and 2 (memory-ceiling
declaration) remain open and are noted where they bite.

---

## 0. Pre-flight

**Blocking — item 1.** Decides whether clients mount via the in-tree `nfs:` type
or need csi-driver-nfs in `kube-system`:

```bash
kubectl get nodes -o name          # then, for EACH node returned:
kubectl debug node/<node-name> -n openms -it --image=busybox -- \
  sh -c 'ls -l /host/sbin/mount.nfs* /host/usr/sbin/mount.nfs* 2>&1;
         echo ---; grep nfs /host/proc/filesystems'
```

Run against both nodes — a node pool can drift. Missing helper means
csi-driver-nfs, **not** installing `nfs-common` via a DaemonSet: Kubermatic
replaces nodes on upgrade, so package installation becomes a permanent obligation
with a race window on every new node.

**Non-blocking but do it first.** PR 1 must be merged and deployed — the
`params.json` Fix 1, the `tasks.py` re-raise, and the `src/Workflow.py` return
value. Without the re-raise, queue mode reports every failure as success and none
of section 4's verification below means anything.

---

## 1. Fixed fsid — open item 3, decided

**Set `Export_Id: 1` and `device-based-fsids: false`. Never change either.**

The value itself is arbitrary; its *stability* is the whole point. With
`device-based-fsids: true` (the chart default) Ganesha derives NFS file handles
from the backing device's major/minor number, and a Cinder volume's `/dev/vdX`
minor is not stable across re-attach. Every client then gets `ESTALE` after the
first NFS pod restart — typically weeks later, with no obvious cause and no
correlation to the change that caused it.

Record it in the values file with a comment stating that changing it invalidates
every client's file handles, because the next person to read this will otherwise
treat it as a tunable:

```yaml
# Export_Id is part of every NFS file handle handed to every client.
# Changing it, or enabling device-based-fsids, invalidates all of them:
# clients get ESTALE until they remount. It is not a tunable. Do not touch.
storageClass:
  ...
nfs:
  exportId: 1
  deviceBasedFsids: false
```

Verify after deploy — the export should show a stable fsid independent of the
device:

```bash
kubectl -n template-app-storage exec "$(kubectl -n template-app-storage get pod -l app=nfs-server -o name | head -n 1)" -- \
  sh -c 'grep -i "Export_Id\|Fsid" /export/vfs.conf 2>/dev/null || cat /etc/ganesha/ganesha.conf'
```

---

## 2. `.demos` seeding race — open item 4, fix

`streamlit-deployment.yaml:25-26` currently runs, in an initContainer, under
`replicas: 2`:

```sh
mkdir -p /workspaces-streamlit-template/.demos
cp -rn /app/example-data/workspaces/. /workspaces-streamlit-template/.demos/
```

Two failure branches, one silent and one fatal:

- **Silent**: `cp` writes in place with no temp-and-rename, so pod B can see a
  file pod A is still writing, decide it exists, and skip it — permanently. A
  truncated demo workspace that never repairs itself.
- **Fatal**: `-n` does not apply to directories, and `mkdirat`/`openat(O_EXCL)`
  returning `EEXIST` is a hard `exit 1` — so the losing pod ends in
  `Init:CrashLoopBackOff` and never self-resolves.

Both get worse with RWX, because the two replicas can now genuinely run at the
same moment on different nodes.

**Fix — copy to a private temp directory, then rename. A lock file is the wrong
tool; `rename(2)` on a directory is already atomic.**

```sh
set -eu
DEST=/workspaces-streamlit-template/.demos
if [ -d "$DEST" ]; then
  echo "demos already seeded"
  exit 0
fi
TMP="${DEST}.tmp.$$"
rm -rf "$TMP"
mkdir -p "$TMP"
cp -r /app/example-data/workspaces/. "$TMP"/
# mv -T onto an existing non-empty directory fails, which is exactly what we
# want: the winner renames, the loser cleans up and exits 0.
if mv -T "$TMP" "$DEST" 2>/dev/null; then
  echo "demos seeded"
else
  echo "lost seeding race, another replica won"
  rm -rf "$TMP"
fi
```

Note the `if [ -d ]; then … fi` rather than `[ -d ] && exit 0` — under `set -e`
the latter exits non-zero when the directory is absent, which is the common path.

---

## 3. Cutover

Decision 4 provisions a **fresh** Cinder PVC in `template-app-storage` rather than
migrating the existing one, so the old volume stays intact and untouched
throughout. That is what makes section 5 cheap.

1. Create `template-app-storage`, labelled `pod-security.kubernetes.io/enforce=privileged`.
2. Label `openms` explicitly `enforce=baseline` — do not rely on the absent label.
3. Provision the new Cinder PVC in `template-app-storage`.
4. Deploy Ganesha with `existingClaim`, `Export_Id: 1`, `deviceBasedFsids: false`,
   `strategy: Recreate`, 1 replica, and **explicit memory request and limit**.
5. Apply the default-deny ingress plus the two allow rules on 2049: the
   pod-label-scoped one admitting `app: template-app` in `openms`, and an
   `ipBlock` for the cluster's node addresses. **The second is not optional
   and ships as a placeholder.** The provisioner emits in-tree `nfs:` PVs,
   which the kubelet mounts from the node's own address in the host network
   namespace — that matches no `podSelector`, so with the placeholder left in
   place every mount hangs. Read the addresses from `kubectl get nodes -o wide`
   and narrow the range as far as it will go; check it does not contain the pod
   CIDR, which would hand every pod in the cluster root over every workspace.
6. Create the PVC in `openms` on the new StorageClass, mounted at the unchanged
   path `/workspaces-streamlit-template`. It is a NEW claim, `workspaces-nfs-pvc`,
   not an edit of `workspaces-pvc`: a bound PVC's spec is immutable apart from
   `resources.requests`, so `kubectl apply` would be rejected outright, and the
   only way past that is deleting a claim whose `cinder-csi` class reclaims with
   `Delete` — destroying the volume section 5 rolls back to.
7. Seed `.demos` via the fixed initContainer above, and create the `.nfs-probe`
   sentinel.
8. Repoint the streamlit and rq-worker Deployments at the new claim. Delete the
   `nodeselector.yaml` patches; keep the `memory-tier-*` components as resource
   patches; set requests == limits.
9. Deploy the storage canary and the sidebar indicator.

---

## 4. Verification — open item 5

Run in order. Each is a pass/fail assertion, not an observation. **Stop at the
first failure**; later steps assume earlier ones passed.

### 4.1 The thing the whole project is for

```bash
kubectl -n openms get pods -o wide -l app=template-app
```

**Assert:** at least two pods, on **two different nodes**, all `Running`.
This is the acceptance criterion for the entire exercise — if every pod is still
on one node, nothing was achieved regardless of what else passes.

### 4.2 Shared visibility, cross-node

From a pod on node A, then a pod on node B:

```bash
# node A
kubectl -n openms exec <pod-a> -- sh -c 'echo hello-from-a > /workspaces-streamlit-template/.crosscheck'
# node B
kubectl -n openms exec <pod-b> -- cat /workspaces-streamlit-template/.crosscheck
```

**Assert:** `hello-from-a`. Close-to-open consistency guarantees this on a fresh
`open()`; if it fails, the mount options are wrong.

### 4.3 POSIX features the codebase actually requires

```bash
kubectl -n openms exec <pod-a> -- sh -c '
  cd /workspaces-streamlit-template
  ln -sf /app/example-data/mzML/Control.mzML .symcheck && readlink .symcheck   # absolute symlink
  echo x > .rncheck.tmp && mv .rncheck.tmp .rncheck && echo rename-ok          # atomic rename
  flock .rncheck -c "echo flock-ok"                                            # advisory locking
  rm -f .symcheck .rncheck'
```

**Assert:** an absolute path from `readlink`, `rename-ok`, and `flock-ok`.

Absolute symlinks are non-negotiable — `common.py:179`, `:678` and
`fileupload.py:91` all call `symlink_to(x.resolve())`, so demo seeding breaks
without them. `flock` is not needed today but is the intended lock backend for
Fix 3, so failing here changes that decision to a Redis lock.

### 4.4 End-to-end workflow

Run a real workflow through the UI, small enough to finish quickly.

**Assert:** it completes, results appear in `results()`, and the log renders. Then
confirm the failure signal actually works — this is what PR 1 bought:

```bash
kubectl -n openms exec deploy/rq-worker -- \
  python -c "from redis import Redis; from rq import Queue; import os;
             q=Queue('openms-workflows', connection=Redis.from_url(os.environ['REDIS_URL']));
             print('failed:', len(q.failed_job_registry))"
```

**Assert:** a deliberately broken workflow lands in the failed registry. Before
PR 1 this count was structurally always zero, so a non-zero value here is the
proof that PR 1 works.

### 4.5 Ganesha restart — the routine case

```bash
kubectl -n template-app-storage delete pod -l app=nfs-server
```

**Assert:** clients block rather than erroring (this is `hard` mounts working as
intended); a workflow running throughout **completes**; the sidebar indicator goes
red then green within ~30s of the pod becoming ready plus the grace period.

This is the single most valuable test in the list, because a Ganesha restart is a
routine event and this is exactly the case a `soft` mount would have corrupted.

### 4.6 Detection

```bash
kubectl -n template-app-storage scale statefulset -l app=nfs-server --replicas=0
```

**Assert:** within ~30s the `rq-worker` pod reports `0/1 Ready`; the sidebar
indicator shows unreachable; **Streamlit stays `Ready` and keeps serving** — that
last one verifies decision 7's reversal, that a wedged mount degrades the app
rather than removing it from service. Scale back to 1 and confirm recovery.

---

## 5. Rollback — open item 6

**Rollback is cheap by construction**, because the cutover never touched the
original volume.

**Trigger it if:** 4.1 shows pods still co-located after the nodeSelector removal;
4.3 fails on symlinks or atomic rename; 4.5 shows workflows dying rather than
blocking through a restart; or sustained `ESTALE` appears in worker logs.

**Procedure** — one apply, roughly a minute:

1. `kubectl -n openms scale deploy/streamlit deploy/rq-worker --replicas=0`
2. Re-apply the previous manifests: Deployments mounting the **original**
   `workspaces-pvc` in `openms`, with the `memory-tier-low` nodeSelector restored.
   That claim is still Bound to its Cinder volume — the cutover created
   `workspaces-nfs-pvc` alongside it and never touched it — so there is no
   restore step, only an apply.
3. Scale back up. Everything lands on one node again, as before.
4. `kubectl -n template-app-storage scale statefulset -l app=nfs-server --replicas=0` — leave the
   namespace and its volume in place for diagnosis rather than deleting them.

**What is lost:** anything written since cutover. Acceptable under decision 2, and
the same loss the 7-day GC inflicts on schedule anyway.

**What is not lost:** the original Cinder volume, untouched throughout.

**Do not** delete the `template-app-storage` PVC while diagnosing — `reclaimPolicy` is
`Delete`, so removing the claim destroys the volume and the evidence with it.

---

## 6. After cutover — first week

- Watch the sidebar indicator for unexplained red flaps: that is `ESTALE` from an
  fsid problem, and it appears late rather than immediately.
- Watch worker memory against the new requests == limits. Guaranteed QoS means the
  pod is killed at its limit rather than being allowed to borrow, so a limit that
  was previously generous headroom is now a hard wall.
- Measure before assuming: per-volume Cinder throughput and node NIC speed are both
  unknown, and they set the real concurrent-user ceiling described in decision 11.
