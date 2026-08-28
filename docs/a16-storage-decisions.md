> **What this is.** The decision record behind the NFS-Ganesha storage tier —
> what was chosen, what was rejected, and why. Manifest comments in `k8s/storage/`
> cite it by decision number when a value is deliberate rather than arbitrary.
>
> It is a snapshot of the reasoning at the time of the multi-node work, not a
> living document. Where it disagrees with the code, the code is current.

# A16 implementation — decision record

Outcome of a design interview, 2026-08-19. Subject: running a Ganesha NFS-server
pod on a Cinder ReadWriteOnce volume to synthesise RWX, so the OpenMS
streamlit-template can use both de.NBI Berlin nodes.

Ten questions, all answered, plus a concurrency assessment added afterwards.
Each entry records the decision, not the debate.

---

## Locked decisions

### 1. A16 is the destination, not a bridge
Consequence: the NFS server must be hardened rather than tolerated, and the
server image is a multi-year commitment.

### 2. Availability posture — outage accepted, recovery is destructive
A storage-node failure is a **total outage for all users**, not 1/N. Accepted
deliberately.

Recovery does **not** require de.NBI support, because the data is disposable:
provision a fresh Cinder volume, repoint the claim, restart. Losing in-flight
workspaces is acceptable — the app already deletes them on a timer.

Backups are handled with OpenStack tooling, outside Kubernetes, which also
defuses the `reclaimPolicy: Delete` hazard recorded in `docs/storage-defect-register.md`.

> Open: confirm those are Cinder *backups* rather than only *snapshots*. If
> snapshots live in the same Ceph pool as the volume, a backend failure takes
> both — acceptable for a bridge, weak for a destination.

### 3. Server: sig-storage Ganesha, pinned by digest
`kubernetes-sigs/nfs-ganesha-server-and-external-provisioner`, chart configured
with `existingClaim` so the zero-migration property is preserved.

Rejected: `itsthenetwork/nfs-server-alpine` (last pushed 7+ years ago, needs
`privileged` plus host kernel modules) and `openebs/dynamic-nfs-provisioner`
(archived). Userspace Ganesha avoids kernel-module dependencies on node images
that de.NBI controls, not us.

**Mandatory settings, not optional:**

- `device-based-fsids: false`, with a fixed fsid. It defaults to `true` and
  derives NFS file handles from the backing device's major/minor, which is not
  stable across Cinder re-attach. Left alone, every client ESTALEs after the
  first NFS pod restart — weeks later, with no obvious cause.
- `strategy: Recreate`. The default `RollingUpdate` deadlocks: the new pod
  cannot mount the RWO claim while the old one still holds it.
- 1 replica. The chart supports no more, which is consistent with decision 2.
- **Explicit memory request and limit on the Ganesha pod.** The chart default is
  modest, and N concurrent write streams mean N sets of buffers and dirty page
  cache in one userspace process. Left at defaults, heavy load OOMKills it —
  every client then hangs on `hard` mounts and eats the ~90s NFSv4 grace period
  on restart, with the same load waiting when it returns. This is the one
  genuine collapse mode in the design, and it is a one-line fix.

### 4. Namespace layout — Option B, split
- **New `openms-storage`**, labelled `pod-security.kubernetes.io/enforce=privileged`.
  Holds Ganesha and the Cinder PVC.
- **`openms`** labelled `enforce=baseline` explicitly, rather than relying on the
  absence of a label.
- **No volume migration.** Provision a fresh Cinder PVC in the new namespace,
  seed `.demos`, cut over. The disposable-data property makes the usual
  patch-PV / clear-claimRef / rebind surgery unnecessary, and the old volume
  stays intact as an instant rollback.

Rationale: `openms` is shared with another application (`app=nuxl-app`), and
Ganesha exports `no_root_squash`. Keeping the storage tier in its own namespace
means the exemption covers only the component that needs it.

### 5. Ordering — fixes, then storage, then spread
Three PRs, in order:

1. **`params.json` Fix 1** + `tasks.py` re-raise + the `src/Workflow.py` return
   value.
