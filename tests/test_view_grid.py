"""Tests for the reusable linked-grid template stack (src/view/grid.py + helpers).

Headless / no-browser: mirrors how OpenMS-Insight's own tests construct components
(``mock_streamlit`` patching ``st.session_state`` + a temp cache dir). Components are built
from the committed example parquet via ``data_path=`` and exercised through
``_prepare_vue_data`` / ``_get_component_args``. The grid / show_linked_grid / LayoutManager
are driven under a minimal mocked Streamlit context (each component's ``__call__`` is patched
to run the data path without the Vue bridge, since AppTest cannot spawn the preprocessing
subprocess).
"""

import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "example-data" / "insight"


class MockSessionState(dict):
    """Dict with attribute access, like st.session_state."""

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


class _Col:
    """Fake st.columns() column / container: context manager + the widgets the grid uses."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def warning(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def button(self, *a, **k):
        return False


_COLS_RECORD = []


def _columns(spec, **k):
    n = spec if isinstance(spec, int) else len(spec)
    _COLS_RECORD.append(n)
    return [_Col() for _ in range(n)]


def _container(*a, **k):
    return _Col()


def _noop(*a, **k):
    return None


@pytest.fixture
def mock_streamlit():
    state = MockSessionState()
    with patch("streamlit.session_state", state):
        yield state


@pytest.fixture
def cache_dir():
    return tempfile.mkdtemp(prefix="tmpl_view_grid_")


def _build_components(cache):
    """Construct the four demo components from the example parquet fixtures.

    Uses ``data=pl.scan_parquet(...)`` (in-process preprocessing) rather than ``data_path=``
    so construction does not spawn a subprocess. This mirrors OpenMS-Insight's own
    construction tests (which build from ``data=`` LazyFrames) and keeps these tests robust
    when run in the same pytest session as the Streamlit ``AppTest`` GUI tests (the spawn
    subprocess used by ``data_path=`` crashes under that shared runner -- a known AppTest
    limitation, not a code defect). The demo *page* deliberately uses ``data_path=`` for the
    production memory-efficiency benefit; the ``data_path=`` path itself is covered by
    :func:`test_component_data_path_construction`.
    """
    from openms_insight import Heatmap, LinePlot, SequenceView, Table

    return {
        "spectra_table": Table(
            cache_id="t_spectra",
            data=pl.scan_parquet(DATA / "spectra.parquet"),
            cache_path=cache,
            interactivity={"spectrum": "scan_id"},
            index_field="scan_id",
            default_row=0,
            title="Spectrum Table",
        ),
        "spectrum_plot": LinePlot(
            cache_id="t_spectrum_plot",
            data=pl.scan_parquet(DATA / "peaks.parquet"),
            cache_path=cache,
            filters={"spectrum": "scan_id"},
            interactivity={"peak": "peak_id"},
            x_column="mass",
            y_column="intensity",
            highlight_column="is_annotated",
            annotation_column="ion_label",
            title="MS/MS Spectrum",
        ),
        "peak_map": Heatmap(
            cache_id="t_peak_map",
            data=pl.scan_parquet(DATA / "heat.parquet"),
            cache_path=cache,
            x_column="rt",
            y_column="mass",
            intensity_column="intensity",
            interactivity={"spectrum": "scan_id", "peak": "peak_id"},
            title="Peak Map",
        ),
        "sequence_view": SequenceView(
            cache_id="t_seq",
            sequence_data=pl.scan_parquet(DATA / "sequences.parquet"),
            peaks_data=pl.scan_parquet(DATA / "peaks.parquet"),
            cache_path=cache,
            filters={"spectrum": "scan_id"},
            interactivity={"peak": "peak_id"},
            deconvolved=True,
            title="Fragment Coverage",
        ),
    }


def _patch_component_calls(stack, fake_call):
    """Patch ``__call__`` on every concrete component class (they don't all share it)."""
    from openms_insight import Heatmap, LinePlot, SequenceView, Table

    stack.enter_context(patch("streamlit.columns", _columns))
    stack.enter_context(patch("streamlit.container", _container))
    stack.enter_context(patch("streamlit.warning", _noop))
    stack.enter_context(patch("streamlit.divider", _noop))
    for cls in (Table, LinePlot, Heatmap, SequenceView):
        stack.enter_context(patch.object(cls, "__call__", fake_call))


# --------------------------------------------------------------------------- #
# fixtures (the committed example parquet) load with the documented schema
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name,cols",
    [
        ("spectra", {"scan_id", "rt", "ms_level", "precursor_mz", "n_peaks"}),
        ("peaks", {"scan_id", "peak_id", "mass", "intensity", "is_annotated", "ion_label"}),
        ("heat", {"scan_id", "rt", "mass", "intensity", "peak_id"}),
        ("sequences", {"scan_id", "sequence", "precursor_charge"}),
    ],
)
def test_example_fixtures_load(name, cols):
    df = pl.read_parquet(DATA / f"{name}.parquet")
    assert df.height > 0
    assert cols.issubset(set(df.columns))


