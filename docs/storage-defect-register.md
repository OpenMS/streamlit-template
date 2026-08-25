> **What this is.** The defect register compiled while making this template run
> across multiple nodes: verified defects in the workflow framework, the
> Kubernetes manifests and the CI, each with the evidence that established it.
> Source comments and tests cite these IDs (`A2`, `G1`, `D2`, …) to explain what
> a guard is defending against.
>
> **Not all of these are fixed.** It is a register of what was found, not a list
> of what was resolved, and it records the state at the time of that work. Check
> the code before assuming an entry is still live.

# Verified defect register

Found while researching node-distributed deployment, 2026-08-17/18.
**Every item here is independent of the distribution question** — these are bugs
in `main` today. Several are made dramatically worse by adding a second node,
which is noted where it applies.

Provenance is stated per entry:

- **[repo]** — verified by reading this repository directly during the session.
- **[agent]** — verified by a research agent against external source
  (CPython, Kubernetes, RQ, Streamlit) and not independently re-checked here.
- **[agent+repo]** — agent finding, confirmed against this repository.

---

## A. Silent data loss

### A1. `@st.cache_data` memoises a side-effecting write **[agent+repo]**
`src/fileupload.py:9`

`save_uploaded_mzML` is decorated with `@st.cache_data`, but its whole purpose
is the side effect of writing files. The destination is read from
`st.session_state.workspace` *inside* the body, so it is **not part of the cache
key**; Streamlit keys `UploadedFile` on name + content.

Upload a file to workspace A, then upload the byte-identical, same-named file to
workspace B: cache hit, body never executes, **the file is never written to
workspace B**, and the cached `st.success("Successfully added uploaded files!")`
is replayed so the user is told it worked.

Live today. `replicas: 2` makes it non-deterministic (per-replica cache), not
better. Fix: drop the decorator, or key on the workspace explicitly.

### A2. A torn `params.json` read permanently deletes parameters **[agent+repo]**
`ParameterManager.py:136`, `:207-212`, `:190-191`, `:377-378`

`save_parameters` is a read-modify-write:

- `:136` — `json_params = self.get_parameters_from_json() | json_params`
- `:207-212` — `get_parameters_from_json` wraps the read in a bare `except:`
  that returns `{}` after showing *"Attempting to load an invalid JSON parameter
  file. Reset to defaults."*
- `:190-191` / `:377-378` — the write is `open(path, "w")` + `json.dump`,
  truncate-then-rewrite with no temp-file + `os.replace`.

So a single transient torn read makes the merge `{} | this_session_params`, and
that is written back — **permanently erasing `_defaults`, `_flag_params`, and
every other tool's saved values**, while telling the user it was a deliberate
reset.

`os.replace` alone does **not** fix this. It prevents third parties observing a
torn file; it does nothing about lost update or the empty-dict laundering. The
lock is the load-bearing half. Reported reproducible on current `main` in ~15
minutes with two processes.

---

## B. Failures reported as successes

### B1. Queue mode can never report a failed workflow **[repo]**
`src/workflow/tasks.py:108`, `:143-148`

`:108` logs the `WORKFLOW FINISHED` marker unconditionally, without inspecting
what `execution()` returned. `:143-148` **returns a dict** from the exception
handler instead of re-raising.

RQ therefore records every job as finished successfully, including crashed ones.
Consequences: `health.py`'s `failed_jobs` metric is structurally always zero;
`Retry` would be inert for application failures; no queue-mode UI can show a
failure.

### B2. The success signal is inverted in the other direction too **[repo]**
`src/Workflow.py:54`

Annotated `-> None` and returns nothing, so `workflow_process()` never logs the
marker and a **successful** local run renders "Errors occurred, check log file."
Documented in CLAUDE.md; combined with B1 the signal is wrong in both modes, in
opposite directions.

### B3. An ImportError renders "Workflow completed successfully" **[agent+repo]**
`src/workflow/tasks.py:46-55` vs `:60`

The module imports and `importlib.import_module` run **before** the `logs/`
rmtree at `:60`. An ImportError therefore appends `ERROR:` to the *previous*
run's log, and `classify_log_outcome` substring-searches the whole file — so
`StreamlitUI.py:1569-1571` reports success for a workflow that never started.
The `st_ctime` displayed at `:1564` is inode change time, so the stale log even
looks fresh.

Fix: slice the log from the last `STARTING WORKFLOW`. ~5 lines;
`tests/test_log_status.py` already exists.

### B4. A killed pod shows "running" forever **[repo]**
`StreamlitUI.py:1509-1513`

```python
pid_exists = self.executor.pid_dir.exists() and list(self.executor.pid_dir.iterdir())
if not is_running and pid_exists:
    is_running = True
```

This does not merely read `pids/` as a hint — it **overrides an authoritative
"not running" from the queue**. A SIGKILLed pod never reaches
`CommandExecutor.py:150` to unlink its PID file, so the UI shows
"Workflow running..." on a 1s rerun loop indefinitely, after RQ has already
finished or failed the job.

---

## C. Log loss

### C1. Tool output is truncated by a race **[agent+repo]**
`CommandExecutor.py:185-186`, `:201-202`

