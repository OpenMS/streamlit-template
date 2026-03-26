# Add a Python Analysis Tool

Add a custom Python analysis script to `src/python-tools/` with auto-generated UI.

## Instructions

1. **Ask the user** for:
   - Tool name (lowercase, hyphens for spaces)
   - What the tool does
   - Input/output file types
   - Parameters: name, type, default value, constraints

2. **Create the tool script** at `src/python-tools/<name>.py`:

```python
import json
import sys

DEFAULTS = [
    # Hidden I/O parameters (always include these)
    {"key": "in", "value": [], "help": "Input files.", "hide": True},
    {"key": "out", "value": [], "help": "Output files.", "hide": True},
    # Visible parameters — examples of each type:
    {
        "key": "threshold",
        "value": 1000.0,
        "name": "Intensity Threshold",
        "help": "Minimum intensity for filtering.",
        "min": 0.0,
        "max": 100000.0,
        "step_size": 100.0,
    },
    {
        "key": "method",
        "value": "default",
        "name": "Processing Method",
        "options": ["default", "advanced", "custom"],
        "help": "Which algorithm to use.",
    },
    {
        "key": "num-features",
        "value": 10,
        "name": "Number of Features",
        "widget_type": "slider",
        "min": 1,
        "max": 100,
        "step_size": 1,
        "help": "How many features to report.",
    },
    {
        "key": "advanced-setting",
        "value": 5,
        "name": "Advanced Setting",
        "help": "Only shown in advanced mode.",
        "advanced": True,
    },
    {
        "key": "enabled",
        "value": True,
        "name": "Enable Processing",
    },
]


def get_params():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r") as f:
            return json.load(f)
    else:
        return {}


if __name__ == "__main__":
    params = get_params()
    # Tool logic here — read inputs, process, write outputs
```

3. **Wire into a workflow** by adding to the workflow's `configure()` and `execution()` methods:

```python
# In configure():
self.ui.input_python("tool_name")

# In execution():
self.executor.run_python("tool_name", {"in": input_files})
```

## DEFAULTS Metadata Keys

| Key | Required | Type | Description |
|-----|----------|------|-------------|
| `key` | Yes | str | Unique identifier for the parameter |
| `value` | Yes | any | Default value (type determines widget: bool=checkbox, str with options=selectbox, number=number_input) |
| `name` | No | str | Display name in the UI |
| `help` | No | str | Tooltip text |
| `hide` | No | bool | If `True`, parameter is not shown in UI (use for in/out files) |
| `options` | No | list | Valid choices — renders as selectbox |
| `min` | No | number | Minimum value for numeric inputs |
| `max` | No | number | Maximum value for numeric inputs |
| `step_size` | No | number | Step size for numeric inputs |
| `widget_type` | No | str | Override widget type: `"slider"`, `"textarea"`, `"number"`, `"text"`, etc. |
| `advanced` | No | bool | If `True`, only shown when user expands advanced parameters |

## Reference Files

- Example tool: `src/python-tools/example.py`
- Another example: `src/python-tools/export_consensus_feature_df.py`
- UI generation: `src/workflow/StreamlitUI.py` — `input_python()` method
- Execution: `src/workflow/CommandExecutor.py` — `run_python()` method

## Checklist

- [ ] Script created in `src/python-tools/` with DEFAULTS list
- [ ] `get_params()` function and `__main__` block included
- [ ] `in` and `out` keys in DEFAULTS with `"hide": True`
- [ ] Wired into workflow via `self.ui.input_python()` and `self.executor.run_python()`
