# Svelte App: an in-browser web app

The template ships a second frontend next to the Streamlit app: a **Svelte**
single-page app (`frontend/`) that runs **OpenMS itself in the browser**, as
WebAssembly, the way [prose-web](https://github.com/timosachsenberg/prose-web)
does. There is no Python server and no backend: a static page loads the
OpenMS module into a Web Worker, keeps workspaces in the browser's own
storage, and runs workflows on the user's machine. Data leaves the machine
only when the user clicks **Share workspace**.

## Run it

```bash
cd frontend
npm install          # also fetches the OpenMS WebAssembly package (checksummed)
npm run build
python3 serve.py     # opens http://localhost:8501/
```

`serve.py` only hands the browser its files, from `localhost`, with the two
headers OpenMS's threads need (`Cross-Origin-Opener-Policy: same-origin`,
`Cross-Origin-Embedder-Policy: require-corp`). Any static server works for
the built `dist/` folder too: where the server cannot send those headers, the
app registers a small service worker (`public/coi-sw.js`) that adds them and
reloads once.

For development, `npm run dev` serves the app with hot reload on port 5173,
with the same headers. `npm test` runs the engine, the workflow framework and
the example workflow in Node, on the same WebAssembly module.

## How it is built

| Piece | Where | What it does |
|---|---|---|
| OpenMS | `public/openms/` (fetched by `scripts/fetch-openms.mjs`) | The multi-threaded OpenMS WebAssembly package, pinned by checksum |
| Engine | `src/lib/engine/` | OpenMS in a module Web Worker; `engine.call("op", ...)` from the page |
| Workspace store | `src/lib/storage/store.ts` | The browser's origin private file system (OPFS), laid out as Streamlit workspaces |
| Workflow framework | `src/lib/workflow/` | `WorkflowSpec`, parameters, `RunContext`, logs and the runner |
| Tools | `src/lib/tools/` | The counterpart of TOPP tools: parameters plus one command on the module |
| Steps | `src/steps/` | The counterpart of `src/python-tools/`, with the same `DEFAULTS` |
| Workflows | `src/workflows/` | One spec per workflow (as one `WorkflowManager` subclass) |
| Pages | `src/pages/`, `src/nav.ts` | The counterpart of `content/` and the `pages` dict of `app.py` |
| Page-side services | `src/lib/backend/` | Workspaces, the workflow pages, tables, ZIP files, sharing |
| Share service | `share-server/share.py` | Optional reference service the Share button uploads to |

`settings.json`, `default-parameters.json`, `presets.json`, `docs/*.md` and
`example-data/` are the repository's own files, bundled at build time.

### One process per run

The toolbox, the viewer and the configure page share one engine worker. A
workflow run gets a worker of its own, with its own OpenMS module, so the pages
stay responsive and **Stop** simply terminates that worker (and writes the
`WORKFLOW CANCELLED` marker, as the Streamlit app does). A run continues while
the app stays open in the tab, on any page; closing the tab ends it.

### Workspaces

A workspace is a folder in the browser's storage with the Streamlit layout:

```
<workspace>/params.json                 page parameters (default-parameters.json)
<workspace>/mzML-files/                 files of the OpenMS example pages
<workspace>/<workflow>/params.json      workflow parameters, same format as ParameterManager
<workspace>/<workflow>/input-files/<key>/, results/, logs/
```

The sidebar exports a workspace as a ZIP and imports one, so workspaces move
between browsers and computers. **Share workspace** (shown when `share_url` is
set in `settings.json`, or `VITE_SHARE_URL` at build time) uploads the
workspace's parameters, logs and results, and its input files only when the
user ticks the box, and returns a link (`?shared=<id>`) that opens a copy in
any browser. `share-server/share.py` is a small reference service for it
(standard library only, shares expire after 30 days).

## Build a workflow

A workflow is a `WorkflowSpec` in `src/workflows/`, registered in
`src/workflows/index.ts`, with its pages added in `src/nav.ts`
(`workflowPages("<slug>")`). It reads like its Streamlit counterpart:

```ts
export const myWorkflow: WorkflowSpec = {
  name: "My Workflow",
  upload: [Upload("mzML-files", ["mzML"], { name: "MS data" })],
  configure: [
    SelectFiles("mzML-files", { multiple: true }),
    Tab("Feature Detection", [Tool("FeatureFinderMetabo", { customDefaults: { "algorithm:common:noise_threshold_int": 1000 } })]),
    Widget("run-step", false, "Run my step", { widgetType: "checkbox" }),
    Step("my_step", { visibleIf: { key: "run-step", equals: true } }),
  ],
  results: [{ component: "table", title: "Features", props: { file: "results/my-step/table.tsv" } }],
  async execute(ctx) {
    const mzML = ctx.getFiles(ctx.params["mzML-files"]);
    const features = ctx.getFiles(mzML, "featureXML", "feature-detection");
    if (!(await ctx.runTool("FeatureFinderMetabo", { in: mzML, out: features }))) return false;
    if (ctx.params["run-step"] && !(await ctx.runStep("my_step", { in: features }))) return false;
    return true;
  },
};
```

| Streamlit (`src/Workflow.py`) | Svelte (`src/workflows/*.ts`) |
|---|---|
| `self.ui.upload_widget(key, ...)` | `Upload(key, fileTypes, ...)` |
| `self.ui.select_input_file(key, ...)` | `SelectFiles(key, ...)` |
| `self.ui.input_widget(key, value, name, ...)` | `Widget(key, value, name, ...)` |
| `self.ui.input_TOPP(tool, ...)` | `Tool(tool, ...)` |
| `self.ui.input_python(script)` | `Step(name)` |
| `reactive=True` and an `if` | `visibleIf: { key, equals }` |
| `self.params[key]` | `ctx.params[key]` |
| `self.logger.log(msg, level)` | `ctx.log(msg, level)` |
| `self.file_manager.get_files(...)` | `ctx.getFiles(...)` |
| `self.executor.run_topp(tool, io)` | `await ctx.runTool(tool, io)` |
| `self.executor.run_python(script, io)` | `await ctx.runStep(step, io)` |

`execute()` returns `true` only when every step succeeded, exactly as
`execution() -> bool`: the run page reads the outcome from the same log
markers.

### Tools

A tool (`src/lib/tools/`) declares its parameters and runs one command on the
module. Parameters usually come straight from the OpenMS algorithm's defaults
(`algorithmParams(O, "MassTraceDetection", "algorithm:mtd")`), so the
configure page shows every parameter with its type, valid values, bounds and
description, as `input_TOPP` does from a tool's `.ini`. Parameters are stored
in `params.json` as TOPP parameters are, so `presets.json` presets apply
unchanged.

The template ships `FeatureFinderMetabo` (the TOPP tool's mass trace
detection, elution peak detection and feature finding, with its
`algorithm:common` section) and `FeatureLinkerUnlabeledKD`. The WebAssembly
build has no feature grouping algorithm, so the linker is a TypeScript
stand-in that links nearest features within the RT and m/z tolerances and
writes consensusXML; it does no RT alignment.

What a tool can do is what the OpenMS WebAssembly build exposes
(`public/openms/openms.d.ts`): file formats (mzML, featureXML, consensusXML,
idXML, mzIdentML, FASTA, MGF), peak picking and filters, mass trace and
feature detection, theoretical spectra, digestion, isotope patterns, and the
SimpleSearchEngine and ProSE searches. An arbitrary TOPP executable cannot run
in the browser.

### Steps

A step (`src/steps/`) is the counterpart of a Python tool: a `DEFAULTS` list
with the same keys (`key`, `value`, `name`, `help`, `hide`, `options`, `min`,
`max`, `step_size`, `widget_type`, `advanced`) that generates its widgets,
and a `run()` that gets the merged parameters and the module. Their
parameters are stored as `"<step>.ts:<key>"`.

### Results

`results` lists components of `src/lib/results/registry.ts` with their props;
each gets the workflow directory. `table` shows any TSV, CSV or JSON file of
the workflow directory as a paginated, sortable, searchable table. Add a
Svelte component there for anything else.

## Limits of running in the browser

- Only what the WebAssembly build of OpenMS exposes can run; there are no TOPP
  executables, no Python and no OpenMS-Insight (whose components need a
  Streamlit/Python side).
- Files are copied into the browser's storage; the browser cannot reference a
  file on disk in place. Storage is per browser and per site, and the browser
  may clear it under storage pressure unless the page was granted persistent
  storage (the app asks for it).
- A run lasts as long as the tab: closing it ends the run.
- Threads need a cross-origin isolated page (`serve.py`, `npm run dev`, or the
  service worker on other hosts).
