# Create a New Streamlit Page

Add a new page to the OpenMS web application.

## Instructions

1. **Ask the user** for:
   - Page name and icon (emoji)
   - Which section in the sidebar it belongs to (look at existing sections in `app.py`)
   - Whether it needs tracked parameters
   - Whether it's a standalone page or part of a workflow

2. **Create the page file** at `content/<page_name>.py` following this pattern:

```python
import streamlit as st
from src.common.common import page_setup, save_params

params = page_setup()

st.title("Page Title")

# Page content here using Streamlit components
# For tracked parameters, use matching keys:
# st.number_input("Label", value=params["my-key"], key="my-key")

save_params(params)
```

3. **Register the page** in `app.py` by adding an entry to the `pages` dictionary:

```python
st.Page(Path("content", "<page_name>.py"), title="Page Title", icon="🔬"),
```

Add to an existing section or create a new section key in the dict.

4. **Add default parameters** if the page uses tracked widget state. Add entries to `default-parameters.json` with keys matching the widget `key=` arguments.

5. **Create source logic** if the page has non-trivial logic. Put it in `src/<page_name>.py` and import from the page file.

## Reference Files

- Existing pages: `content/` directory (e.g., `content/quickstart.py`, `content/digest.py`)
- Page setup function: `src/common/common.py` — `page_setup()`, `save_params()`, `show_fig()`, `show_table()`
- App entry point: `app.py` (page registration in pages dict)
- Default parameters: `default-parameters.json`

## Real-World Examples

- **quantms-web** (OpenMS/quantms-web) adds proteomics-specific pages for quantification results, quality control, and statistical analysis
- **umetaflow** (OpenMS/umetaflow) adds metabolomics pages for feature detection, annotation, and EIC extraction
- **FLASHApp** (OpenMS/FLASHApp) adds specialized visualization pages for FLASHDeconv results with custom Vue.js components

## Checklist

- [ ] Page file created in `content/`
- [ ] Page registered in `app.py` pages dict
- [ ] Default parameters added to `default-parameters.json` (if any)
- [ ] `page_setup()` called at top of page
- [ ] `save_params(params)` called at bottom of page
- [ ] Source logic in `src/` if non-trivial
