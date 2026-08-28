# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

**The standard framework for building web applications for mass spectrometry (MS) data analysis**, used across the OpenMS ecosystem for proteomics and metabolomics research. It wraps **OpenMS/pyOpenMS** (the leading open-source C++/Python library for computational MS) and its **TOPP tools** (~200 command-line tools for MS pipelines) into interactive Streamlit apps.

Production apps built from this template: **quantms-web** (quantitative proteomics), **umetaflow** (untargeted metabolomics), **FLASHApp** (top-down proteomics).

### MS Domain Context

- **Input data**: mzML (raw spectra), featureXML (detected features), consensusXML (features linked across samples), idXML (peptide/protein IDs), traML (targeted transitions)
- **Workflows chain TOPP tools**: e.g. `FeatureFinderMetabo` (detect LC-MS features) → `FeatureLinkerUnlabeledKD` (align across runs) → custom Python post-processing
- **Proteomics** = peptide/protein ID + quantification (`MSGFPlusAdapter`, `FidoAdapter`, `ProteinQuantifier`); **metabolomics** = feature detection + annotation (`FeatureFinderMetabo`, `MetaboliteAdductDecharger`, `SiriusAdapter`)
- **MS visualizations**: mass spectra (m/z vs intensity), chromatograms (RT vs intensity), peak maps (RT vs m/z heatmaps), isotope patterns, fragment ion annotations, volcano plots

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

# Kubernetes. TWO roots, and the storage one goes first: it publishes the
# StorageClass workspace-pvc.yaml claims, so applying the overlay alone leaves
# every pod Pending. `apply -k` has no --enable-helm flag, hence the pipe.
kubectl kustomize k8s/overlays/prod/          # render + validate
kubectl kustomize --enable-helm k8s/storage/  # render + validate (needs helm)

kubectl kustomize --enable-helm k8s/storage/ | kubectl apply -f -
kubectl apply -k k8s/overlays/prod/
```

CI uses **Python 3.10** for all Linux test/lint jobs. Windows packaging uses 3.11; `requirements.txt` was compiled against 3.12.

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
k8s/storage/              # SEPARATE root: NFS-Ganesha serving the RWX workspace volume
docker/entrypoint.sh      # THE container entrypoint (redis + rq workers + streamlit [+ nginx])
```

### Runtime model: workspaces

Every session gets a **workspace directory** holding that user's files and parameters. `page_setup()` resolves it and guarantees `<workspace>/mzML-files/` exists.

- **Local** (`online_deployment: false`): workspace is a named dir (default `default`) under `../workspaces-<repository-name>`; the sidebar offers a create/switch/delete UI.
- **Online** (`online_deployment: true`): a fresh UUID workspace per session, exposed as the `?workspace=` query param so URLs are shareable. Root comes from `$WORKSPACES_DIR` (default `/workspaces-streamlit-template`).

`st.session_state.location` is `"local"` or `"online"` derived **solely from `online_deployment` in settings.json** (`src/common/common.py:466`). Workspace names are validated against path traversal by `is_safe_workspace_name()`. `clean-up-workspaces.py` deletes workspaces older than 7 days (k8s CronJob at 03:00; skips dot-dirs like `.demos/`).

### Local vs online differences

| | local | online |
|---|---|---|
| Workflow execution | `multiprocessing.Process` | Redis/RQ queue |
| Captcha + GDPR consent | skipped (`controllo` forced true) | enforced |
| mzML upload | many files at once, or reference a local folder | one file at a time |
| Save-as-demo | hidden | shown if admin password set |
| Max threads | `max_threads.local` (4), user-overridable | `max_threads.online` (2) |

## Core Patterns

### Simple pages

```python
from src.common.common import page_setup, save_params
params = page_setup()
st.number_input("X", value=params["example-x-dimension"], key="example-x-dimension")
save_params(params)
```

