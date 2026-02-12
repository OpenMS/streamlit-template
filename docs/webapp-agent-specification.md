# Specification: OpenMS WebApp Builder Agent

> An AI agent system that lets users describe mass spectrometry analysis requirements in natural language and interactively build Streamlit webapps using pyopenms, TOPP tools, openms-insight, and pyopenms-viz.

**Status**: Specification
**Date**: 2026-02-12
**Companion**: See `webapp-agent-investigation.md` for research and exploratory notes.

---

## 1. Product Overview

### 1.1 What It Is

A conversational agent that guides users through building OpenMS Streamlit webapps via a two-phase interactive flow:

1. **Pipeline design** — The user describes their analysis. The agent proposes a processing pipeline as a diagram, the user refines it.
2. **Results configuration** — The agent suggests debug-first visualizations based on the pipeline's output file types. The user selects which views to include.

The agent then generates the complete Streamlit application, verifies it launches, and supports iterative refinement within the same session.

### 1.2 What It Is Not

- Not a form-filling wizard — the user describes what they want conversationally.
- Not one-shot generation — the user iterates ("also add X", "make Y faster", "change Z").
- Not just code generation — the agent verifies the app launches and can diagnose runtime errors.
- Not an autonomous system — the user approves the pipeline and results layout before code generation begins.

### 1.3 Target Users

CLI-comfortable developers and bioinformaticians who understand mass spectrometry concepts but may not know the streamlit-template internals, OpenMS tool names, or openms-insight APIs.

---

## 2. User Experience

### 2.1 The Two-Phase Flow

```
User describes requirements
        │
        ▼
┌─────────────────────────────────┐
│  PHASE 1: Pipeline Design        │
│                                   │
│  Agent asks clarifying questions  │
│  Agent proposes pipeline diagram  │
│  User approves / modifies         │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│  PHASE 2: Results Configuration  │
│                                   │
│  Agent suggests default views     │
│  (debug-first: Tables for every   │
│   intermediate output)            │
│  User adds optional views         │
│  User approves layout             │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│  CODE GENERATION & PREVIEW       │
│                                   │
│  Agent generates Streamlit code   │
│  Agent launches app, verifies     │
│  User sees preview, gives feedback│
│  Agent iterates                   │
└─────────────────────────────────┘
```

### 2.2 Phase 1: Pipeline Design

The agent asks domain-specific clarifying questions, then presents a pipeline diagram showing:

- Input files and their formats
- Each processing step (TOPP tool or pyopenms operation)
- File format transformations at each step
- Whether each step runs per-file or collects all files

**Example interaction:**

```
User: I need an untargeted metabolomics workflow. Users upload centroided
      mzML files, detect features, link across samples, and explore results.

Agent: A few questions:
  1. What mass accuracy does your instrument provide (ppm)?
  2. Should users be able to adjust feature detection parameters,
     or lock them to sensible defaults?

User: 5 ppm, let them adjust but show good defaults.

Agent:
  mzML files (upload)
    │
    ▼ per file
  FeatureFinderMetabo              ← TOPP tool, configurable
  mzML → featureXML                   5 ppm mass tolerance default
    │
    ▼ all files collected
  FeatureLinkerUnlabeledKD         ← TOPP tool, configurable
  featureXML[] → consensusXML
    │
    ▼ export
  ConsensusXML → Polars LazyFrame

  Does this pipeline look right?

User: Add adduct detection after feature finding.

Agent: Updated:
  ...
  FeatureFinderMetabo
  mzML → featureXML
    │
    ▼ per file                     ← NEW
  MetaboliteAdductDecharger        ← NEW
  featureXML → featureXML          ← NEW
    │
    ▼ all files collected
  FeatureLinkerUnlabeledKD
  ...
```

The user modifies the pipeline through conversation ("add X after Y", "remove Z", "make W configurable") until they approve it.

### 2.3 Phase 2: Results Configuration

