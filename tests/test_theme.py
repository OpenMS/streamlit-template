"""The OpenMS theme: config.toml, its fonts, the layout style sheet and the plot colours."""

import tomllib
from pathlib import Path

from src.common.plot_style import SPECTRUM_STYLING, spectrum_styling

ROOT = Path(__file__).resolve().parents[1]


def _theme_css(css, dark):
    # common.py imports Streamlit at module level; the helper itself is pure.
    from src.common.common import theme_css

    return theme_css(css, dark)


def test_every_font_face_is_shipped():
    config = tomllib.loads((ROOT / ".streamlit/config.toml").read_text(encoding="utf-8"))
    assert config["server"]["enableStaticServing"] is True
    faces = config["theme"]["fontFaces"]
    families = {f["family"] for f in faces}
    assert {config["theme"]["font"], config["theme"]["headingFont"], config["theme"]["codeFont"]} <= families
    for face in faces:
        assert face["url"].startswith("app/static/")
        assert (ROOT / face["url"].removeprefix("app/")).is_file(), face["url"]


def test_theme_defines_light_and_dark_without_base():
    config = tomllib.loads((ROOT / ".streamlit/config.toml").read_text(encoding="utf-8"))
    assert "base" not in config["theme"]
    for scheme in ("light", "dark"):
        assert config["theme"][scheme]["primaryColor"].startswith("#")


def test_dark_blocks_are_kept_for_dark_and_dropped_for_light():
    css = "a { color: red; }\n@media (prefers-color-scheme: dark) { a { color: blue; } b { x: y; } }\nc { z: 1; }"
    light = _theme_css(css, dark=False)
    dark = _theme_css(css, dark=True)
    assert "blue" not in light and "red" in light and "c { z: 1; }" in light
    assert "a { color: blue; } b { x: y; }" in dark and "prefers-color-scheme" not in dark


def test_shipped_style_sheet_resolves_cleanly():
    css = (ROOT / "src/common/theme.css").read_text(encoding="utf-8")
    for dark in (False, True):
        out = _theme_css(css, dark)
        assert "prefers-color-scheme" not in out
        assert out.count("{") == out.count("}")


def test_spectrum_styling_copies_and_merges():
    styling = spectrum_styling(selectedColor="#000000", annotationColors={"background": "#fff"})
    assert styling["selectedColor"] == "#000000"
    assert styling["annotationColors"]["background"] == "#fff"
    assert styling["annotationColors"]["massButton"] == SPECTRUM_STYLING["annotationColors"]["massButton"]
    assert "background" not in SPECTRUM_STYLING["annotationColors"]


def test_fonts_listed_with_their_licenses():
    from src.common import third_party

    fonts = third_party.fonts()
    assert [f.name for f in fonts] == ["Raleway", "Montserrat Alternates", "JetBrains Mono"]
    assert all(f.license == "OFL-1.1" and "SIL OPEN FONT LICENSE" in third_party.license_text(f).upper() for f in fonts)