`page_setup()` must be the first call — it loads settings, resolves the workspace, renders the sidebar and applies the captcha gate. Widget `key`s must exist verbatim in `default-parameters.json`; `save_params()` copies matching session-state values into `<workspace>/params.json`. Display-only pages skip `save_params()`. (`content/digest.py` is a non-conforming outlier that never calls `page_setup()` at all.)

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

Each workflow gets four thin content pages calling `wf.show_file_upload_section()` / `show_parameter_section()` / `show_execution_section()` / `show_results_section()`. Decorate `configure()` and `results()` with `@st.fragment`.

**`execution()` must be annotated `-> bool` and `return True` only when every step succeeded.** Both callers — `workflow_process()` locally and `tasks.execute_workflow()` in queue mode — log the `WORKFLOW FINISHED` marker only for a truthy return, and a missing marker is classified as an error. `run_topp()` and `run_python()` both return `False` on failure; gate every call on it, or a run whose third tool died is still reported as a success. The shipped example (`src/Workflow.py`) does exactly this — copy its structure *and* its return type.

**Upgrading a fork:** queue mode previously wrote the marker unconditionally and returned a result dict from its exception handler, so *every* queued job was recorded successful and RQ's `FailedJobRegistry` was structurally empty. It now honours the return value and re-raises. A subclass still declared `execution() -> None` keeps working — `None` is accepted as success with a deprecation warning in the workflow log — but it reports nothing when a tool fails, so fix the signature when you rebase.

The workflow directory is `<workspace>/<workflow-name-lowercased-hyphenated>/`, containing `params.json`, `ini/`, `logs/`, `pids/`.

- **`file_manager.get_files(files, set_file_type=, set_results_dir=, collect=True)`** derives output paths from input paths. `collect=True` folds a list into a single nested list for tools that accept many inputs at once. It **raises `ValueError` on an empty list**, so guard the user's selection first. `set_results_dir="auto"` generates a random 4-char dir — fine for intermediates, but use a named subdir for anything `results()` has to find.
- **`executor.run_topp(tool, input_output={...})`** pairs the n-th input with the n-th output; every list in `input_output` must be length 1 or the same length, else `ValueError`. Length-1 entries are reused for every command. It parallelises across files up to `max_threads` and splits threads per command.
- **Cancellation** is PID-file based: `run_command()` touches `pids/<pid>`; `stop_workflow()` SIGTERMs each PID (`executor.stop()` is a SIGKILL fallback used only when no stop function is wired in). Workflow status is "running" if `pids/` is non-empty (local) or taken from the RQ job (online).
- **Logging**: `self.logger.log(msg, level)` writes to `logs/minimal.log` (level 0), `commands-and-run-times.log` (≤1), `all.log` (≤2). Terminal state is parsed from the markers `WORKFLOW FINISHED` / `WORKFLOW CANCELLED` by `_log_status.classify_log_outcome()` — cancellation wins over error, because a TOPP subprocess often dies noisily during teardown.

### Queue mode (online)

`start_workflow()` flushes params to disk, then dispatches to Redis/RQ if `online_deployment` is true and Redis is reachable, else to a local `multiprocessing.Process`. The container entrypoint starts `redis-server`, N × `rq worker openms-workflows`, and the Streamlit server(s) — all in one image.

**`src/workflow/tasks.py` runs inside the RQ worker and must stay importable without Streamlit.** It rebuilds the workflow object with `object.__new__(WorkflowClass)` and hand-injects the members, deliberately bypassing `__init__` because that needs Streamlit. So **anything reachable from `execution()` must be session-state free** — the worker has no `st.session_state`. Worker and UI share state only through the workspace filesystem (`params.json`, `logs/`, `pids/`) and RQ job metadata. `REDIS_URL` defaults to `redis://localhost:6379/0`.

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