Once the pipeline is approved, the agent proposes visualizations based on the output file types of each step. The principle is **debug-first**: every intermediate file type gets a Table view by default so users can verify each step worked.

**Example interaction:**

```
Agent: Now let's set up the results. Based on your pipeline outputs:

  ── Step Outputs (debug views) ──────────────────────────────

  FeatureFinderMetabo → featureXML (per sample)
    ☑ Table: features per file (RT, m/z, intensity, charge, quality)
    ☐ Heatmap: RT × m/z scatter per file

  FeatureLinkerUnlabeledKD → consensusXML
    ☑ Table: consensus features (RT, m/z, intensities per sample)
    ☐ Heatmap: RT × m/z with sample as color category

  ── Summary Views ───────────────────────────────────────────

    ☐ Bar chart: feature count per sample
    ☐ Bar chart: total intensity per sample

  ☑ = included by default, ☐ = available to add.
  Which additional views do you want?

User: Add the heatmaps and the feature count bar chart.

Agent: Updated results layout:

  Results page 1: "Step Outputs"
  ┌─────────────────────────────────────────────────┐
  │  Selectbox: choose sample file                   │
  │                                                   │
  │  Table ◄──► Heatmap                              │
  │  (features for     (RT × m/z,                    │
  │   selected file)    linked selection)             │
  └─────────────────────────────────────────────────┘

  Results page 2: "Cross-Sample Results"
  ┌─────────────────────────────────────────────────┐
  │  Bar chart: feature count per sample             │
  │                                                   │
  │  Table ◄──► Heatmap                              │
  │  (consensus         (RT × m/z,                   │
  │   features)          sample as color)            │
  └─────────────────────────────────────────────────┘

  Should I generate the app?
```

### 2.4 File-Type-to-Visualization Mapping

The agent uses deterministic rules to suggest visualizations based on output file types:

| Output Format | Default Views (☑) | Optional Views (☐) |
|--------------|-------------------|-------------------|
| **featureXML** (per file) | Table (RT, mz, intensity, charge, quality, FWHM) | Heatmap (x=RT, y=mz, value=intensity) |
| **consensusXML** | Table (RT, mz, quality, intensity_0..N) | Heatmap (x=RT, y=mz, color=sample or intensity); Bar chart (feature count per sample); Bar chart (total intensity per sample) |
| **idXML** | Table (sequence, charge, score, RT, mz, protein) | LinePlot (matched spectrum, needs mzML); SequenceView (peptide + fragment ions, needs mzML); Score distribution histogram |
| **mzML** (raw) | Table (spectrum index, RT, MS level, TIC, base peak) | LinePlot (selected spectrum); Heatmap (x=RT, y=mz, value=intensity) via pyopenms-viz peakmap |
| **mzTab** | Table (protein/peptide/PSM sections) | VolcanoPlot (if fold-change + p-value columns present); Bar chart (quantification summary) |

### 2.5 Iterative Refinement

After code generation, the user can refine in the same session:

```
User: The consensus table has too many columns. Hide the per-sample
      intensity columns by default.

Agent: [Edits the Table column config]

User: Add a spectrum viewer — when I click a consensus feature, show the
      MS1 spectrum closest to that RT from the first sample.

Agent: That needs the original mzML files at results time. I'll add pyopenms
       code to extract the nearest spectrum and display it as a LinePlot
       linked to the consensus Table via StateManager.
       [Adds spectrum extraction logic + LinePlot component]
```

---

## 3. System Architecture

### 3.1 Deployment Modes

The system supports two deployment modes:

**Mode A: CLI (Claude Agent SDK)** — For developers. The agent runs locally via Claude Code or a custom Agent SDK script. Generated apps run on localhost. This is the primary development and prototyping mode.

**Mode B: Web UI with Live Preview** — For broader access. A web interface with a chat panel and a live preview panel showing the generated app running in a sandboxed Docker container.

