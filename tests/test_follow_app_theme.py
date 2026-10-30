"""
Tests for follow_app_theme() in src/common/common.py.

follow_app_theme() lets Plotly figures follow the app's light or dark theme:
it switches the figure to the Streamlit Plotly template and drops the white
backgrounds, black axes and black annotation text that pyopenms-viz and the
"plotly_white"/"simple_white" templates set, while keeping trace colors.

Streamlit (and the other heavy runtime deps pulled in by common.py) are mocked
before import, mirroring tests/test_legal_links.py.
"""
import os
import sys
from unittest.mock import MagicMock

import plotly.graph_objects as go
import plotly.io as pio

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Mock streamlit and the other heavy
# imports pulled in by src/common/common.py, so importing follow_app_theme here
# doesn't require a running Streamlit app context.
#
# IMPORTANT: these mocks are installed into sys.modules only for the duration of
# the import below and then restored, so they don't leak into other test modules
# (e.g. the AppTest-based tests that need the real `streamlit` package). This
# mirrors the pattern in tests/test_parameter_presets.py.
mock_streamlit = MagicMock()

_MOCKED_MODULES = {
    "streamlit": mock_streamlit,
    "streamlit.components": MagicMock(),
    "streamlit.components.v1": MagicMock(),
    "streamlit.source_util": MagicMock(),
    "pandas": MagicMock(),
    "psutil": MagicMock(),
    # Local submodules with their own heavy deps (e.g. the captcha image library).
    "src.common.captcha_": MagicMock(),
    "src.common.admin": MagicMock(),
}
_saved_modules = {name: sys.modules.get(name) for name in _MOCKED_MODULES}
sys.modules.update(_MOCKED_MODULES)

# Force a FRESH import of src.common.common under the streamlit mock, even if an
# earlier test module (e.g. test_gui.py) already imported the real-streamlit-bound
# version. Save whatever was cached first so we can restore it afterwards.
_saved_common = sys.modules.pop("src.common.common", None)

from src.common.common import follow_app_theme  # noqa: E402

# Restore the real modules (or remove ones that weren't present) so that other
# test modules get the genuine packages.
for _name, _orig in _saved_modules.items():
    if _orig is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _orig
# Restore the original cached common module (the real-streamlit-bound one, if
# any) so AppTest-based test modules keep getting the genuine package.
# follow_app_theme keeps working: it holds a reference to the freshly-imported
# mock-bound module's globals (and the same `mock_streamlit` object the tests
# mutate).
if _saved_common is None:
    sys.modules.pop("src.common.common", None)
else:
    sys.modules["src.common.common"] = _saved_common

# The real streamlit registers its "streamlit" Plotly template on import; with
# streamlit mocked here, register a stand-in so the template name validates.
if "streamlit" not in pio.templates:
    pio.templates["streamlit"] = go.layout.Template()


def _light_mode_figure():
    fig = go.Figure(go.Scatter(x=[1, 2], y=[3, 4], line_color="#2d3a9d"))
    fig.update_layout(
        template="simple_white", plot_bgcolor="#FFFFFF", paper_bgcolor="white"
    )
    fig.update_xaxes(linecolor="black", tickcolor="black")
    fig.update_yaxes(linecolor="#000000", tickcolor="rgb(0, 0, 0)")
    fig.add_annotation(x=1, y=3, text="281.05", font=dict(color="black"))
    fig.add_annotation(x=2, y=4, text="y3", font=dict(color="#f24c5c"))
    return fig


def test_uses_streamlit_template_and_clears_backgrounds():
    fig = follow_app_theme(_light_mode_figure())
    layout = fig.to_dict()["layout"]
    assert "plot_bgcolor" not in layout
    assert "paper_bgcolor" not in layout
    assert fig.layout.template == pio.templates["streamlit"]


def test_clears_black_axes_and_annotation_text_only():
    fig = follow_app_theme(_light_mode_figure())
    assert fig.layout.xaxis.linecolor is None
    assert fig.layout.xaxis.tickcolor is None
    assert fig.layout.yaxis.linecolor is None
    assert fig.layout.yaxis.tickcolor is None
    assert fig.layout.annotations[0].font.color is None
    # Colors that carry meaning stay.
    assert fig.layout.annotations[1].font.color == "#f24c5c"
    assert fig.data[0].line.color == "#2d3a9d"


def test_returns_same_figure():
    fig = _light_mode_figure()
    assert follow_app_theme(fig) is fig
