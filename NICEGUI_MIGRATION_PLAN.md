# Streamlit to NiceGUI Migration Plan

## Executive Summary

This document outlines a comprehensive plan for migrating the OpenMS Streamlit Template from Streamlit to NiceGUI. The migration involves significant architectural changes due to fundamental differences in execution models between the two frameworks.

**Estimated Scope**: ~15,000 lines of code to modify or rewrite
**Recommended Approach**: Hybrid migration (rewrite core framework, incrementally migrate pages)

---

## Table of Contents

1. [Architectural Comparison](#1-architectural-comparison)
2. [Migration Challenges](#2-migration-challenges)
3. [Component Mapping](#3-component-mapping)
4. [Implementation Phases](#4-implementation-phases)
5. [Detailed Task Breakdown](#5-detailed-task-breakdown)
6. [File-by-File Migration Guide](#6-file-by-file-migration-guide)
7. [Testing Strategy](#7-testing-strategy)
8. [Risk Mitigation](#8-risk-mitigation)
9. [Dependencies](#9-dependencies)

---

## 1. Architectural Comparison

### Execution Model

| Aspect | Streamlit | NiceGUI |
|--------|-----------|---------|
| **Paradigm** | Script re-execution on every interaction | Event-driven with persistent components |
| **State** | `st.session_state` (auto-synced) | `app.storage.*` or class-based (manual) |
| **Rendering** | Top-to-bottom script execution | Component tree with reactive updates |
| **Async** | Limited (experimental) | Native async/await support |
| **Updates** | Full page rerun or `@st.fragment` | WebSocket-based targeted updates |

### Navigation Model

| Aspect | Streamlit | NiceGUI |
|--------|-----------|---------|
| **Multi-page** | `st.navigation()` + `st.Page()` | `@ui.page('/route')` decorators |
| **URL State** | `st.query_params` | FastAPI query parameters |
| **Sharing** | Query param based workspace IDs | Route + query params |

### Key Implications

1. **No Script Re-execution**: All Streamlit code that relies on top-to-bottom execution must be converted to event handlers
2. **Explicit State Management**: Widget values don't auto-sync; must use binding or callbacks
3. **Component Persistence**: UI elements persist across interactions (no need to recreate)
4. **Native Async**: Long-running tasks can use proper async patterns instead of multiprocessing hacks

---

## 2. Migration Challenges

### Critical Challenges

#### 2.1 WorkflowManager Framework (~2000 lines)

**Current Design**:
```python
class WorkflowManager:
    def start_workflow(self):
        self.show_file_upload_section()  # Creates Streamlit widgets
        self.show_parameter_section()     # Creates Streamlit widgets
        self.show_execution_section()     # Polls logs via rerun
        self.show_results_section()       # Creates Streamlit widgets
```

**Challenge**: Every method assumes Streamlit's rerun model and uses `st.*` widgets directly.

**Solution**: Create `NiceGUIWorkflowManager` with component-based UI generation and event-driven updates.

#### 2.2 StreamlitUI Widget Factory (~1159 lines)

**Current Design**:
```python
class StreamlitUI:
    def input_widget(self, type, key, value, ...):
        if type == "text":
            return st.text_input(label, value, key=key)
        elif type == "number":
            return st.number_input(label, value, key=key)
        # ... etc
```

**Challenge**: Returns widget values directly (Streamlit pattern). NiceGUI widgets are objects that need binding.

**Solution**: Create `NiceGUIWidgetFactory` that returns bound components with change handlers.

#### 2.3 TOPP Parameter Generation

**Current Design**:
- Auto-generates `.ini` files via subprocess
- Parses INI to create form widgets
- Stores modified values in `params.json`
- Uses session state key prefixes

**Challenge**: Entire flow assumes Streamlit's state management.

**Solution**: Create `ParameterForm` class that:
- Generates NiceGUI form from INI
- Binds values to a parameter store
- Saves to JSON on change

#### 2.4 Real-Time Log Streaming

**Current Design**:
```python
while process_running:
    logs = read_log_file()
    display_logs()
    time.sleep(1)
    st.rerun()  # Refresh display
```

**Challenge**: Relies on script rerun for updates.

**Solution**: Use NiceGUI's native async + WebSocket:
```python
async def stream_logs():
    with ui.log() as log_display:
        while process_running:
            new_lines = await read_log_async()
            log_display.push(new_lines)
            await asyncio.sleep(1)
```

### Medium Challenges

#### 2.5 File Upload/Download

**Streamlit**:
```python
files = st.file_uploader("Upload", accept_multiple_files=True)
st.download_button("Download", data, filename)
```

**NiceGUI**:
```python
ui.upload(on_upload=handle_upload, multiple=True)
ui.button("Download", on_click=lambda: ui.download(data, filename))
```

**Additional Complexity**: Local mode uses Tkinter dialogs - need alternative for NiceGUI.

#### 2.6 Layout Components

| Streamlit | NiceGUI | Notes |
|-----------|---------|-------|
| `st.columns([1,2,1])` | `ui.row()` + `ui.column()` | Manual width control |
| `st.tabs(["A","B"])` | `ui.tabs()` + `ui.tab_panels()` | Similar API |
| `st.expander("Title")` | `ui.expansion("Title")` | Nearly identical |
| `st.sidebar` | `ui.left_drawer()` | Different behavior |
| `st.form()` | Manual event batching | No direct equivalent |

#### 2.7 Session/Workspace Management

**Current**:
- `st.session_state` for runtime state
- `st.query_params` for shareable URLs
- Workspace directories per session

**NiceGUI**:
- `app.storage.user` (server-side, per user)
- `app.storage.browser` (client-side, localStorage)
- FastAPI query params for URLs

### Lower Challenges

#### 2.8 Visualization

Both frameworks support Plotly natively:
- Streamlit: `st.plotly_chart(fig)`
- NiceGUI: `ui.plotly(fig)`

#### 2.9 CAPTCHA

Custom implementation - port logic to NiceGUI components.

#### 2.10 GDPR Consent

React component - either port to NiceGUI or use iframe embedding.

---

## 3. Component Mapping

### Widget Mapping

| Streamlit | NiceGUI | Binding Pattern |
|-----------|---------|-----------------|
| `st.text_input(key=k)` | `ui.input().bind_value(store, k)` | Two-way binding |
| `st.number_input(key=k)` | `ui.number().bind_value(store, k)` | Two-way binding |
| `st.text_area(key=k)` | `ui.textarea().bind_value(store, k)` | Two-way binding |
| `st.selectbox(key=k)` | `ui.select().bind_value(store, k)` | Two-way binding |
| `st.multiselect(key=k)` | `ui.select(multiple=True)` | Two-way binding |
| `st.checkbox(key=k)` | `ui.checkbox().bind_value(store, k)` | Two-way binding |
| `st.slider(key=k)` | `ui.slider().bind_value(store, k)` | Two-way binding |
| `st.radio(key=k)` | `ui.radio().bind_value(store, k)` | Two-way binding |
| `st.button(on_click=f)` | `ui.button(on_click=f)` | Callback |
| `st.file_uploader()` | `ui.upload(on_upload=f)` | Async callback |
| `st.download_button()` | `ui.download()` or custom | Custom handler |

### Layout Mapping

| Streamlit | NiceGUI |
|-----------|---------|
| `st.columns([1,2])` | `with ui.row(): ui.column(); ui.column()` |
| `st.tabs(["A","B"])` | `with ui.tabs(): ui.tab("A"); ui.tab("B")` |
| `st.expander("X")` | `ui.expansion("X")` |
| `st.sidebar` | `ui.left_drawer()` or `ui.header()` |
| `st.container()` | `ui.card()` or `ui.column()` |
| `st.empty()` | `ui.element()` or conditional rendering |

### Display Mapping

| Streamlit | NiceGUI |
|-----------|---------|
| `st.markdown("# H1")` | `ui.markdown("# H1")` |
| `st.write(obj)` | `ui.label(str(obj))` |
| `st.dataframe(df)` | `ui.table()` or `ui.aggrid()` |
| `st.plotly_chart(fig)` | `ui.plotly(fig)` |
| `st.image(img)` | `ui.image(img)` |
| `st.code(code)` | `ui.code(code)` |
| `st.json(data)` | `ui.json_editor(data)` |

### Status/Progress Mapping

| Streamlit | NiceGUI |
|-----------|---------|
| `st.spinner("Loading")` | `ui.spinner()` |
| `st.progress(0.5)` | `ui.linear_progress(value=0.5)` |
| `st.status("Running")` | `ui.stepper()` or custom |
| `st.success/error/warning/info()` | `ui.notify()` |
| `st.toast("Message")` | `ui.notify("Message")` |

---

## 4. Implementation Phases

### Phase 1: Foundation (Core Framework)

**Objective**: Create the NiceGUI equivalent of the workflow framework.

**Deliverables**:
1. `NiceGUIWorkflowManager` - Base workflow orchestration
2. `NiceGUIWidgetFactory` - Widget generation from specs
3. `StateManager` - Session and parameter state management
4. `FileHandler` - Upload/download handling
5. Base page layout and navigation

**Files to Create**:
```
src/nicegui/
├── __init__.py
├── workflow_manager.py      # WorkflowManager equivalent
├── widget_factory.py        # StreamlitUI equivalent
├── state_manager.py         # Session state management
├── file_handler.py          # File upload/download
├── layout.py                # Common layout components
├── navigation.py            # Multi-page navigation
└── utils.py                 # Helper functions
```

### Phase 2: Infrastructure

**Objective**: Implement supporting systems.

**Deliverables**:
1. Workspace management (create, switch, delete)
2. Parameter persistence (JSON/INI)
3. CAPTCHA system
4. GDPR consent flow
5. Logging and monitoring

**Files to Create/Modify**:
```
src/nicegui/
├── workspace.py             # Workspace management
├── parameter_manager.py     # Parameter persistence
├── captcha.py               # CAPTCHA component
├── gdpr.py                  # GDPR consent
└── logger.py                # Logging utilities
```

### Phase 3: Page Migration

**Objective**: Migrate all 16 pages to NiceGUI.

**Priority Order** (by dependency and complexity):

1. **Quick Wins** (standalone pages):
   - `quickstart.py` - Welcome page
   - `documentation.py` - Static content
   - `digest.py` - Simple tool
   - `peptide_mz_calculator.py` - Simple tool
   - `isotope_pattern_generator.py` - Simple tool
   - `fragmentation.py` - Simple tool

2. **Core Workflow**:
   - `file_upload.py` - File handling
   - `topp_workflow_file_upload.py` - Framework upload
   - `topp_workflow_parameter.py` - Parameter forms
   - `topp_workflow_execution.py` - Async execution
   - `topp_workflow_results.py` - Results display

3. **Complex Pages**:
   - `raw_data_viewer.py` - Visualization
   - `run_example_workflow.py` - pyOpenMS workflow
   - `download_section.py` - Download manager
   - `simple_workflow.py` - Caching example
   - `run_subprocess.py` - External tools

### Phase 4: Integration & Testing

**Objective**: Ensure everything works together.

**Deliverables**:
1. Integration testing
2. Migration of existing tests to NiceGUI
3. Performance optimization
4. Documentation updates
5. Docker configuration updates

### Phase 5: Polish & Deployment

**Objective**: Production readiness.

**Deliverables**:
1. UI/UX refinements
2. Error handling improvements
3. Accessibility review
4. Browser compatibility testing
5. Deployment documentation
6. PyInstaller configuration for executables

---

## 5. Detailed Task Breakdown

### Phase 1: Foundation

#### 1.1 Project Setup
- [ ] Add NiceGUI to requirements.txt
- [ ] Create `src/nicegui/` package structure
- [ ] Create main NiceGUI app entry point (`app_nicegui.py`)
- [ ] Configure NiceGUI settings (theme, storage, etc.)

#### 1.2 StateManager
- [ ] Define state storage strategy (app.storage.user vs class-based)
- [ ] Implement workspace state management
- [ ] Implement parameter state management with JSON persistence
- [ ] Create state binding utilities for widgets
- [ ] Implement cache clearing on workspace change

#### 1.3 NiceGUIWidgetFactory
- [ ] Create base `WidgetFactory` class
- [ ] Implement `input_widget()` method with type dispatch
- [ ] Implement `input_TOPP()` for INI-based forms
- [ ] Implement `input_python()` for DEFAULTS-based forms
- [ ] Add advanced/basic parameter toggle support
- [ ] Implement widget value binding to state store

#### 1.4 NiceGUIWorkflowManager
- [ ] Create base `WorkflowManager` class
- [ ] Implement `show_file_upload_section()` with NiceGUI components
- [ ] Implement `show_parameter_section()` with NiceGUI forms
- [ ] Implement `show_execution_section()` with async log streaming
- [ ] Implement `show_results_section()` with NiceGUI displays
- [ ] Port `workflow_process()` async execution model

#### 1.5 FileHandler
- [ ] Implement async file upload handling
- [ ] Create upload widget with drag-and-drop
- [ ] Implement file download (single file and ZIP)
- [ ] Port external file reference support
- [ ] Implement example data fallback loading
- [ ] Create file browser component

#### 1.6 Navigation & Layout
- [ ] Create main app layout with header/sidebar/content
- [ ] Implement multi-page navigation with routes
- [ ] Create sidebar navigation component
- [ ] Implement workspace switcher in sidebar
- [ ] Add hardware monitoring display (CPU/RAM)
- [ ] Create common page wrapper component

### Phase 2: Infrastructure

#### 2.1 Workspace Management
- [ ] Port workspace directory structure creation
- [ ] Implement online mode (UUID-based workspaces)
- [ ] Implement local mode (user-named workspaces)
- [ ] Create workspace create/delete UI
- [ ] Implement query param based workspace sharing
- [ ] Port workspace cleanup script

#### 2.2 Parameter Persistence
- [ ] Port `ParameterManager` class
- [ ] Implement JSON parameter save/load
- [ ] Implement INI file generation for TOPP tools
- [ ] Create parameter export (JSON) functionality
- [ ] Create parameter export (Markdown) functionality
- [ ] Implement parameter import functionality
- [ ] Add reset to defaults functionality

#### 2.3 CAPTCHA System
- [ ] Port CAPTCHA image generation
- [ ] Create CAPTCHA verification component
- [ ] Implement session state for verification status
- [ ] Add regeneration on wrong answer

#### 2.4 GDPR Consent
- [ ] Create consent dialog component
- [ ] Implement consent state persistence
- [ ] Integrate with analytics enable/disable
- [ ] Port or recreate consent UI

#### 2.5 Logging & Execution
- [ ] Port multi-level Logger class
- [ ] Create real-time log display component
- [ ] Implement async log streaming
- [ ] Port CommandExecutor for TOPP tools
- [ ] Implement process management (start/stop)
- [ ] Create progress indicators

### Phase 3: Page Migration

#### 3.1 Simple Tools (Standalone)
- [ ] Migrate `quickstart.py`
- [ ] Migrate `documentation.py`
- [ ] Migrate `digest.py`
- [ ] Migrate `peptide_mz_calculator.py`
- [ ] Migrate `isotope_pattern_generator.py`
- [ ] Migrate `fragmentation.py`

#### 3.2 TOPP Workflow Pages
- [ ] Migrate `topp_workflow_file_upload.py`
- [ ] Migrate `topp_workflow_parameter.py`
- [ ] Migrate `topp_workflow_execution.py`
- [ ] Migrate `topp_workflow_results.py`

#### 3.3 Complex Pages
- [ ] Migrate `file_upload.py`
- [ ] Migrate `raw_data_viewer.py`
- [ ] Migrate `run_example_workflow.py`
- [ ] Migrate `download_section.py`
- [ ] Migrate `simple_workflow.py`
- [ ] Migrate `run_subprocess.py`

### Phase 4: Integration & Testing

#### 4.1 Testing Framework
- [ ] Set up NiceGUI testing infrastructure
- [ ] Create test utilities for component testing
- [ ] Implement mock file upload/download
- [ ] Create workflow execution tests

#### 4.2 Test Migration
- [ ] Convert page launch tests
- [ ] Convert widget interaction tests
- [ ] Convert workflow execution tests
- [ ] Convert documentation tests

#### 4.3 Integration Testing
- [ ] Test full workflow end-to-end
- [ ] Test workspace management flows
- [ ] Test file upload/download cycles
- [ ] Test parameter persistence
- [ ] Test multi-user scenarios

### Phase 5: Polish & Deployment

#### 5.1 UI/UX
- [ ] Apply consistent theming
- [ ] Add loading states and transitions
- [ ] Implement error boundaries
- [ ] Add keyboard navigation
- [ ] Review mobile responsiveness

#### 5.2 Deployment
- [ ] Update Dockerfile
- [ ] Update docker-compose.yml
- [ ] Test containerized deployment
- [ ] Update PyInstaller configuration
- [ ] Test Windows executable generation

#### 5.3 Documentation
- [ ] Update README.md
- [ ] Update developer documentation
- [ ] Create migration guide
- [ ] Update API documentation

---

## 6. File-by-File Migration Guide

### Core Files

#### `app.py` → `app_nicegui.py`

**Before (Streamlit)**:
```python
import streamlit as st

pages = {
    "Category": [
        st.Page("content/page1.py", title="Page 1"),
        st.Page("content/page2.py", title="Page 2"),
    ]
}
pg = st.navigation(pages)
pg.run()
```

**After (NiceGUI)**:
```python
from nicegui import ui, app

@ui.page('/')
def home():
    with ui.header():
        ui.label("App Name")
    with ui.left_drawer():
        ui.link("Page 1", "/page1")
        ui.link("Page 2", "/page2")
    ui.label("Welcome!")

@ui.page('/page1')
def page1():
    # Page 1 content
    pass

@ui.page('/page2')
def page2():
    # Page 2 content
    pass

ui.run(title="App Name", port=8501)
```

#### `src/workflow/StreamlitUI.py` → `src/nicegui/widget_factory.py`

**Before (Streamlit)**:
```python
def input_widget(self, type, key, value, **kwargs):
    if type == "text":
        return st.text_input(kwargs.get("label", key), value, key=key)
    elif type == "number":
        return st.number_input(kwargs.get("label", key), value, key=key)
```

**After (NiceGUI)**:
```python
def input_widget(self, type: str, key: str, value: Any, **kwargs) -> ui.element:
    label = kwargs.get("label", key)

    if type == "text":
        widget = ui.input(label, value=value)
    elif type == "number":
        widget = ui.number(label, value=value)

    # Bind to state store
    widget.bind_value(self.state_store, key)
    return widget
```

#### `src/workflow/WorkflowManager.py` → `src/nicegui/workflow_manager.py`

**Before (Streamlit)**:
```python
def show_execution_section(self):
    with st.status("Running..."):
        while self.executor.is_running():
            logs = self.read_logs()
            st.write(logs)
            time.sleep(1)
            st.rerun()
```

**After (NiceGUI)**:
```python
async def show_execution_section(self):
    with ui.card():
        log_display = ui.log()
        progress = ui.linear_progress(value=0)

        async for log_line in self.stream_logs():
            log_display.push(log_line)
            progress.value = self.get_progress()
```

#### `src/common/common.py` → `src/nicegui/utils.py`

**Before (Streamlit)**:
```python
def page_setup(page: str = ""):
    settings = load_settings()
    st.set_page_config(page_title=settings["app-name"])

    if "workspace" not in st.session_state:
        st.session_state.workspace = create_workspace()
```

**After (NiceGUI)**:
```python
def page_setup(page: str = ""):
    settings = load_settings()

    # Access user storage
    if "workspace" not in app.storage.user:
        app.storage.user["workspace"] = create_workspace()

    return settings
```

### Content Pages

#### Simple Tool Example: `content/digest.py`

**Before (Streamlit)**:
```python
import streamlit as st
from utils.digest import digest_protein

st.title("Protein Digest")
sequence = st.text_area("Enter sequence")
enzyme = st.selectbox("Enzyme", ["Trypsin", "Chymotrypsin"])

if st.button("Digest"):
    results = digest_protein(sequence, enzyme)
    st.dataframe(results)
```

**After (NiceGUI)**:
```python
from nicegui import ui
from utils.digest import digest_protein

@ui.page('/digest')
def digest_page():
    ui.label("Protein Digest").classes('text-h4')

    sequence = ui.textarea("Enter sequence")
    enzyme = ui.select("Enzyme", options=["Trypsin", "Chymotrypsin"])
    results_table = ui.table(columns=[], rows=[]).classes('hidden')

    async def run_digest():
        results = digest_protein(sequence.value, enzyme.value)
        results_table.columns = [{"name": c, "label": c, "field": c} for c in results.columns]
        results_table.rows = results.to_dict('records')
        results_table.classes(remove='hidden')

    ui.button("Digest", on_click=run_digest)
```

#### Workflow Page Example: `content/topp_workflow_execution.py`

**Before (Streamlit)**:
```python
from src.Workflow import Workflow

workflow = Workflow()
workflow.show_execution_section()
```

**After (NiceGUI)**:
```python
from nicegui import ui
from src.nicegui.workflow import Workflow

@ui.page('/workflow/execution')
async def execution_page():
    workflow = Workflow()
    await workflow.show_execution_section()
```

---

## 7. Testing Strategy

### Unit Tests

Test individual components in isolation:

```python
# test_widget_factory.py
from src.nicegui.widget_factory import WidgetFactory

def test_input_widget_text():
    factory = WidgetFactory()
    widget = factory.input_widget("text", "test_key", "test_value")
    assert widget.value == "test_value"

def test_input_widget_number():
    factory = WidgetFactory()
    widget = factory.input_widget("number", "test_key", 42)
    assert widget.value == 42
```

### Integration Tests

Test page workflows:

```python
# test_workflow.py
from nicegui.testing import Screen

async def test_workflow_execution(screen: Screen):
    screen.open('/workflow/execution')
    screen.click('Start Workflow')
    await screen.wait_for('Workflow Complete')
    assert screen.find('Download Results').is_visible()
```

### E2E Tests

Test complete user journeys:

```python
# test_e2e.py
async def test_full_workflow(screen: Screen):
    # Upload files
    screen.open('/workflow/upload')
    screen.upload('example.mzML')

    # Configure parameters
    screen.open('/workflow/parameters')
    screen.fill('mass_tolerance', '10')

    # Execute
    screen.open('/workflow/execution')
    screen.click('Start')
    await screen.wait_for('Complete', timeout=120)

    # Download results
    screen.open('/workflow/results')
    screen.click('Download')
```

---

## 8. Risk Mitigation

### High Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking workflow execution | Critical | Extensive testing, run in parallel with Streamlit during transition |
| Data loss in workspaces | Critical | Backup workspace data, test migration scripts |
| Performance regression | High | Benchmark critical paths, profile before/after |
| User experience regression | High | A/B testing, user feedback collection |

### Medium Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Browser compatibility issues | Medium | Test on Chrome, Firefox, Safari, Edge |
| Mobile responsiveness | Medium | Test on various screen sizes |
| Memory leaks in long sessions | Medium | Profile memory usage, implement cleanup |

### Rollback Plan

1. Keep Streamlit version functional during migration
2. Feature flag to switch between implementations
3. Database migration scripts reversible
4. Docker images tagged by version

---

## 9. Dependencies

### New Dependencies

Add to `requirements.txt`:

```
nicegui>=1.4.0
fastapi>=0.100.0
uvicorn>=0.23.0
python-multipart>=0.0.6  # For file uploads
aiofiles>=23.0.0         # For async file operations
```

### Removed Dependencies

These Streamlit-specific packages can be removed after migration:

```
streamlit
streamlit-js-eval
```

### Updated Dependencies

Some packages may need version updates for NiceGUI compatibility:

```
plotly>=5.22.0  # NiceGUI plotly support
pandas>=2.0.0   # For data handling
```

---

## Appendix A: NiceGUI Quick Reference

### State Management

```python
# User-specific (server-side, survives page refresh)
app.storage.user['key'] = value

# Browser-specific (localStorage)
app.storage.browser['key'] = value

# Global (shared across all users)
app.storage.general['key'] = value

# Tab-specific (lost on refresh)
app.storage.tab['key'] = value
```

### Reactive Updates

```python
# Binding
ui.input().bind_value(storage, 'key')

# Refreshable
@ui.refreshable
def my_section():
    ui.label(f"Value: {state.value}")

# Manual update
element.refresh()
```

### Async Patterns

```python
# Async page
@ui.page('/async')
async def async_page():
    result = await long_running_task()
    ui.label(result)

# Background task
ui.timer(1.0, lambda: update_display())

# Async button handler
async def handle_click():
    await process_data()
ui.button("Run", on_click=handle_click)
```

### File Handling

```python
# Upload
def handle_upload(e: events.UploadEventArguments):
    content = e.content.read()
    filename = e.name

ui.upload(on_upload=handle_upload, multiple=True)

# Download
ui.button("Download", on_click=lambda: ui.download(data, "file.txt"))
```

---

## Appendix B: Migration Checklist

### Pre-Migration
- [ ] Backup all workspace data
- [ ] Document current behavior
- [ ] Set up parallel development branch
- [ ] Create feature flags

### During Migration
- [ ] Phase 1 complete and tested
- [ ] Phase 2 complete and tested
- [ ] Phase 3 complete and tested
- [ ] Phase 4 complete and tested
- [ ] Phase 5 complete and tested

### Post-Migration
- [ ] All tests passing
- [ ] Performance benchmarks met
- [ ] User acceptance testing complete
- [ ] Documentation updated
- [ ] Deployment successful
- [ ] Old code removed
- [ ] Monitoring in place

---

*Document Version: 1.0*
*Last Updated: 2026-01-15*