```
┌──────────────────────────────────────────────────────┐
│                    Browser                            │
│  ┌────────────────────┐  ┌─────────────────────────┐ │
│  │   Chat Panel        │  │  Live Preview (iframe)  │ │
│  │                      │  │                          │ │
│  │   Conversational     │  │  Generated Streamlit     │ │
│  │   pipeline design    │  │  app running in sandbox  │ │
│  │   + results config   │  │  auto-reloads on edits   │ │
│  └────────────────────┘  └─────────────────────────┘ │
└───────────┬──────────────────────────┬───────────────┘
            │ WebSocket                 │ HTTPS (proxied)
            ▼                           ▼
┌────────────────────┐    ┌───────────────────────────┐
│ Orchestrator       │    │ Reverse Proxy (Traefik)    │
│ (FastAPI +         │───►│ /preview/{session}         │
│  Claude Agent SDK) │    │ → sandbox container:{port} │
└────────────────────┘    └──────────┬────────────────┘
                                     ▼
                          ┌───────────────────────────┐
                          │ Sandbox Pool               │
                          │  ┌─────────┐ ┌─────────┐  │
                          │  │ OpenMS  │ │ OpenMS  │  │
                          │  │ Docker  │ │ Docker  │  │
                          │  │ + TOPP  │ │ + TOPP  │  │
                          │  └─────────┘ └─────────┘  │
                          └───────────────────────────┘
```

### 3.2 Agent Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Orchestrator Agent                       │
│  - Manages the two-phase conversation flow               │
│  - Maintains the pipeline spec as a structured object    │
│  - Delegates to specialized sub-agents                   │
└────┬──────────┬──────────────┬──────────────┬───────────┘
     │          │              │              │
     ▼          ▼              ▼              ▼
┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────────────────┐
│ Planner │ │ Coder   │ │ Reviewer │ │ Preview/Test   │
│         │ │         │ │          │ │                │
│ Phase 1 │ │ Genera- │ │ Checks   │ │ Launches app   │
│ + 2     │ │ tes     │ │ code     │ │ in container   │
│ conver- │ │ Stream- │ │ quality, │ │ or locally,    │
│ sation  │ │ lit     │ │ format   │ │ captures       │
│         │ │ code    │ │ chains,  │ │ errors         │
│         │ │         │ │ security │ │                │
└─────────┘ └─────────┘ └──────────┘ └────────────────┘
```

### 3.3 Pipeline Specification Object

During Phase 1, the agent builds and maintains a structured pipeline specification:

```python
pipeline_spec = {
    "name": "Metabolomics Feature Finding",
    "inputs": [
        {"name": "mzML files", "format": "mzML", "multiple": True,
         "constraints": ["centroided"]},
    ],
    "steps": [
        {
            "tool": "FeatureFinderMetabo",
            "type": "topp",
            "per": "file",
            "in": {"in": "mzML"},
            "out": {"out": "featureXML"},
            "configurable": True,
            "prominent_params": [
                "algorithm:common:noise_threshold_int",
                "algorithm:mtd:mass_error_ppm",
                "algorithm:common:chrom_peak_snr",
            ],
        },
        {
            "tool": "MetaboliteAdductDecharger",
            "type": "topp",
            "per": "file",
            "in": {"in": "featureXML"},
            "out": {"out": "featureXML"},
            "configurable": True,
            "prominent_params": [
                "algorithm:MetaboliteFeatureDeconvolution:potential_adducts",
            ],
        },
        {
            "tool": "FeatureLinkerUnlabeledKD",
            "type": "topp",
            "per": "collected",
            "in": {"in": "featureXML[]"},
            "out": {"out": "consensusXML"},
            "configurable": True,
            "prominent_params": [
                "algorithm:link:rt_tol",
                "algorithm:link:mz_tol",
            ],
        },
    ],
    "results": {
        "pages": [
            {
                "title": "Step Outputs",
                "components": [
                    {"type": "Table", "data_source": "featureXML",
                     "scope": "per_file", "columns": ["RT", "mz", "intensity", "charge", "quality"]},
                    {"type": "Heatmap", "data_source": "featureXML",
                     "scope": "per_file", "x": "RT", "y": "mz", "value": "intensity",
                     "linked_to": "Table", "link_key": "feature_id"},
                ],
            },
            {
                "title": "Cross-Sample Results",
                "components": [
                    {"type": "bar_chart", "data_source": "consensusXML",
                     "metric": "feature_count_per_sample"},
                    {"type": "Table", "data_source": "consensusXML",
                     "columns": ["RT", "mz", "quality", "avg_intensity", "n_samples"]},
                    {"type": "Heatmap", "data_source": "consensusXML",
                     "x": "RT", "y": "mz", "color": "sample",
                     "linked_to": "Table", "link_key": "consensus_id"},
                ],
            },
        ],
    },
}
```

This spec drives three things:
1. **Diagram rendering** — formatted as the ASCII pipeline shown to the user
2. **Code generation** — translated into `WorkflowManager` methods by the Coder agent
3. **Validation** — the Reviewer agent checks that output formats chain correctly

### 3.4 Code Generation Targets

The agent generates code following the `streamlit-template` patterns:

| Generated File | Purpose |
|----------------|---------|
| `src/MyWorkflow.py` | `WorkflowManager` subclass with `upload()`, `configure()`, `execution()`, `results()` |
| `content/my_workflow_upload.py` | Upload page — calls `workflow.upload()` |
| `content/my_workflow_configure.py` | Configure page — calls `workflow.configure()` |
| `content/my_workflow_run.py` | Execution page — calls `workflow.execution()` |
| `content/my_workflow_results.py` | Results page(s) — openms-insight components |
| `app.py` (edited) | Page registration via `st.Page()` |
| `presets.json` (edited) | Parameter defaults for the specific use case |

---

## 4. TOPP Tool Parameter Curation

### 4.1 Three-Tier Parameter Visibility

For each TOPP tool, parameters are organized into three tiers:

| Tier | Visibility | Who Decides | Example |
|------|-----------|-------------|---------|
| **Always hidden** | Never shown to webapp users | Agent (deterministic) | `-in`, `-out`, `-ini`, `-threads`, `-log`, `-debug`, `-force` |
| **Prominent** | Shown prominently on the Configure page | Domain expert (per tool, per use case) | `mass_error_ppm`, `noise_threshold_int`, `enzyme` |
| **Advanced** | Shown under an "Advanced" expander | Domain expert (per tool, per use case) | `reestimate_mt_sd`, `width_filtering`, `trace_termination_*` |

### 4.2 What the Agent Handles Automatically

The agent can always hide framework/internal parameters without domain input:
- File I/O paths (`-in`, `-out`, `-ini`) — handled by `CommandExecutor`
- `-threads` — set by the framework
- `-log`, `-debug`, `-test`, `-force`, `-no_progress` — runtime flags

For tools not yet curated by a domain expert, the agent falls back to showing all non-internal parameters grouped by subsection (the current template default behavior).

### 4.3 What Requires Domain Expert Input

The following must be provided by domain experts and encoded in the skill files:

**Prominent parameters per tool per use case:**
```yaml
FeatureFinderMetabo:
  untargeted_metabolomics:
    prominent:
      - algorithm:common:noise_threshold_int:
          label: "Noise threshold"
          hint: "Set based on instrument. Orbitrap: ~1e4, TOF: ~1e3"
      - algorithm:mtd:mass_error_ppm:
          label: "Mass accuracy (ppm)"
          hint: "Match your instrument spec"
      - algorithm:common:chrom_peak_snr:
          label: "Peak signal-to-noise"
          hint: "Lower = more features, higher = fewer but more confident"
    advanced:
      - algorithm:epd:width_filtering
      - algorithm:mtd:reestimate_mt_sd
