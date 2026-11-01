---
name: new-app-from-spec
description: Use when creating a new OpenMS web app from the template, or when generating or regenerating an app's workflows, pages and identity from its app.yaml spec.
---

# New app from a spec

Turn an `app.yaml` spec into a working app: a repository derived from the
template, its identity set everywhere, one `WorkflowManager` subclass per
workflow with its four pages, result views, presets and deployment config.
The spec is the input; this skill never invents what the spec does not say.

The notebook route (`notebook-to-webapp`) is for when the science lives in a
notebook. This route is for when it can be written down as TOPP tools and
python-tools.

## 1. Get a valid spec

Start from the template's `app.yaml` and change it, or take the user's.
Schema: `utils/app_spec.schema.json`. Check it before anything else:

```bash
python -m utils.app_spec path/to/app.yaml
```

Ask the user only for what the schema requires and is missing (`app.slug`,
`app.name`, `app.repository`, `app.domain`, at least one workflow with steps).
Propose a default for each from the rest of the spec. Every TOPP tool named in
`steps` must exist (`<Tool> --help` in the full image, or the OpenMS docs); a
step that is not a TOPP tool is a `python:` step (a script in
`src/python-tools/`) or an `external:` one (an adapter's third-party binary).

## 2. Create the repository with template history

The app must share history with the template, or `sync-from-template` cannot
merge later. Never copy files into an empty repository.

```bash
git clone https://github.com/OpenMS/streamlit-template <slug>
cd <slug>
git remote rename origin template
git remote add origin https://github.com/<app.repository>.git
git branch --show-current     # the template's default, main; rename only if it differs
cp /path/to/the/spec/app.yaml app.yaml   # the user's spec replaces the template's example
python -m utils.app_spec      # schema check now; the consistency errors are expected until step 3
```

From here on every step reads `app.yaml` in the new repository, never the
template's example.

Creating the GitHub repository itself is the user's step (or an org admin's);
ask for it and continue locally meanwhile.

## 3. Identity

Run `configure-app-identity` with the spec's `app` block. It writes
settings.json, the k8s overlay, the storage tier names, the image names and the
desktop installer names, and `python -m utils.app_spec` checks them afterwards.

## 4. Workflows

For each entry of `workflows`, follow `create-workflow`, filled from the spec
instead of from an interview:

| spec | code |
|---|---|
| `name` | `super().__init__("<name>", ...)`; slug = lowercase-hyphenated name |
| `inputs` + top-level `inputs.<key>.types` | one `self.ui.upload_widget(key=<key>, file_types=<types>)` per key; `raw`/`d` in types means `execution()` calls `self.executor.convert_to_mzml()` first |
| `steps[].tool` | `self.ui.input_TOPP("<tool>")` in `configure()`, `self.executor.run_topp("<tool>", ...)` in `execution()`, gated on its return value |
| `steps[].instance` | `tool_instance_name=` in **both** calls |
| `steps[].collect` | `self.file_manager.get_files(prev, collect=True)` |
| `steps[].in` | the input key or the earlier step whose outputs feed this one |
| `steps[].python` | `self.ui.input_python("<name>")` + `run_python`; the script needs a `DEFAULTS` list (`add-python-tool`) |
| `steps[].optional` | an `input_widget` checkbox in `configure()`; skip the step when it is off |
| `multi_run: true` | `multi_run = True` on the class; read results via `self.results_dir` |
| `presets: true` | an entry in `presets.json` (`add-presets`) |

`execution()` is `-> bool` and returns `True` only when every step succeeded.
Register the four pages in `app.py` under a section named after the workflow.

## 5. Results

For each entry of `results`, map `role` to a component by lookup, the same
vocabulary as `build-insight-dashboard`: `table` → `show_insight_table`,
`peakmap` → Insight `Heatmap`, `mirror`/`spectrum` → Insight `LinePlot`,
`volcano` → `VolcanoPlot`, `sequence` → `SequenceView`. `custom` names an
app-owned page and is left to the user. Add `openms-insight` to
`requirements.txt` when any Insight role is used.

## 6. Remove what the app does not use

Delete the template's example pages and their `app.py` entries unless `pages`
lists them, and remove the example workflow if no spec workflow reuses
`src/Workflow.py`. Keep `content/documentation.py` and rewrite `docs/` intro
text from `app.description`.

## 7. Deployment

`deploy.k8s.enabled` → `configure-k8s-deployment`, answering its interview
from `deploy.k8s` (hosts, storage, worker_tier, replicas). `deploy.desktop` →
`configure-desktop-installers`. `deploy.docker_compose` →
`configure-docker-compose-deployment`. Copy
`.github/workflows/template-sync.yml` unchanged; it reads `template:` from the
spec.

## 8. Prove it

```bash
python -m utils.app_spec
python -m pytest test_gui.py tests/
streamlit run app.py   # upload the example data, run each workflow once
```

A workflow that has not run end to end on example data is not done. Open the
PR against the new repository, not the template.

## Checklist

- [ ] Spec valid, and every TOPP tool in it exists
- [ ] Repository shares history with the template (`git merge-base HEAD template/main` prints a commit)
- [ ] `configure-app-identity` ran; `python -m utils.app_spec` clean
- [ ] One workflow class per spec workflow, every executor call gated
- [ ] Result views mapped by role; Insight in requirements if used
- [ ] Unused template pages removed
- [ ] Each workflow ran once on example data
