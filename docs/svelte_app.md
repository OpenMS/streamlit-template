# Svelte App: a local web app

The template ships a second frontend next to the Streamlit app: a **Svelte**
single-page app (`frontend/`) driven by a small **local Python server**
(`server/`). Everything runs on your own computer. The server binds to
`127.0.0.1` only, runs the same OpenMS TOPP tools and pyOpenMS code as the
Streamlit app, and keeps your data in the same workspaces.

## Run it

```bash
pip install -r requirements-svelte.txt
cd frontend && npm install && npm run build && cd ..
python -m server            # opens http://127.0.0.1:8765/
```

The TOPP Workflow pages need the OpenMS TOPP tools on `PATH` (they ship with
an OpenMS installation and the full Docker image). The toolbox, the pyOpenMS
pages and the viewers only need pyOpenMS.

For frontend development, run `python -m server --no-browser` and, in
`frontend/`, `npm run dev`; Vite serves the app on port 5173 and forwards
`/api` to the server.

## How it is built

| Piece | Where | What it does |
|---|---|---|
| Svelte app | `frontend/src/` | Pages, sidebar, workflow sections, plots (Plotly) and tables |
| Page registry | `frontend/src/nav.ts` | The counterpart of the `pages` dict in `app.py` |
| Local server | `server/` | FastAPI app under `/api`, serves the built frontend |
| Workflow specs | `server/workflows.py` | Upload, configure and results pages of each workflow, as data |
| Result components | `frontend/src/lib/results/` | Svelte components a workflow's results page names |

### Why a local server and not WebAssembly

[prose-web](https://github.com/timosachsenberg/prose-web) runs one OpenMS
search engine in the browser through WebAssembly. That works for a single
algorithm compiled into the module, but the template's core is the TOPP
Workflow Framework: it chains arbitrary TOPP tools as subprocesses, runs them
in parallel, and its downstream apps call tools (Comet, Percolator, SIRIUS,
FLASHDeconv, ...) that have no WebAssembly build. A browser cannot start
processes, so those workflows need a native process on the user's machine.
The server is that process, and it is kept local: no remote host, no upload
of data anywhere.

The choice per feature:

| Feature | Runs in | Why |
|---|---|---|
| TOPP workflows (run, logs, stop) | local server | TOPP tools are native executables |
| TOPP parameter UI | local server | Reads each tool's `.ini` via `-write_ini` |
| Workspaces, files, parameters | local server | Real files on disk, shared with the Streamlit app |
| pyOpenMS toolbox, mzML viewer | local server | Reuses the template's pyOpenMS code unchanged |
| Tables | server-paginated | Only the visible page reaches the browser |
| Plots | browser (Plotly) | Data is binned server-side where it can be large (peak map) |

The toolbox pages are the natural first candidates for an in-browser
WebAssembly build of OpenMS once one is released; the frontend calls them
through `/api/tools/*` so that swap stays local to those pages.

### Same workspaces as the Streamlit app

The server writes `params.json`, `input-files/`, `results/`, `logs/` and
`pids/` exactly as the Streamlit `WorkflowManager` does, so a workspace can be
opened in either app. Runs go through `src/workflow/tasks.py:execute_workflow`,
the Streamlit-free entry point the online queue worker uses, so a workflow's
`execution()` method runs unchanged.

## Adding a workflow

1. Write the `WorkflowManager` subclass with its `execution()` as usual (see
   `src/Workflow.py`).
2. Describe its pages in `server/workflows.py`:

   ```python
   WorkflowSpec(
       name="My Workflow", module="src.MyWorkflow", cls="MyWorkflow",
       upload=[Upload("mzML-files", ["mzML"], name="MS data")],
       configure=[
           SelectFiles("mzML-files"),
           Tab("Search", [TOPP("CometAdapter", exclude_parameters=["database"])]),
           Tab("Options", [Widget("run-extra", False, "Run the extra step"),
                           Python("my_tool", visible_if={"key": "run-extra", "equals": True})]),
       ],
       results=[ResultView("table", "Identifications", {"file": "results/ids.tsv"})],
   )
   ```

   Each item mirrors a StreamlitUI call: `Upload` is `upload_widget`,
   `SelectFiles` is `select_input_file`, `TOPP` is `input_TOPP` (same
   arguments), `Python` is `input_python`, `Widget` is `input_widget`, `Tab` is
   `st.tabs`. `visible_if` replaces `reactive=True` plus an `if`.
3. Register its pages in `frontend/src/nav.ts` with `workflowPages("my-workflow")`.
4. For custom result views, add a Svelte component to
   `frontend/src/lib/results/registry.ts` and name it in a `ResultView`.

## Feature parity

The checklist of Streamlit features and their state in this app is
`frontend/PARITY.md`.