```

**Instrument-specific defaults:**
```yaml
defaults_by_instrument:
  Orbitrap:  { mass_error_ppm: 5,  noise_threshold_int: 1e4 }
  TOF:       { mass_error_ppm: 20, noise_threshold_int: 1e3 }
  TripleQuad: { mass_error_ppm: 50, noise_threshold_int: 1e2 }
```

**Parameter warnings:**
```yaml
warnings:
  - param: algorithm:common:noise_threshold_int
    condition: "> 1e6"
    message: "Very high threshold — you may miss low-abundance features"
  - param: algorithm:mtd:mass_error_ppm
    condition: "< 1"
    message: "Sub-ppm tolerance is unrealistic for most instruments"
```

**Pipeline ordering rules:**
```yaml
ordering_rules:
  - after: CometAdapter
    must_run: PeptideIndexer
    reason: "FalseDiscoveryRate requires indexed peptides"
  - after: FeatureFinderMetabo
    optional: MetaboliteAdductDecharger
    reason: "Adduct grouping improves feature linking"
```

### 4.4 Bootstrapping Process

1. Pick the 10 most-used TOPP tools across existing OpenMS webapps
2. For each, have a domain expert spend ~5 minutes listing: prominent parameters, hidden parameters, and "gotcha" warnings
3. Encode into skill files as structured YAML blocks
4. Refine iteratively: every time the agent makes a wrong parameter decision, update the skill file

---

## 5. Visualization Strategy

### 5.1 Library Selection

| Library | Default for | Rationale |
|---------|------------|-----------|
| **openms-insight** | Tables, Heatmaps, LinePlots, VolcanoPlots, SequenceViews | Cross-component linking, server-side pagination, caching for large datasets |
| **pyopenms-viz** | Chromatograms, mobilograms, 3D peakmaps | Plot types openms-insight doesn't cover |
| **Raw Plotly** | Simple summary charts (bar charts, histograms) | Lightweight, no special MS semantics needed |

### 5.2 Debug-First Principle

Every intermediate pipeline output gets a Table view by default. Tables are the most debuggable — users can scroll, sort, filter, and immediately see if something went wrong (0 features, garbage scores, missing proteins). Interactive visualizations are opt-in additions on top.

### 5.3 Cross-Component Linking Pattern

When the agent generates openms-insight components, it wires them with `StateManager`:

```python
from openms_insight import Table, Heatmap, StateManager

state = StateManager()

# Table produces a selection
table = Table(
    cache_id="features",
    data=feature_data,
    interactivity={"selected_feature": "feature_id"},
)

# Heatmap consumes the selection
heatmap = Heatmap(
    cache_id="feature_map",
    data=feature_data,
    filters={"selected_feature": "feature_id"},
    x_col="RT", y_col="mz", value_col="intensity",
)
```

The linking key (`"selected_feature"`) is shared state. Clicking a row in the Table updates this key, which filters the Heatmap to highlight the corresponding point.

---

## 6. Knowledge System

### 6.1 Skill Files

Located in `.claude/skills/` (repo-scoped, loaded automatically by Claude Code):

```
.claude/skills/
├── openms-webapp-builder/
│   └── SKILL.md          # Core template patterns, generation rules
├── topp-workflow/
│   └── SKILL.md          # TOPP tool catalog, parameter curation, pipeline chains
├── pyopenms-tools/
│   └── SKILL.md          # Direct pyopenms usage in Streamlit
├── openms-insight/
│   └── SKILL.md          # Interactive component patterns, StateManager
└── pyopenms-viz/
    └── SKILL.md          # Simple plot patterns (chromatogram, spectrum, peakmap)
