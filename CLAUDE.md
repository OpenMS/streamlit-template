# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

It is template-owned: every app gets this file unchanged through the template sync. What is specific to one app (its purpose, its own modules, its commands and gotchas) goes in the app-owned `CLAUDE.app.md`, imported here:

@CLAUDE.app.md

## What This Is

**The standard framework for building web applications for mass spectrometry (MS) data analysis**, used across the OpenMS ecosystem for proteomics and metabolomics research. It wraps **OpenMS/pyOpenMS** (the leading open-source C++/Python library for computational MS) and its **TOPP tools** (~200 command-line tools for MS pipelines) into interactive Streamlit apps.

Production apps built from this template: **quantms-web** (quantitative proteomics), **umetaflow** (untargeted metabolomics), **FLASHApp** (top-down proteomics).

### MS Domain Context

- **Input data**: mzML (raw spectra), featureXML (detected features), consensusXML (features linked across samples), idXML (peptide/protein IDs), traML (targeted transitions)
- **Workflows chain TOPP tools**: e.g. `FeatureFinderMetabo` (detect LC-MS features) → `FeatureLinkerUnlabeledKD` (align across runs) → custom Python post-processing
- **Proteomics** = peptide/protein ID + quantification (`MSGFPlusAdapter`, `FidoAdapter`, `ProteinQuantifier`); **metabolomics** = feature detection + annotation (`FeatureFinderMetabo`, `MetaboliteAdductDecharger`, `SiriusAdapter`)
- **MS visualizations**: mass spectra (m/z vs intensity), chromatograms (RT vs intensity), peak maps (RT vs m/z heatmaps), isotope patterns, fragment ion annotations, volcano plots

## Agent operating rules

Standing rules for an agent (Claude Code or another) working on the template or on an app made from it: which repository a change goes to, what to build it with, and what every pull request needs. What the user asks for in the session wins over these.

### Which repository gets the change

- **Template first.** A change goes as a PR to `OpenMS/streamlit-template` when it touches a template-owned file (anything not listed in `sync.app_owned` of the app's `app.yaml`: `src/workflow/`, `src/common/`, `src/layout_manager/`, `src/data_import/`, `src/sync/`, `docker/`, the Dockerfiles, `k8s/base`, `k8s/components`, `.github/`, `electron/`, `.claude/`, this file), when a second app would want it, or when it fixes a bug the template has too. It reaches the apps through the template sync (`template-sync.yml`, or a merge of the template's `main` into the app), never by editing the template-owned file in the app. App-specific behaviour in template-owned code becomes a template option (a parameter whose default keeps the old behaviour, a `settings.json` key, a method the app overrides), not a fork of the file. Skill `upstream-to-template` splits such a change out of app work; `sync-from-template` brings it back.
- **App repository** for what the app owns: its workflow and python tools, its result pages and viewer components, its presets and parameter names, its identity (`settings.json`, hosts, overlay patches), its own dependencies in `requirements.txt` (most apps list it in `sync.app_owned`; where one does not, `sync-from-template` resolves the conflict) and its `CLAUDE.app.md`.
- **openms-insight** (`t0mdavid-m/OpenMS-Insight`) for visualization components and for component features any app could use: a new plot or component, an option of an existing one, a rendering or linking bug. The app then only configures the component. Until openms-insight releases the change, an app PR may depend on its branch or a dev build (see *Releases*).
- **One PR per repository** when a change spans several, each naming the PRs it needs, merged in dependency order: openms-insight, then the template, then the app's template sync, then the app.
- Merge template-sync PRs with a merge commit, never squash, or the next sync conflicts again.

### What to build with

- **Visualizations: OpenMS-Insight first** (`Table`, `LinePlot`, `Heatmap`, `VolcanoPlot`, `SequenceView`, the spectrum components), linked through one shared `StateManager` and arranged with the layout manager's view bar. pyopenms-viz or plotly only where no Insight component fits; when a generic component is missing, add it to openms-insight rather than writing a one-off plot in the app.
- **Data processing: TOPP tools** through `executor.run_topp()`, so the run gets progress, cancellation and the processing report. **pyOpenMS for glue code**: reading and converting results, small steps between tools. A Python reimplementation of something a TOPP tool does needs a stated reason; a missing algorithm or option belongs in OpenMS.
- **Template features before new code**: run folders and follow-up runs, the view bar, experimental design, upload and import widgets, presets, `parameter-names.json`. Extend one of them (in the template) before building a parallel mechanism in an app.

### Pull requests

- **Show every visual change.** Attach screenshots, and a short video for an interaction, of what the change looks like in the running app (before and after when it changes something existing; light and dark theme when colors are involved). Upload them to the PR; skill `verify-webapp-usability` drives a headless browser.
- **Describe the change on its own terms**: what it does for users and why. Do not name competing or third-party tools, or "parity", in a PR title or description.
- Run the repository's tests and pylint (*Commands*) on what you changed before pushing, and add a test when you fix a bug.

### Releases

- **Every openms-insight change a release depends on must be in a published openms-insight version on PyPI**, and the app's `requirements.txt` pins that version (`openms-insight==X.Y.Z`, as `upgrade-openms-insight` does). No git branches, dev builds, wheels from elsewhere or unreleased versions in a release; if the needed change is not on PyPI yet, release openms-insight first. Skills `release-app` and `upgrade-openms-insight`.

### Secrets

- **Never put a password, token or other credential in plaintext anywhere on GitHub**: code, commits, PR and issue text, CI logs. Store only a hash in a repository (as `developer_mode.password_sha256` does) or inject the value through a Kubernetes secret or a GitHub Actions secret. `.streamlit/secrets.toml` stays untracked.

## Commands

All commands run **from the repo root** — tests and the app resolve paths relative to CWD (`settings.json`, `content/…`, `example-data/…`).

```bash
# Setup. pytest and fakeredis are NOT in requirements.txt.
pip install -r requirements.txt
pip install pytest fakeredis

# Run the app
streamlit run app.py

# Tests — three separate groups, no conftest.py and no pytest config anywhere
python -m pytest test_gui.py tests/      # what ci.yml runs
python -m pytest test.py                 # what workflow-tests.yml runs (needs network)
python -m pytest                         # everything (default discovery finds all three)

# Single file / test / parametrized case
python -m pytest tests/test_topp_workflow_parameter.py
python -m pytest tests/test_queue_manager_cancel.py::test_cancel_missing_job_returns_false
python -m pytest "test_gui.py::test_launch[content/file_upload.py]"

# Lint (gating in CI, but --errors-only so it is permissive)
pylint $(git ls-files '*.py') --disable=C0103,C0114,C0301,C0411,W0212,W0631,W0602,W1514,W2402,E0401,E1101,F0001,R1732 --errors-only

# Docker (full image: OpenMS + TOPP tools; Dockerfile_simple: pyOpenMS only)
docker-compose up -d --build

# Kubernetes. TWO roots, and the storage one (once per cluster) goes first: it publishes the
# StorageClass workspace-pvc.yaml claims, so applying the overlay alone leaves
# every pod Pending. `apply -k` has no --enable-helm flag, hence the pipe.
kubectl kustomize k8s/overlays/prod/          # render + validate
kubectl kustomize --enable-helm k8s/storage/  # render + validate (needs helm)

kubectl kustomize --enable-helm k8s/storage/ | kubectl apply -f -
kubectl apply -k k8s/overlays/prod/
```

CI uses **Python 3.11** for all Linux test/lint jobs, the same as the Docker images and the desktop apps (pyOpenMS 3.6 and tornado 6.6 need it); `requirements.txt` was compiled against 3.12.

### Test suite shape

- `test.py` — unittest, downloads an mzML from GitHub with **no skip guard** (fails offline).
- `test_gui.py` — `streamlit.testing.v1.AppTest` smoke tests launching every page. `content/quickstart.py` is deliberately excluded (raises `StreamlitPageNotFoundError`).
- `tests/*.py` — unit tests. Redis is never required: queue tests use `pytest.importorskip("fakeredis")` at module level and inject `FakeStrictRedis`. TOPP binaries are never required either — `run_topp` tests mock `run_command` and assert on the *built command list*.
- Several tests swap `sys.modules['streamlit']` for a `MagicMock`, import the module under test, then purge `src.workflow.*` from `sys.modules` so `AppTest` still gets the real package. **Test ordering is load-bearing** — adding `pytest-xdist` or random ordering will break this.

## Architecture

