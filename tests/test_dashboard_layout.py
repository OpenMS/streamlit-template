"""Tests for src/common/dashboard/layout.py and quant.py (Streamlit-free)."""

import json

import pytest

from src.common.dashboard.layout import (
    Panel,
    active_layout,
    delete_layout,
    drop_unknown,
    layout_path,
    load_layout,
    save_layout,
    validate_layout,
)
from src.common.dashboard.quant import (
    QUANT_DEFAULT_LAYOUT,
    QUANT_PANEL_SPECS,
    quant_panels,
)

PANELS = [
    Panel("table", "Table"),
    Panel("plot", "Plot", requires="table"),
    Panel("summary", "Summary"),
    Panel("extra", "Extra"),
]


def test_valid_layout():
    assert validate_layout([[["summary"], ["table", "plot"]]], PANELS) == ""


@pytest.mark.parametrize(
    ("layout", "message"),
    [
        ([], "Empty layout"),
        ([[]], "View is empty"),
        ([[["table"]], [["table"]]], "At most 1 views"),
        ([[["table", "plot", "summary", "extra"]]], "at most 3 panels"),
        ([[["nope"]]], 'Unknown panel "nope"'),
        ([[["table"], ["table"]]], "placed twice"),
        ([[["plot"]]], "Plot needs Table"),
        ([[["table"], []]], "Empty row"),
    ],
)
def test_invalid_layouts(layout, message):
    assert message in validate_layout(layout, PANELS)


def test_several_views_name_the_view():
    layout = [[["table"]], [["plot"]]]
    assert validate_layout(layout, PANELS, max_views=2) == "Plot needs Table in view 2"


def test_save_load_delete(tmp_path):
    assert load_layout(tmp_path, "quant") is None
    save_layout(tmp_path, "quant", [[["table"]], [["summary"]]], side_by_side=True)
    assert load_layout(tmp_path, "quant") == {
        "layout": [[["table"]], [["summary"]]],
        "side_by_side": True,
    }
    # side by side only applies to two views
    save_layout(tmp_path, "quant", [[["table"]]], side_by_side=True)
    assert load_layout(tmp_path, "quant")["side_by_side"] is False
    delete_layout(tmp_path, "quant")
    assert load_layout(tmp_path, "quant") is None
    delete_layout(tmp_path, "quant")  # deleting twice is fine


def test_broken_file_counts_as_no_layout(tmp_path):
    path = layout_path(tmp_path, "quant")
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_layout(tmp_path, "quant") is None
    path.write_text(json.dumps({"layout": "x"}), encoding="utf-8")
    assert load_layout(tmp_path, "quant") is None


def test_dashboard_name_cannot_leave_the_directory(tmp_path):
    with pytest.raises(ValueError):
        layout_path(tmp_path, "../escape")


def test_active_layout_drops_panels_this_app_lacks(tmp_path):
    default = [["summary"], ["table"]]
    assert active_layout(tmp_path, "quant", PANELS, default) == ([default], False)
    save_layout(tmp_path, "quant", [[["gone"], ["table", "gone"]]])
    assert active_layout(tmp_path, "quant", PANELS, default) == ([[["table"]]], False)
    save_layout(tmp_path, "quant", [[["gone"]]])
    assert active_layout(tmp_path, "quant", PANELS, default) == ([default], False)


def test_drop_unknown_removes_empty_rows_and_views():
    assert drop_unknown([[["a"], ["table", "a"]], [["a"]]], PANELS) == [[["table"]]]


def test_quant_default_layout_is_valid():
    renderers = {name: (lambda ctx: None) for name, *_ in QUANT_PANEL_SPECS}
    panels = quant_panels(renderers)
    assert validate_layout([QUANT_DEFAULT_LAYOUT], panels) == ""


def test_quant_panels_offers_only_what_the_app_draws():
    panels = quant_panels({"volcano": lambda ctx: None, "abundance_per_sample": print})
    assert [p.name for p in panels] == ["volcano", "abundance_per_sample"]
    # its requirement is not drawn here, so it is not required
    assert panels[1].requires is None
    with pytest.raises(KeyError, match="volcanoo"):
        quant_panels({"volcanoo": print})
