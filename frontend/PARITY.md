# Svelte app: feature parity with the Streamlit template

Goal: everything the Streamlit template offers, in a Svelte app that runs
entirely on the user's machine, with OpenMS as WebAssembly in the browser
(as prose-web). Features that exist only for hosted deployments, or that
cannot exist in a browser, are listed as not applicable.

Legend: ✅ done · 🟡 partial · ⬜ not started · ➖ not applicable

## App shell

| Feature (Streamlit) | Svelte app | Notes |
|---|---|---|
| Page registry by section (`app.py`) | ✅ | `src/nav.ts` |
| Quickstart page | ✅ | |
| Documentation page (`docs/*.md` rendered in-app) | ✅ | Bundled at build time; `docs/toppframework.py` is Streamlit code and is not rendered |
| Sidebar: workspaces create / switch / delete | ✅ | Browser storage (OPFS); `?workspace=` in the URL |
| Sidebar: load demo workspace | ✅ | From `settings.json` `demo_workspaces`, bundled |
| Sidebar: save workspace as demo (admin password) | ➖ | Hosted deployments only; export a workspace ZIP instead |
| Workspace export / import (ZIP) | ✅ | New: workspaces live in the browser |
| Share workspace on a click (optional upload, link opens a copy) | ✅ | `share_url` in `settings.json`; `share-server/share.py` |
| Sidebar settings: image export format | ✅ | |
| Sidebar settings: spectrum bin peaks / bins | ⬜ | The viewer bins the peak map itself |
| Sidebar: resource monitor | ✅ | Browser storage used and OpenMS threads (a page cannot read CPU or RAM) |
| Sidebar: queue monitor | ➖ | No queue |
| Legal links | ✅ | |
| Captcha, GDPR consent, analytics | ➖ | Nothing is sent anywhere |
| Online mode, Redis/RQ queue, k8s | ➖ | The app is a static page |
| Light / dark theme | ✅ | Follows the OS |
| Local launcher | ✅ | `frontend/serve.py` (headers for threads); any static host works through `public/coi-sw.js` |
| Packaged desktop build | ⬜ | Candidate: a Neutralino shell like prose-web's |

## TOPP Workflow Framework