```
app.py                    # Entry point — registers pages via st.Page() in a dict
settings.json             # App name/version, online_deployment, workspaces, threads, analytics, legal links
default-parameters.json   # Default workspace params (keys must match widget keys)
presets.json              # Named parameter sets per TOPP workflow
content/                  # One .py per Streamlit page
src/
  common/common.py        # page_setup(), load_params(), save_params(), show_fig(), show_table(), sidebar
  common/captcha_.py      # Captcha + GDPR consent gate (online mode only)
  common/admin.py         # Admin-password gate for "save workspace as demo"
  Workflow.py             # Example WorkflowManager subclass
  workflow/               # The TOPP Workflow Framework (see below)
  python-tools/           # Custom Python analysis scripts with DEFAULTS lists
  view.py, fileupload.py  # pyOpenMS plotting + mzML upload for the simple pages
utils/                    # Streamlit-free helpers (FASTA, digest) used by content/digest.py
docs/                     # Markdown rendered in-app by content/documentation.py
k8s/                      # Kustomize base + worker-size components + prod overlay
k8s/storage/              # SEPARATE root, once per cluster: OpenStack Manila CSI + the RWX StorageClass
k8s/ci-storage/           # CI only: in-cluster NFS-Ganesha publishing the same StorageClass for kind
k8s/storage-s3/           # OPTIONAL root, once per cluster: JuiceFS on an S3 bucket + S3 gateway (class openms-juicefs-s3)
docker/entrypoint.sh      # THE container entrypoint (redis + rq workers + streamlit [+ nginx])
```

### Runtime model: workspaces

Every session gets a **workspace directory** holding that user's files and parameters. `page_setup()` resolves it and guarantees `<workspace>/mzML-files/` exists.

- **Local** (`online_deployment: false`): workspace is a named dir (default `default`) under `../workspaces-<repository-name>`; the sidebar offers a create/switch/delete UI.
- **Online** (`online_deployment: true`): a fresh UUID workspace per session, exposed as the `?workspace=` query param so URLs are shareable. Root comes from `$WORKSPACES_DIR` (default `/workspaces-streamlit-template`).

**Starting from a demo.** `demo_workspaces.new_workspace` in settings.json names a demo workspace that every new online workspace starts from (and the local `default` workspace, with every other demo beside it), via `seed_new_workspace()`. On Linux `copy_demo_workspace()` links files of at least `LINK_MIN_BYTES` (1 MiB) and copies smaller ones (settings, the cache index, file lists), so a new session does not wait for the example data to be copied and writing a small file never changes the shared demo; an app that writes large result files in place must replace a link first. Without the key a new workspace starts empty.

`st.session_state.location` is `"local"` or `"online"` derived **solely from `online_deployment` in settings.json** (`src/common/common.py:466`). Workspace names are validated against path traversal by `is_safe_workspace_name()`. `clean-up-workspaces.py` deletes workspaces older than 7 days (k8s CronJob at 03:00; skips dot-dirs like `.demos/`).

### Local vs online differences

| | local | online |
|---|---|---|
| Workflow execution | own `python -c` process running `tasks.execute_workflow` | Redis/RQ queue |
| Captcha + GDPR consent | skipped (`controllo` forced true) | enforced |
| mzML upload | many files at once, or reference a local folder | one file at a time |
| Save-as-demo | hidden | shown if admin password set |
| Max threads | `max_threads.local`, user-overridable | the worker's cgroup CPU quota, else `max_threads.online` |

## Core Patterns

### Simple pages

```python
from src.common.common import page_setup, save_params
params = page_setup()
st.number_input("X", value=params["example-x-dimension"], key="example-x-dimension")
save_params(params)
```

`page_setup()` must be the first call — it loads settings, resolves the workspace, renders the sidebar and applies the captcha gate. Widget `key`s must exist verbatim in `default-parameters.json`; `save_params()` copies matching session-state values into `<workspace>/params.json`. Display-only pages skip `save_params()`. A page that skips `page_setup()` also misses the theme's layout style sheet (`tests/test_theme.py` checks every menu page calls it).

Register pages in `app.py` under a named section:

```python
pages = {"Section Name": [st.Page(Path("content", "my_page.py"), title="My Page", icon="🔬")]}
```

### TOPP workflows (WorkflowManager)

Subclass `WorkflowManager` (see `src/Workflow.py`) and implement four methods:

- `upload()` — `self.ui.upload_widget()`; files land in `<workflow_dir>/input-files/<key>/`
- `configure()` — `self.ui.input_TOPP()`, `self.ui.input_python()`, `self.ui.input_widget()`
- `execution()` — `self.file_manager.get_files()` to derive paths, then `self.executor.run_topp()` / `run_python()`
- `results()` — display outputs

Each workflow gets four thin content pages calling `wf.show_file_upload_section()` / `show_parameter_section()` / `show_execution_section()` / `show_results_section()`. An optional fifth page calls `wf.show_results_download_section(exclude=[...])`, which offers every file under `<workflow_dir>/results/` singly or as a ZIP (pass `exclude` for caches that are not results). Decorate `configure()` and `results()` with `@st.fragment`.

**Run flow.** The configure page ends with `wf.show_run_button(run_page, summary=...)`, a bar that sticks to the bottom of the window while the page scrolls, with an optional line on what will run beside the button (`sticky=False` draws the button alone). It saves the settings, opens the Run page and starts the workflow there at once (a session flag that `show_execution_section()` pops, so a reload never starts a second run; while a run is going it only opens the Run page). `show_execution_section(results_page=..., results_label=...)` offers the results page below the success message of a finished run; its button sets `st.session_state[latest_results_key(workflow_dir)]` (`src/workflow/StreamlitUI.py`), which a results page without run folders pops to show the newest result (a multi-run workflow shows the new run anyway). A user goes configure → run → results without a second click on Start. A workflow with run folders, or one that sets the class attribute `name_runs = True`, gets a name field beside the button (`name_label=`, default "Run name"): a run is given that name, and `execution()` of a workflow without run folders reads it with `self.run_name()` (kept apart from params.json as `last-run-name.txt`, empty when none was given).

**Multi-run workflows (opt-in, FLASHApp-style).** Set the class attribute `multi_run = True` on the subclass and every start becomes its own named result set instead of overwriting `results/`. Layout: `<workflow_dir>/runs/<run_id>/{run.json, params.json, results/, logs/}`, managed by the Streamlit-free `RunManager` (`src/workflow/RunManager.py`; widgets in `src/workflow/run_widgets.py`). What changes for the subclass:

- **Read and write results through `self.results_dir`**, never `Path(self.workflow_dir, "results")`. `FileManager.get_files(set_results_dir=...)` already targets the current run. In `execution()` it is the new run; in `results()` it is the run picked on the page.
- The Run page gets a run-name field; `show_results_section()` draws a run picker before calling `results()`; `show_results_download_section()` lists all runs (show, history, rename, ZIP download of results + params + logs, delete) above the per-file download of the picked run. A run's **History** (🕘, `run_widgets.run_history_section`, data from the Streamlit-free `run_history.py`) says how it came about (the run it follows, adds files to or reuses), its settings that differ from the defaults, its processing report and, for a workflow that sets the class attribute `configure_page`, **Start again with these settings** (`WorkflowManager.start_again` → `follow_up(run_id, page=configure_page)`), which opens the configure page with the run's files and settings.
- The picked run is shared by every page of the workflow (`run_widgets.get_selected_run`, default: newest finished run). Pages without a workflow object call `run_widgets.select_run(RunManager(workflow_dir))`; `wf.select_runs()` returns several ids for side-by-side comparisons.
- **Read a run's parameters from `self.runs.params(run_id)`**, not the workflow's `params.json` — that file holds the settings for the *next* run.
- **Follow-up runs.** `self.follow_up(run_id, changes={...}, page=..., note=...)` (`RunManager.restore_settings`) makes a run's parameters and its `experimental-design.tsv` (copied into each run at start) the workflow's again, with `changes` on top (a dict value is merged into the stored one), records `_follow_up` in `params.json` and switches to `page`; the Configure page then says whose settings these are, and the next run's processing report names the run it follows. **More files** for the same experiment: `follow_up(run_id, page=..., add_files="mzML-files")` empties that key (only the files picked then are processed) and records the next run as `adds_to` the experiment's first run in its `run.json`; `runs.experiment(run_id)` lists that run and every finished run adding to it, the run picker lists the experiment once (`runs.experiments()`, `get_selected_run` returns its first run), and the results page computes over all of them (`src/Workflow.py`'s `merge_feature_tables` matches the features of added runs). **An analysis added to a run** (the dialog of a view the run was not processed for): `follow_up(run_id, changes, page=..., same_files="mzML-files", keep=[tools])` takes exactly that run's files, drawn locked on the Configure page, and `input_TOPP()` of each tool in `keep` says its results are reused in place of its settings, so only the steps after them can be changed; `execution()` finds the run in `self.follow_up_info()["reuses"]` and takes those tools' results from it (the example adds the custom Python tool on the run's features), the new run sits next to the old one, and its processing report names the reused results. `start_from(..., same_files=key, files=[...], keep=[...], reuses=[ids])` is the same without run folders. An app without run folders calls `self.start_from(params, changes, name=..., page=...)` with the settings it stored for that result (`RunManager.apply_settings`). For more files it passes `adds_to=[<its result ids>]` and `files=[...]`; `execution()` reads them with `self.follow_up_info()` (the start keeps them in `last-follow-up.json`) and computes over the earlier results and its own. Offer it where a run lacks an analysis (see *Views the data was not processed for*).
- Queue mode passes `run_id` to `tasks.execute_workflow`; the worker writes into that run and marks it finished/failed. Stopping a run marks it cancelled.
- Switching an existing workflow to multi-run moves a non-empty `results/` into a run named "Earlier run" on first load (`RunManager.adopt_legacy_results`), so demo workspaces and users' earlier results stay visible.