TOPP defaults come from `ini/<Tool>.ini`, generated on demand via `<Tool> -write_ini` and never mutated. Values merge as **ini defaults < `_defaults` (from `custom_defaults=`) < user overrides**, and only values differing from the effective default are persisted. `-ini` is never passed on the command line — every effective parameter becomes an explicit CLI arg.

**Reserved keys in a workflow's `params.json`** — never use as widget keys: `_defaults`, `_flag_params`, `max_threads`, or anything containing `.py:` (python-tool params) or `:1:` (TOPP params).

`tool_instance_name` lets the same TOPP tool appear several times with independent parameters. **Pass the same string to both `input_TOPP()` and `run_topp()`**, or parameters get written under one key and read under another. The `.ini` and the executable keep the real tool name; params.json and session keys use the instance name.

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

`presets.json` maps a workflow name (lowercase, hyphenated) to named parameter sets, surfaced by `ui.preset_buttons()`:

```json
{"topp-workflow": {"High Sensitivity": {
    "_description": "Tooltip text",
    "FeatureFinderMetabo": {"algorithm:common:noise_threshold_int": 500.0},
    "_general": {"custom-key": value}
}}}
```

### Input files and zero-copy references

Simple pages keep mzML in `<workspace>/mzML-files/`; workflows keep uploads in `<workflow_dir>/input-files/<key>/`. In both, a file can be **referenced instead of copied**: absolute paths are appended to a sentinel file **`external_files.txt`** in that directory. Every consumer that lists the directory must filter this filename out (see `content/raw_data_viewer.py:17`, `src/workflow/StreamlitUI.py:284`).

Two paths produce those references — the local-mode "Make a copy of files" checkbox (unchecked), and the online-mode mounted-data browser. The latter renders only when `local_data_dir` from settings.json is a **real mount point** (`os.path.ismount`), because the image pre-creates `/mounted-data` as a bind target; this is what makes read-only `-v host:/mounted-data:ro` mounts usable without copying into the workspace volume.

Simple-page workflow outputs go to `<workspace>/mzML-workflow-results/<timestamp>/`.

## Visualization

`src/view.py` plots via the pyopenms-viz **`ms_plotly`** backend on `MSExperiment.get_df()` DataFrames (`df.plot(backend="ms_plotly", kind="chromatogram"|"spectrum"|"peakmap")`), with a 3D peak map only under 2500 points. Use `show_fig()` / `show_table()` from `src/common/common.py` so downloads and the configured image format work consistently.

Downstream apps also use **OpenMS-Insight** (`Table`, `LinePlot`, `Heatmap`, `VolcanoPlot`, `SequenceView`) for very large datasets with server-side pagination and cross-component linking — note it is **not** a dependency of this template.

## Documentation and deployment

- `docs/*.md` is **single-sourced**: `content/documentation.py` reads those files and renders them in-app. Editing a doc changes the page. `docs/toppframework.py` is executable doc content — its *code samples* stay current because they are pulled from live source via `getsource()`/`st.help()`, but its surrounding prose does not (see gotchas).
- `test_gui.py::test_documentation` parametrizes over the exact selectbox labels in `documentation.py` — **renaming a doc chapter breaks CI** unless both are updated.
- Four Dockerfiles: `Dockerfile` (full, builds OpenMS `release/3.5.0` + TOPP tools from source) and `Dockerfile_simple` (pyOpenMS via pip only), each with an `.arm` variant. All use `docker/entrypoint.sh`.
- Kubernetes: `k8s/base` → `k8s/components/memory-tier-{low,high}` → `k8s/overlays/prod` (sets `namePrefix`, GHCR image, Traefik hosts, `REDIS_URL`), plus the separate `k8s/storage/` root. The `memory-tier-*` components are **pod sizing only** — a tier is how big a worker is, not which node it runs on, and `requests == limits` there is what makes the worker Guaranteed QoS. **Nothing in `k8s/` pins a pod to a node**: no `nodeSelector`, no `nodeName`, no `nodeAffinity`, no `openms.de/memory-tier` labels. The scheduler places pods, and `rq-worker` runs a fixed replica count spread over `kubernetes.io/hostname` with `maxSkew: 1`. CI validates with kubeconform, asserts those invariants statically (`.github/scripts/ci-assertions.sh`), and runs kind integration tests against both nginx and Traefik ingress; the kind jobs apply `k8s/overlays/ci/`, which is `prod` with the worker shrunk to fit a runner.
- Env/secrets: `WORKSPACES_DIR`, `REDIS_URL`, `STREAMLIT_SERVER_COUNT` (>1 puts nginx in front of N Streamlit instances), and `st.secrets["admin"]["password"]` from `.streamlit/secrets.toml` (mounted at `/app/admin-secrets/secrets.toml` in k8s) gating save-as-demo.