2. `openms-storage` + Ganesha + the NFS-backed PV.
3. Delete the memory-tier `nodeselector.yaml` patches, keep the components as
   resource patches, set requests == limits, and add the second worker. See
   decision 10 — the tier is now the pod size, not the node.

PR 1 is not optional. Until `tasks.py:143-148` re-raises instead of returning a
dict, queue mode reports every failure as success — so the cutover in PR 2 could
not be validated against anything.

**Fix 1** (required before A16): stop `get_parameters_from_json` laundering read
failures into `{}`. Ten lines, zero runtime I/O. Separates *file absent* —
legitimately `{}` — from *read failed*, which must never become `{}`, because
the caller merges the result and writes it back. On NFS this is the case that
matters: a single user alone on the system loses every stored parameter when the
NFS server restarts and the read returns ESTALE.

**Fix 2** (atomic writes) deferred. When it lands: use
`tempfile.mkstemp(dir=path.parent)`, **not** a pid-based temp name —
Streamlit runs every session as a thread inside one process, so all concurrent
sessions in a pod share a pid and would interleave into one temp file. Also note
Fix 2 adds ~4 metadata operations per widget render on a metadata-bound
filesystem; measure it after cutover and consider debouncing the save.

**Fix 3** (locking) deferred until the second worker exists. When it lands,
prefer `flock` on the params file over a Redis lock: NFSv4.1 has integrated
locking, so the lock and the data live on the same filesystem and cannot
diverge — whereas the current Redis (1 replica, 256Mi, `--appendonly no`) could
only support an advisory lock needing a fencing token.

### 6. Mount options — `hard`, NFSv4.1
- **`hard`**, not `soft`. The data is disposable but the *jobs* are not: a soft
  mount converts a brief server restart into a truncated featureXML, which is
  the one failure class the 7-day retention does not cover. Clients block and
  resume instead.
- **NFSv4.1** — integrated locking (needed for Fix 3), a single port 2049 with
  no separate NLM/statd (which makes the NetworkPolicy tractable), and stateful
  reclaim.
- **`nconnect=4`** — nodes run kernel 6.8, and it helps the metadata-heavy
  access pattern specifically.
- **Default `actimeo`** — close-to-open consistency already guarantees a fresh
  read on every `open()`, and `Logger` closes per message while the UI reopens
  per second. Lowering it would add GETATTR traffic for no correctness gain.
- **Default grace period.** Accept ~90s of degraded service after any Ganesha
  restart, during which locks are reclaimed but new ones are refused.

### 7. Detection — signal only, never self-heal
With `hard` mounts the failure mode is a hang, not an error, and nothing in the
system currently detects one: `health.py` inspects only Redis and RQ,
`/_stcore/health` is filesystem-blind, `rq-worker` has no probes, and RQ's parent
process keeps heartbeating while its work horse is blocked in an NFS syscall.

- **Readiness probe only on `rq-worker`**: `timeout 5 stat …/.nfs-probe`.
  Readiness has no traffic effect on a worker, so it is purely an alertable
  signal.
- **Never a liveness probe on `rq-worker`.** It would kill in-flight TOPP jobs,
  and restarting cannot fix NFS — a crash loop that destroys work while the
  fault persists.
- **NOT in Streamlit's readiness probe.** An earlier draft put the mount check
  there so a wedged mount produced an honest 503. Reversed: with `hard` mounts a
  saturated share makes `stat` exceed the probe timeout, so the probe would pull
  every Streamlit pod out of Traefik and the app would go *down* under exactly
  the load it should survive. The probe timeout would silently become a
  load-shedding threshold. Degradation should be visible, not fatal — the
  sidebar indicator carries that signal instead.
- **TCP liveness on Ganesha's 2049.** The one place a liveness probe is correct.
- The `.nfs-probe` sentinel is exempt from the 7-day GC twice over:
  `clean-up-workspaces.py:27` skips dot-names, and it only considers directories.

### 8. Sidebar storage indicator
Follows the existing `monitor_queue()` pattern at `common.py:231` —
`@st.fragment(run_every=5)` backed by a function in `health.py`, rendering
nothing in local mode when `REDIS_URL` is unset.