# --------------------------------------------------------------------------- #
# every component constructs from data_path= and runs the two contract methods
# --------------------------------------------------------------------------- #
def test_components_construct_and_prepare(mock_streamlit, cache_dir):
    comps = _build_components(cache_dir)
    assert set(comps) == {"spectra_table", "spectrum_plot", "peak_map", "sequence_view"}
    for comp in comps.values():
        for state in ({}, {"spectrum": 1, "peak": 21}):
            vue = comp._prepare_vue_data(state)
            assert isinstance(vue, dict)
            args = comp._get_component_args()
            assert isinstance(args, dict) and "componentType" in args


# --------------------------------------------------------------------------- #
# render_linked_grid wiring: shared StateManager, per-cell keys, <=3 columns
# --------------------------------------------------------------------------- #
def test_render_linked_grid_wiring(mock_streamlit, cache_dir):
    from openms_insight import StateManager

    from src.view.grid import render_linked_grid

    comps = _build_components(cache_dir)
    builders = {k: (lambda c=v: c) for k, v in comps.items()}
    rendered = []

    def fc(self, key=None, state_manager=None, height=None):
        self._prepare_vue_data(
            state_manager.get_all_selections() if state_manager else {}
        )
        rendered.append((key, id(state_manager)))
        return None

    layout = [["spectra_table", "spectrum_plot"], ["peak_map", "sequence_view"]]
    _COLS_RECORD.clear()
    with ExitStack() as stack:
        _patch_component_calls(stack, fc)
        sm = render_linked_grid(layout, builders, state_key="exp0", grid_key="g")

    assert isinstance(sm, StateManager)
    assert sorted(r[0] for r in rendered) == ["g_0_0", "g_0_1", "g_1_0", "g_1_1"]
    # all cells shared exactly one StateManager (cross-linking)
    assert len({r[1] for r in rendered}) == 1
    assert _COLS_RECORD == [2, 2]


def test_render_linked_grid_clamps_to_three_columns(mock_streamlit, cache_dir):
    from src.view.grid import MAX_COLUMNS, render_linked_grid

    comps = _build_components(cache_dir)
    builders = {k: (lambda c=v: c) for k, v in comps.items()}
    rendered = []

    def fc(self, key=None, state_manager=None, height=None):
        rendered.append(key)
        return None

    big = [["spectra_table", "spectrum_plot", "peak_map", "sequence_view"]]
    _COLS_RECORD.clear()
    with ExitStack() as stack:
        _patch_component_calls(stack, fc)
        render_linked_grid(big, builders, state_key="big", grid_key="b")

    assert _COLS_RECORD == [MAX_COLUMNS]
    assert len(rendered) == MAX_COLUMNS


def test_render_linked_grid_on_missing(mock_streamlit, cache_dir):
    from src.view.grid import render_linked_grid

    comps = _build_components(cache_dir)
    builders = {k: (lambda c=v: c) for k, v in comps.items()}
    rendered = []

    def fc(self, key=None, state_manager=None, height=None):
        rendered.append(key)
        return None

    with ExitStack() as stack:
        _patch_component_calls(stack, fc)
        # warn -> skip, no cell rendered, no raise
        render_linked_grid([["nope"]], builders, state_key="m1")
        assert rendered == []
        # error -> KeyError
        with pytest.raises(KeyError):
            render_linked_grid([["nope"]], builders, state_key="m2", on_missing="error")
    # invalid on_missing rejected up-front
    with pytest.raises(ValueError):
        render_linked_grid([["spectra_table"]], builders, state_key="m3", on_missing="x")


# --------------------------------------------------------------------------- #
# show_linked_grid: one independent StateManager per experiment
# --------------------------------------------------------------------------- #
def test_show_linked_grid_one_state_manager_per_experiment(mock_streamlit, cache_dir):
    from src.common.common import show_linked_grid

    comps = _build_components(cache_dir)
    builders = {k: (lambda c=v: c) for k, v in comps.items()}
    two_exp = [[["spectra_table"]], [["peak_map"]]]

    def _make_fc(sink):
        def fc(self, key=None, state_manager=None, height=None):
            sink.append(id(state_manager))
            return None

        return fc

    for side_by_side in (True, False):
        seen = []
        with ExitStack() as stack:
            _patch_component_calls(stack, _make_fc(seen))
            show_linked_grid(two_exp, builders, tool="demo", side_by_side=side_by_side)
        assert len(set(seen)) == 2, f"side_by_side={side_by_side}"