## Repo playbooks in `.claude/skills/`

Eight task-specific procedures live here: `create-page`, `create-workflow`, `add-presets`, `add-python-tool`, `add-visualization`, `configure-app-settings`, `configure-docker-compose-deployment`, `configure-k8s-deployment`.

**They are flat `.md` files with no YAML frontmatter, so they are not loadable Claude Code skills** (that requires `.claude/skills/<name>/SKILL.md`) — nothing surfaces them automatically. Read the relevant one by path before doing the corresponding task; they contain the interview questions, templates and checklists to follow.

## Conventions and gotchas

- Pages in `content/`, logic in `src/`. Simple-page widget keys must match `default-parameters.json`. TOPP parameter paths are colon-separated (`algorithm:section:param`).
- **`page_setup()` must run before `Workflow()`** — the constructor dereferences `st.session_state["workspace"]`, and the upload widgets need `location` / `previous_dir` / `local_dir`, all set by `page_setup()`.
- **`input_TOPP()` and `input_python()` require `st.session_state["advanced"]`**, which only `parameter_section()` creates. Calling them from a page that does not go through `show_parameter_section()` raises `KeyError`.
- **The workflow slug is load-bearing in three places at once**: the workflow directory, the `presets.json` top-level key, and every session-state prefix. Renaming a workflow silently orphans its presets *and* abandons existing user parameters.
- Presets apply by writing `params.json` and *deleting* the matching session keys so widgets re-initialize. This misses widgets left at `widget_type="auto"` for numeric/selectbox/multiselect types (an auto-widget double-prefixes its session key), whose stale value then overwrites the preset — pass an explicit `widget_type` for any parameter you intend to drive from a preset.
- Keep new `src/workflow/` logic importable with `streamlit` and `pyopenms` mocked at the `sys.modules` level — that is how most of `tests/` exercises it.
- `docs/toppframework.py` is the most current prose on the framework but has drifted: it still names `src/TOPPWorkflow.py` and `content/6_TOPP-Workflow.py`, and its `input_python` example passes an `input_output=` argument that method does not accept.
- **There is no `pyproject.toml`** despite the pip-compile header in `requirements.txt` — it was never committed, so the lockfile cannot be regenerated. Edit `requirements.txt` directly (the redis/rq/xlsxwriter lines at the bottom are already hand-maintained).
- **The root `entrypoint.sh` is dead code** — superseded by `docker/entrypoint.sh` (all four Dockerfiles copy that one). Its `RUNTIME_DIR` default even names a different project.
- `hooks/hook-analytics.py` is *not* a PyInstaller hook: it rewrites Streamlit's installed `static/index.html` in site-packages to inject analytics. Only run it inside a container image build.
- `.streamlit/secrets.toml` is gitignored; only `.example` is tracked. `example-data/workspaces/` *is* tracked, so save-as-demo writes into version control.
- `docs/build_app.md` is stale where it refers to `APP_NAME`/`REPOSITORY_NAME` in `src/common.py`; those now live in `settings.json` and the module is `src/common/common.py`.