Both reader threads `break` as soon as `process.poll() is not None`, discarding
whatever is still buffered in the pipe.

Reproduced with the repository's exact reader code and latency injected in place
of `Logger.log`:

| per-line reader latency | buggy | fixed |
|---|---|---|
| 0 ms | 1000/1000 | 1000/1000 |
| 0.5 ms | **3**/1000 | 1000/1000 |
| 2.0 ms | **1**/1000 | 1000/1000 |

Two consequences. It is a **race**, so a naive regression test passes against the
buggy code — latency injection is load-bearing in any test. And because
`Logger.log` does open/write/close per line, a network filesystem puts it
squarely in the 0.5–2 ms band: **distribution converts a latent race into ~99.9%
silent log loss.**

Correction to an earlier belief: this does **not** discard the
`WORKFLOW FINISHED` / `WORKFLOW CANCELLED` markers. Those are written directly
by `Logger` from the Python process and never traverse the subprocess pipe.
What is lost is the tool's own output — the diagnostic you need *after* the run
has already been marked failed.

The correct idiom already exists in this repo at `src/run_subprocess.py:29`
(`output == "" and process.poll() is not None`), which makes the
`CommandExecutor` version look like an editing accident.

### C2. `bufsize=1  # Line buffered` is a no-op **[agent]**
`CommandExecutor.py:123`

`Popen` passes `line_buffering` only to the **stdin** wrapper; stdout/stderr get
`line_buffering=False` and `bufsize` normalises to `-1`.

### C3. `src/run_subprocess.py` can deadlock **[agent]**
Drains stdout fully, then stderr — so a child filling the 64 KiB stderr pipe
buffer blocks forever.

---

## D. Kubernetes manifests

### D1. Nightly workspace cleanup can die permanently and silently **[repo]**
`k8s/base/cleanup-cronjob.yaml`

The CronJob mounts the RWO PVC but carries **no placement constraint** — the
memory-tier component patches `kind: Deployment`, and a CronJob is not one. It
can therefore be scheduled on the node where the Cinder volume is not attached
and hang on Multi-Attach. With `concurrencyPolicy: Forbid`, one hung job blocks
**every** subsequent cleanup, with no error surface.

Check: `kubectl get cronjob,jobs -A | grep -i cleanup`

### D2. The memory-tier nodeSelector is unscoped **[repo]**
`k8s/components/memory-tier-{low,high}/nodeselector.yaml`

Patches `target: {kind: Deployment}` with **no name**, so
`openms.de/memory-tier` lands on `streamlit`, `rq-worker` *and* `redis`.

This is why the second node is unusable — and it means an RWX storage migration
would **silently do nothing**: everything would stay pinned, and the migration
would look like it succeeded.

### D3. `rq-worker` has no probes, no grace period, no PDB **[repo]**
`k8s/base/rq-worker-deployment.yaml`

Zero probes (streamlit and redis have two each), so a worker wedged on a dead
mount is invisible indefinitely. No `terminationGracePeriodSeconds`, so the 30s
default kills an hour-long job 30s into a drain. No PodDisruptionBudget.

### D4. `k8s/base/ingress.yaml` is a dead dependency **[agent]**
kubernetes/ingress-nginx was archived read-only on 2026-03-24 — no further
security patches; the mooted successor was abandoned.

### D5. Nothing reaps zombies **[agent]**
RQ's `wait_for_horse` calls `os.wait4(self.horse_pid, 0)` — a specific pid,
never `waitpid(-1)`. The manifest runs `exec rq worker`, so PID 1 is the worker.
`kill_horse` uses SIGKILL, so this fires on every cancellation.

Manifest-only fix: `shareProcessNamespace: true` makes the pause container PID 1,
which reaps with `waitpid(-1, NULL, WNOHANG)`. No image rebuild.

### D6. `docs/kubernetes-deployment.md:81` is wrong **[agent]**
Asserts the VolumeBinding plugin pins pods to the node holding the attached
volume. It does not — `volume_binding.go` checks PV *node affinity* only. The
scheduler will place a pod on the wrong node; you get a Multi-Attach hang at
attach time, not a scheduling refusal.

### D7. The 7-day GC can delete workspaces that are actively in use **[repo]**
`clean-up-workspaces.py:15`, `:32`

Two things, found during the A16 design interview.

First, retention is **7 days**, not the two weeks it is often described as:
`threshold = current_time - (86400 * 7)`, hardcoded, with no env var or
settings key.

Second, and worse: line 32 uses `os.path.getmtime(directory)` on the *top-level
workspace directory*. A directory's mtime changes only when an entry directly
inside it changes. Once `mzML-files/` and the workflow directory exist, nothing
a user does refreshes it — writing `topp-workflow/params.json` touches the
workflow directory's mtime, not the workspace's, and `page_setup()`'s
`mkdir(parents=True, exist_ok=True)` does not update mtime on an existing
directory.

So a user working in the same workspace for eight days has it deleted underneath
them on day seven, mid-session, while actively using it.