```

### 6.2 Skill File Quality Principles

1. **Concrete examples over descriptions** — Include complete, working code the agent can adapt, not abstract explanations.
2. **Decision rules over option lists** — Tell the agent *when* to pick each tool, not just *what* tools exist.
3. **Anti-patterns prevent mistakes** — Every time the agent generates broken code, add the correct pattern.
4. **File format chains prevent broken pipelines** — Document which outputs feed which inputs.

### 6.3 TOPP Tool Registry

A machine-readable database at `tools/topp_tool_registry.json`:

```json
{
  "FeatureFinderMetabo": {
    "description": "Detects features in centroided LC-MS metabolomics data",
    "category": "feature_detection",
    "input_formats": {"in": "mzML"},
    "output_formats": {"out": "featureXML"},
    "per": "file",
    "use_cases": ["untargeted_metabolomics"],
    "prominent_params": {
      "untargeted_metabolomics": [
        "algorithm:common:noise_threshold_int",
        "algorithm:mtd:mass_error_ppm",
        "algorithm:common:chrom_peak_snr"
      ]
    },
    "typical_next": ["MetaboliteAdductDecharger", "FeatureLinkerUnlabeledKD"],
    "typical_prev": ["PeakPickerHiRes"]
  }
}
```

### 6.4 What Domain Experts Need to Provide

Ranked by impact on agent output quality:

1. **Working code from real apps** — Complete `WorkflowManager` subclass + results page from a production webapp (UmetaFlow, StreamSage, etc.)
2. **Parameter curation** — For the top 10 TOPP tools: prominent params, hidden params, warnings, instrument defaults
3. **Pipeline recipes** — "When I build X, I always do Y" rules (e.g., "always run PeptideIndexer before FalseDiscoveryRate")
4. **Data shapes** — Column names and types for each file format when exported to DataFrame
5. **Common user mistakes** — "Users often upload profile data when centroided is required"

---

## 7. Web Interface & Sandbox Security

### 7.1 Sandbox Container Configuration

Each user session gets an isolated container based on the OpenMS Docker image. The agent runs in the orchestrator and writes files into the container's mounted workspace volume. The container only runs Streamlit.

```yaml
services:
  sandbox:
    image: openms-sandbox:latest
    read_only: true
    tmpfs:
      - /tmp:size=100M
    volumes:
      - workspace:/app/workspace       # Only writable mount
    networks:
      - sandbox-internal               # No internet access
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    pids_limit: 100
```

### 7.2 Threat Model & Mitigations

#### Threat 1: Malicious User Prompts

User tries to get the agent to generate harmful code ("also run `rm -rf /`").

| Layer | Mitigation |
|-------|------------|
| Agent system prompt | Explicit instructions to never generate shell commands, outbound network calls, or filesystem access outside `/app/workspace/` |
| Static analysis gate | Before writing code to the container, scan for: `subprocess`, `os.system`, `exec`, `eval`, `__import__`, outbound HTTP calls |
| Container isolation | Even if malicious code runs, it's sandboxed (read-only filesystem, no network, capability-dropped) |

#### Threat 2: Unintentional Vulnerable Code

Agent generates code with XSS, path traversal, or other vulnerabilities.

| Layer | Mitigation |
|-------|------------|
| Skill files | Encode safe patterns; agent copies them rather than inventing |
| Review sub-agent | Second LLM pass checking for security issues before deployment |
| Streamlit sandboxing | Streamlit already restricts what Python code can do in the browser |

#### Threat 3: Container Escape

Assume some malicious/buggy code will run. The container must be a hard boundary.

| Isolation Option | Level | Overhead | Notes |
|-----------------|-------|----------|-------|
| Standard Docker | Process-level (namespaces + cgroups) | Low | Good enough for trusted users |
| gVisor (runsc) | User-space kernel | Medium | Intercepts all syscalls; used by Google Cloud Run |
| Kata Containers | Lightweight VM per container | Higher | Full VM isolation; used by AWS Fargate |
| E2B | Cloud sandboxes (third-party) | None (hosted) | Purpose-built for AI code execution |

#### Threat 4: Resource Exhaustion

User generates an app that consumes all CPU/memory/disk.

| Mitigation | Detail |
|-----------|--------|
| Per-container limits | CPU, memory, PID limits (see container config above) |
| Workspace size cap | 1 GB per session |
| Session timeout | Auto-destroy containers after 30 minutes of inactivity |
| Rate limiting | Max N container launches per user per hour |

#### Threat 5: Supply Chain (pip install)

Agent generates code requiring `pip install some-malicious-package`.

| Approach | Trade-off |
|----------|-----------|
| **Allowlist only** (recommended) | Container ships pre-installed with pyopenms, openms-insight, pyopenms-viz, polars, pandas, plotly, scipy, numpy, scikit-learn. No runtime installs allowed. |
| Vetted package list | Curated ~50 allowed packages. Install from this list only. |

#### Threat 6: Cross-Session Data Leakage

| Mitigation | Detail |
|-----------|--------|
| Per-session containers | Each session gets its own container + volume |
| Volume destruction | Volumes destroyed when session ends |
| Network isolation | Containers cannot see each other |

### 7.3 Defense-in-Depth Summary

```
User Input
  │
  ▼
