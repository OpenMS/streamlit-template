# Add Parameter Presets

Add or modify parameter presets for a TOPP workflow in `presets.json`.

## Instructions

1. **Ask the user** for:
   - Which workflow the presets are for
   - Preset names and descriptions
   - Parameter values for each preset (TOPP tool parameters and/or custom widget parameters)

2. **Determine the workflow key** from the display name:
   - Convert to lowercase, replace spaces with hyphens
   - Example: "TOPP Workflow" -> "topp-workflow"
   - Example: "Metabolite Analysis" -> "metabolite-analysis"

3. **Read or create `presets.json`** at the repository root. Add entries following this schema:

```json
{
  "workflow-name": {
    "Preset Name": {
      "_description": "Tooltip text shown on hover over the preset button",
      "TOPPToolName": {
        "algorithm:section:param_name": value
      },
      "_general": {
        "custom-widget-key": value
      }
    }
  }
}
```

4. **Verify the result** by checking that:
   - Workflow name key matches the name passed to `WorkflowManager.__init__()` (lowercased, hyphenated)
   - TOPP tool names match those used in `input_TOPP()` calls
   - Parameter paths use colon-separated format matching the TOPP tool's .ini structure
   - `_general` keys match widget keys from `input_widget()` calls
   - JSON is valid

## Schema Rules

- **Workflow key**: lowercase, hyphens — must match `WorkflowManager("Display Name", ...)` converted
- **`_description`**: optional tooltip text for the preset button
- **TOPP tool keys**: dictionary name must exactly match the TOPP tool name (e.g., `"FeatureFinderMetabo"`)
- **TOPP parameter paths**: colon-separated, e.g., `"algorithm:common:noise_threshold_int"`
- **`_general`**: overrides for custom `input_widget()` keys (non-TOPP parameters)
- **Keys starting with `_`** are metadata and not applied as tool parameters

## How Presets Work at Runtime

1. Preset buttons auto-appear in `parameter_section()` via `StreamlitUI.preset_buttons()`
2. Only presets matching the current workflow name are displayed
3. Clicking a preset updates `params.json` in the workspace and refreshes the UI
4. If no `presets.json` exists or no presets match, no buttons are shown

## Reference Files

- Existing presets: `presets.json`
- Preset loading: `src/workflow/ParameterManager.py`
- Preset buttons: `src/workflow/StreamlitUI.py` — `preset_buttons()` method
- Documentation: `docs/build_app.md` (Parameter Presets section)

## Example

For a workflow initialized as `super().__init__("Feature Analysis", ...)`:

```json
{
  "feature-analysis": {
    "High Sensitivity": {
      "_description": "Optimized for detecting low-abundance features",
      "FeatureFinderMetabo": {
        "algorithm:common:noise_threshold_int": 500.0,
        "algorithm:common:chrom_peak_snr": 2.0
      }
    },
    "Fast Processing": {
      "_description": "Quick analysis with relaxed thresholds",
      "FeatureFinderMetabo": {
        "algorithm:common:noise_threshold_int": 2000.0
      },
      "_general": {
        "run-python-script": false
      }
    }
  }
}
```

## Checklist

- [ ] Workflow key is lowercase with hyphens, matching the WorkflowManager name
- [ ] Each preset has a descriptive `_description`
- [ ] TOPP tool names match exactly
- [ ] Parameter paths use colon-separated format
- [ ] `presets.json` is valid JSON