**The sidebar must never touch the filesystem.** A `stat` on a `hard`-mounted
wedged path blocks in uninterruptible sleep and cannot be killed, so a fragment
re-running every 5 seconds would accumulate unkillable threads — the indicator
would become the hang.

Inverted design:

```
canary pod                                    sidebar
  stat .nfs-probe ──ok──▶ SETEX storage:ok:<node> 30 ──▶ reads Redis only
       └── blocks on wedged NFS ──▶ key expires ──▶ indicator goes red
```

- Redis TTL *is* the liveness mechanism; no timeout logic to get wrong.
- Key per node via the Downward API, or a healthy node masks a wedged one.
- **Three states**: connected / unreachable / **unknown when Redis is down**.
  A red tick caused by a dead Redis sends you debugging the wrong layer.
- Prefer a separate small canary Deployment over a thread in `rq-worker`.

### 9. NetworkPolicy — pod-label-scoped
Ingress rule in `openms-storage`, admitting only pods labelled
`app: template-app` — which the prod overlay already sets via `commonLabels`.
Plus a default-deny ingress in that namespace. No egress rules.

Namespace-scoping was rejected: it would grant NuXL's pods root read/write to
every workspace, undoing the reason for the namespace split. Add
`openms-storage` to the CI kustomize render check so label drift appears as a
diff rather than as a 3am mount failure.

### 10. Worker topology — tiers become pod sizes, not node labels

**Fixed worker count. No autoscaling, no per-job pods, no dispatcher.** KEDA,
`ScaledJob` and the RQ-worker-as-dispatcher options are all out.

**The tier moves from the node to the pod.** Instead of
`openms.de/memory-tier: high|low` node labels plus a `nodeSelector`, each worker
Deployment is simply *sized*: N small workers with small requests/limits, M large
workers with large ones. The cluster then places them wherever they fit.

Why this is better than what the interview had landed on:

- **It deletes a defect instead of working around it.** `D2` in `docs/storage-defect-register.md` — the
  unscoped `nodeSelector` patching `kind: Deployment` with no name — stops needing
  to be scoped, because the `nodeselector.yaml` patches are removed outright. The
  `memory-tier-*` components survive as *resource* patches, which is exactly what
  is now wanted.
- **It scales without redesign.** At 100 nodes there are no labels to maintain and
  no per-tier node pools to balance. A large worker asks for its memory and lands
  wherever there is room.
- **`topologySpreadConstraints` start working.** A13 found they produce a false
  pass today, because `maxSkew` is measured over *eligible* domains and the
  nodeSelector left exactly one eligible node. With the selector gone every node is
  eligible, so `maxSkew: 1` genuinely enforces the spread.
- **The cleanup CronJob problem disappears.** `D1` — the CronJob hanging on
  Multi-Attach because it carries no placement constraint — is moot once the volume
  is RWX.

**Consequence that is now architectural, not advisory: requests must equal limits.**
The pod size *is* the tier, so a large worker requesting 2Gi against a 180Gi limit
would be schedulable anywhere and would then OOM. Setting requests == limits gives
Guaranteed QoS and `oom_score_adj = -997` instead of today's burstable ~937.
Previously a recommendation; under this design the architecture does not work
without it.

**Queue strategy: one queue per size class.** A job is routed by choosing the queue
matching the smallest size class that fits. Each worker still watches exactly one
queue name, so RQ's crash-safe `BLMOVE` dequeue stays engaged. The routing function
itself is trivial; the interesting part is how a workflow declares its ceiling —
see the open item below.

**Revisit trigger.** Fixed workers statically partition capacity. That is correct
at the current size and stops being correct as node count grows, because the split
becomes a guess that is wrong most of the time and fragmentation appears. Revisit
when node count grows materially or when the large-tier workers are observed idle
while the small-tier queue backs up. Instrumentation for that already exists:
`health.py` reads per-queue depth and worker state for the sidebar.

### 11. Concurrent write behaviour under DIA load

Assessed for ~30 concurrent users each producing ~100 GB of output over a run.

