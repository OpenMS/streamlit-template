# Investigation: AI Agent for Interactive OpenMS WebApp Generation

## Executive Summary

This document investigates how to build an AI agent system that allows users to describe their mass spectrometry analysis requirements in natural language and interactively generate Streamlit webapps using the OpenMS ecosystem (pyopenms, TOPP tools, pyopenms-viz).

The recommended approach is a **Claude Agent SDK-based system** that leverages the existing `streamlit-template` as a scaffolding framework, with specialized sub-agents for planning, code generation, and preview/testing.

---

## Table of Contents

1. [Current Template Architecture](#1-current-template-architecture)
2. [OpenMS Ecosystem Capabilities](#2-openms-ecosystem-capabilities)
3. [Agent Architecture Design](#3-agent-architecture-design)
4. [Implementation Approaches](#4-implementation-approaches)
5. [Skill & Knowledge System](#5-skill--knowledge-system)
6. [Preview & Testing Strategy](#6-preview--testing-strategy)
7. [Recommended Implementation Plan](#7-recommended-implementation-plan)
8. [Open Questions & Risks](#8-open-questions--risks)

---

## 1. Current Template Architecture

The `streamlit-template` provides a production-grade foundation with:

### Core Framework (`src/workflow/`, ~3,185 lines)
- **`WorkflowManager`** — Base class with 4-phase pattern: `upload()`, `configure()`, `execution()`, `results()`
- **`StreamlitUI`** — Auto-generates Streamlit widgets from TOPP tool `.ini` files (1,434 lines)
- **`ParameterManager`** — Handles parameter persistence, presets, and session state
- **`CommandExecutor`** — Executes TOPP tools with parallel threading support
- **`FileManager`** — Manages workspace file paths and I/O routing

### App Structure
- **`app.py`** — Multi-page navigation with `st.Page()` registration
- **`content/`** — 16 page files demonstrating various patterns (TOPP workflows, pyOpenMS tools, visualizations)
- **`settings.json`** / **`presets.json`** — Global configuration and parameter presets

### Key Patterns an Agent Must Understand
1. **Creating a new workflow** = subclass `WorkflowManager` + create content page(s) + register in `app.py`
2. **Adding a TOPP tool** = call `self.ui.input_TOPP("ToolName")` in `configure()` + `self.executor.run_topp("ToolName", ...)` in `execution()`
3. **Adding a visualization** = use `pyopenms-viz` DataFrames with `st.plotly_chart()` or custom Plotly code
4. **Adding a simple tool** = create a standalone content page using pyopenms directly (see `peptide_mz_calculator.py`)

---

## 2. OpenMS Ecosystem Capabilities

### pyopenms (v3.3.0+)
Python bindings to the OpenMS C++ library. Provides:
- **File I/O**: mzML, mzXML, featureXML, consensusXML, idXML, FASTA, mzTab, etc.
- **Core types**: `MSExperiment`, `MSSpectrum`, `FeatureMap`, `ConsensusMap`
- **Chemistry**: `AASequence`, `EmpiricalFormula`, `TheoreticalSpectrumGenerator`
- **Signal processing**: Peak picking, smoothing, filtering, calibration
- **Feature detection**: `FeatureFinderCentroided`, `FeatureFinderMetabo`, etc.
- **Identification**: Search engine wrappers, FDR, protein inference
- **Parameter system**: `Param`, `ParamXMLFile` for tool configuration

### TOPP Tools (100+ command-line tools)
Organized by category:
- **File handling**: `FileConverter`, `FileFilter`, `FileMerger`
- **Peak picking**: `PeakPickerHiRes`
- **Feature detection**: `FeatureFinderMetabo`, `FeatureFinderCentroided`, `FeatureFinderIdentification`
- **Map alignment**: `MapAlignerPoseClustering`, `MapAlignerIdentification`
- **Feature linking**: `FeatureLinkerUnlabeledKD`, `FeatureLinkerUnlabeledQT`
- **Identification**: `CometAdapter`, `SageAdapter`, `MSGFPlusAdapter`
- **Post-processing**: `FalseDiscoveryRate`, `PeptideIndexer`, `IDFilter`
- **Quantification**: `ProteinQuantifier`, `ProteomicsLFQ`, `IsobaricAnalyzer`
- **Metabolomics**: `AccurateMassSearch`, `MetaboliteSpectralMatcher`, `SiriusAdapter`
- **Cross-linking**: `OpenPepXL`, `RNPxlSearch`
- **DIA/SWATH**: `OpenSwathWorkflow` and associated tools
- **Quality control**: `QualityControl`

### pyopenms-viz (v1.0.0+)
DataFrame-based MS visualization with multiple backends:
```python
import pandas as pd
pd.set_option("plotting.backend", "ms_plotly")
df.plot(kind="chromatogram")   # RT vs intensity
df.plot(kind="spectrum")       # m/z vs intensity
df.plot(kind="peakmap")        # 2D heatmap (RT x m/z)
df.plot(kind="mobilogram")     # Ion mobility
```
Outputs standard Plotly/Bokeh/matplotlib figures compatible with `st.plotly_chart()`.

### openms-insight (v0.1.13+)
[GitHub: t0mdavid-m/openms-insight](https://github.com/t0mdavid-m/openms-insight) — A Python library providing **interactive Vue.js-based Streamlit custom components** for mass spectrometry data visualization. Created by Tom David Muller (Kohlbacher Lab, co-lead author of the OpenMS WebApps paper). Installable via `pip install openms-insight`.

**Five visualization components:**

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Table** | Tabulator.js | Server-side paginated, filterable, sortable tables with CSV export and custom formatters (scientific, signed, badge) |
| **LinePlot** | Plotly.js | Stick-style mass spectrum visualization with peak highlighting, selection, annotations, and SVG export |
| **Heatmap** | Plotly scattergl | 2D scatter plots with multi-resolution cascading downsampling, categorical coloring, zoom-based level selection |
| **VolcanoPlot** | Plotly.js | Differential expression visualization with adjustable significance thresholds, three-category coloring |
| **SequenceView** | Custom Vue | Peptide sequence display with fragment ion matching (uses pyopenms `TheoreticalSpectrumGenerator`), amino acid modification rendering |

**Key architectural features:**
- **Cross-component linked selection** via `StateManager` — clicking a row in a Table highlights the corresponding point in a Heatmap or LinePlot
- **Declarative filter/interactivity mapping** — components declare `filters={"key": "column"}` and `interactivity={"key": "column"}` for linkage
- **Multi-resolution downsampling** — cascading spatial binning for million-point heatmaps (smooth zooming)
- **Server-side pagination** — only current page sent to browser, enabling millions-of-rows tables
- **Subprocess preprocessing** — heavy computation in spawned processes so memory is freed
- **Automatic disk caching** — preprocessed data saved to Parquet with config-hash invalidation
- **Cache reconstruction** — components reinstantiated from cache without re-specifying data

**Tech stack:** Python + Polars (backend preprocessing) → Vue 3 + Pinia + Vuetify + Plotly.js + Tabulator.js (frontend)

**Usage pattern:**
```python
from openms_insight import Table, Heatmap, LinePlot, StateManager
import polars as pl

data = pl.scan_parquet("features.parquet")
state = StateManager()

table = Table(
    cache_id="feature_table", data=data,
    filters={"selected": "feature_id"},
    interactivity={"selected": "feature_id"},
)
heatmap = Heatmap(
    cache_id="feature_map", data=data,
    filters={"selected": "feature_id"},
    x_col="RT", y_col="mz", value_col="intensity",
)

table()    # Render table
heatmap()  # Render heatmap — linked to table selections
```

**Relationship to pyopenms-viz:** While pyopenms-viz provides single-line DataFrame plotting (matplotlib/Plotly/Bokeh backends), openms-insight provides richer interactive components with cross-component state, server-side pagination, and caching. They are complementary — pyopenms-viz for quick static/simple interactive plots, openms-insight for complex interactive dashboards with large datasets.

---

## 3. Agent Architecture Design

### Recommended: Claude Agent SDK with Specialized Sub-Agents

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface Layer                       │
│  (Streamlit chat interface OR CLI via Claude Agent SDK)       │
└──────────────┬──────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                   Orchestrator Agent                         │
│  - Interprets user requirements                              │
│  - Manages conversation state                                │
│  - Delegates to specialized sub-agents                       │
│  - Tracks progress via structured files                      │
└──────┬──────────┬───────────────┬──────────────┬────────────┘
       │          │               │              │
       ▼          ▼               ▼              ▼
┌──────────┐ ┌──────────┐ ┌───────────┐ ┌────────────────┐
│ Planner  │ │  Coder   │ │ Reviewer  │ │ Preview/Test   │
│ Agent    │ │  Agent   │ │ Agent     │ │ Agent          │
│          │ │          │ │           │ │                │
│ - Asks   │ │ - Genera-│ │ - Checks  │ │ - Launches     │
│   clarif.│ │   tes    │ │   code    │ │   Streamlit    │
│   ques-  │ │   Stream-│ │   quality │ │ - Captures     │
│   tions  │ │   lit    │ │ - Verifies│ │   errors       │
│ - Builds │ │   code   │ │   OpenMS  │ │ - Reports      │
│   spec   │ │ - Uses   │ │   usage   │ │   results      │
│ - Selects│ │   templ- │ │ - Ensures │ │ - Takes        │
│   TOPP   │ │   ate    │ │   best    │ │   screenshots  │
│   tools  │ │   patt-  │ │   pract.  │ │                │
│          │ │   erns   │ │           │ │                │
└──────────┘ └──────────┘ └───────────┘ └────────────────┘
```

### Core Loop

```
1. USER describes requirements ("I need a metabolomics feature finding workflow")
2. PLANNER asks clarifying questions, selects appropriate tools, produces spec
3. USER confirms/refines the spec
4. CODER generates Streamlit code using template patterns
5. PREVIEW agent launches the app, captures errors
6. REVIEWER validates code quality and OpenMS best practices
7. Results shown to USER for feedback
8. Loop back to step 4 for refinements
```

---

## 4. Implementation Approaches

### Approach A: Claude Agent SDK (Recommended)

**Architecture**: Python application using the Claude Agent SDK to create a multi-agent system.

```python
from claude_agent_sdk import query, ClaudeAgentOptions

# Main orchestrator
async for message in query(
    prompt=user_requirement,
    options=ClaudeAgentOptions(
        system_prompt=ORCHESTRATOR_PROMPT,
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        agents=[planner_agent, coder_agent, reviewer_agent, preview_agent],
        cwd="/path/to/workspace"
    )
):
    display_to_user(message)
```

**Advantages**:
- Leverages Claude's strong code generation capabilities
- Built-in tool use (file read/write/edit, bash for running streamlit)
- Sub-agent support for specialized tasks
- Session resumption for long-running interactions
- MCP (Model Context Protocol) for custom tool integrations
- Same infrastructure that powers Claude Code

**Custom MCP Tools to Build**:

| Tool | Purpose |
|------|---------|
| `list_topp_tools` | Query available TOPP tools and their descriptions |
| `get_topp_params` | Get parameter schema for a specific TOPP tool |
| `preview_app` | Launch Streamlit app and report status/errors |
| `validate_workflow` | Check that a workflow follows template patterns |
| `get_template_pattern` | Return code snippets for common patterns |

**Skill Files** (`.claude/skills/`):
```
.claude/skills/
├── openms-webapp-builder/
│   └── SKILL.md          # How to generate OpenMS webapps
├── topp-workflow/
│   └── SKILL.md          # How to create TOPP-based workflows
├── pyopenms-tools/
│   └── SKILL.md          # How to use pyopenms in Streamlit
├── visualization/
│   └── SKILL.md          # How to use pyopenms-viz
└── openms-insight/
    └── SKILL.md          # How to use openms-insight interactive components
```

### Approach B: Streamlit Chat Interface with LLM Backend

**Architecture**: A Streamlit app that embeds a chat interface, calling the Anthropic API directly.

```python
import streamlit as st
import anthropic

st.title("OpenMS WebApp Builder")

# Chat interface
user_input = st.chat_input("Describe your webapp...")

if user_input:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        system=BUILDER_SYSTEM_PROMPT,
        messages=st.session_state.messages + [{"role": "user", "content": user_input}],
        tools=[...],  # Custom tool definitions
    )
    # Process tool calls, generate code, show preview
```

**Advantages**:
- Self-contained — the builder IS a Streamlit app
- Users interact through familiar Streamlit UI
- Can show live preview in an iframe or separate tab
- No CLI dependency

**Disadvantages**:
- More complex to implement tool use properly
- Must handle file operations manually
- No built-in sub-agent support

### Approach C: Hybrid — Claude Agent SDK Backend + Streamlit Frontend

**Architecture**: Streamlit frontend for user interaction, Claude Agent SDK running as a backend service.

```
┌─────────────────┐     HTTP/WebSocket     ┌──────────────────┐
│   Streamlit UI   │ ◄──────────────────► │  Agent Service    │
│   (chat + preview│                       │  (Claude SDK)     │
│    + file browser)│                       │  (FastAPI)        │
└─────────────────┘                       └──────────────────┘
```

This mirrors the [agent-service-toolkit](https://github.com/JoshuaC215/agent-service-toolkit) pattern (LangGraph + FastAPI + Streamlit).

**Advantages**:
- Best of both worlds — rich UI + powerful agent
- Agent can run long tasks asynchronously
- Frontend can show real-time progress
- Scalable architecture

**Disadvantages**:
- Most complex to build and deploy
- Two services to manage

### Recommendation

**Start with Approach A (Claude Agent SDK)** for rapid prototyping and validation. It provides the most capable agent infrastructure with minimal boilerplate. Migrate to Approach C if a web-based UI becomes a requirement for end users who don't have CLI access.

---

## 5. Skill & Knowledge System

The agent needs deep knowledge of the OpenMS ecosystem to generate correct code. This is best provided through a combination of:

### 5.1 System Prompt — Core Patterns

The system prompt should encode the fundamental patterns:

```markdown
# OpenMS WebApp Generation Rules

## Workflow Creation Pattern
To create a new TOPP-based workflow:
1. Subclass `WorkflowManager` in `src/YourWorkflow.py`
2. Implement `upload()`, `configure()`, `execution()`, `results()`
3. Create content pages in `content/`
4. Register pages in `app.py`

## Available TOPP Tools by Use Case
- Feature detection (metabolomics): FeatureFinderMetabo
- Feature detection (proteomics): FeatureFinderCentroided
- Feature linking: FeatureLinkerUnlabeledKD
- Map alignment: MapAlignerPoseClustering
- Database search: CometAdapter, SageAdapter
- FDR control: FalseDiscoveryRate
- Protein inference: Epifany
...
```

### 5.2 Skill Files — Detailed Reference

Placed in `.claude/skills/` for progressive disclosure:

**`openms-webapp-builder/SKILL.md`**:
```markdown
# OpenMS WebApp Builder Skill

## Template Structure
- app.py: Multi-page navigation (st.Page registration)
- content/: Page files (one per page)
- src/: Workflow classes and framework code
- src/workflow/: Core framework (DO NOT MODIFY)

## Code Patterns

### Simple pyOpenMS Tool Page
[Complete example based on peptide_mz_calculator.py]

### TOPP Workflow (4-page pattern)
[Complete example based on Workflow.py + topp_workflow_*.py]

### Custom pyOpenMS Workflow
[Complete example based on mzmlfileworkflow.py + run_example_workflow.py]

### Visualization with pyopenms-viz
[Examples using ms_plotly backend with st.plotly_chart()]

### Interactive Dashboards with openms-insight
[Examples using Table, Heatmap, LinePlot, VolcanoPlot, SequenceView]
[StateManager for cross-component linked selection]
[When to use openms-insight vs pyopenms-viz]
```

### 5.3 Tool Parameter Database

A structured reference of TOPP tool capabilities:

```json
{
  "FeatureFinderMetabo": {
    "description": "Detects features in centroided LC-MS metabolomics data",
    "input_formats": ["mzML"],
    "output_formats": ["featureXML"],
    "key_parameters": {
      "algorithm:common:noise_threshold_int": "Intensity threshold for noise removal",
      "algorithm:common:chrom_peak_snr": "Signal-to-noise ratio for peak detection",
      "algorithm:mtd:mass_error_ppm": "Allowed mass deviation in ppm"
    },
    "typical_pipelines": ["Metabolomics feature finding", "UmetaFlow"]
  }
}
```

### 5.4 Example Workflows Library

Pre-built workflow specifications that the agent can reference or adapt:

| Workflow | Tools Used | Use Case |
|----------|-----------|----------|
| Metabolomics Feature Finding | `FeatureFinderMetabo` → `FeatureLinkerUnlabeledKD` | Untargeted metabolomics |
| Proteomics Database Search | `PeakPickerHiRes` → `CometAdapter` → `PeptideIndexer` → `FalseDiscoveryRate` | Bottom-up proteomics |
| Label-Free Quantification | `ProteomicsLFQ` | Protein quantification |
| DIA/SWATH Analysis | `OpenSwathWorkflow` → `PyProphet` → `TRIC` | Data-independent acquisition |
| Cross-Linking MS | `OpenPepXL` → `XFDR` | Structural proteomics |
| RNA MS | `NucleicAcidSearchEngine` | Oligonucleotide analysis |

---

## 6. Preview & Testing Strategy

### 6.1 Streamlit Auto-Reload

Streamlit's built-in auto-reload is ideal for iterative development:

```python
# Agent writes/edits code files
# Streamlit detects changes and auto-reloads
# Agent captures any errors from stderr
```

### 6.2 Preview Agent Implementation

```python
import subprocess
import time

def preview_app(app_path: str, port: int = 8502) -> dict:
    """Launch Streamlit app and capture startup errors."""
    proc = subprocess.Popen(
        ["streamlit", "run", app_path, "--server.port", str(port),
         "--server.headless", "true"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(5)  # Wait for startup

    if proc.poll() is not None:
        # Process crashed
        return {"status": "error", "stderr": proc.stderr.read().decode()}

    return {"status": "running", "url": f"http://localhost:{port}"}
```

### 6.3 Validation Checks

The reviewer agent should verify:
1. **Import correctness** — All pyopenms/TOPP imports exist
2. **File format chains** — Output formats match next tool's input formats
3. **Parameter validity** — Parameter names exist for the specified tool version
4. **Template compliance** — Code follows `WorkflowManager` patterns
5. **Session state safety** — Proper use of `st.session_state` keys
6. **Error handling** — Graceful handling of missing files, invalid data

### 6.4 Testing Pipeline

```bash
# Syntax check
python -c "import ast; ast.parse(open('content/new_page.py').read())"

# Import check
python -c "import content.new_page"

# Full app launch test
streamlit run app.py --server.headless true &
sleep 10
curl -s http://localhost:8501 | grep -q "200"

# Run existing test suite
pytest tests/
```

---

## 7. Recommended Implementation Plan

### Phase 1: Foundation — Skill Files & Knowledge Base

**Goal**: Encode OpenMS domain knowledge so the agent can generate correct code.

**Deliverables**:
1. `.claude/skills/openms-webapp-builder/SKILL.md` — Core patterns and rules
2. `.claude/skills/topp-tools/SKILL.md` — TOPP tool reference with parameters
3. `.claude/skills/pyopenms-viz/SKILL.md` — Visualization patterns (simple/quick plots)
4. `.claude/skills/openms-insight/SKILL.md` — Interactive component patterns (complex dashboards)
5. `tools/topp_tool_registry.json` — Machine-readable TOPP tool database
6. `tools/workflow_templates/` — Example workflow specifications

### Phase 2: Agent Prototype — Single-Agent with Claude Agent SDK

**Goal**: Working prototype that can generate simple webapps from natural language.

**Deliverables**:
1. `agent/builder.py` — Main agent script using `claude_agent_sdk.query()`
2. System prompt with OpenMS knowledge and template patterns
3. Custom MCP tools: `list_topp_tools`, `get_topp_params`, `preview_app`
4. Basic write→test→fix loop

**Example interaction**:
```
User: Create a webapp for metabolomics feature detection from mzML files
Agent: I'll create a metabolomics feature detection workflow. Let me ask a few questions:
  1. Do you need feature linking across multiple samples?
  2. What mass accuracy does your instrument provide (ppm)?
  3. Do you want to include adduct detection?
User: Yes to linking, 5 ppm, no adducts
Agent: [Generates Workflow.py + content pages + registers in app.py]
Agent: [Launches preview, verifies no errors]
Agent: Your app is ready! It includes:
  - File upload for mzML files
  - FeatureFinderMetabo configuration (5 ppm default)
  - FeatureLinkerUnlabeledKD for cross-sample linking
  - Interactive feature map visualization
```

### Phase 3: Multi-Agent System

**Goal**: Specialized agents for higher quality output.

**Deliverables**:
1. **Planner agent** — Interviews user, selects tools, generates spec
2. **Coder agent** — Generates Streamlit code from spec
3. **Reviewer agent** — Validates code quality, OpenMS correctness
4. **Preview agent** — Launches app, captures errors, reports status
5. Orchestrator that manages the agent pipeline

### Phase 4: Web-Based UI (Optional)

**Goal**: Make the builder accessible to non-CLI users.

**Deliverables**:
1. Streamlit chat interface for the builder
2. FastAPI backend wrapping Claude Agent SDK
3. Live preview panel (iframe or separate tab)
4. Workspace management for multiple generated apps

---

## 8. Resolved Decisions

| Question | Decision | Implication |
|----------|----------|-------------|
| **Target users** | CLI-comfortable developers/bioinformaticians | Use **Approach A: Claude Agent SDK** directly — no web UI needed for the builder itself |
| **Scope of generation** | Both standalone apps and pages within existing template | Agent needs two modes: scaffold-from-template and add-page-to-existing |
| **TOPP tool availability** | Flexible — compile from source or provide precompiled binaries | Include TOPP binaries in the agent's environment (Docker image or local install) |
| **Visualization default** | openms-insight first, pyopenms-viz as fallback | Agent defaults to openms-insight components; only falls back to pyopenms-viz for plot types openms-insight doesn't cover (chromatogram, mobilogram, peakmap 3D) |

---

## 9. Open Question: Repository Location

### Option A: Inside this `streamlit-template` repo

**For:**
- Agent lives next to the code it generates — zero-friction access to template patterns, example workflows, and framework source
- Skill files (`.claude/skills/`) are repo-scoped by design, so they naturally belong here
- Contributors to the template can also contribute to the agent
- Single CI/CD pipeline; agent tests can verify generated code against the real template
- The template IS the agent's primary knowledge source — co-location keeps them in sync

**Against:**
- Bloats the template repo with agent infrastructure (`agent/`, MCP tools, system prompts, test fixtures)
- Template users who just want to build webapps manually must carry agent code they don't use
- Different release cadences — agent may iterate faster than the template framework
- Muddies the repo's purpose: is it a template or an agent?

### Option B: Separate repo (e.g., `OpenMS/openms-webapp-agent`)

**For:**
- Clean separation of concerns — template is the "library", agent is the "consumer"
- Independent versioning and release cycles
- Agent repo can pin a specific template version, avoiding breakage from template changes
- Easier to add other agent capabilities later (e.g., generating non-Streamlit apps, batch processing scripts)
- Lighter template repo stays focused on its core purpose

**Against:**
- Cross-repo synchronization burden — template pattern changes must be manually propagated to agent skill files
- Skill files can't be repo-scoped (would need to be copied or symlinked)
- Two repos to clone, two CI pipelines to maintain
- The agent needs the template source code at generation time anyway — so it will either clone it or vendor it, adding complexity

### Recommendation

**Start inside this repo** (as `agent/` + `.claude/skills/`), with the expectation of extracting to a separate repo if/when the agent grows beyond simple code generation. The skill files *must* live here regardless (they're repo-scoped Claude Code config), so starting co-located avoids premature indirection.

---

## 10. Remaining Open Questions

1. **Model selection**: Claude Opus for planning/reviewing, Claude Sonnet for code generation (faster, cheaper), Claude Haiku for simple validation tasks? Or single model throughout?

2. **pyopenms-viz fallback scope**: openms-insight doesn't cover chromatogram, mobilogram, or 3D peakmap plot types. Should the agent use pyopenms-viz for these, or should we request these as openms-insight features?

3. **Existing app migration**: Should the agent be able to refactor existing OpenMS webapps (e.g., adding openms-insight components to an app currently using raw Plotly)?

---

## 11. Risks

| Risk | Mitigation |
|------|------------|
| Generated code has incorrect TOPP tool parameters | Validate against `.ini` files; use `get_topp_params` tool |
| Hallucinated pyopenms API calls | Skill files with verified examples; reviewer agent checks |
| Incorrect openms-insight component config | Validate filter/interactivity mappings against DataFrame columns |
| Streamlit session state conflicts | Template enforces naming conventions; validation checks |
| Context window exhaustion on complex apps | Claude Agent SDK context compaction; break into sub-tasks |
| Preview launch failures | Headless mode; error capture; fallback to syntax-only check |
| User requirements too vague | Planner agent asks structured questions before generation |

### Dependencies

- **Claude Agent SDK** (Python): `pip install claude-agent-sdk`
- **Anthropic API key**: Required for agent operation
- **OpenMS TOPP tools**: Required for `.ini` generation and workflow testing
- **pyopenms**: Required for parameter validation
- **pyopenms-viz**: Required for simple visualization code generation
- **openms-insight**: Required for interactive dashboard generation (`pip install openms-insight`)

---

## Appendix A: Comparison of Implementation Approaches

| Criterion | A: Claude Agent SDK | B: Streamlit + API | C: Hybrid |
|-----------|---------------------|-------------------|-----------|
| Time to prototype | Low | Medium | High |
| Code generation quality | High (built-in tools) | Medium | High |
| User experience | CLI-based | Web-based | Web-based |
| Sub-agent support | Native | Manual | Via SDK |
| Session management | Built-in | Manual | Built-in |
| Preview capability | Bash tool | iframe | iframe |
| Deployment complexity | Low | Low | Medium |
| Scalability | Single user | Multi-user | Multi-user |

## Appendix B: Relevant External Projects

- **[Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)** — Anthropic's SDK for building custom agents (powers Claude Code)
- **[agent-service-toolkit](https://github.com/JoshuaC215/agent-service-toolkit)** — LangGraph + FastAPI + Streamlit reference architecture
- **[streamlit-app-builder](https://github.com/sitamgithub-MSIT/streamlit-app-builder)** — Gemini-based Streamlit app generator from mockups
- **[Bolt.new](https://github.com/stackblitz/bolt.new)** — In-browser full-stack app builder with WebContainers
- **[Dyad](https://www.dyad.sh/)** — Open-source local-first AI app builder

## Appendix C: Existing OpenMS WebApps (Built with this Template)

These serve as reference implementations the agent can learn from:
- **TOPPView Lite** — MS data viewer
- **StreamSage** — Proteomics database searching
- **UmetaFlow** — Metabolomics pipeline
- **FLASHViewer** — Top-down proteomics
- **NuXL** — Cross-linking analysis
- **NASEWEIS** — Oligonucleotide MS analysis
- **MHCQuant** — Immunopeptidomics

## Appendix D: Visualization Library Decision Guide

| Criterion | pyopenms-viz | openms-insight |
|-----------|-------------|----------------|
| **Complexity** | Single-line `.plot()` calls | Component instantiation with config |
| **Interactivity** | Basic (Plotly zoom/pan) | Rich (cross-component linking, selection) |
| **Large datasets** | Limited by browser memory | Multi-resolution downsampling, server-side pagination |
| **Plot types** | Chromatogram, spectrum, peakmap, mobilogram | Table, LinePlot, Heatmap, VolcanoPlot, SequenceView |
| **Backend** | Plotly, Bokeh, matplotlib | Vue.js + Plotly.js + Tabulator.js |
| **State management** | None | StateManager with cross-component sync |
| **Caching** | None | Automatic disk caching with hash invalidation |
| **Best for** | Quick exploratory plots, simple apps | Interactive dashboards, production apps, large datasets |

**Agent heuristic**: Default to pyopenms-viz for simple visualization pages. Switch to openms-insight when the user needs: (a) linked selection across components, (b) tables with >10K rows, (c) heatmaps with >100K points, (d) peptide sequence/fragment visualization, or (e) differential expression volcano plots.