# --------------------------------------------------------------------------- #
# LayoutManager: trim/expand/validate/dependency + persistence round-trip
# --------------------------------------------------------------------------- #
def test_layout_manager_trim_expand_validate(mock_streamlit):
    from src.view.grid import LayoutManager

    options = ["Spectrum table", "Spectrum plot", "Peak map", "Sequence view"]
    names = ["spectra_table", "spectrum_plot", "peak_map", "sequence_view"]
    lm = LayoutManager(options, names, store=_DummyStore(), session_prefix="t")

    labels = [[["Spectrum table", "Spectrum plot"]], [["Peak map", ""]]]
    trimmed = lm.trim(labels)
    assert trimmed == [[["spectra_table", "spectrum_plot"]], [["peak_map"]]]
    assert lm.expand(trimmed) == [[["Spectrum table", "Spectrum plot"]], [["Peak map"]]]

    assert lm.validate([[[""]]]) != ""  # empty rejected
    assert lm.validate(labels) == ""  # valid accepted

    # "(... needed)" dependency validation + idempotent add_options
    lm.add_options(["Sequence view (Spectrum table needed)"], ["seqdep"])
    before = len(lm.component_names)
    lm.add_options(["Sequence view (Spectrum table needed)"], ["seqdep"])
    assert len(lm.component_names) == before
    assert lm.validate([[["Sequence view (Spectrum table needed)"]]]) != ""
    assert (
        lm.validate([[["Spectrum table", "Sequence view (Spectrum table needed)"]]])
        == ""
    )


def test_layout_manager_persistence_roundtrip(mock_streamlit):
    from src.view.grid import LayoutManager
    from src.workflow.FileManager import FileManager

    ws = Path(tempfile.mkdtemp(prefix="tmpl_lm_ws_"))
    fm = FileManager(ws, cache_path=ws / "cache")
    lm = LayoutManager(
        ["Spectrum table"],
        ["spectra_table"],
        store=fm,
        layout_id="demo_layout",
        session_prefix="t2",
    )
    assert lm.get_layout() is None
    trimmed = [[["spectra_table"]]]
    lm.set_layout(trimmed, side_by_side=True)
    got = lm.get_layout()
    assert got == (trimmed, True)


class _DummyStore:
    """In-memory Store protocol impl for trim/expand/validate tests (no disk)."""

    def __init__(self):
        self._d = {}

    def get_results(self, dataset_id, name_tags):
        return {t: self._d[(dataset_id, t)] for t in name_tags}

    def store_data(self, dataset_id, name_tag, data):
        self._d[(dataset_id, name_tag)] = data

    def result_exists(self, dataset_id, name_tag):
        return (dataset_id, name_tag) in self._d

    def remove_results(self, dataset_id):
        self._d = {k: v for k, v in self._d.items() if k[0] != dataset_id}


def test_store_protocol_satisfied_by_filemanager():
    """FileManager structurally satisfies the grid.Store protocol."""
    from src.view.grid import Store
    from src.workflow.FileManager import FileManager

    ws = Path(tempfile.mkdtemp(prefix="tmpl_store_"))
    fm = FileManager(ws, cache_path=ws / "cache")
    assert isinstance(fm, Store)


def test_component_data_path_construction():
    """The demo page's ``data_path=`` path works end-to-end (subprocess preprocessing).

    Run in a clean interpreter via ``subprocess`` so it exercises the exact production path
    (Insight spawns a preprocessing subprocess for ``data_path=``) without being affected by
    the Streamlit ``AppTest`` GUI tests that may share this pytest session.
    """
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        f"""
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        class S(dict):
            def __getattr__(s, k):
                try: return s[k]
                except KeyError as e: raise AttributeError(k) from e
            def __setattr__(s, k, v): s[k] = v

        DATA = Path({str(DATA)!r})
        with patch("streamlit.session_state", S()):
            from openms_insight import Table, LinePlot, Heatmap, SequenceView
            cache = tempfile.mkdtemp()
            Table(cache_id="dp_t", data_path=str(DATA/"spectra.parquet"), cache_path=cache,
                  interactivity={{"spectrum": "scan_id"}}, index_field="scan_id", default_row=0)
            LinePlot(cache_id="dp_lp", data_path=str(DATA/"peaks.parquet"), cache_path=cache,
                     filters={{"spectrum": "scan_id"}}, interactivity={{"peak": "peak_id"}},
                     x_column="mass", y_column="intensity")
            Heatmap(cache_id="dp_h", data_path=str(DATA/"heat.parquet"), cache_path=cache,
                    x_column="rt", y_column="mass", intensity_column="intensity")
            SequenceView(cache_id="dp_sv", sequence_data_path=str(DATA/"sequences.parquet"),
                         peaks_data_path=str(DATA/"peaks.parquet"), cache_path=cache,
                         filters={{"spectrum": "scan_id"}}, deconvolved=True)
            print("DATA_PATH_OK")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert "DATA_PATH_OK" in proc.stdout, (
        f"data_path construction failed:\nstdout={proc.stdout}\nstderr={proc.stderr[-2000:]}"
    )