Fix: walk for the newest mtime beneath the workspace rather than reading the top
directory's own, or touch the workspace directory in `page_setup()`. The walk is
more correct; the touch is one line.

---

## E. Concurrency, smaller

All **[agent+repo]** unless noted.

- `WorkflowManager.py:94` — `pid_dir.mkdir()` without `exist_ok`, and it runs
  *after* the child is spawned at `:91`.
- `Logger.py:26-28` — exists-then-mkdir TOCTOU.
- `CommandExecutor.py:413` — writes python-tool params to a **fixed** path in the
  workflow dir, unlinked at `:419`. Two concurrent runs collide.
- `tasks.py:96-97` — the `results/` rmtree has **no** `ignore_errors` (unlike
  `logs/` at `:60`) and raises into the generic handler; `:97` mkdirs without
  `exist_ok`.
- `WorkflowManager.py:64` — `job_id` is built from the workflow **slug** plus
  `int(time.time())`, not the workspace. Two users, same workflow, same second
  collide — and RQ without `unique=True` does no collision detection, silently
  overwriting existing job data for a reused id.
- seed-demos `cp -rn` under `replicas: 2` — has a silent branch (cp writes in
  place with no temp+rename, so a pod can skip a file another is still writing,
  permanently) and a fatal one (`EEXIST` is a hard exit 1, and `-n` never applies
  to directories) → `Init:CrashLoopBackOff` that never self-resolves. Fix is
  copy-to-temp plus `mv -T`, not a lock file.

---

## G. Configuration silently ignored, and unvalidated input

### G1. `max_threads.online` has been dead code for 6.5 months **[agent]**
`CommandExecutor.py:39`, regression from `eb9c205` (PR #333, 2026-01-31)

At the streamlit 1.49.1 tag, `get_session_state()` returns a lazily-created
**empty global mock** when there is no `ScriptRunContext`, rather than raising.
Inside the RQ work horse there is no context, so
`st.session_state.get("settings", {})` is `{}`, `online_deployment` reads
`False`, and the **local** branch runs. The effective budget is
`params.json["max_threads"]` or the hardcoded literal `4` — never
`max_threads.online: 2`.

PR #333's final step moved the helper out of `common.py`, where session state
did exist. Live since 2026-01-31; quantms-web is affected identically.

### G2. Any anonymous session can set the shared worker's thread budget **[agent]**
The params-import uploader writes uploaded JSON verbatim — **no reserved-key
filter and no clamp**. `max_threads` is a reserved key per CLAUDE.md, and
nothing enforces that. On a shared online deployment an anonymous visitor can
therefore set the worker's thread budget to an arbitrary value.

### G3. The 16Gi memory limit buys no OOM protection **[agent]**
`k8s/components/memory-tier-low/worker-resources.yaml`

Burstable `oom_score_adj = 1000 - 1000 * memRequest / capacity`, so the 1Gi
request scores ~969 against BestEffort's 1000. **Only the request affects OOM
ranking; the limit does not.** Compounding it, `MSGFPlusAdapter` defaults
`java_memory` to 3500 MB *per process* divided by nothing — four concurrent
adapters ask 14 GB against that 16Gi limit.

Note the standard advice, "just delete the CPU limit", is a trap here: every
auto-detecting runtime reads the *limit* and falls back to the **node**, never
the request.

---

## F. Configuration and CI

- `requirements.txt:142-143` — `rq>=1.16.0` and `redis>=5.0.0` are **unbounded**,
  so rebuilds install RQ 2.11 today. Features are present but not guaranteed;
  the unbounded floor is itself a supply-chain risk. **[repo]**
- `.github/workflows/build-and-test.yml:593`, `:733` — the
  `sed 's|storageClassName: cinder-csi|standard|g'` silently no-ops the moment
  the PVC stops naming `cinder-csi`, so kind CI would quietly stop exercising the
  storage path. **[repo]**
- `.streamlit/config.toml:14` — `maxUploadSize = 200` MB, against routinely
  larger mzML. **[repo]**
- CI runs `kubeconform -kubernetes-version 1.28.0`, which will reject
  `matchLabelKeys` (added in 1.29) if anti-affinity work adopts it. **[agent]**

---

## Suggested order

The dependency that matters most: **`replicas: 1` currently serialises the queue,
and that is the only reason A2 and the E-group races are not firing.** A second
worker makes them reachable for the first time.

1. **B1, B2, B3** — make failures visible. Everything else is unverifiable until
   a failed run reports as failed. Small, no dependencies.
2. **A1, A2** — the two silent data-loss bugs. A2 needs the lock, not just
   atomic writes.
3. **C1** — delete the `poll()` break. Note it increases log volume, which makes
   the per-second whole-file re-read at `StreamlitUI.py:1546` worse, so pair it
   with a decision about log transport.
4. **D1, D2, D3, G1, G3** — manifest and config; no algorithmic risk.
   Note the CPU oversubscription originally suspected here is largely absent:
   `TOPPBase` registers `-threads` with default 1 and calls
   `omp_set_num_threads()` before `main_()`, so it is a real hard cap. Memory,
   not CPU, is the binding resource.
5. Only then anything from the distribution work itself.
