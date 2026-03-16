# Manual Conversion Guide: Nextflow to TOPP Workflow Framework

This guide provides step-by-step instructions for manually converting nf-core/Nextflow workflows that use OpenMS TOPP tools into the Streamlit-based TOPP Workflow Framework.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Step 1: Analyze the Nextflow Workflow](#step-1-analyze-the-nextflow-workflow)
4. [Step 2: Extract Parameters](#step-2-extract-parameters)
5. [Step 3: Map the Workflow DAG](#step-3-map-the-workflow-dag)
6. [Step 4: Create the Workflow Class](#step-4-create-the-workflow-class)
7. [Step 5: Implement File Upload](#step-5-implement-file-upload)
8. [Step 6: Implement Parameter Configuration](#step-6-implement-parameter-configuration)
9. [Step 7: Implement Execution Logic](#step-7-implement-execution-logic)
10. [Step 8: Implement Results Display](#step-8-implement-results-display)
11. [Common Patterns](#common-patterns)
12. [Reference: Nextflow to TOPP Mappings](#reference-nextflow-to-topp-mappings)

---

## Overview

### What This Guide Covers

Converting a Nextflow DSL2 workflow to the TOPP Workflow Framework involves:

- Translating declarative channel-based data flow to imperative Python
- Mapping Nextflow parameters to Streamlit UI widgets
- Converting process definitions to `run_topp()` calls
- Handling file grouping and metadata

### Conceptual Differences

| Nextflow | TOPP Framework |
|----------|----------------|
| Declarative DAG | Imperative Python |
| Channels (reactive streams) | File lists (explicit) |
| `process { }` blocks | `executor.run_topp()` calls |
| `params.x` | `self.params["x"]` |
| Implicit parallelism | Explicit via file lists |
| `tuple val(meta), path(file)` | Metadata dict + file path |

---

## Prerequisites

Before starting, ensure you have:

1. Access to the Nextflow workflow source code:
   - Main workflow file (e.g., `workflows/mhcquant.nf`)
   - Module definitions (e.g., `modules/local/` or `modules/nf-core/`)
   - Configuration files (`nextflow.config`, `conf/modules.config`)
   - Parameter schema (`nextflow_schema.json`)

2. Understanding of:
   - The TOPP Workflow Framework (see `TOPP Workflow Framework` in the app sidebar)
   - OpenMS TOPP tools being used
   - The biological/analytical purpose of the workflow

---

## Step 1: Analyze the Nextflow Workflow

### 1.1 Identify All Processes

List every process/module called in the workflow. For each, note:

```
Process Name | TOPP Tool | Inputs | Outputs | Key Parameters
-------------|-----------|--------|---------|---------------
DECOYDATABASE | DecoyDatabase | fasta | fasta | decoy_string
COMETADAPTER | CometAdapter | mzML, fasta | idXML | precursor_tol, fragment_tol
PEPTIDEINDEXER | PeptideIndexer | idXML, fasta | idXML | enzyme, decoy_string
...
```

### 1.2 Trace the Data Flow

Create a simple DAG showing how files flow between processes:

```
Input Files
    │
    ▼
┌─────────────────┐
│ DECOYDATABASE   │ fasta → decoy_fasta
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ COMETADAPTER    │ mzML + decoy_fasta → idXML
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ PEPTIDEINDEXER  │ idXML + decoy_fasta → indexed_idXML
└────────┬────────┘
         │
        ...
```

### 1.3 Identify Conditional Steps

Note any processes that are conditional:

```groovy
// In Nextflow:
if (params.quantify) {
    FEATUREFINDER(ch_mzml)
}
```

These become Python `if` statements in the execution method.

### 1.4 Identify Grouping Operations

Look for channel operations that group files:

```groovy
// Nextflow grouping patterns to watch for:
.groupTuple()           // Group by first element
.collect()              // Collect all into single list
.join()                 // Join channels by key
.combine()              // Cartesian product
.map { meta, file -> [meta.sample, file] }  // Re-key by metadata
```

---

## Step 2: Extract Parameters

### 2.1 Parse the Parameter Schema

Open `nextflow_schema.json` and extract all user-configurable parameters:

```json
{
  "properties": {
    "fdr_threshold": {
      "type": "number",
      "default": 0.01,
      "description": "FDR threshold for peptide filtering"
    },
    "enzyme": {
      "type": "string",
      "default": "unspecific cleavage",
      "enum": ["unspecific cleavage", "trypsin", "chymotrypsin", ...]
    }
  }
}
```

### 2.2 Create Parameter Mapping Table

Map each Nextflow parameter to its TOPP equivalent:

```
Nextflow Param        | TOPP Tool      | TOPP Parameter           | UI Widget
----------------------|----------------|--------------------------|----------
params.fdr_threshold  | IDFilter       | score:pep                | number_input
params.enzyme         | CometAdapter   | enzyme                   | selectbox
params.precursor_tol  | CometAdapter   | precursor_mass_tolerance | number_input
params.quantify       | (workflow)     | (conditional flag)       | checkbox
```

### 2.3 Identify TOPP Tool Parameters

For each TOPP tool, determine which parameters should be exposed in the UI:

```bash
# Generate INI file to see all parameters
FeatureFinderMetabo -write_ini FeatureFinderMetabo.ini

# Key parameters are usually under algorithm:* sections
```

---

## Step 3: Map the Workflow DAG

### 3.1 Create Step Definitions

For each process, define the conversion:

```python
# Step template
{
    "step_id": "feature_detection",
    "nextflow_process": "FEATUREFINDERMETABO",
    "topp_tool": "FeatureFinderMetabo",
    "inputs": {
        "in": "mzML files from previous step or upload"
    },
    "outputs": {
        "out": "featureXML files"
    },
    "results_dir": "feature-detection",
    "condition": None,  # or "self.params['run_feature_detection']"
    "parallel": True    # Process each file independently
}
```

### 3.2 Determine File Flow

For each step, determine:
- **Source**: Where do input files come from? (upload, previous step)
- **Transformation**: Does the file type change? (mzML → featureXML)
- **Cardinality**: 1-to-1, many-to-1 (collect), or 1-to-many?

---

## Step 4: Create the Workflow Class

### 4.1 Basic Structure

Create your workflow file in `src/`:

```python
# src/MyWorkflow.py

import streamlit as st
from src.workflow.WorkflowManager import WorkflowManager
from pathlib import Path
import pandas as pd

class MyWorkflow(WorkflowManager):
    """
    Converted from: nf-core/workflow-name
    Original: https://github.com/nf-core/workflow-name

    This workflow performs:
    1. Step one description
    2. Step two description
    ...
    """

    def __init__(self) -> None:
        super().__init__("My Workflow", st.session_state["workspace"])

    def upload(self) -> None:
        """Define file upload widgets."""
        pass  # Implement in Step 5

    def configure(self) -> None:
        """Define parameter configuration UI."""
        pass  # Implement in Step 6

    def execution(self) -> None:
        """Implement workflow execution logic."""
        pass  # Implement in Step 7

    def results(self) -> None:
        """Display workflow results."""
        pass  # Implement in Step 8
```

### 4.2 Register the Workflow

Add pages in `app.py`:

```python
# In app.py, add to the pages dict:
"My Workflow": [
    st.Page(Path("content", "my_workflow_upload.py"), title="Upload"),
    st.Page(Path("content", "my_workflow_params.py"), title="Configure"),
    st.Page(Path("content", "my_workflow_run.py"), title="Run"),
    st.Page(Path("content", "my_workflow_results.py"), title="Results"),
],
```

Create the content pages (copy from existing `topp_workflow_*.py` files and modify the import).

---

## Step 5: Implement File Upload

### 5.1 Identify Required Inputs

From the Nextflow workflow, identify all input files:

```groovy
// Nextflow input channels
ch_mzml = Channel.fromPath(params.input)
ch_fasta = Channel.fromPath(params.fasta)
ch_samplesheet = Channel.fromPath(params.samplesheet)
```

### 5.2 Create Upload Widgets

```python
def upload(self) -> None:
    tabs = st.tabs(["MS Data", "Database", "Sample Info"])

    with tabs[0]:
        self.ui.upload_widget(
            key="mzML-files",
            name="MS Data",
            file_types="mzML",
            fallback=[str(f) for f in Path("example-data", "mzML").glob("*.mzML")],
        )

    with tabs[1]:
        self.ui.upload_widget(
            key="fasta-db",
            name="Protein Database",
            file_types="fasta",
        )

    with tabs[2]:
        self.ui.upload_widget(
            key="sample-sheet",
            name="Sample Sheet",
            file_types=["tsv", "csv"],
        )
```

### 5.3 Handle Optional Inputs

For optional inputs in Nextflow:

```groovy
// Nextflow optional input
ch_optional = params.optional_file ? Channel.fromPath(params.optional_file) : Channel.empty()
```

In TOPP Framework, just check if files were uploaded:

```python
# In execution(), check if optional files exist
if self.params.get("optional-files"):
    optional_files = self.file_manager.get_files(self.params["optional-files"])
    # Use optional_files...
```

---

## Step 6: Implement Parameter Configuration

### 6.1 Organize Parameters into Tabs

Group related parameters logically:

```python
@st.fragment
def configure(self) -> None:
    # File selection
    self.ui.select_input_file("mzML-files", multiple=True)

    # Parameter tabs
    tabs = st.tabs([
        "**Preprocessing**",
        "**Database Search**",
        "**FDR Control**",
        "**Quantification**",
        "**Output Options**"
    ])

    with tabs[0]:
        self._configure_preprocessing()

    with tabs[1]:
        self._configure_search()

    # ... etc
```

### 6.2 Map Nextflow Parameters to Widgets

For each parameter type:

**Boolean (checkbox):**
```groovy
// Nextflow
params.skip_decoy_generation = false
```
```python
# TOPP Framework
self.ui.input_widget(
    key="skip-decoy-generation",
    default=False,
    name="Skip decoy database generation"
)
```

**Number (number_input):**
```groovy
// Nextflow
params.fdr_threshold = 0.01
```
```python
# TOPP Framework
self.ui.input_widget(
    key="fdr-threshold",
    default=0.01,
    name="FDR Threshold",
    min_value=0.0,
    max_value=1.0,
    step=0.01
)
```

**Choice (selectbox):**
```groovy
// Nextflow
params.enzyme = "unspecific cleavage"  // with enum in schema
```
```python
# TOPP Framework
self.ui.input_widget(
    key="enzyme",
    default="unspecific cleavage",
    name="Enzyme",
    options=["unspecific cleavage", "trypsin", "chymotrypsin", "lys-c"]
)
```

**String (text_input):**
```groovy
// Nextflow
params.fixed_mods = ""
```
```python
# TOPP Framework
self.ui.input_widget(
    key="fixed-mods",
    default="",
    name="Fixed Modifications",
    help="Comma-separated list of fixed modifications"
)
```

### 6.3 Expose TOPP Tool Parameters

For tools with complex parameters, use `input_TOPP()`:

```python
with tabs[1]:  # Database Search tab
    st.subheader("Comet Search Settings")

    # This auto-generates UI for all CometAdapter parameters
    self.ui.input_TOPP(
        "CometAdapter",
        custom_defaults={
            "precursor_mass_tolerance": 10.0,
            "fragment_bin_tolerance": 0.02,
        },
        exclude_parameters=["in", "out", "database"]  # Hide I/O params
    )
```

---

## Step 7: Implement Execution Logic

### 7.1 Basic Structure

```python
def execution(self) -> None:
    # 1. Validate inputs
    if not self.params["mzML-files"]:
        self.logger.log("ERROR: No mzML files selected.")
        return

    # 2. Get input files
    in_mzml = self.file_manager.get_files(self.params["mzML-files"])
    self.logger.log(f"Processing {len(in_mzml)} mzML files")

    # 3. Execute workflow steps
    self._step_preprocessing(in_mzml)
    # ... more steps
```

### 7.2 Converting Process Definitions

**Nextflow Process:**
```groovy
process OPENMS_DECOYDATABASE {
    input:
    tuple val(meta), path(fasta)

    output:
    tuple val(meta), path("*_decoy.fasta"), emit: decoy_fasta

    script:
    """
    DecoyDatabase -in $fasta -out ${fasta.baseName}_decoy.fasta \
        -decoy_string DECOY -decoy_string_position prefix
    """
}
```

**TOPP Framework Equivalent:**
```python
def _step_decoy_database(self, in_fasta: list) -> list:
    """Generate decoy database."""
    self.logger.log("Generating decoy database...")

    # Define output files
    out_fasta = self.file_manager.get_files(
        in_fasta,
        set_file_type="fasta",
        set_results_dir="decoy-database"
    )

    # Run the tool
    self.executor.run_topp(
        "DecoyDatabase",
        input_output={
            "in": in_fasta,
            "out": out_fasta
        },
        custom_params={
            "decoy_string": "DECOY",
            "decoy_string_position": "prefix"
        }
    )

    return out_fasta
```

### 7.3 Handling Conditional Steps

**Nextflow:**
```groovy
if (params.run_centroidisation) {
    PEAKPICKERHIRES(ch_mzml)
    ch_processed = PEAKPICKERHIRES.out.mzml
} else {
    ch_processed = ch_mzml
}
```

**TOPP Framework:**
```python
def _step_preprocessing(self, in_mzml: list) -> list:
    """Preprocess mzML files (optional centroiding)."""

    if self.params.get("run-centroidisation", False):
        self.logger.log("Running peak centroiding...")

        out_centroided = self.file_manager.get_files(
            in_mzml,
            set_file_type="mzML",
            set_results_dir="centroided"
        )

        self.executor.run_topp(
            "PeakPickerHiRes",
            input_output={"in": in_mzml, "out": out_centroided}
        )

        return out_centroided
    else:
        self.logger.log("Skipping centroiding (data already centroided)")
        return in_mzml
```

### 7.4 Handling Collected Files (Many-to-One)

**Nextflow:**
```groovy
ch_features.collect()
    .map { files -> [files] }
    .set { ch_collected }

FEATURELINKERUNLABELED(ch_collected)
```

**TOPP Framework:**
```python
def _step_feature_linking(self, in_features: list) -> list:
    """Link features across samples."""
    self.logger.log(f"Linking features from {len(in_features)} files...")

    # Collect all input files into a single list for the tool
    collected_input = self.file_manager.get_files(in_features, collect=True)

    # Single output file
    out_consensus = self.file_manager.get_files(
        "consensus_features.consensusXML",
        set_results_dir="feature-linking"
    )

    self.executor.run_topp(
        "FeatureLinkerUnlabeledKD",
        input_output={
            "in": collected_input,  # [[file1, file2, file3, ...]]
            "out": out_consensus
        }
    )

    return out_consensus
```

### 7.5 Handling Grouped Operations

**Nextflow:**
```groovy
ch_files
    .map { meta, file -> [meta.condition, file] }
    .groupTuple()
    .set { ch_by_condition }
```

**TOPP Framework:**
```python
def _group_by_condition(self, files: list, sample_sheet: str) -> dict:
    """Group files by condition from sample sheet."""
    import pandas as pd

    # Load sample sheet
    df = pd.read_csv(sample_sheet, sep="\t")

    # Create mapping: filename -> condition
    file_to_condition = dict(zip(df["filename"], df["condition"]))

    # Group files
    groups = {}
    for f in files:
        filename = Path(f).name
        condition = file_to_condition.get(filename, "unknown")
        if condition not in groups:
            groups[condition] = []
        groups[condition].append(f)

    return groups

def _step_process_by_condition(self, in_files: list):
    """Process files grouped by condition."""
    sample_sheet = self.params["sample-sheet"][0]
    groups = self._group_by_condition(in_files, sample_sheet)

    for condition, files in groups.items():
        self.logger.log(f"Processing condition: {condition} ({len(files)} files)")
        # Process this group...
```

### 7.6 Handling Join Operations

**Nextflow:**
```groovy
ch_mzml.join(ch_idxml, by: [0])  // Join by meta.id
```

**TOPP Framework:**
```python
def _join_files(self, files_a: list, files_b: list) -> list:
    """Join two file lists by base name."""
    # Create lookup by base name
    b_lookup = {Path(f).stem: f for f in files_b}

    joined = []
    for a in files_a:
        stem = Path(a).stem
        if stem in b_lookup:
            joined.append((a, b_lookup[stem]))

    return joined

# Usage
joined = self._join_files(mzml_files, idxml_files)
for mzml, idxml in joined:
    # Process paired files
    pass
```

### 7.7 Complete Execution Example

```python
def execution(self) -> None:
    """Execute the complete workflow."""

    # === Validation ===
    if not self.params["mzML-files"]:
        self.logger.log("ERROR: No mzML files selected.")
        return

    if not self.params["fasta-db"]:
        self.logger.log("ERROR: No protein database provided.")
        return

    # === Get input files ===
    in_mzml = self.file_manager.get_files(self.params["mzML-files"])
    in_fasta = self.file_manager.get_files(self.params["fasta-db"])

    self.logger.log(f"Starting workflow with {len(in_mzml)} mzML files")

    # === Step 1: Preprocessing (optional) ===
    processed_mzml = self._step_preprocessing(in_mzml)

    # === Step 2: Decoy Database ===
    if not self.params.get("skip-decoy-generation", False):
        db_fasta = self._step_decoy_database(in_fasta)
    else:
        db_fasta = in_fasta
        self.logger.log("Using provided database (decoy generation skipped)")

    # === Step 3: Database Search ===
    search_results = self._step_database_search(processed_mzml, db_fasta)

    # === Step 4: Peptide Indexing ===
    indexed_results = self._step_peptide_indexer(search_results, db_fasta)

    # === Step 5: FDR Filtering ===
    filtered_results = self._step_fdr_filter(indexed_results)

    # === Step 6: Quantification (optional) ===
    if self.params.get("run-quantification", False):
        quant_results = self._step_quantification(processed_mzml, filtered_results)

    # === Step 7: Export Results ===
    self._step_export(filtered_results)

    self.logger.log("Workflow completed successfully!")
```

---

## Step 8: Implement Results Display

### 8.1 Basic Results Structure

```python
@st.fragment
def results(self) -> None:
    """Display workflow results."""

    results_dir = Path(self.workflow_dir, "results")

    if not results_dir.exists():
        st.warning("No results found. Please run the workflow first.")
        return

    tabs = st.tabs(["Summary", "Identifications", "Quantification", "QC Plots"])

    with tabs[0]:
        self._show_summary()

    with tabs[1]:
        self._show_identifications()

    with tabs[2]:
        self._show_quantification()

    with tabs[3]:
        self._show_qc_plots()
```

### 8.2 Display Data Tables

```python
def _show_identifications(self):
    """Display identification results."""
    tsv_file = Path(self.workflow_dir, "results", "export", "identifications.tsv")

    if not tsv_file.exists():
        st.info("No identification results available.")
        return

    df = pd.read_csv(tsv_file, sep="\t")

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total PSMs", len(df))
    col2.metric("Unique Peptides", df["sequence"].nunique())
    col3.metric("Proteins", df["accession"].nunique())

    # Filterable table
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    # Download button
    st.download_button(
        "Download TSV",
        df.to_csv(sep="\t", index=False),
        file_name="identifications.tsv",
        mime="text/tab-separated-values"
    )
```

### 8.3 Display Plots

```python
def _show_qc_plots(self):
    """Display QC plots."""
    import plotly.express as px
    from src.common.common import show_fig

    # Load data
    results_file = Path(self.workflow_dir, "results", "export", "identifications.tsv")
    if not results_file.exists():
        st.info("No data available for plotting.")
        return

    df = pd.read_csv(results_file, sep="\t")

    # Score distribution
    st.subheader("Score Distribution")
    fig = px.histogram(df, x="score", nbins=50, title="PSM Score Distribution")
    show_fig(fig, "score-distribution")

    # Mass error distribution
    if "mass_error_ppm" in df.columns:
        st.subheader("Mass Error Distribution")
        fig = px.histogram(df, x="mass_error_ppm", nbins=50,
                          title="Precursor Mass Error (ppm)")
        show_fig(fig, "mass-error")

    # Peptide length distribution
    if "sequence" in df.columns:
        df["peptide_length"] = df["sequence"].str.len()
        st.subheader("Peptide Length Distribution")
        fig = px.histogram(df, x="peptide_length",
                          title="Peptide Length Distribution")
        show_fig(fig, "peptide-length")
```

---

## Common Patterns

### Pattern 1: Parallel Processing (1-to-1)

Most common pattern - each input file produces one output file:

```python
# Input: [sample1.mzML, sample2.mzML, sample3.mzML]
# Output: [sample1.featureXML, sample2.featureXML, sample3.featureXML]

in_files = self.file_manager.get_files(self.params["mzML-files"])
out_files = self.file_manager.get_files(in_files, "featureXML", "features")

self.executor.run_topp("FeatureFinderMetabo", {
    "in": in_files,
    "out": out_files
})
# Automatically runs in parallel for each file pair
```

### Pattern 2: Collection (Many-to-1)

Multiple inputs combined into single output:

```python
# Input: [s1.featureXML, s2.featureXML, s3.featureXML]
# Output: [consensus.consensusXML]

in_files = self.file_manager.get_files(feature_files, collect=True)
out_file = self.file_manager.get_files("consensus.consensusXML",
                                        set_results_dir="linking")

self.executor.run_topp("FeatureLinkerUnlabeledKD", {
    "in": in_files,   # [[s1.featureXML, s2.featureXML, s3.featureXML]]
    "out": out_file   # [consensus.consensusXML]
})
```

### Pattern 3: Shared Input (N-to-N with shared file)

Multiple files processed with a shared resource:

```python
# Each mzML searched against same database
# Input: [s1.mzML, s2.mzML], database.fasta
# Output: [s1.idXML, s2.idXML]

in_mzml = self.file_manager.get_files(self.params["mzML-files"])
in_db = self.file_manager.get_files(self.params["fasta-db"])  # Single file
out_idxml = self.file_manager.get_files(in_mzml, "idXML", "search")

self.executor.run_topp("CometAdapter", {
    "in": in_mzml,      # [s1.mzML, s2.mzML]
    "database": in_db,  # [database.fasta] - reused for each
    "out": out_idxml    # [s1.idXML, s2.idXML]
})
```

### Pattern 4: Two-Input Pairing

Two file lists that need to be paired:

```python
# Input: [s1.mzML, s2.mzML] + [s1.idXML, s2.idXML]
# Output: [s1_annotated.idXML, s2_annotated.idXML]

in_mzml = self.file_manager.get_files(mzml_files)
in_idxml = self.file_manager.get_files(idxml_files)
out_annotated = self.file_manager.get_files(in_idxml, "idXML", "annotated")

# Files are paired by index: mzml[0] with idxml[0], etc.
self.executor.run_topp("SomeAnnotator", {
    "in_mzml": in_mzml,
    "in_id": in_idxml,
    "out": out_annotated
})
```

### Pattern 5: Conditional Branching

```python
def _step_rescoring(self, in_idxml: list) -> list:
    """Apply rescoring based on selected engine."""

    engine = self.params.get("rescoring-engine", "percolator")

    out_rescored = self.file_manager.get_files(
        in_idxml, "idXML", "rescored"
    )

    if engine == "percolator":
        self.logger.log("Running Percolator rescoring...")
        self.executor.run_topp("PercolatorAdapter", {
            "in": in_idxml,
            "out": out_rescored
        })
    elif engine == "mokapot":
        self.logger.log("Running Mokapot rescoring...")
        # Mokapot might be a Python tool
        self.executor.run_python("mokapot_wrapper", {
            "in": in_idxml,
            "out": out_rescored
        })
    else:
        self.logger.log("Skipping rescoring")
        return in_idxml

    return out_rescored
```

---

## Reference: Nextflow to TOPP Mappings

### Channel Operations

| Nextflow | TOPP Framework |
|----------|----------------|
| `Channel.fromPath(params.x)` | `self.file_manager.get_files(self.params["x"])` |
| `ch.collect()` | `self.file_manager.get_files(files, collect=True)` |
| `ch.map { ... }` | Python list comprehension |
| `ch.filter { ... }` | `[f for f in files if condition]` |
| `ch.groupTuple()` | Custom dict-based grouping |
| `ch.join(other)` | Custom join by filename |
| `ch.mix(other)` | `files_a + files_b` |
| `ch.first()` | `files[0]` |
| `ch.ifEmpty(value)` | `files if files else default` |

### Process Components

| Nextflow | TOPP Framework |
|----------|----------------|
| `process NAME { }` | Method `def _step_name(self):` |
| `input: path(file)` | Method parameter |
| `output: path("*.ext")` | `file_manager.get_files(..., set_file_type="ext")` |
| `script: """cmd"""` | `executor.run_topp("cmd", {...})` |
| `when: condition` | `if condition:` in Python |
| `publishDir` | `set_results_dir` parameter |

### Parameter Types

| Nextflow Schema | Python Widget |
|-----------------|---------------|
| `"type": "boolean"` | `input_widget(..., default=False)` → checkbox |
| `"type": "integer"` | `input_widget(..., default=0)` → number_input |
| `"type": "number"` | `input_widget(..., default=0.0)` → number_input |
| `"type": "string"` | `input_widget(..., default="")` → text_input |
| `"type": "string", "enum": [...]` | `input_widget(..., options=[...])` → selectbox |

---

## Checklist for Conversion

Use this checklist when converting a workflow:

- [ ] **Analysis Phase**
  - [ ] Listed all processes/modules
  - [ ] Documented data flow (DAG)
  - [ ] Identified conditional steps
  - [ ] Identified grouping operations
  - [ ] Extracted all parameters

- [ ] **Implementation Phase**
  - [ ] Created workflow class file
  - [ ] Created content pages
  - [ ] Registered in app.py
  - [ ] Implemented `upload()` method
  - [ ] Implemented `configure()` method
  - [ ] Implemented `execution()` method
  - [ ] Implemented `results()` method

- [ ] **Testing Phase**
  - [ ] Tested with example data
  - [ ] Verified parameter UI works
  - [ ] Verified each step executes correctly
  - [ ] Verified results display correctly
  - [ ] Compared output with Nextflow version

---

## Example: Converting a Simple 3-Step Workflow

Here's a complete example converting a simple feature detection workflow:

**Nextflow Original:**
```groovy
params.mzml = "data/*.mzML"
params.noise_threshold = 1000

workflow {
    ch_mzml = Channel.fromPath(params.mzml)

    FEATUREFINDERMETABO(ch_mzml)

    FEATURELINKERUNLABELED(FEATUREFINDERMETABO.out.features.collect())

    TEXTEXPORTER(FEATURELINKERUNLABELED.out.consensus)
}

process FEATUREFINDERMETABO {
    input: path(mzml)
    output: path("*.featureXML"), emit: features
    script:
    """
    FeatureFinderMetabo -in $mzml -out ${mzml.baseName}.featureXML \
        -algorithm:common:noise_threshold_int ${params.noise_threshold}
    """
}

process FEATURELINKERUNLABELED {
    input: path(features)
    output: path("consensus.consensusXML"), emit: consensus
    script:
    """
    FeatureLinkerUnlabeledKD -in $features -out consensus.consensusXML
    """
}

process TEXTEXPORTER {
    input: path(consensus)
    output: path("*.tsv")
    script:
    """
    TextExporter -in $consensus -out results.tsv
    """
}
```

**TOPP Framework Conversion:**
```python
# src/FeatureWorkflow.py

import streamlit as st
from src.workflow.WorkflowManager import WorkflowManager
from pathlib import Path
import pandas as pd


class FeatureWorkflow(WorkflowManager):
    """Simple feature detection and linking workflow."""

    def __init__(self) -> None:
        super().__init__("Feature Workflow", st.session_state["workspace"])

    def upload(self) -> None:
        self.ui.upload_widget(
            key="mzML-files",
            name="MS Data",
            file_types="mzML",
        )

    @st.fragment
    def configure(self) -> None:
        self.ui.select_input_file("mzML-files", multiple=True)

        tabs = st.tabs(["**Feature Detection**", "**Feature Linking**"])

        with tabs[0]:
            self.ui.input_TOPP(
                "FeatureFinderMetabo",
                custom_defaults={"algorithm:common:noise_threshold_int": 1000.0}
            )

        with tabs[1]:
            self.ui.input_TOPP("FeatureLinkerUnlabeledKD")

    def execution(self) -> None:
        # Validate
        if not self.params["mzML-files"]:
            self.logger.log("ERROR: No mzML files selected.")
            return

        # Get input files
        in_mzml = self.file_manager.get_files(self.params["mzML-files"])
        self.logger.log(f"Processing {len(in_mzml)} mzML files")

        # Step 1: Feature Detection
        self.logger.log("Running feature detection...")
        out_features = self.file_manager.get_files(
            in_mzml, "featureXML", "feature-detection"
        )
        self.executor.run_topp(
            "FeatureFinderMetabo",
            input_output={"in": in_mzml, "out": out_features}
        )

        # Step 2: Feature Linking
        self.logger.log("Linking features...")
        in_collected = self.file_manager.get_files(out_features, collect=True)
        out_consensus = self.file_manager.get_files(
            "consensus.consensusXML", set_results_dir="feature-linking"
        )
        self.executor.run_topp(
            "FeatureLinkerUnlabeledKD",
            input_output={"in": in_collected, "out": out_consensus}
        )

        # Step 3: Export to TSV
        self.logger.log("Exporting results...")
        out_tsv = self.file_manager.get_files(
            "results.tsv", set_results_dir="export"
        )
        self.executor.run_topp(
            "TextExporter",
            input_output={"in": out_consensus, "out": out_tsv}
        )

        self.logger.log("Workflow complete!")

    @st.fragment
    def results(self) -> None:
        tsv_path = Path(self.workflow_dir, "results", "export", "results.tsv")

        if not tsv_path.exists():
            st.warning("No results found. Please run the workflow first.")
            return

        df = pd.read_csv(tsv_path, sep="\t")

        st.metric("Consensus Features", len(df))
        st.dataframe(df, use_container_width=True)

        st.download_button(
            "Download Results",
            df.to_csv(sep="\t", index=False),
            file_name="feature_results.tsv"
        )
```

---

## Troubleshooting

### Common Issues

**1. Tool not found**
```
ERROR: FeatureFinderMetabo: command not found
```
Ensure OpenMS TOPP tools are in PATH. Check Dockerfile uses the correct base image.

**2. File not found errors**
```
ERROR: Input file does not exist: /path/to/file.mzML
```
Check that `file_manager.get_files()` is returning the correct paths. Use `self.logger.log()` to debug file paths.

**3. Parameter not applied**
```
Parameter noise_threshold not being used
```
Ensure parameter key in UI matches what `run_topp()` expects. Check INI file generation.

**4. Parallel execution issues**
```
Only one file processed instead of all
```
Check that input list has correct length. Ensure `collect=True` is not accidentally set.

---

## Additional Resources

- [TOPP Workflow Framework Documentation](../content/topp_workflow_docs.py) - Interactive docs in the app
- [OpenMS TOPP Tool Documentation](https://openms.de/doxygen/release/latest/html/TOPP_documentation.html)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [nf-core Pipeline Documentation](https://nf-co.re/)
