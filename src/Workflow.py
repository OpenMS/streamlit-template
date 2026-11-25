import shutil
import streamlit as st
from src.workflow.WorkflowManager import WorkflowManager

# for result section:
from pathlib import Path
import pandas as pd
import plotly.express as px
from src.common.common import show_fig
from src.layout_manager import (
    edit_comparison, member_switch, render_layout, request_analysis, resolve_layout, view_bar,
)
from src.workflow.run_widgets import run_label
from src.workflow.guide import QUANTIFICATION


def merge_feature_tables(tables: list, ppm: float = 10.0, rt_tolerance: float = 30.0):
    """One consensus feature table from the tables of several runs.

    Each table has ``mz`` and ``rt`` columns followed by one intensity column
    per file (after ``quality``). A feature of a later table joins the nearest
    feature of the tables before it within ``ppm`` and ``rt_tolerance``
    seconds, otherwise it is a feature of its own; a file it was not found in
    has no intensity (NaN).
    """
    merged = tables[0].copy()
    for table in tables[1:]:
        files = [c for c in table.columns[4:] if c not in merged.columns]
        for c in files:
            merged[c] = float("nan")
        new_rows = []
        columns = [merged.columns.get_loc(c) for c in files]
        for _, row in table.iterrows():
            # By position: two features can share a rounded label
            close = (((merged["mz"] - row["mz"]).abs() <= row["mz"] * ppm * 1e-6)
                     & ((merged["rt"] - row["rt"]).abs() <= rt_tolerance)).to_numpy().nonzero()[0]
            if len(close) == 0:
                new_rows.append(row)
                continue
            best = close[(merged["rt"].iloc[close] - row["rt"]).abs().to_numpy().argmin()]
            merged.iloc[best, columns] = row[files].values
        if new_rows:
            merged = pd.concat([merged, pd.DataFrame(new_rows)])
    return merged


def _no_settings() -> None:
    st.toast("This run recorded no settings to start from.", icon=":material/error:")