**Experimental design**: `self.ui.experimental_design("mzML-files")` in `configure()` shows a condition / biological replicate / fraction table for the selected files (pass `reactive=True` to that `select_input_file` so the table follows the selection), with design.tsv and SDRF import. It saves `<workflow_dir>/experimental-design.tsv` in the OpenMS two-table format, which a TOPP tool takes as `-design`; `src/workflow/ExperimentalDesign.py` (Streamlit-free, so usable in `execution()`) reads, writes and checks it.

**`execution()` must be annotated `-> bool` and `return True` only when every step succeeded.** `tasks.execute_workflow()`, which runs it in local and queue mode alike (`workflow_process()` only in a frozen build), logs the `WORKFLOW FINISHED` marker for `True` and, with a deprecation warning, for a legacy `None` (see *Upgrading a fork* below); `False` or an exception leaves it out, and a missing marker is classified as an error. `run_topp()` and `run_python()` both return `False` on failure; gate every call on it, or a run whose third tool died is still reported as a success. The shipped example (`src/Workflow.py`) does exactly this — copy its structure *and* its return type.

**Upgrading a fork:** queue mode previously wrote the marker unconditionally and returned a result dict from its exception handler, so *every* queued job was recorded successful and RQ's `FailedJobRegistry` was structurally empty. It now honours the return value and re-raises. A subclass still declared `execution() -> None` keeps working — `None` is accepted as success with a deprecation warning in the workflow log — but it reports nothing when a tool fails, so fix the signature when you rebase.

The workflow directory is `<workspace>/<workflow-name-lowercased-hyphenated>/`, containing `params.json`, `ini/`, `logs/`, `pids/`.

