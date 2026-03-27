# OpenMS Web App Framework

## Who Is This For?

The OpenMS web app framework is designed for **wetlab scientists and users who are new to computational mass spectrometry analysis**. Rather than learning command-line tools, scripting, or complex software installations, users get a streamlined browser-based interface where they can:

1. **Upload** their data files (mzML, featureXML, etc.)
2. **Configure** analysis parameters through intuitive widgets
3. **Run** entire workflows with a single click
4. **View and download** results immediately

The goal is to remove the barrier between raw mass spectrometry data and meaningful results. A researcher who has just finished collecting data on the instrument can open a web app, upload their files, and have a complete analysis pipeline running without writing a single line of code.

## The Workflow Framework

At the heart of every OpenMS web app is the **Workflow framework** (`src/workflow/`). It provides the upload-configure-execute-results pattern that all apps follow. A developer subclasses `WorkflowManager` and implements four methods:

```python
class Workflow(WorkflowManager):
    def upload(self):
        # File upload widgets
        self.ui.upload_widget(key="mzML-files", name="MS data", file_types="mzML")

    def configure(self):
        # Parameter widgets for each tool
        self.ui.input_TOPP("FeatureFinderMetabo")
        self.ui.input_TOPP("FeatureLinkerUnlabeledKD")

    def execution(self):
        # Chain tools together — this is where the pipeline is defined
        in_mzML = self.file_manager.get_files(self.params["mzML-files"])
        out_ffm = self.file_manager.get_files(in_mzML, "featureXML", "feature-detection")
        self.executor.run_topp("FeatureFinderMetabo", input_output={"in": in_mzML, "out": out_ffm})
        # ... more steps

    def results(self):
        # Display output tables, figures, downloads
```

The framework automatically generates four pages (upload, configure, run, results) from these methods. Users navigate through them in order — no need to understand what happens behind the scenes.

## Concurrent Job Execution

The framework supports **concurrent execution** of computationally intensive steps through its `CommandExecutor`. When a TOPP tool needs to process multiple input files independently, the executor automatically parallelizes the work using threads.

### How It Works

The `CommandExecutor` uses Python's `threading.Thread` with a `threading.Semaphore` to control concurrency. The number of parallel threads is configured via `max_threads` in `settings.json`:

```json
"max_threads": {
    "local": 4,
    "online": 2
}
```

Thread allocation is handled intelligently. When processing N files with M available threads, the executor:
- Runs `min(N, M)` files in parallel
- Distributes remaining threads to each command for internal parallelization via the TOPP tool's `-threads` parameter

### Examples

**Feature detection on 8 mzML files with 4 threads:**
`FeatureFinderMetabo` needs to process each file independently. The executor runs 4 files in parallel (each with 1 internal thread), then the remaining 4.

**Peptide identification on 12 mzML files with 6 threads:**
A search engine adapter like `MSGFPlusAdapter` processes each file separately. The executor runs 6 files concurrently (1 internal thread each), then the next 6.

**Feature detection on 2 mzML files with 8 threads:**
Only 2 files, so 2 run in parallel — but each gets 4 internal threads, speeding up the per-file computation.

### Online Mode: Redis Queue

For deployed (online) apps, the framework includes a **Redis Queue (RQ)** backend (`QueueManager.py`) that manages job submission, status tracking, and progress reporting. Jobs are enqueued with a 2-hour timeout, and users see real-time queue position and progress updates in the UI.

## Local Setup and Symlinks

When running locally, the framework supports **symlinks for example and demo data** on Linux. Instead of copying large mzML files (which can be hundreds of megabytes each), the file manager creates symbolic links to the original files. This was implemented to make demo workspace loading and example data handling fast and disk-efficient.

Key details:
- **Data files** (mzML, featureXML, etc.) are symlinked to avoid duplication
- **Configuration files** (params.json, .ini files) are copied so they can be modified independently per workspace
- On non-Linux platforms, the framework falls back to full file copies

This means a user can load demo data or switch between workspaces almost instantly, even with large datasets.

## Cluster Support Considerations

The framework does not currently include HPC/cluster integration, but the architecture makes it feasible. The `execution()` method in `Workflow.py` is the natural starting point — it defines the sequence of tool invocations and their input/output relationships:

```python
def execution(self):
    in_mzML = self.file_manager.get_files(self.params["mzML-files"])

    # Step 1: Feature Detection (per-file, parallelizable)
    out_ffm = self.file_manager.get_files(in_mzML, "featureXML", "feature-detection")
    self.executor.run_topp("FeatureFinderMetabo", input_output={"in": in_mzML, "out": out_ffm})

    # Step 2: Feature Linking (collects all outputs, single job)
    in_fl = self.file_manager.get_files(out_ffm, collect=True)
    out_fl = self.file_manager.get_files("feature_matrix.consensusXML", set_results_dir="feature-linking")
    self.executor.run_topp("FeatureLinkerUnlabeledKD", input_output={"in": in_fl, "out": out_fl})

    # Step 3: Export results
    self.executor.run_python("export_consensus_feature_df", input_output={"in": out_fl[0]})
```

Each `run_topp()` and `run_python()` call is a discrete step with clearly defined inputs and outputs. To add cluster support, one could replace or extend the `CommandExecutor` to submit these steps as cluster jobs (e.g., via SLURM, SGE, or Nextflow) rather than running them as local threads. The `FileManager` already manages all intermediate file paths, so the handoff between steps is well-defined.

That said, cluster integration would add significant setup complexity — users would need access to a configured HPC environment, shared filesystems, and job scheduler credentials. This contrasts with the framework's core goal of simplicity, so it would likely be offered as an advanced deployment option rather than a default.