**Accepted: the design degrades before it collapses.** NFS has no per-client QoS,
so all writers share one queue at the server, and `hard` mounts mean nobody errors
— they wait. Saturation therefore presents as everything slowing together rather
than as corruption. That is an acceptable failure mode here.

Two caveats recorded rather than solved:

- **There are no bulkheads.** One pathological workflow degrades every user,
  including the UI, because everything mounts the same share. Accepted.
- **`.osw` and `.sqMass` are SQLite** — small random writes plus an `fsync` per
  commit, each of which is a synchronous round trip over NFS. Synchronous op
  latency, not bandwidth, is what saturates first; you can be far below the NIC's
  capacity and still be fully queued. NFSv4.1's integrated locking makes this
  *supported*, not *fast*.

**Escape hatch if writes do saturate**, not adopted now: write results to
node-local scratch during the run and promote to the shared tier on completion.
That converts N hours-long streams of small synchronous writes into N bulk
sequential copies, and keeps SQLite on local disk where it belongs. It composes
with everything above — no change to Ganesha, the namespace layout or the mount
options. Cost: results are not visible until the workflow finishes, and a crashed
pod loses them.

**Unmeasured.** de.NBI Berlin's per-volume Cinder throughput, whether QoS caps
apply, and node NIC speed are all unknown, and they set the real ceiling. A load
test of N pods writing concurrently plus a representative SQLite commit workload
would find the knee where latency goes non-linear — that number is the true
concurrent-user limit, and it will be smaller than the bandwidth arithmetic
suggests.

---

## Open items

| # | Item | Blocks |
|---|---|---|
| 1 | Does the node have `mount.nfs`? Decides in-tree `nfs:` PV vs csi-driver-nfs in `kube-system`. Probe: `kubectl debug node/<n> -n openms …` | PR 2 |
| 2 | How a workflow **declares its memory ceiling** — constant, class attribute, or a callable over (params, inputs, threads). The routing function is trivial; the declaration is the design. Research outline at `../job-tier-routing` | PR 3 |
| ~~3~~ | ~~Fixed fsid value~~ — **closed**: `Export_Id: 1`, `deviceBasedFsids: false`, never changed. See `docs/a16-storage-runbook.md` §1 | — |
| ~~4~~ | ~~`.demos` seeding race~~ — **closed**: copy-to-temp plus `mv -T`, script in `docs/a16-storage-runbook.md` §2 | — |
| ~~5~~ | ~~Cutover verification~~ — **closed**: six ordered pass/fail assertions in `docs/a16-storage-runbook.md` §4 | — |
| ~~6~~ | ~~Rollback procedure~~ — **closed**: `docs/a16-storage-runbook.md` §5. Cheap by construction, since the cutover never touches the original volume | — |

---

## Facts established during the interview

Cluster, verified live:

- `openms` carries **no** `pod-security.kubernetes.io/*` labels, so it inherits
  the built-in default of `privileged`. Confirmed empirically — a pod requesting
  `DAC_READ_SEARCH` admits.
- `default` and `kubernetes-dashboard` carry `enforce=baseline`; `kube-system`,
  `kube-public`, `kube-node-lease` and `cloud-init-settings` carry `privileged`.
  So PSA is applied per namespace, not cluster-wide.
- `kubectl auth can-i create daemonsets -n kube-system` → **yes**;
  `update namespaces` → **yes**. csi-driver-nfs is installable.
- **`openms` is shared with another application**, labelled `app=nuxl-app`.
- A `traefik` namespace exists and is unlabelled.

Codebase, verified by reading:

- Retention is **7 days**, not two weeks — `clean-up-workspaces.py:15`,
  hardcoded, with no env var or settings key.
- Nothing enumerates the workflow directory itself; every `iterdir()` in
  `src/workflow/` targets a subdirectory. A `params.json.*.tmp` sibling is inert.
- `health.py` inspects only Redis and RQ, and is wired to `common.py:235` for
  sidebar display — not as a probe endpoint.
- `os.getpid()` is not unique per session: Streamlit runs sessions as threads
  within one process.

New defect found during the interview — see `docs/storage-defect-register.md` entry D7.