- **`file_manager.get_files(files, set_file_type=, set_results_dir=, collect=True)`** derives output paths from input paths. `collect=True` folds a list into a single nested list for tools that accept many inputs at once. It **raises `ValueError` on an empty list**, so guard the user's selection first. `set_results_dir="auto"` generates a random 4-char dir — fine for intermediates, but use a named subdir for anything `results()` has to find.
- **`executor.run_topp(tool, input_output={...})`** pairs the n-th input with the n-th output; every list in `input_output` must be length 1 or the same length, else `ValueError`. Length-1 entries are reused for every command. It parallelises across files up to `max_threads` and splits threads per command. `run_topp(..., allow_failed=True)` goes on without the files the tool fails on: it returns True while any command succeeded, `executor.failed` holds the indices of the others and `executor.keep_succeeded(list)` drops them from the next step's lists; the log and the finished run's Run page name each file left out and its error. False still means it failed on every file.
- **Cancellation** is PID-file based: `run_command()` touches `pids/<pid>`; `stop_workflow()` SIGTERMs each PID (`executor.stop()` is a SIGKILL fallback used only when no stop function is wired in). Workflow status is "running" if `pids/` is non-empty (local) or taken from the RQ job (online).
- **Logging**: `self.logger.log(msg, level)` writes to `logs/minimal.log` (level 0), `commands-and-run-times.log` (≤1), `all.log` (≤2). Terminal state is parsed from the markers `WORKFLOW FINISHED` / `WORKFLOW CANCELLED` by `_log_status.classify_log_outcome()` — cancellation wins over error, because a TOPP subprocess often dies noisily during teardown.
- **Run progress**: `run_topp()` records each call as a step with one entry per command in `logs/progress.json` (`src/workflow/progress.py`, Streamlit-free); the Run page shows the running tool, "file n of N", the tool's own TOPP progress (parsed from the end of `all.log`), and after a failure the tool, file and error line. A workflow that runs its tools sample by sample calls `self.executor.progress.start_samples(names)` and wraps each sample in `with self.executor.progress.sample(i):`; the Run page then lists the samples (waiting, running with its tool, done, failed) instead.
- **Processing report** (`src/workflow/processing_report.py`, Streamlit-free; buttons in `report_ui.py`): each `run_topp()` and `run_python()` step also records its provenance in `progress.json` (tool version from the generated `.ini`, the parameters that differ from the defaults, each command's input and output files), and `progress.record_alias(path, source, note)` ties a converted or renamed file to its original (`convert_to_mzml` does). `report_for(workflow_dir, run_id)` follows outputs back to the input files and lists, per input file, every tool call that worked on it, then each call's parameters; `to_markdown` / `to_pdf` (reportlab) write it. The Run page offers it under the run's outcome, the run list in each run's History, and a run's ZIP holds it as processing-report.md. A Python tool shows its output in the report only when the workflow passes it as an `out…` key of `input_output`. A workflow without run folders writes each start's logs over the last ones, so it keeps a start's report with its results by calling `processing_report.keep_report(self.workflow_dir, <folder of the result>)` at the end of `execution()` (progress.json, params.json, last-follow-up.json and the .ini of each tool it ran); `report_for(folder)` and `report_buttons(folder)` then show that start's report. **Methods** (`src/workflow/methods_text.py`, Streamlit-free) is the methods section for a publication, written from the same report: the app and OpenMS version, each finished tool call in order with its non-default parameters (named as in `parameter-names.json`) and the references (the OpenMS WebApps and OpenMS papers). It replaced the parameter-based method summary: the Run page shows the last run's in the **Methods** expander at the top (`report_ui.methods_section`), the Configure page downloads it (📑 Methods), and a non-compact `report_buttons()` draws it as a popover beside the report (`methods=False` leaves it out), so each run's History has it too; an app words its own tools and cites itself in the optional `methods` block of settings.json (`reference`, `tools: {<tool or instance>: {text, reference}}`).

### Queue mode (online)

`start_workflow()` flushes params to disk, then dispatches to Redis/RQ if `online_deployment` is true and Redis is reachable, else to a local process: `sys.executable -c` running the same `tasks.execute_workflow`, so a local run gets a fresh interpreter. Never fork the server for it — a forked child inherits the OpenMP (pyOpenMS) and polars thread pools without their threads and hangs at its first mzML load or polars query; `spawn` re-runs the page script. Only a frozen (PyInstaller) build still uses `multiprocessing.Process`, which cannot run `-c`. Either way the workflow class is imported by `__module__` in the new process, so define it in `src/`, never in a page script. `tasks.execute_workflow` builds the object with `object.__new__` (next paragraph), so in local mode too an attribute a subclass sets in its own `__init__` is not there in `execution()`: make it a class attribute, or derive it from `self.params` / `self.workflow_dir` inside `execution()`. The container entrypoint starts `redis-server`, N × `rq worker openms-workflows`, and the Streamlit server(s) — all in one image.

**`src/workflow/tasks.py` runs inside the RQ worker (and the local workflow process) and must stay importable without Streamlit.** It rebuilds the workflow object with `object.__new__(WorkflowClass)` and hand-injects the members, deliberately bypassing `__init__` because that needs Streamlit. So **anything reachable from `execution()` must be session-state free** — the worker has no `st.session_state`. Worker and UI share state only through the workspace filesystem (`params.json`, `logs/`, `pids/`) and RQ job metadata. `REDIS_URL` defaults to `redis://localhost:6379/0`.

**The worker refuses a job from a page that runs other code.** `submit_job()` stamps `job.meta["app_build"]` (`src/workflow/app_build.py`: `settings.json` version plus a hash of `src/**/*.py`), and `execute_workflow()` stops before anything runs with a `WorkerBuildMismatchError` when the worker's hash differs, telling the user to restart the workers. Web and worker pods are separate Deployments of one image; with a moving tag such as `latest` a release reaches only the pods that restart, and an old worker then runs the new page's parameters with its old TOPP tools ("Parameters passed to '<tool>' are invalid", exit code 6). A job without a stamp, or a side whose hash is empty, is let through.

**A queued run's time limit grows with its input files** (`src/workflow/job_timeout.py`): `queue_settings.default_timeout` + `timeout_per_input` per selected input file, at most `max_timeout` (defaults 2 h, 30 min, 7 days); `WorkflowManager.job_timeout()` computes it, a subclass may override it, and the sync service uses the same rule. The run's log names the limit, and a run that reaches it says so and SIGTERMs the tools listed in `pids/`, which would otherwise outlive the job.

The off-switches are `online_deployment` and unsetting `REDIS_URL`. `docs/REDIS_QUEUE_IMPLEMENTATION_PLAN.md` is a pre-implementation design doc written in future tense — the work shipped, its line references are stale, and the `queue_settings.enabled` flag it describes is read nowhere. Read the code.

### Parameters — two independent systems

Do not confuse them. `default-parameters.json` belongs **only** to the simple-page system; `presets.json` belongs **only** to the workflow framework.

| | Simple pages | TOPP workflows |
|---|---|---|
| Store | `<workspace>/params.json` | `<workspace>/<workflow-slug>/params.json` |
| Defaults | `default-parameters.json` | widget defaults in code + generated `.ini` |
| API | `page_setup()` → `params`, `save_params(params)` | `ParameterManager`, auto-saved on every widget render |
| Keys | widget `key` == JSON key | prefixed, see below |

Workflow keys carry prefixes built from the workflow slug (`ParameterManager.py:71`):

- `param_prefix` = `"<slug>-param-"` — custom widgets
- `topp_param_prefix` = `"<slug>-TOPP-"` — TOPP params, keyed `"<Instance>:1:<param:path>"`. The literal `:1:` segment separates instance from parameter path and is load-bearing throughout.

TOPP defaults come from `ini/<Tool>.ini`, generated on demand via `<Tool> -write_ini` and never edited; `create_ini()` writes it again when the tool executable is newer than the file (workspaces outlive images), and `run_topp()` leaves out, with a warning in the log, any stored parameter the tool's .ini does not list. Values merge as **ini defaults < `_defaults` (from `custom_defaults=`) < user overrides**, and only values differing from the effective default are persisted. `-ini` is never passed on the command line — every effective parameter becomes an explicit CLI arg.

**Thread budget.** Both `max_threads` keys default to `"auto"` (`null` and `-1` mean the same): every usable CPU but one, at least 1 (`settings_io.default_thread_count()`). Usable is the smaller of the CPUs the process may run on (`sched_getaffinity`) and the cgroup CPU quota, so a container with `--cpus 4` on a 64 core host counts 4. A number pins the budget. Online, a readable cgroup quota still wins over `max_threads.online`, because the rq-worker's pod spec is its allocation.

**Reserved keys in a workflow's `params.json`** — never use as widget keys: `_defaults`, `_flag_params`, `max_threads`, or anything containing `.py:` (python-tool params) or `:1:` (TOPP params).

`tool_instance_name` lets the same TOPP tool appear several times with independent parameters. **Pass the same string to both `input_TOPP()` and `run_topp()`**, or parameters get written under one key and read under another. The `.ini` and the executable keep the real tool name; params.json and session keys use the instance name.

**Display names.** `parameter-names.json` (app-owned, next to `presets.json`) gives TOPP parameters a name users understand, per tool: `{"FLASHDeconv": {"SD:tol": "Mass tolerance (ppm)", "SD:min_charge": {"name": "Lowest charge", "help": "..."}}}`, keyed by tool (or `tool_instance_name`, looked up first) and the parameter path after `:1:`. `input_TOPP()` uses it as the widget label and help (the help keeps the tool's own name), the **All N parameters** dialog shows it beside the tool's name, and its filter matches both. A section path as key (`"SD": "Spectral deconvolution"`) names that section's heading on the page. Map the parameters and sections an app shows by default; the rest keep the tool's name. It changes only labels: params.json, presets and the command line keep the real names. Reader: `src/workflow/parameter_names.py` (Streamlit-free). `input_TOPP(advanced_parameters=[...])` moves parameters the tool does not tag as advanced (output options, for example) off the page into the dialog; parameters tagged as input or output files are on neither.

Boolean **flag** parameters (valueless CLI switches) are declared explicitly — `input_TOPP("Tool", flag_parameters=["force"])` — and `run_topp` emits a bare `-force` when truthy, omitting it entirely when falsy. (`ParameterManager.bool_param_paths_from_param_xml_ini` and friends are a vestigial earlier attempt that nothing reads.)

For conditional UI (a widget that shows/hides others), pass `reactive=True` to `input_widget`, `select_input_file`, or `input_TOPP` so the change reruns the parent `configure()` instead of only its isolated fragment. Read the changed value from `st.session_state` (not `self.params`, which is stale within that rerun) using the prefixes above.

### Python tools

Scripts in `src/python-tools/` declare a `DEFAULTS` list; `ui.input_python("example")` imports the file and auto-generates widgets from it. Params are passed to the script as a JSON file argv.

```python
DEFAULTS = [
    {"key": "in", "value": [], "hide": True},
    {"key": "my-param", "value": 5, "name": "My Parameter", "help": "Description",
     "min": 1, "max": 100, "step_size": 1, "widget_type": "slider", "advanced": False},
]
```

### Presets

`presets.json` maps a workflow name (lowercase, hyphenated) to named parameter sets, surfaced by `ui.preset_buttons()`. Users can also save their own presets (`ui.user_presets()`, stored in `<workflow_dir>/user-presets.json` with the last applied preset); a user preset is a full snapshot that leaves out input file selections and `max_threads`, and its name may not shadow a built-in one:

```json
{"topp-workflow": {"High Sensitivity": {
    "_description": "Tooltip text",
    "FeatureFinderMetabo": {"algorithm:common:noise_threshold_int": 500.0},
    "_general": {"custom-key": value}
}}}
```

### Input files and zero-copy references

Simple pages keep mzML in `<workspace>/mzML-files/`; workflows keep uploads in `<workflow_dir>/input-files/<key>/`. In both, a file can be **referenced instead of copied**: absolute paths are appended to a sentinel file **`external_files.txt`** in that directory. Every consumer that lists the directory must filter this filename out (see `content/raw_data_viewer.py:17`, `src/workflow/StreamlitUI.py:284`).

Two paths produce those references — the local-mode "Make a copy of files" checkbox (unchecked), and the mounted-data browser (**📂 Data folder**, online and in a local container alike). The latter renders only when `local_data_dir` from settings.json is a **real mount point** (`os.path.ismount`), because the image pre-creates `/mounted-data` as a bind target; this is what makes read-only `-v host:/mounted-data:ro` mounts usable without copying into the workspace volume. `LOCAL_DATA_HOST_DIR` names the host folder behind the mount, shown as a link (`src/workflow/host_paths.py`) so users know where to put files. A local install without a desktop display (no Tk dialog) gets the browser upload and a folder-path field instead of the native pickers (`native_dialog_available()`). `upload_widget(manual_import_sources=("pride",))` keeps an import source from filling that upload by file type: its files go there only when the user picks it in the import table.

Simple-page workflow outputs go to `<workspace>/mzML-workflow-results/<timestamp>/`.

**Input folders.** `upload_widget(suggest_folders=True)` and the Browse dialog of `select_input_file(upload=...)` sort a key's files into folders, labels kept in `<workflow_dir>/input-folders.json` (`src/workflow/InputFolders.py`, Streamlit-free; the files do not move). `experimental_design()` takes a file's folder as its condition, or, with `suggest=True`, the groups the file names within one folder suggest (a folder holding a whole experiment, `ctrl_R1` … `drug_R2`). A `fallback` given as a dict (`{path: folder}`) puts the example files in those folders when they are copied in; a demo workspace ships the same labels as its own `input-folders.json`.

**Vendor formats.** `upload_widget(file_types=["mzML", "raw", "d"])` accepts Thermo `.raw` files and Bruker `.d` folders (local: picked through the folder field, since the Tk file dialog cannot select a folder; online: uploaded as a zip, unpacked by `vendor_files.extract_bruker_zip()`). `execution()` turns them into mzML with `self.executor.convert_to_mzml(paths)`, which passes mzML through, runs **FileConverter** on `.raw` (Windows: ThermoRawFileParser on the .NET Framework, FileConverter in the Windows `TOPP_TOOLS`; macOS and Linux: OpenMS's built-in reader, which hosts a .NET 8+ runtime that the desktop build bundles with `electron/scripts/stage-dotnet.sh` and `payload.js` exposes as `DOTNET_ROOT`; the Docker image builds OpenMS `WITH_THERMO_RAW=OFF` and uses ThermoRawFileParser on `mono`) and `src/python-tools/bruker_to_mzml.py` on `.d` (timsrust + pyOpenMS `PeakPickerHiRes`; timsTOF TDF only, BAF/TSF fail with a message pointing at msconvert). Results are cached in `<workflow_dir>/converted-mzML/` while newer than the input; it returns `None` on failure, so gate on it.

**Proteome from UniProt.** `self.ui.uniprot_proteome_download(key)`, drawn below the `upload_widget(key)` of a protein database, searches UniProt proteomes by organism name or taxonomy ID (reference proteomes only by default), and downloads the picked one, its reviewed (Swiss-Prot) entries or all of them, optionally with isoforms, as FASTA into that widget's folder; the file replaces the example file and becomes the selection of `select_input_file(key)`. On a configure page, `self.ui.select_protein_database(key)` offers the choice between *Your file* (`select_input_file(key)`) and *UniProt proteome* (that search, drawn in place); it opens on UniProt when the selected file came from there. `select_input_file(key, upload=dict(..., uniprot=True))` puts the same search in an **Import from UniProt proteome** tab of its Browse dialog instead, right after *Your files*, and leaves *Import from PRIDE* out of that dialog. The REST calls are in the Streamlit-free `src/workflow/uniprot.py` (requests spaced by `MIN_INTERVAL`, 429 and server errors retried after `Retry-After`; `UNIPROT_REST_URL` points it elsewhere), the widget in `src/workflow/uniprot_ui.py`.

**Import from a link** (`src/data_import/`). With it enabled, `file_upload_section()` draws three tabs, **Data on your computer** (the page's `upload()`), **Cloud data** and **Import from PRIDE** (`ui.link_import_section(source="link"|"pride")`, one job folder; `link-import/source` names the tab that started the running import, which alone shows its progress). Both import tabs download files from a link into the folders of the page's `upload_widget()`s: each widget registers its key, file types, folder and example files in `ui.upload_targets`, and an imported file goes to the first widget whose types match it. Sources (`sources.py`): PRIDE Archive datasets (an accession such as `PXD000001`, the project or ProteomeXchange page, the `10.6019/` DOI or the FTP folder; files through the v3 API, downloaded over HTTPS from the FTP server, a vendor file whose run is there as mzML too left unticked via `RemoteFile.preselect`), Zenodo, Figshare, OneDrive (personal folders through the public shares API; SharePoint single files via `download=1`), public S3 / Swift folder listings, and any single file (presigned links included). An uncompressed tar or zip whose server answers Range requests is listed in place (`remote.py`) and its members download as byte ranges; anything else archive-like is downloaded whole and unpacked with path, link and size checks (`job._unpack`). `job.run_import` runs as a `multiprocessing.Process` in both deployments and talks to the page only through `<workflow_dir>/link-import/` (`status.json` with a heartbeat, a `cancel` file, `request.json` for restarts), so any Streamlit replica can show or stop it and a restart resumes the `.part` files. Online, `net.make_session(guard=True)` refuses non-public addresses before every request and redirect and checks the connected peer again (DNS rebinding); the local app is unguarded. Off unless `settings.json` has `data_import.enabled`; `data_import.pride_example` sets the accession the PRIDE tab shows as its example (default `PXD000001`). Everything but `ui.py` is Streamlit-free.

## Workspace sync (offline app ↔ online workspace)

`src/sync/` lets the offline (Electron) app push a local workspace's inputs (the files a user uploads, nothing else) into an online workspace, run its workflows there and pull the results back, for files too large for the browser uploader (raw files, Bruker `.d` folders). Off unless `workspace_sync.enabled` is set in settings.json. The template ships it enabled but **`developer_only`**: `sync_enabled()` then shows the sidebar panel, page and Run-page choice only to a session that unlocked **developer mode** (⚙️ Settings → Developer password, `src/common/developer.py`, checked against `developer_mode.password_hash`, a salted scrypt hash made with `python -m src.common.developer` — only the hash is in settings.json; the env var `DEVELOPER_PASSWORD_HASH` overrides it per deployment, `none` disables; an unsalted `password_sha256` / `DEVELOPER_PASSWORD_SHA256` is still accepted; no hash, no developer mode; online an unlock lasts for the browser session, in the local app it is remembered in `<local workspaces dir>/.developer-mode` across restarts until Lock, and a new password hash forgets it). The sync service runs either way. The `enabled` flag registers the **Workspace Sync** page (`content/workspace_sync.py` → `src/common/workspace_sync.py`) in `app.py` for both builds. Online it issues tokens; offline it lists every input item (a file or a whole `.d` folder) and every result file with its state on both sides, and pushes or pulls the selected ones in a background thread. Items are grouped per workflow (`Item.workflow`); per workflow the user ticks "Upload inputs" and "Download results", stored in `<workspace>/.sync-prefs.json`, and **Keep in sync** runs a loop (`_watch`, every 30 s while the app runs) that transfers whatever is pending in the ticked directions. **Cloud runs:** workflows listed in `workspace_sync.workflows` (`{"<wf dir>": "module:Class"}`) get "Run on cloud" (upload the workflow's inputs, then `POST /sync/runs/<wf>` with the local `params.json`), live status, the log tail and Stop. Input paths in the parameters are sent as `sync-workspace://<rel>` (`client.portable_params`) and pointed at the server's copies by `runs.resolve_params`, which refuses the run while any is missing. A run uploads only the input items its parameters name (`client.run_inputs`). The workflow's **Run page** offers the same as "Run on: This computer / Online workspace" (`WorkflowManager._run_online` → `workspace_sync.render_run_choice`) for a linked workspace and a listed workflow, with the expected upload size before starting. For a `multi_run` workflow class the server creates a run (named as on the desktop) and the job writes into it; `<wf>/runs/<id>/**` is pulled once its `run.json` no longer says running, so the desktop's Results page lists the run. `src/sync/runs.py` queues `tasks.execute_workflow` on the same RQ queue and `.job_id` file as the online Run button, so the online pages show the run too; the sync service therefore needs `REDIS_URL`. The page's menu entry is hidden by CSS in `app.py`; users open it from the **Workspace Sync** sidebar panel (`render_sync_sidebar()`, called by `render_sidebar`). Offline the panel shows pending counts, a live transfer and a one-click **Sync** (push everything new or changed, then pull everything new or updated); online it shows whether a desktop app is linked and the uploads arriving (`server.incoming()`). The sidebar never waits on the network: item states live in the module-level `_STATUS` store and are refreshed in a background thread once older than a minute (ten seconds while a cloud run is active). Both panels are `st.fragment(run_every=…)` and rerun only themselves, never the page. 

- **Server** `python -m src.sync.server` (tornado, no Streamlit), routed at `/sync`: tus 1.0.0 uploads, Range downloads, sha256 manifests. It runs in a container of its own: in k8s the `sync` Deployment and Service (`k8s/base/sync-deployment.yaml`, no session affinity, any replica continues any upload), with `/sync` routes in `ingress.yaml` and as `routes/1` of the Traefik IngressRoute (overlays patch its host match and service name like `routes/0`); in docker-compose the `sync` service. A single container (`docker run`, Apptainer) has `docker/entrypoint.sh` start it on `$SYNC_PORT` (8502) itself; setting `SYNC_UPSTREAM=host:port` skips that and points the nginx load balancer's `/sync/` there. Disabled, it serves `/sync/health` only.
- **Auth** is a sync token from the online panel "Link desktop app", stored hashed in `<root>/.sync-tokens/`. The workspace UUID is never a credential.
- **Scope** (`src/sync/paths.py`, enforced on both sides): push `mzML-files/**`, `<wf>/input-files/<key>/**` (paths in `external_files.txt` are sent as real files); pull `<wf>/results/**`. Partial uploads live in `<root>/.sync-uploads/` on the shared volume, so any replica continues them; a PATCH holds a POSIX record lock on `<id>.lock` (cluster-wide over NFSv3 through NLM; released by the kernel when the holding process dies, and by statd's reboot notification when a node dies), a second writer gets 423 and the client retries after a HEAD.
- Robustness: tus chunks (`chunk_mb`) each carry a sha256 the server verifies, and a chunk cut off mid-transfer is truncated away; downloads resume by Range from `.<name>.sync-part`; lost connections are retried with back-off until `give_up_after` passes without progress; every finished file is checked against its sha256. The background thread must not touch `st.session_state`.
- Client state: `<workspace>/.sync.json` (link + open uploads) and `.sync-cache.json` (hash cache). `tests/test_workspace_sync.py` runs a real server against the client.

## Visualization

**Layout manager** (`src/layout_manager/`, ported from FLASHApp). A page with several components defines a catalog (`{"name", "label", "group", "requires"?}`; `requires` is one name, or a list of which one has to be there, named in messages by `requires_label`), a default layout (rows of names, at most 3 per row) and a renderer per name. `layout_editor(path, components, default_layout, key)` is a drag-and-drop editor that runs in the browser (`frontend/index.html`, plain JS, no build step) and saves JSON to `path` (e.g. `<workspace>/layouts/<page>.json`) only on Save or Reset; `resolve_layout()` reads it back, dropping names the catalog no longer offers, and `render_layout(rows, renderers)` draws each row in `st.columns`. `layout_button(...)` opens the same editor in an **Edit layout** dialog. `layout_presets(path, components, presets, default_layout, key)` adds a **View** selector of ready-made layouts (`{"name", "label", "layout", "help"?}`): picking one stores its rows for every experiment (`apply_preset`, the experiments and their datasets stay), and a layout saved in the editor that is none of them shows as Custom (`match_preset`). `max_experiments > 1` adds FLASHApp's experiments: `render_experiments(layout, side_by_side, datasets, renderers, key)` draws each experiment below its own dataset selector (experiment n starts on the n-th dataset, the pick is kept by id), two side by side in columns; `renderers(dataset_id, index)` returns that experiment's renderers, so give each experiment its own widget keys and Insight `StateManager`. **View bar** (preferred over `layout_presets` + `layout_button`): `view_bar(path, components, presets, default_layout, key, actions=[...])` draws one segmented control with as many views as fit (presets, then the user's own, marked with a dot), **+** as its last segment, **More** for the rest and ✏️. ✏️ opens `views_editor` in a **Customize views** dialog: a list of views (drag to order, untick to keep a view in More only), the rows of the selected view, and a searchable component palette; presets are read-only there (**Duplicate to edit**). **+** opens the editor on a new view, a copy of the current one, whose starting point can be switched (Empty or any view) until it is changed. Views live in the same JSON (`current`, `views`; `load_views`/`save_views`/`select_view`/`validate_views`), the current view is also written as `layout`, so `resolve_layout` keeps working; the first preset's layout should be `default_layout` (or name the view current while nothing is saved with `default_view`, for a page that picks its default by what a dataset holds), and a layout saved before views existed becomes the view "My layout". `actions` (`{"id", "icon", "help", "on_click"}`) are icon buttons after ✏️ whose `on_click` runs on the next rerun. Give every component of an experiment the same `experiment_state(key, index, dataset_id)` (an Insight `StateManager` per experiment, cleared when its dataset changes), so a selection stays when the user switches views; an identifier that means something else in each component (a row number of its own table) goes in `private=[...]` with `owner=<component>`, and stays apart while the rest is shared. **Zoom and selection kept with a view**: `view_bar(states=lambda i: experiment_state(...), datasets=...)` lets every view keep each experiment's selection and zoom as `defaults` (📌 stores them through `capture_defaults`, opening the view and ↺ apply them with `apply_defaults`; pagination is never kept, and a selection saved for one dataset is applied only while it is shown). Insight plots keep their zoom in the state only with `zoom_identifier=zoom_identifier(name)` (`zoom@<name>`, `{"x": [lo, hi], "y": [lo, hi]}`, a missing axis is its full extent). A view's `defaults` may also hold point `annotations` per component (`{point_id: {"highlight", "annotation"}}`), applied like a selection under `annotations@<component>` (`annotations_identifier`) for the renderer to pass to `set_dynamic_annotations`. Ready-made views (a preset's own `defaults` entry) and views with `"by": "assistant"` are read-only (the editor locks both; **Duplicate to edit**) but may carry `defaults`, and 📌 works on them too: the user's pin is stored in the views JSON (`own_defaults` on a preset, the assistant's kept as `original_defaults`) and replaces theirs, and removing it (`set_view_defaults(..., None)`, `has_own_defaults`) brings theirs back; only plots whose openms-insight constructor takes `zoom_identifier` keep their zoom (a Heatmap's restored zoom is written with `xRange`/`yRange` too, which it reads on the server); `VIEW_EXTRAS` (`by`, `runs`, `explanation`, `question`, `created`) survive a load and save. **Links to a view**: `view_bar(link=True)` adds 🔗, a dialog with a URL (the page's own query parameters, the workspace among them, plus `view` and `show`: each experiment's dataset, selection, zoom and annotations as base64 JSON, `link_params`/`read_link`/`link_url` in `layout.py`); opening it picks the view and applies the rest once per session, then drops `view`/`show` from the URL. A page with dataset selectors of its own sets them from `linked_datasets(key)` before the bar ("View MS data" does). `layout.py` is Streamlit-free. "View MS data" uses the view bar. Components that share an Insight `StateManager` stay linked wherever they are placed, so a renderer must not depend on another component having rendered first. **Views the data was not processed for.** A component names the analyses it needs (`"needs": "identification"` or a list), the page passes `available` (the set of analyses the shown run has; `render_experiments` takes a callable per dataset) and `analyses` (`{"identification": {"label", "help"}}`). `view_bar` then draws views needing a missing analysis muted with a **+** badge, which says the view opens once that analysis is added (the editor's palette marks such components), and a click opens `missing_analysis_dialog` with the choices `unavailable_options(missing, view)` returns (`{"label", "help", "icon", "on_click"}`, usually one: process more files with the run's settings and the missing analysis switched on via `follow_up`, so the comparison is computed over the experiment). `render_layout(..., components, available, analyses, on_missing)` draws a note with an **Add …** button in place of such a component; `on_missing=lambda m, n: request_analysis(key, m, component=n)` opens the bar's dialog. An app with a grid renderer of its own draws the same note with `missing_note(...)`. **Extending an experiment.** Settings that add files (`follow_up(..., add_files=key)`, or `start_from(..., adds_to=..., files=..., files_key=key)`) show the experiment's processed files apart, above that key's `select_input_file` (**In the experiment already**, disabled), and offer only the others as **Files to add**; the page's own run button starts with these settings: `show_run_button` says beside it what the start does (`WorkflowManager._follow_up_summary`: adds the picked files to <experiment>, adds to <run>, or starts from the settings of <run>) and asks for files while none are picked, and on a Run page without that button its Start does the same. The note at the top offers **Start a new experiment instead**, which keeps the settings but drops the link to the earlier run. Offer this for any experiment, not only for a locked view: the example Results page has an **Add analysis** action in its view bar (`Workflow.add_files`). `src/Workflow.py`'s Results page is the example.


`src/view.py` plots via the pyopenms-viz **`ms_plotly`** backend on `MSExperiment.get_df()` DataFrames (`df.plot(backend="ms_plotly", kind="chromatogram"|"spectrum"|"peakmap")`), with a 3D peak map only under 2500 points. Use `show_fig()` / `show_table()` from `src/common/common.py` so downloads and the configured image format work consistently.

**Light and dark theme.** `.streamlit/config.toml` defines `[theme.light]` and `[theme.dark]` (Streamlit ≥ 1.51) and no `theme.base`, so the app follows the OS color scheme and users switch in ⋮ → Settings. Setting `base` pins one theme and removes the choice. `show_fig()` passes every figure through `follow_app_theme()`, which puts it on Streamlit's Plotly template and drops the white background, black axes and black annotation text that pyopenms-viz and `plotly_white`/`simple_white` set; call it yourself for a figure that goes to `st.plotly_chart` directly. In custom HTML, never set a light `background-color` without also setting the text `color`, or the text turns white on it in the dark theme. Insight components and Streamlit components read the active theme from Streamlit's render args.

**OpenMS look (Studio Blue).** The palette, fonts and radii are in `[theme]` of `.streamlit/config.toml` (Raleway text, Montserrat Alternates headings, JetBrains Mono code, self-hosted as woff2 in `static/fonts/` with their OFL licenses, served because `server.enableStaticServing` is on; every Dockerfile and the desktop build copy `static/`). What the config cannot express (the page sheet, the nav pill, the gradient bar under page titles, lining numerals, the panel behind Insight iframes) is `src/common/theme.css`, injected by `apply_theme_css()` in `page_setup()`, inline and as a `<style id="openms-theme-css">` in the document head (`st.html(..., unsafe_allow_javascript=True)`), which stays while another page from the menu replaces the old page's elements, so the switch does not flash Streamlit's own look. Its dark rules are written as `@media (prefers-color-scheme: dark)` blocks, but `theme_css()` resolves them by the app's theme (`st.context.theme.type`), not the OS, so the in-app switch works. Spectra use one plot style everywhere: `src/common/plot_style.py` (Streamlit-free) holds the peak, matched-fragment and picked colours, and `spectrum_styling()` returns the `styling=` dict for an Insight spectrum component (grey peaks, matched fragments `#3157e9`, the picked one `#ff7501`), with overrides merged in.

Downstream apps also use **OpenMS-Insight** (`Table`, `LinePlot`, `Heatmap`, `VolcanoPlot`, `SequenceView`) for very large datasets with server-side pagination and cross-component linking — note it is **not** a dependency of this template, and does not become one. It belongs to the **generated app**, which declares `openms-insight>=0.2.0` in its own `requirements.txt`; `build-insight-dashboard` puts it there, syncs the app's venv and confirms the import before mapping anything. Insight is the first solution, not a preference: `role` is a fixed vocabulary (`table`, `mirror`, `peakmap`, `chromatogram`) and each entry maps to a component by lookup, so pyopenms-viz is reached only when the role is outside that list or the import failed — and the wireframe names which. The framework had neither the install step nor the vocabulary until a run built a whole dashboard on a machine where the package was absent and told its user the fallback was for continuity with their notebook.

## Documentation and deployment

- `docs/*.md` is **single-sourced**: `content/documentation.py` reads those files and renders them in-app. Editing a doc changes the page. `docs/toppframework.py` is executable doc content — its *code samples* stay current because they are pulled from live source via `getsource()`/`st.help()`, but its surrounding prose does not (see gotchas).
- **Contributors section**: `render_contributors()` (`src/common/contributors.py`), called once at the end of the front page, shows contributor pictures and handles grouped by what they worked on. The **framework** group comes from the template-owned `src/common/framework-contributors.json`, so it is the same in every app; the app's own groups (the app, the OpenMS tools it runs, its visualizations) come from the app-owned `contributors.json` in the root, which counts only when its `repository` equals `repository-name` in settings.json (the template's example copy is ignored elsewhere). Each group lists GitHub logins ordered by contributions, `names` maps logins to real names, and an optional `lead` replaces the opening sentence. Pictures load from GitHub, nothing is stored. `python -m utils.contributors` rebuilds every group that names a `github` repository (bots and `exclude` left out, `extra` appended); `"contributors": {"enabled": false}` in settings.json hides the section.
- `test_gui.py::test_documentation` parametrizes over the exact selectbox labels in `documentation.py` — **renaming a doc chapter breaks CI** unless both are updated.
- **Desktop apps** (`.github/workflows/build-desktop-app.yaml`): the `openms` job (reusable `.github/workflows/openms.yml`, input `openms:`) decides release or build — a released version (`3.5.0`, or a release tag) is just downloaded later; any other `[owner/repo@]ref` is built from source on all three platforms (Windows: vcpkg presets if present, else OpenMS/contrib; macOS/Linux: `tools/ci` scripts), cached per commit SHA and uploaded as `openms-<platform>`. Then one `build` job, a matrix over Windows / macOS (arm64) / Linux, runs the same bash steps everywhere (Git Bash on Windows): `electron/scripts/stage-openms.sh` (the release's Windows installer / `.pkg` / `.deb`, or the built package as `OPENMS_PACKAGE`), `stage-dotnet.sh` (macOS and Linux: the .NET runtime for FileConverter's .raw reader), `stage-python.sh` (python-build-standalone on all three), copy the app, then `package.sh` — the only platform-specific step (NSIS / signed+notarized dmg / AppImage) — and `install-app.sh` + `smoke-payload.js` (also converts a Thermo .raw file when FileConverter is staged) + `smoke-app.js` + `e2e.js` against the installed app. Artifacts are `OpenMS-App-<platform>`; the `release` job attaches them. Installer size: `stage-openms.sh` leaves out `share/OpenMS/examples` and every `THIRDPARTY` folder no staged tool runs (an app that calls one itself names it in `THIRDPARTY_TOOLS`), `stage-python.sh` takes the stripped python-build-standalone build, and `package.json` packs the NSIS archive solid (LZMA, `differentialPackage: false`) and the dmg with lzfse (`ULFO`). The AppImage keeps mksquashfs' gzip and the dmg is not bzip2 (`UDBZ`): both are read compressed while the app runs (the AppImage always, the dmg when started from the mounted image), and xz or bzip2 made the app start a minute or more slower; the NSIS archive is unpacked once at install. Its `scope` job runs the full build only on a release, a manual run, nightly when `main` moved, or a PR that changes packaging (`electron/`, the workflow, `openms.yml`, requirements, `settings.json`, `app.py`) or carries the label `desktop-build`. Every CI workflow has a `concurrency` group per ref: a new push to a PR cancels its running checks, and `ci.yml` no longer runs on branch pushes.
- Four Dockerfiles: `Dockerfile` (full, builds OpenMS + TOPP tools + pyOpenMS from source) and `Dockerfile_simple` (pyOpenMS via pip only), each with an `.arm` variant. All use `docker/entrypoint.sh`. The full image builds `ARG OPENMS_BRANCH` (default `v3.6.0`; a release branch, a tag such as `v3.6.0`, or `develop`) on Ubuntu 24.04 with Python 3.11: dependencies from Ubuntu packages plus Apache Arrow/Parquet 23 (`ARG ARROW_VERSION`), never from the contrib or vcpkg submodules, and the pyOpenMS wheel the way the checked-out source builds it (autowrap/Cython up to 3.5, nanobind from 3.6). `Dockerfile` and `Dockerfile.arm` differ only in their header comment. The Dockerfiles are template-owned and carry no app values: the bundled Windows installer is the latest release of `github-user`/`repository-name` from `settings.json`, and an app's command line tools from conda-forge (SIRIUS, for example) go one spec per line in its optional app-owned `conda-requirements.txt`, installed into `streamlit-env` after the OpenMS build (a line ending in `# [x86_64]` or `# [aarch64]` only on that `uname -m`, for a tool conda-forge builds for one architecture). `build-and-test.yml` builds the four images listed in `deploy.images` of `app.yaml` (default all four: `full-amd64`, `simple-amd64`, `full-arm64`, `simple-arm64`; `full` or `simple` alone stands for that image on both architectures, so an app without TOPP tools sets `[simple]` and skips the from-source OpenMS builds); an app whose dependencies have no build for a platform, such as a pip pin without a linux/aarch64 wheel, leaves that image out there instead of editing the workflow, and the kind matrices and multi-arch manifests follow the list. It can be dispatched with `openms_branch` to build the full images on another OpenMS. **Fewer CI minutes:** `deploy.desktop: []` turns off the desktop build (a manual run still builds), and the `ci:` block of `app.yaml` turns off the optional checks: `kind_tests` (the nginx and Traefik kind jobs), `apptainer` (Apptainer test and SIF), `example_workflow_tests` (`workflow-tests.yml`) and `openms_release` (`openms-release.yml`), each `true` by default. **New OpenMS releases are adopted automatically**: `openms-release.yml` runs weekly (template and apps) and, when the full Dockerfile builds the release just before the newest one, opens one `openms-release` PR made by `.github/scripts/openms_release.py` (Dockerfiles, `pyopenms` pin, desktop default, CI Python). A repo on an older release, `develop` or a fork branch is left alone; closing the PR declines that release.
- Kubernetes: `k8s/base` → `k8s/components/memory-tier-{low,high}` → `k8s/overlays/prod` (sets `namePrefix`, GHCR image, Traefik hosts, `REDIS_URL`), plus the separate `k8s/storage/` root (Manila CSI drivers and the `openms-manila-nfs` StorageClass, applied once per cluster and shared by every app; each app's workspace PVC gets a Manila NFS share of its own; CI's kind jobs apply `k8s/ci-storage/` instead, an in-cluster Ganesha server publishing a class of the same name, and `assert_storage_class_contract` keeps the two in step). The `memory-tier-*` components are **pod sizing only** — a tier is how big a worker is, not which node it runs on, and `requests == limits` there is what makes the worker Guaranteed QoS. **Nothing in `k8s/` pins a pod to a node**: no `nodeSelector`, no `nodeName`, no `nodeAffinity`, no `openms.de/memory-tier` labels. The scheduler places pods, and `rq-worker` runs a fixed replica count spread over `kubernetes.io/hostname` with `maxSkew: 1`. CI validates with kubeconform, asserts those invariants statically (`.github/scripts/ci-assertions.sh`), and runs kind integration tests against both nginx and Traefik ingress; the kind jobs apply `k8s/overlays/ci/`, which is `prod` with the worker shrunk to fit a runner.
- **S3 storage (optional)**: `k8s/storage-s3/` mounts an S3 bucket as a POSIX file system with JuiceFS (metadata in PostgreSQL), so TOPP tools still see paths; an app switches by adding the component `k8s/components/storage-s3` to its overlay, which renames the workspace claim to `workspaces-s3-pvc` and sets `WORKSPACES_S3_*` for the in-cluster S3 gateway (one bucket per app slug). Manila stays the default. Code that benefits from the S3 API (polars scans) goes through `src/common/storage.py`: `s3_enabled()`, `uri(path)`, `options()` and `presigned_url()` fall back to the local path and `None` when the variables are unset, so the same call works on both. Writes stay on the mounted path. See `docs/kubernetes-deployment.md` §3c.
- Env/secrets: `WORKSPACES_DIR`, `REDIS_URL`, `STREAMLIT_SERVER_COUNT` (>1 puts nginx in front of N Streamlit instances), and `st.secrets["admin"]["password"]` from `.streamlit/secrets.toml` (mounted at `/app/admin-secrets/secrets.toml` in k8s) gating save-as-demo.

## Repo skills in `.claude/skills/`

Twenty-five loadable skills live here, each as `<name>/SKILL.md` with YAML frontmatter, so they surface automatically.

**Task playbooks** (originally flat `.md` files, converted): `create-page`, `create-workflow`, `add-presets`, `add-python-tool`, `add-visualization`, `configure-app-settings`, `configure-docker-compose-deployment`, `configure-k8s-deployment`.

**Software factory** (one template feeds the apps): `new-app-from-spec` (generate an app from `app.yaml`), `configure-app-identity` (every place the slug and name live), `sync-from-template` (merge the template into an app, conflicts resolved by `sync.app_owned`), `upstream-to-template` (template-first rule), `configure-desktop-installers`, `release-app`, `upgrade-openms`, `upgrade-openms-insight`, `parity-check`, `triage-ci`.

### App spec and template sync

`app.yaml` (schema `utils/app_spec.schema.json`) says what an app is: identity, inputs, workflows as TOPP/python steps, result views by Insight role, deploy targets, and `sync.app_owned`, the files the app owns. `python -m utils.app_spec` validates it and checks it against `settings.json` (`app-name`, `online_deployment`), the prod overlay's `namePrefix` and the storage namespace; `tests/test_app_spec.py` runs that. In the template it describes the example app and is the starting point for a new one.

`.github/workflows/template-sync.yml` runs weekly in every app (never in the template itself): it merges `template.branch` of `template.repository` from `app.yaml`, keeps the app's side of conflicts in app-owned files, and opens or updates one `template-sync` PR; a conflict in a template-owned file, or no common history, opens an issue instead. Set a `TEMPLATE_SYNC_TOKEN` secret (fine-grained PAT or GitHub App token with contents, pull-requests, issues and workflows write): the default `GITHUB_TOKEN` cannot push a merge that changes `.github/workflows/`, and PRs it opens do not trigger CI.

**Review queue** (`docs/review-queue.md`): PRs are sorted by risk. Dependabot patch/minor PRs (`.github/workflows/auto-merge.yml`) and template-sync PRs without any conflict are set to auto-merge, but only where the default branch has required status checks; `.github/CODEOWNERS` marks the full-review paths. `.github/scripts/setup-review-queue.sh OWNER/REPO CHECK...` is the one-time admin setup (merge options + default-branch ruleset). `sync.auto_merge: false` in `app.yaml` opts an app out.

**Notebook → webapp framework** — turns a Jupyter notebook into an app. `notebook-to-webapp` orchestrates; the five stage skills also work standalone against an existing app:

| skill | stage |
|---|---|
| `capture-notebook-workflow` | classify cells, extract a Streamlit-free python tool, golden-value test |
| `interview-parameters` | one batch review: demo shortcuts, then config parameters ranked by provenance (measurement is opt-in) |
| `scaffold-workflow-app` | `WorkflowManager` subclass, four pages, registration, hides all 15 template pages and rewrites Documentation from the notebook, smoke run |
| `build-insight-dashboard` | link graph → wireframe → panels, plus the style contract |
| `verify-webapp-usability` | headless-browser gate; **AppTest cannot see Insight components** |

Plus `connect-browser-control`, run from preflight: it connects the Claude browser
extension and proves the attached browser can load a page this host serves **on
loopback**, so design rounds put the app in that same window. **Attached is
not theirs** — the extension answering proves a browser exists somewhere
reachable, not that anyone is sitting at it, and only the marker separates the
two. The marker's verdict is reach, never presence: `switch_browser` was measured
and **excludes the browser you are already attached to**, so nothing available
proves a human is there and the framework does not pretend otherwise. Where the
browser runs is never a finding and never reaches the user; what does reach them
is the one thing they can act on. **A run never settles for the gate's headless
browser on its own judgement**: every road short of confirmed control ends in an
ask — the click, the click and a restart, or a browser to install — and only an
explicit no licenses going without. The ask stops the *question*, not the setup:
the store page opens in the browser the run found, **by naming that executable**
(`start`/`open`/`xdg-open` resolve the default, which sent one run's store page
to Firefox), the rest of preflight runs while the user clicks, and then the run
**watches** `list_connected_browsers` every fifteen seconds rather than waiting
to be told — a device has been measured connecting before its user typed
anything. Control is confirmed
**once**, and it can go stale silently — a user closing their browser re-attaches
the session elsewhere while `navigate` keeps returning success — so a page that
comes back wrong is repaired by re-enumerating, never by re-probing.

Two carry runnable tools: `interview-parameters/probe.py` (measures what each parameter does, and detects one parameter masking another) and `verify-webapp-usability/gate.py` (the browser gate). **Both are opt-in or internal.** `probe.py` no longer runs by default — it is O(n²) and only ever needed to justify *hiding* a parameter, so config parameters are ranked by provenance and an unmeasured one may be exposed but never hidden. `gate.py` runs on every results page but never appears in a user-facing turn.

**Users enter through the Quickstart page**, not through a slash command: `content/quickstart.py` holds an entry prompt they copy into any agentic terminal. It names the orchestrator **by file path**, because a repo cloned mid-session puts its skills on disk but not in the running session's registry — do not shorten it to the skill name.

**Two interaction shapes, not interchangeable.** An *interview* is one batch, arriving already decided — every row carries the recommendation the framework would act on, so the user's work is disagreeing rather than choosing from nothing (capture findings, config parameters). A *design round* puts one rendered thing **in the user's own browser** and offers up to three suggestions — one on **data**, one on **layout**, one on **behaviour**, each pointing at something visible — plus a free field and an exit, then re-renders. Rounds run on the Upload, Configure and Results pages; the first two are bounded to *template functionality* (widget arguments, section naming and order, presets), because the template chose those pages' shape. None opens before a **smoke run** has driven upload→configure→execute→results once with the notebook's own data. The gate runs before the final page round and feeds it, rephrased as suggestions.

**Everything the user decides is asked, never drawn.** Suggestions and findings arrive as options they select, one at a time — a checklist printed into the transcript is a control the reader cannot operate, and a list too long for one screen asks whether the recommendation stands before it asks about any single row.

**A user-facing turn is capped at 200 words and never contains the framework's own vocabulary** — cell classes, harvesting, probes, sweeps, gates, screenshots, `DEFAULTS`/`OUTPUTS`.

**The skills never name the evaluation corpus.** Rules are earned by running three specific notebooks, so worked examples drift toward quoting them — at which point an agent handed one of those notebooks can read its expected answer out of the skill it is being measured against. Measured values are written as placeholders (`<n> of <total> spectra`, `df.head(<n>)`, `cell <k>`) and filled from the run at hand.

Design and rationale: `docs/notebook-to-webapp-design.md`, `docs/adr/0001..0005`, glossary in `CONTEXT.md`. The user-facing walkthrough is `docs/notebook_to_webapp.md`, rendered in-app.

## Conventions and gotchas

- Pages in `content/`, logic in `src/`. Simple-page widget keys must match `default-parameters.json`. TOPP parameter paths are colon-separated (`algorithm:section:param`).
- **`page_setup()` must run before `Workflow()`** — the constructor dereferences `st.session_state["workspace"]`, and the upload widgets need `location` / `previous_dir` / `local_dir`, all set by `page_setup()`.
- **There is no "Show advanced parameters" toggle.** `input_TOPP()` draws a tool's common parameters, and its **All N parameters** dialog holds every other one (advanced, and those left out by `include_parameters`); `input_python()` puts `"advanced": True` entries in a collapsed expander. An app that wants everything on the page sets `st.session_state["advanced"] = True` itself.
- **The workflow slug is load-bearing in three places at once**: the workflow directory, the `presets.json` top-level key, and every session-state prefix. Renaming a workflow silently orphans its presets *and* abandons existing user parameters.
- Presets apply by writing `params.json` and *deleting* the matching session keys so widgets re-initialize. This misses widgets left at `widget_type="auto"` for numeric/selectbox/multiselect types (an auto-widget double-prefixes its session key), whose stale value then overwrites the preset — pass an explicit `widget_type` for any parameter you intend to drive from a preset.
- Keep new `src/workflow/` logic importable with `streamlit` and `pyopenms` mocked at the `sys.modules` level — that is how most of `tests/` exercises it.
- `docs/toppframework.py` is the most current prose on the framework but has drifted: it still names `src/TOPPWorkflow.py` and `content/6_TOPP-Workflow.py`, and its `input_python` example passes an `input_output=` argument that method does not accept.
- **Dependency licenses.** A dependency added or re-pinned in `requirements*.txt`, `conda-requirements.txt` or a `package.json` gets its license looked up (PyPI, conda-forge, npm) by `utils/dependency_licenses.py`: in a Claude Code session by the PostToolUse hook `.claude/hooks/dependency_licenses.py` right after the edit, and on every pull request by `dependency-licenses.yml` (report in the job summary). Permissive licenses pass and the report says where to attribute them (pip packages appear in the About dialog on their own; conda tools need a line in the README; bundled npm code keeps its notice in the build output). Anything else (LGPL, MPL, GPL, non-commercial, unknown) fails until a person has read it and recorded the decision in the app-owned `dependency-licenses.json` (`accepted: {name: {license, reason, attribution}}`); an entry covers the license it names, so a package that changes its license is asked about again. `python -m utils.dependency_licenses --all` checks every dependency.
- **There is no `pyproject.toml`** despite the pip-compile header in `requirements.txt` — it was never committed, so the lockfile cannot be regenerated. Edit `requirements.txt` directly (the redis/rq/xlsxwriter lines at the bottom are already hand-maintained).
- **The root `entrypoint.sh` is dead code** — superseded by `docker/entrypoint.sh` (all four Dockerfiles copy that one). Its `RUNTIME_DIR` default even names a different project.
- `hooks/hook-analytics.py` is *not* a PyInstaller hook: it rewrites Streamlit's installed `static/index.html` in site-packages to inject analytics. Only run it inside a container image build.
- `.streamlit/secrets.toml` is gitignored; only `.example` is tracked. `example-data/workspaces/` *is* tracked, so save-as-demo writes into version control.
- `docs/build_app.md` is stale where it refers to `APP_NAME`/`REPOSITORY_NAME` in `src/common.py`; those now live in `settings.json` and the module is `src/common/common.py`.