| Feature (StreamlitUI / WorkflowManager) | Svelte app | Notes |
|---|---|---|
| Workflow definition | ✅ | `src/workflows/*.ts`: `upload`, `configure`, `results`, `execute()` |
| `execution() -> bool` contract, `WORKFLOW FINISHED` marker | ✅ | `src/lib/workflow/runner.ts` |
| Same workspace layout and `params.json` format | ✅ | Steps store `"<step>.ts:<key>"` where Python tools store `"<script>.py:<key>"` |
| `FileManager.get_files` (type, results dir, collect) | ✅ | `ctx.getFiles` |
| `run_topp` (n-th input to n-th output, reuse of single entries, collect) | ✅ | `ctx.runTool`; commands run one after another, OpenMS uses threads inside |
| `run_python` with `DEFAULTS` | ✅ | `ctx.runStep`, steps in `src/steps/` |
| Arbitrary TOPP executables | ➖ | Tools are written against the WebAssembly API (`src/lib/tools/`) |
| Example: FeatureFinderMetabo | ✅ | MTD → EPD → FFM with the TOPP tool's sections and `algorithm:common` |
| Example: FeatureLinkerUnlabeledKD | 🟡 | TypeScript stand-in (no grouping algorithm in the build): nearest-neighbour linking, no RT alignment; writes consensusXML |
| Example: export consensus features to TSV | ✅ | Reads the consensusXML with OpenMS |
| `upload_widget`: upload files | ✅ | Drag and drop (files and folders), pick files, pick a folder |
| `upload_widget`: reference files in place (`external_files.txt`) | ➖ | A page cannot read a file by path; files are copied into browser storage |
| `upload_widget`: fallback example files | ✅ | Replaced by the first added file |
| Remove one / all input files | ✅ | |
| Download all input files as ZIP | ✅ | |
| Mounted-data browser (online `local_data_dir`) | ➖ | |
| `select_input_file` (single / multiple) | ✅ | |
| `input_widget` types: text, textarea, number, selectbox, slider, checkbox, multiselect, password, auto | ✅ | |
| `input_TOPP`: widgets from the tool's parameters | ✅ | From the OpenMS algorithm defaults: types, valid strings, bounds, descriptions, advanced tags, sections |
| `input_TOPP`: `exclude_parameters` / `include_parameters` | ✅ | Same suffix matching |
| `input_TOPP`: `custom_defaults` (`_defaults`) | ✅ | Three-layer merge as ParameterManager |
| `input_TOPP`: `tool_instance_name` | ✅ | `instance` |
| `input_TOPP`: `display_subsections`, `display_tool_name` | ✅ | |
| `input_TOPP`: `flag_parameters` | ➖ | No command lines; booleans are parameters |
| `input_TOPP`: `display_subsection_tabs`, `num_cols` | ⬜ | Layout is responsive instead of fixed columns |
| `reactive=True` conditional UI | ✅ | `visibleIf` on any item |
| Show advanced parameters toggle | ✅ | |
| Threads (`max_threads`) | ✅ | OpenMS threads of the run's module |
| Presets (`presets.json`) | ✅ | The same file |
| Load default parameters (reset, keeps a backup) | ✅ | |
| Export / import parameters | ✅ | |
| Method summary (markdown for publications) | ✅ | Names the OpenMS version of the module |
| Unreadable `params.json` refuses writes, offers reset | ✅ | |
| Per-parameter filter and reset to default | ✅ | New in the Svelte app |
| Run: start / stop | ✅ | A worker per run; stop terminates it and writes `WORKFLOW CANCELLED` |
| Run: live log, log level, lines to show | ✅ | The three log files of `Logger` |
| Run: outcome (finished / cancelled / error) from log markers | ✅ | `classifyLogOutcome` |
| Run: parameter summary | ✅ | |
| Run continues after the app is closed | ➖ | It runs in the tab; it continues across pages, not after the tab closes |
| Results: custom results page | ✅ | Components registered in `src/lib/results/registry.ts` |
| Results: example consensus feature table + bar plot | ✅ | |
| Results download page (single files, ZIP of folders) | ✅ | |
| `show_table`: large tables | ✅ | Parsed once, paginated, sorted and searched in the page |
| `show_fig`: download in chosen image format | ✅ | |
| OpenMS-Insight components | ➖ | They need Streamlit and Python; Svelte result components take their place |

## OpenMS pages (pyOpenMS in Streamlit)

| Page | Svelte app | Notes |
|---|---|---|
| In Silico Digest | ✅ | Same values as `utils/digest.py` |
| m/z Calculator | ✅ | Same values as `src/peptide_mz_calculator.py` |
| Isotopic Pattern Calculator | 🟡 | Formula, peptide and averagine mass; oligonucleotides need `NASequence`, which the build lacks |
| Fragment Ion Generation | ✅ | |
| File Upload (workspace mzML files) | ✅ | |
| View MS data: spectra table, spectrum plot | ✅ | |
| View MS data: TIC / BPC | ✅ | |
| View MS data: peak map | ✅ | Binned in the worker |
| View MS data: 3D peak map | ⬜ | |
| Run Workflow (example mzML workflow) | ✅ | |
| Download Results (per run ZIP, delete) | ✅ | |
| Simple Workflow | ✅ | |
| Run Subprocess | ✅ | "Run in the Background": a Web Worker is the browser's subprocess |

## Developer experience

| Item | Svelte app | Notes |
|---|---|---|
| Tests in Node on the WebAssembly module | ✅ | `npm test`: parameters, tables, linking, the example workflow end to end, toolbox values |
| Type check (`svelte-check`) | ✅ | |
| CI job for the Svelte app | ✅ | `.github/workflows/svelte-app.yml` (Node only) |
| Browser end-to-end test in CI | ⬜ | Playwright scripts exist locally; to be added |
| Docs for building an app on the Svelte frontend | ✅ | `docs/svelte_app.md` |
| Skills for the Svelte frontend | ⬜ | |
| Static deployment (GitHub Pages, any host) | 🟡 | Works through the service worker; no deploy workflow yet |
