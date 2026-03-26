# OpenMS Streamlit WebApp Template

## Project Overview

This is the base template for building mass spectrometry (MS) web applications using Streamlit and OpenMS/pyOpenMS. All OpenMS web apps are derived from this template, including:

- **OpenMS/quantms-web** — quantitative proteomics workflows
- **OpenMS/umetaflow** — untargeted metabolomics analysis (UmetaFlow pipeline)
- **OpenMS/FLASHApp** — top-down proteomics visualization (FLASHDeconv results)

These derived apps customize the template by adding domain-specific workflows, pages, and tools while inheriting the core framework.

## Architecture

```
app.py                          # Entry point — registers pages via st.Page() in a dict
settings.json                   # App config: name, version, deployment mode, threading
default-parameters.json         # Default workspace parameters (tracked via widget keys)
presets.json                    # Parameter presets for TOPP workflows
content/                        # Streamlit pages (one .py per page)
src/
  common/common.py              # Utilities: page_setup(), save_params(), show_fig(), show_table()
  Workflow.py                   # Example WorkflowManager subclass (TOPP workflow)
  workflow/
    WorkflowManager.py          # Base class: upload/configure/execution/results pattern
    StreamlitUI.py              # Widget library: upload_widget, input_TOPP, input_python, etc.
    ParameterManager.py         # JSON parameter persistence + TOPP .ini generation
    CommandExecutor.py           # Runs TOPP tools and Python scripts as subprocesses
    FileManager.py              # Workspace file organization
    Logger.py                   # Structured workflow logging
    QueueManager.py             # Redis queue for online deployments
  python-tools/                 # Custom Python analysis scripts (with DEFAULTS dicts)
Dockerfile                      # Full build: OpenMS + TOPP tools + pyOpenMS
Dockerfile_simple               # Lightweight: pyOpenMS only
docker-compose.yml              # Deployment config
```

## Key Patterns

### Pages

Every page starts with `page_setup()` which handles workspace initialization, sidebar rendering, and parameter loading:

```python
from src.common.common import page_setup
params = page_setup()
```

Pages are registered in `app.py` under named sections:

```python
pages = {
    "Section Name": [
        st.Page(Path("content", "my_page.py"), title="My Page", icon="🔬"),
    ],
}
```

### Parameters

Parameters are tracked via widget keys that match entries in `default-parameters.json`. The `save_params(params)` call at the end of a page persists any widget state changes:

```python
params = page_setup()
st.number_input("X", value=params["my-param"], key="my-param")
save_params(params)
```

### TOPP Workflows (WorkflowManager)

Complex workflows subclass `WorkflowManager` and implement 4 methods:
- `upload()` — file upload widgets via `self.ui.upload_widget()`
- `configure()` — TOPP params via `self.ui.input_TOPP()`, Python tool params via `self.ui.input_python()`
- `execution()` — run tools via `self.executor.run_topp()` and `self.executor.run_python()`
- `results()` — display outputs

Each workflow gets 4 content pages (upload, configure, run, results) that call `wf.show_*_section()`.

Decorate `configure()` and `results()` with `@st.fragment` for partial reruns.

### Python Tools

Custom scripts in `src/python-tools/` define a `DEFAULTS` list for auto-generated UI:

```python
DEFAULTS = [
    {"key": "in", "value": [], "hide": True},
    {"key": "my-param", "value": 5, "name": "My Parameter", "help": "Description",
     "min": 1, "max": 100, "step_size": 1, "widget_type": "slider"},
]
```

### Presets

Parameter presets in `presets.json` map workflow names (lowercase, hyphens) to named parameter sets:

```json
{
  "workflow-name": {
    "Preset Name": {
      "_description": "Tooltip text",
      "TOPPToolName": {"algorithm:section:param": value},
      "_general": {"custom-key": value}
    }
  }
}
```

## Visualization Libraries

Two libraries are commonly used in template-based apps:

### pyopenms-viz
Pandas DataFrame extension for MS visualization. Use the plotly backend in Streamlit:
```python
import pyopenms_viz
df.plot.ms_spectrum(backend="plotly")  # spectrum plot
df.plot.peak_map(backend="plotly")     # 2D peak map
df.plot.chromatogram(backend="plotly") # chromatogram
```

### OpenMS-Insight (t0mdavid-m/openms-insight)
Vue.js-backed interactive Streamlit components for large MS datasets:
- `Table` — server-side pagination with Tabulator.js
- `LinePlot` — stick-style mass spectra via Plotly
- `Heatmap` — 2D scatter handling millions of points
- `VolcanoPlot` — differential expression visualization
- `SequenceView` — peptide sequence with fragment ion matching

Components support cross-linking via shared identifiers.

## Commands

```bash
# Run locally
pip install -r requirements.txt
streamlit run app.py

# Run tests
python -m pytest tests/

# Docker
docker-compose up --build
```

## Conventions

- Page files go in `content/`, source logic in `src/`
- Widget keys must match parameter keys in `default-parameters.json`
- Workflow names use lowercase with hyphens: "My Workflow" -> "my-workflow"
- Use `show_fig()` and `show_table()` from `src/common/common.py` for consistent display
- Use `@st.fragment` on methods that should partially rerun (configure, results)
- TOPP tool parameters use colon-separated paths: `"algorithm:section:param_name"`