class Workflow(WorkflowManager):
    # Setup pages for upload, parameter, execution and results.
    # For layout use any streamlit components such as tabs (as shown in example), columns, or even expanders.
    # Keep every run as its own result set: the Run page names each run, the
    # Results page picks which one to show and the Download page renames,
    # downloads and deletes them. Results are read from self.results_dir.
    multi_run = True
    # The four steps of the workflow, each a page (src/workflow/guide.py):
    # Describe experiment -> Run analysis -> Explore results -> Export results
    configure_page = Path("content", "topp_workflow_parameter.py")
    run_page = Path("content", "topp_workflow_execution.py")
    results_page = Path("content", "topp_workflow_results.py")
    export_page = Path("content", "topp_workflow_download.py")

    def __init__(self) -> None:
        # Initialize the parent class with the workflow name.
        super().__init__("TOPP Workflow", st.session_state["workspace"])

    def upload(self) -> None:
        t = st.tabs(["MS data"])
        with t[0]:
            # Use the upload method from StreamlitUI to handle mzML file uploads.
            # Thermo .raw and Bruker .d are converted to mzML in execution().
            self.ui.upload_widget(
                key="mzML-files",
                name="MS data",
                file_types=["mzML", "raw", "d"],
                fallback=[str(f) for f in Path("example-data", "mzML").glob("*.mzML")],
                # Offer folders for the groups the file names suggest
                suggest_folders=True,
            )

    def analysis_section(self) -> None:
        """The **Your analysis** box at the top of Describe experiment.

        The input files first (their Browse dialog also takes new files, so
        there is no upload page), then what to do with them, then one
        sentence on what a start will do. Drawn in the page, not in the
        ``configure()`` fragment, so a choice here reruns the page and the
        step tabs below follow it.
        """
        with self.ui.analysis_box():
            # reactive=True so the experimental design follows the selection
            self.ui.select_input_file(
                "mzML-files", multiple=True, reactive=True,
                upload=dict(
                    file_types=["mzML", "raw", "d"],
                    fallback=[str(f) for f in Path("example-data", "mzML").glob("*.mzML")],
                    suggest_folders=True,
                ),
            )
            # What to do with them: a choice stored with the settings, which
            # adds or removes the step it switches on
            self.ui.choice(
                "run-python-script", [False, True],
                labels={False: "Features only", True: "Features and custom step"},
                label="Analysis",
                help="What the run does with the files.",
                option_help={
                    False: "detects features in each file and links them across the files.",
                    True: "also runs the custom Python tool on the linked features.",
                },
            )
            # Ready-made settings for the kind of data, read back from the
            # settings (the preset they hold), never stored themselves
            current = self.current_preset()
            self.ui.preset_choice(
                "feature-preset", "Detection", list(self.DETECTION_PRESETS), current,
                labels=self.DETECTION_PRESETS,
                help="Settings for feature detection and linking (presets.json). "
                     "Change any of them in the steps below.",
            )
            # What the selected files suggest, with a button that applies it
            recommended, why = self.recommend_preset(
                self.ui.current_params().get("mzML-files") or []
            )
            if recommended:
                self.ui.recommendation(why, recommended, current,
                                       f"Use {self.DETECTION_PRESETS[recommended].lower()}",
                                       "feature-preset-recommended")
            self.ui.analysis_summary(self.summary())

    # The presets the Detection control offers (presets.json), with their labels
    DETECTION_PRESETS = {
        "Metabolomics Default": "Balanced",
        "High Sensitivity": "Sensitive",
        "High Specificity": "Strict",
        "Fast Analysis": "Fast",
    }
    # From this many files on, the recommendation is the fast settings
    MANY_FILES = 10

    def current_preset(self):
        """The detection preset the settings hold, None when they are the user's own."""
        name, changed = self.parameter_manager.applied_preset_status()
        return name if name in self.DETECTION_PRESETS and not changed else None

    def recommend_preset(self, files: list) -> tuple:
        """The detection preset the selected files suggest, and why.

        Returns ``(preset, reason)``: a key of ``DETECTION_PRESETS`` and one
        sentence (Markdown) shown beside it, or ``(None, "")`` when there is
        nothing to suggest. The page shows the reason with a button that
        applies the preset, or says the settings already match it.

        The rule here only counts the files. A rule that looks at the data
        goes here too: read what it needs from the files (with pyOpenMS, for
        example the instrument or the number of spectra; cache that read,
        since this runs on every rerun of the page) and return the preset it
        points to. A new preset is an entry in presets.json plus its label in
        ``DETECTION_PRESETS``.
        """
        n = len(files)
        if not n:
            return None, ""
        if n >= self.MANY_FILES:
            preset = "Fast Analysis"
            return preset, (f"For {n} files, **{self.DETECTION_PRESETS[preset]}** "
                            "settings keep the run short.")
        preset = "Metabolomics Default"
        return preset, (f"For {n} file{'s' if n != 1 else ''}, the "
                        f"**{self.DETECTION_PRESETS[preset]}** settings fit most "
                        "metabolomics data.")

    def steps(self) -> list:
        """The steps the chosen analysis runs, in the order they run."""
        steps = ["Samples and groups", "Feature detection", "Feature linking"]
        if self.ui.current_params().get("run-python-script"):
            steps.append("Custom step")
        return steps

    def summary(self) -> str:
        """What a start will do, in one sentence (the box and the Run bar)."""
        params = self.ui.current_params()
        n = len(params.get("mzML-files") or [])
        files = f"{n} file{'s' if n != 1 else ''}" if n else "the selected files"
        extra = " and runs the custom Python tool on them" if params.get("run-python-script") else ""
        return f"Detects features in {files}, links them across the files{extra}."

    @st.fragment
    def configure(self) -> None:
        # One numbered tab per step the chosen analysis runs
        tabs = self.ui.step_tabs(self.steps())
        with tabs["Samples and groups"]:
            # Condition, replicate and fraction per selected file, saved as an
            # OpenMS design.tsv in the workflow directory. Pass that file to a
            # TOPP tool's -design (e.g. ProteomicsLFQ), or read it in
            # execution() with src.workflow.ExperimentalDesign.load_design().
            self.ui.experimental_design("mzML-files", suggest=True)
        with tabs["Feature detection"]:
            # Parameters for FeatureFinderMetabo TOPP tool.
            self.ui.input_TOPP(
                "FeatureFinderMetabo",
                custom_defaults={"algorithm:common:noise_threshold_int": 1000.0},
            )
        with tabs["Feature linking"]:
            self.ui.input_TOPP("FeatureLinkerUnlabeledKD")
            # A setting of the workflow's own (no TOPP tool has it), stored
            # with the run's parameters and read in execution()
            self.ui.input_widget(
                "min-files", 1, "Found in at least (files)",
                help="Keep a linked feature only if it was detected in at least this many files.",
                widget_type="number", min_value=1, max_value=100,
            )
        if "Custom step" in tabs:
            with tabs["Custom step"]:
                # Generate input widgets for a custom Python tool, located at src/python-tools.
                # Parameters are specified within the file in the DEFAULTS dictionary.
                self.ui.input_python("example")

    def execution(self) -> bool:
        # Return True only if every step succeeded. The caller
        # (tasks.execute_workflow, in local and queue mode) writes the
        # "WORKFLOW FINISHED" marker based on this, and that marker is the only
        # thing the run page reads to decide whether the workflow succeeded.
        # Returning None is still accepted, with a deprecation warning;
        # ignoring an executor result marks a failed run successful.

        # Any parameter checks, here simply checking if mzML files are selected
        if not self.params["mzML-files"]:
            self.logger.log("ERROR: No mzML files selected.")
            return False

        # An analysis added to an earlier run (missing_options): its feature
        # detection and linking are reused, only the steps after them run.
        if self._reuse_features():
            return self._custom_tool(Path(self.results_dir, "feature-linking", "feature_matrix.tsv"))

        # Convert any Thermo .raw / Bruker .d input to mzML (mzML passes through).
        in_files = self.executor.convert_to_mzml(self.params["mzML-files"])
        if in_files is None:
            return False

        # Get mzML files with FileManager
        in_mzML = self.file_manager.get_files(in_files)

        # Log any messages.
        self.logger.log(f"Number of input mzML files: {len(in_mzML)}")

        # Prepare output files for feature detection.
        out_ffm = self.file_manager.get_files(
            in_mzML, "featureXML", "feature-detection"
        )

        # Run FeatureFinderMetabo tool with input and output files.
        # run_topp returns False if any of the commands it ran failed. With
        # allow_failed=True a file it fails on is left out instead (the Run
        # page says which and why), and False means it failed on every file.
        self.logger.log("Detecting features...")
        if not self.executor.run_topp(
            "FeatureFinderMetabo",
            input_output={"in": in_mzML, "out": out_ffm},
            allow_failed=True,
        ):
            self.logger.log("ERROR: Feature detection failed.")
            return False
        # The next steps take only the files feature detection worked on
        out_ffm = self.executor.keep_succeeded(out_ffm)

        # Prepare input and output files for feature linking
        in_fl = self.file_manager.get_files(out_ffm, collect=True)
        out_fl = self.file_manager.get_files(
            "feature_matrix.consensusXML", set_results_dir="feature-linking"
        )

        # Run FeatureLinkerUnlabaeledKD with all feature maps passed at once
        self.logger.log("Linking features...")
        if not self.executor.run_topp(
            "FeatureLinkerUnlabeledKD", input_output={"in": in_fl, "out": out_fl}
        ):
            self.logger.log("ERROR: Feature linking failed.")
            return False

        # run_python has the same contract as run_topp: False if the script was
        # not found or exited non-zero.
        self.logger.log("Exporting consensus features to pandas DataFrame...")
        if not self.executor.run_python(
            "export_consensus_feature_df",
            input_output={"in": out_fl[0], "out": str(Path(out_fl[0]).with_suffix(".tsv"))},
        ):
            self.logger.log("ERROR: Exporting consensus features failed.")
            return False
        features = Path(out_fl[0]).with_suffix(".tsv")
        self._keep_features_in(features, int(self.params.get("min-files", 1)))

        return self._custom_tool(features)

    def _keep_features_in(self, table: Path, min_files: int) -> None:
        """Drop the linked features found in fewer than ``min_files`` files
        (the workflow's own setting ``min-files``)."""
        if min_files <= 1:
            return
        df = pd.read_csv(table, sep="\t")
        intensities = df.columns[df.columns.get_loc("quality") + 1:]
        kept = df[df[intensities].notna().sum(axis=1) >= min_files]
        kept.to_csv(table, sep="\t", index=False)
        self.logger.log(f"Kept {len(kept)} of {len(df)} features found in at least {min_files} files.")

    # The steps whose results an analysis added to a run takes from it
    FEATURE_STEPS = ["FeatureFinderMetabo", "FeatureLinkerUnlabeledKD"]

    def _reuse_features(self) -> bool:
        """Copy the feature detection and linking of the run this start adds an
        analysis to (``follow_up(..., same_files=..., keep=FEATURE_STEPS)``)
        into this run. False when the start reuses nothing (or it is gone)."""
        info = self.follow_up_info()
        reuses = info.get("reuses") or []
        if not reuses or not set(self.FEATURE_STEPS) <= set(info.get("kept") or []):
            return False
        source = self.runs.results_dir(reuses[0])
        if not Path(source, "feature-linking", "feature_matrix.tsv").exists():
            self.logger.log(f"The results of {info.get('name', reuses[0])} are gone: running every step.")
            return False
        for step in ("feature-detection", "feature-linking"):
            if Path(source, step).is_dir():
                shutil.copytree(Path(source, step), Path(self.results_dir, step), dirs_exist_ok=True)
        self.logger.log(f"Reusing the features of {info.get('name', reuses[0])}.")
        return True

    def _custom_tool(self, features: Path) -> bool:
        # Check if the custom Python tool should be run.
        if self.params.get("run-python-script"):
            # Example for a custom Python tool, which is located in src/python-tools.
            # It writes the features with the highest mean intensity.
            out_top = self.file_manager.get_files("top-features.tsv", set_results_dir="custom-tool")
            if not self.executor.run_python("example", {"in": [str(features)], "out": out_top}):
                self.logger.log("ERROR: Custom Python script failed.")
                return False
        return True

    # The Results page: components arranged in views, grouped as every
    # Explore results page groups them (guide.COMPONENT_GROUPS). A component that shows
    # the result of an optional step names it as "needs"; views of a run
    # without it are drawn disabled, and a click offers to add it.
    COMPONENTS = [
        {"name": "features", "label": "Consensus features", "group": QUANTIFICATION},
        {"name": "intensities", "label": "Intensities of the selected features", "group": QUANTIFICATION,
         "requires": "features"},
        {"name": "top_features", "label": "Top features (custom Python tool)", "group": QUANTIFICATION,
         "needs": "custom-tool"},
    ]
    PRESETS = [
        {"name": "features", "label": "Features", "layout": [["features", "intensities"]]},
        {"name": "top", "label": "Top features", "layout": [["top_features"]],
         "help": "The features with the highest mean intensity, from the custom Python tool."},
        {"name": "all", "label": "All", "layout": [["features", "intensities"], ["top_features"]]},
    ]
    ANALYSES = {
        "custom-tool": {
            "label": "the custom Python tool",
            "help": "It is an optional step of this workflow (**Python Custom Tool** on the Configure page).",
        },
    }

    def available(self, run_id=None) -> set:
        """The optional analyses a run (default: the one shown) includes."""
        results = self.runs.results_dir(run_id) if run_id else self.results_dir
        found = set()
        if Path(results, "custom-tool", "top-features.tsv").exists():
            found.add("custom-tool")
        return found

    def add_files(self, changes=None) -> None:
        """Open Configure with this run's settings (and ``changes``), to pick
        files that are then processed and added to its experiment."""
        self.follow_up(
            self.run_id, changes or {}, page=self.configure_page,
            note="to add more files", add_files="mzML-files") or _no_settings()

    def add_analysis(self, changes) -> None:
        """Open Configure with this run's settings and ``changes``, to add an analysis
        to the run: its files are locked and its features reused."""
        self.follow_up(
            self.run_id, changes, page=self.configure_page,
            note="with the custom Python tool switched on", same_files="mzML-files",
            keep=self.FEATURE_STEPS) or _no_settings()

    def missing_options(self, missing: list, view) -> list:
        """What the Results page offers for a view whose run lacks ``missing``: the
        missing analysis added to this run, its files and features kept."""
        changes = {"run-python-script": True} if "custom-tool" in missing else {}
        return [{
            "label": "Add the custom Python tool to this run",
            "icon": ":material/add_circle:",
            "help": "Opens Configure with this run's settings and the custom Python tool switched "
                    "on. The run's files stay as they are and its features are reused, so only the "
                    "tool's settings can be changed; the new run is kept next to this one.",
            "on_click": lambda: self.add_analysis(changes),
        }]

    # How features of the runs of an experiment are matched into one table
    # (merge_feature_tables), set in Edit comparison
    MATCHING = {"ppm": 10.0, "rt_tolerance": 30.0}

    def _members(self) -> list:
        return self.runs.experiment(self.run_id) or [self.run_id]

    def _matching_key(self, name: str) -> str:
        return f"topp-results-matching-{self.run_id}-{name}"

    def _matching(self) -> dict:
        # Kept apart from the dialog's widget keys: Streamlit drops a widget's
        # state on a run that does not draw it, i.e. once the dialog is closed
        return {name: float(st.session_state.get(self._matching_key(name), value))
                for name, value in self.MATCHING.items()}

    def _keep_matching(self, name: str) -> None:
        st.session_state[self._matching_key(name)] = st.session_state[self._matching_key(name) + "-input"]

    def _matching_step(self) -> None:
        st.caption("A feature of a later run joins the nearest feature of the runs before it within "
                   "these tolerances; otherwise it is a feature of its own.")
        left, right = st.columns(2)
        matching = self._matching()
        left.number_input("m/z tolerance (ppm)", 0.5, 100.0, matching["ppm"], 0.5,
                          key=self._matching_key("ppm") + "-input",
                          on_change=self._keep_matching, args=("ppm",))
        right.number_input("Retention time tolerance (s)", 1.0, 600.0, matching["rt_tolerance"], 1.0,
                           key=self._matching_key("rt_tolerance") + "-input",
                           on_change=self._keep_matching, args=("rt_tolerance",))

    def _runs_step(self) -> None:
        for run_id in self._members():
            st.markdown(f"- {run_label(self.runs.get(run_id) or {'id': run_id})}")

    def _reset_matching(self) -> None:
        for name in self.MATCHING:
            st.session_state.pop(self._matching_key(name), None)
            st.session_state.pop(self._matching_key(name) + "-input", None)

    def _experiment_bar(self) -> None:
        """Single run | Comparison for an experiment that runs added files to,
        and Edit comparison while the comparison is shown."""
        members = self._members()
        self._single = None
        if len(members) < 2:
            return
        with st.container(horizontal=True, vertical_alignment="bottom"):
            self._single = member_switch(
                f"topp-results-show-{self.run_id}", members,
                label_of=lambda r: run_label(self.runs.get(r) or {"id": r}),
                help_text="Comparison: the features of every run of the experiment, matched into one "
                          "table. Single run: the features of one run.",
            )
            if self._single is None:
                edit_comparison(
                    f"topp-results-{self.run_id}",
                    [("1. Runs", self._runs_step), ("2. Matching features", self._matching_step)],
                    intro="How the runs of this experiment are put into one feature table.",
                    on_reset=self._reset_matching,
                )

    @st.fragment
    def results(self) -> None:
        self._experiment_bar()
        layout_path = Path(self.workflow_dir, "layouts", "results.json")
        view_bar(
            layout_path, self.COMPONENTS, self.PRESETS, self.PRESETS[0]["layout"], key="topp-results-view",
            available=self.available(getattr(self, "_single", None)), analyses=self.ANALYSES,
            unavailable_options=self.missing_options, target="the Results page",
            actions=[{"id": "add-files", "icon": "➕", "label": "Add analysis", "on_click": self.add_files,
                      "help": "Process more files with this run's settings and add them to its experiment"}],
        )
        layout, _ = resolve_layout(layout_path, self.COMPONENTS, self.PRESETS[0]["layout"])
        render_layout(
            layout[0],
            {"features": self._features, "intensities": self._intensities, "top_features": self._top_features},
            components=self.COMPONENTS, available=self.available(getattr(self, "_single", None)),
            analyses=self.ANALYSES, on_missing=lambda missing, name: request_analysis("topp-results-view", missing, component=name),
        )

    def _shown_results(self) -> Path:
        """The results of the run shown: the one picked under Single run, else this run."""
        single = getattr(self, "_single", None)
        return Path(self.runs.results_dir(single)) if single else Path(self.results_dir)

    def _feature_table(self):
        """The consensus features of the shown experiment: one run, or a run and
        the runs that added files to it, their features matched here."""
        single = getattr(self, "_single", None)
        tables = []
        for run_id in [single] if single else self._members():
            file = Path(self.runs.results_dir(run_id), "feature-linking", "feature_matrix.tsv")
            if file.exists():
                tables.append(pd.read_csv(file, sep="\t", index_col=0))
        return merge_feature_tables(tables, **self._matching()) if tables else None

    def _features_key(self) -> str:
        """The feature table's widget key, one per experiment and its runs, so a
        selection never carries over to another table (files added change it)."""
        single = getattr(self, "_single", None)
        if single:
            return f"topp-results-features-{single}"
        # The matching tolerances decide the comparison's rows
        matching = "-".join(f"{v:g}" for v in self._matching().values())
        return "topp-results-features-" + "-".join(self._members()) + f"-{matching}"

    def _features(self) -> None:
        df = self._feature_table()
        if df is None:
            st.warning("No consensus feature file found. Please run workflow first.")
            return
        st.metric("number of consensus features", df.shape[0])
        st.dataframe(df, selection_mode="multi-row", on_select="rerun", key=self._features_key())

    def _intensities(self) -> None:
        df = self._feature_table()
        if df is None:
            return
        # The table shrinks when a run of the experiment is deleted
        rows = (st.session_state.get(self._features_key()) or {}).get("selection", {}).get("rows", [])
        rows = [row for row in rows if 0 <= row < len(df)]
        if rows:
            fig = px.bar(df.iloc[rows, 4:], barmode="group", labels={"value": "intensity"})
            show_fig(fig, "consensus-feature-intensities")
        else:
            st.info("💡 Select one or more rows in the table to show a barplot with intensities.")

    def _top_features(self) -> None:
        file = Path(self._shown_results(), "custom-tool", "top-features.tsv")
        st.markdown("**Top features**")
        st.dataframe(pd.read_csv(file, sep="\t"), hide_index=True)