Agent system prompt rules            ← Layer 1: Don't generate bad code
  │
  ▼
Static analysis gate                 ← Layer 2: Catch obvious issues
  │
  ▼
Code review sub-agent                ← Layer 3: LLM security review
  │
  ▼
Container (no net, read-only,        ← Layer 4: Hard isolation boundary
 resource limits, cap drops)
  │
  ▼
gVisor / Kata / E2B                  ← Layer 5: Kernel-level isolation
```

### 7.4 Recommended Sandbox Provider

**E2B** (https://e2b.dev) for initial deployment:
- Purpose-built for AI code execution sandboxing
- Each sandbox is a Firecracker micro-VM
- Custom Docker image support (use the OpenMS image)
- File upload/download API for the workspace
- Built-in process execution (start Streamlit, capture output)
- Automatic cleanup after timeout

```python
from e2b_code_interpreter import Sandbox

sandbox = Sandbox(template="openms-streamlit")
sandbox.files.write("/app/content/my_workflow.py", generated_code)
process = sandbox.commands.run(
    "streamlit run /app/app.py --server.port 8501 --server.headless true",
    background=True
)
preview_url = sandbox.get_host(8501)
```

Self-hosted alternative: Docker Compose with gVisor runtime.

---

## 8. Implementation Plan

### Phase 1: Skill Files & Knowledge Base

**Goal**: Encode OpenMS domain knowledge so the agent can generate correct code today, using Claude Code directly.

**Deliverables**:
1. `.claude/skills/openms-webapp-builder/SKILL.md` — Template patterns and generation rules
2. `.claude/skills/topp-workflow/SKILL.md` — TOPP tool catalog with parameter curation
3. `.claude/skills/openms-insight/SKILL.md` — Interactive component patterns
4. `.claude/skills/pyopenms-viz/SKILL.md` — Simple plot patterns
5. `tools/topp_tool_registry.json` — Machine-readable TOPP tool database

**Required domain expert input**:
- Working code from 2-3 production webapps
- Parameter curation for the top 10 TOPP tools
- Pipeline recipes for the 5 most common workflow types

**Validation**: Ask the agent (via Claude Code) to generate 3 representative webapps. Note every mistake. Fix skill files. Repeat until quality stabilizes.

### Phase 2: CLI Agent Prototype

**Goal**: Working CLI agent that implements the two-phase flow.

**Deliverables**:
1. `agent/builder.py` — Main script using Claude Agent SDK `query()`
2. System prompt encoding the two-phase conversation flow
3. MCP tools: `list_topp_tools`, `get_topp_params`, `preview_app`, `validate_pipeline`
4. Pipeline spec data structure with diagram rendering
5. File-type-to-visualization mapping logic

**Validation**: End-to-end test with 5 workflow types: metabolomics feature finding, proteomics database search, label-free quantification, DIA/SWATH, cross-linking MS.

### Phase 3: Multi-Agent Specialization

**Goal**: Higher quality output through specialized agents.

**Deliverables**:
1. Planner agent — Handles Phase 1 + 2 conversation, maintains pipeline spec
2. Coder agent — Translates pipeline spec into Streamlit code
3. Reviewer agent — Validates format chains, parameter correctness, security
4. Preview agent — Launches app, captures errors, reports status

### Phase 4: Web UI with Live Preview

**Goal**: Browser-based interface with sandboxed live preview.

**Deliverables**:
1. Streamlit/React chat frontend
2. FastAPI orchestrator backend wrapping Claude Agent SDK
3. Sandbox pool management (E2B or Docker + gVisor)
4. Reverse proxy for preview routing
5. Session management and cleanup

---

## 9. Technology Stack

### Core Dependencies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Agent framework | Claude Agent SDK (Python) | Orchestration, tool use, sub-agents |
| LLM | Claude (Anthropic API) | Code generation, conversation, review |
| Webapp framework | Streamlit | Generated app target platform |
| MS data processing | pyopenms + TOPP tools | Data analysis pipeline |
| Interactive visualization | openms-insight | Tables, heatmaps, lineplots, volcano, sequence |
| Simple visualization | pyopenms-viz | Chromatograms, mobilograms, 3D peakmaps |
| Summary charts | Plotly | Bar charts, histograms |
| Data processing | Polars | DataFrame operations for openms-insight |
| Sandbox (web mode) | E2B or Docker + gVisor | Isolated code execution |
| Backend (web mode) | FastAPI | Orchestrator API |
| Reverse proxy (web mode) | Traefik | Preview URL routing |

### Custom MCP Tools

| Tool | Phase | Purpose |
|------|-------|---------|
| `list_topp_tools` | 2 | Query available TOPP tools with descriptions and categories |
| `get_topp_params` | 2 | Get parameter schema for a specific tool + use case |
| `validate_pipeline` | 2 | Check that a pipeline spec has valid format chains |
| `preview_app` | 2 | Launch Streamlit app and report status/errors |
| `manage_sandbox` | 4 | Create, destroy, and query sandbox containers |

---

## 10. Resolved Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Target users | CLI-comfortable developers/bioinformaticians | Start with users who can use Claude Code directly |
| Scope | Both standalone apps and pages within existing template | Agent needs both modes depending on complexity |
| TOPP tools | Flexible — compile or provide precompiled binaries | OpenMS is open source; include in Docker image |
| Visualization default | openms-insight first, pyopenms-viz as fallback | openms-insight handles large data; pyopenms-viz for uncovered plot types |
| Repo location | Start inside `streamlit-template`, extract later if needed | Skill files must be repo-scoped; co-location avoids premature indirection |

---

## 11. Open Questions

1. **Model selection** — Single model throughout, or mix Opus/Sonnet/Haiku for different agent roles?
2. **pyopenms-viz fallback scope** — Should missing openms-insight plot types (chromatogram, mobilogram, 3D peakmap) be requested as upstream features?
3. **Existing app migration** — Should the agent refactor existing webapps to use openms-insight?
4. **E2B vs self-hosted sandboxing** — Cost/complexity trade-off for the web UI mode.

---

## 12. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Generated code has incorrect TOPP parameters | Medium | High | Validate against `.ini` files; `get_topp_params` MCP tool |
| Hallucinated pyopenms API calls | Medium | High | Skill files with verified examples; reviewer agent |
| Incorrect openms-insight component config | Low | Medium | Validate filter/interactivity mappings against DataFrame columns |
| Pipeline format chain breaks | Medium | High | `validate_pipeline` MCP tool; format chain database |
| Context window exhaustion | Low | Medium | Claude Agent SDK context compaction; sub-task delegation |
| Sandbox escape (web mode) | Very Low | Very High | Defense-in-depth: 5 layers from system prompt to kernel isolation |
| User requirements too vague | High | Low | Planner agent asks structured clarifying questions |
| Skill file knowledge gaps | High initially | Medium | Iterative refinement; domain expert feedback loop |
