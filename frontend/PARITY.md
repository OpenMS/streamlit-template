# Svelte app: feature parity with the Streamlit template

Goal: everything the Streamlit template offers, in the Svelte app, running
entirely on the user's machine. Features that exist only for hosted
deployments are listed as not applicable rather than ported.

Legend: ✅ done · 🟡 partial · ⬜ not started · ➖ not applicable (local only)

## App shell

| Feature (Streamlit) | Svelte app | Notes |
|---|---|---|
| Page registry by section (`app.py`) | ✅ | `frontend/src/nav.ts` |
| Quickstart page | ✅ | Notebook-to-webapp prompt, feature overview, links |
| Documentation page (`docs/*.md` rendered in-app) | ✅ | Same markdown files; `docs/toppframework.py` is Streamlit code and is not rendered |
| Sidebar: workspaces create / switch / delete | ✅ | `?workspace=` in the URL, as in Streamlit |
| Sidebar: load demo workspace | ✅ | Symlinks on Linux, copies elsewhere, as `copy_demo_workspace` |
| Sidebar: save workspace as demo (admin password) | ⬜ | |
| Sidebar settings: image export format | ✅ | Per browser (localStorage) |
| Sidebar settings: spectrum bin peaks / bins | ⬜ | The viewer bins the peak map server-side instead |
| Sidebar: resource monitor (CPU, RAM, disk) | ✅ | |
| Sidebar: queue monitor | ➖ | No queue locally |
| Legal links | ✅ | From `settings.json` |
| Captcha, GDPR consent, analytics | ➖ | Online deployment only |
| Online mode, Redis/RQ queue, k8s | ➖ | The Svelte app is the local deployment |
| Light / dark theme | ✅ | Follows the OS |
| Packaged desktop build (Windows exe / installer) | ⬜ | Candidates: PyInstaller like `run_app.py`, or a Neutralino shell like prose-web |
| Prebuilt frontend shipped with the repo or release | ⬜ | Today `npm run build` is needed once |

## TOPP Workflow Framework

| Feature (StreamlitUI / WorkflowManager) | Svelte app | Notes |
|---|---|---|
| Workflow definition | ✅ | `server/workflows.py` spec mirrors `upload()/configure()/results()` |
| `execution()` reused unchanged | ✅ | Runs via `src/workflow/tasks.py:execute_workflow` |
| Same workspace layout and `params.json` format | ✅ | Workspaces open in both apps |
| `upload_widget`: upload files | ✅ | Drag and drop or file dialog |
| `upload_widget`: add from local folder, copy or reference (`external_files.txt`) | ✅ | Server-side file browser replaces tkinter |
| `upload_widget`: fallback example files | ✅ | Replaced by the first added file |
| Remove one / all input files | ✅ | |
| Download all input files as ZIP | ✅ | |
| Mounted-data browser (online `local_data_dir`) | ➖ | Local paths are browsable directly |
| `select_input_file` (single / multiple) | ✅ | |
| `input_widget` types: text, textarea, number, selectbox, slider, checkbox, multiselect, password, auto | ✅ | |
| `input_TOPP`: widgets from the tool's `.ini` | ✅ | Types, valid strings, min/max, lists, sections |
| `input_TOPP`: `exclude_parameters` / `include_parameters` | ✅ | Same suffix matching |
| `input_TOPP`: `custom_defaults` (`_defaults`) | ✅ | Three-layer merge as ParameterManager |
| `input_TOPP`: `flag_parameters` (`_flag_params`) | ✅ | |
| `input_TOPP`: `tool_instance_name` | ✅ | |
| `input_TOPP`: `display_subsections`, `display_tool_name` | ✅ | |
| `input_TOPP`: `display_subsection_tabs`, `num_cols` | ⬜ | Layout is responsive instead of fixed columns |
| `reactive=True` conditional UI | ✅ | `visible_if` on any item |
| `input_python` from `DEFAULTS` | ✅ | `hide` and `advanced` honoured |
| Show advanced parameters toggle | ✅ | |
| Threads (`max_threads`) | ✅ | |
| Presets (`presets.json`) | ✅ | |
| Load default parameters (reset, keeps a backup) | ✅ | |
| Export / import parameters | ✅ | |
| Method summary (markdown for publications) | ✅ | |
| Unreadable `params.json` refuses writes, offers reset | ✅ | |
| Per-parameter filter and reset to default | ✅ | New in the Svelte app |
| Run: start / stop | ✅ | SIGTERM to every PID, `WORKFLOW CANCELLED` marker |
| Run: live log, log level, lines to show | ✅ | |
| Run: outcome (finished / cancelled / error) from log markers | ✅ | `classify_log_outcome` |
| Run: parameter summary | ✅ | |
| Run continues after the app is closed | ✅ | Separate process; status from `pids/` |
| Results: custom results page | ✅ | Svelte components registered in `lib/results/registry.ts` |
| Results: example consensus feature table + bar plot | ✅ | |
| Results download page (single files, ZIP of folders, `exclude`) | ✅ | |
| `show_table`: large tables | ✅ | Server-side pagination, sort and search |
| `show_fig`: download in chosen image format | ✅ | Plotly toolbar uses the sidebar setting |
| OpenMS-Insight components (Table, LinePlot, Heatmap, VolcanoPlot, SequenceView) | ⬜ | Plan: host Insight's Vue bundle and feed it the args its Python side computes |

## pyOpenMS pages

| Page | Svelte app | Notes |
|---|---|---|
| In Silico Digest | ✅ | Same `utils/digest.py` |
| m/z Calculator | ✅ | Same `src/peptide_mz_calculator.py` |
| Isotopic Pattern Calculator | ✅ | Logic moved to `src/isotope_pattern.py`, shared with the Streamlit page |
| Fragment Ion Generation | ✅ | Logic moved to `src/fragmentation.py`, shared with the Streamlit page |
| File Upload (workspace mzML files) | ✅ | |
| View MS data: spectra table, spectrum plot | ✅ | |
| View MS data: TIC / BPC | ✅ | |
| View MS data: peak map | ✅ | Binned server-side |
| View MS data: 3D peak map | ⬜ | |
| Run Workflow (example mzML workflow) | ✅ | |
| Download Results (per run ZIP, delete) | ✅ | |
| Simple Workflow | ✅ | |
| Run Subprocess | ✅ | |

## Developer experience

| Item | Svelte app | Notes |
|---|---|---|
| Server API tests | ✅ | `tests/svelte/`, TOPP stand-ins built on pyOpenMS |
| Frontend type check (`svelte-check`) | ✅ | |
| CI job for the Svelte app | ✅ | `.github/workflows/svelte-app.yml` |
| Browser end-to-end test in CI | ⬜ | Playwright script exists locally; to be added |
| Skills / docs for building an app on the Svelte frontend | 🟡 | `docs/svelte_app.md` |
| Docker image serving the Svelte app | ⬜ | |
