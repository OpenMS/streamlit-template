"""
``_matches_topp_parameter()`` — how ``input_TOPP(exclude_parameters=...,
include_parameters=...)`` patterns select TOPP parameters.

A plain name matches the end of the parameter path, bounded by ':'. A name
ending in ':' selects a whole top-level section, so a tool can hide a
subsection (e.g. FLASHTnT's ``fd:`` parameters, which only apply to raw input)
without listing every parameter in it.
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Same sys.modules mocking as tests/test_streamlit_ui_param_read.py.
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}

_originals = {
    name: sys.modules.get(name)
    for name in ("streamlit", "pyopenms", "src.common.common")
}
sys.modules["streamlit"] = mock_streamlit
if _originals["pyopenms"] is None:
    sys.modules["pyopenms"] = MagicMock()
if _originals["src.common.common"] is None:
    sys.modules["src.common.common"] = MagicMock()

from src.workflow.StreamlitUI import _matches_topp_parameter, _tags, _txt, _valid_strings

for name, module in _originals.items():
    if module is not None:
        sys.modules[name] = module
    else:
        sys.modules.pop(name, None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)


@pytest.mark.parametrize(
    "pattern, key, expected",
    [
        # suffix matching, bounded by ':'
        ("tol", b"FLASHTnT:1:fd:FD:tol", True),
        ("FD:tol", b"FLASHTnT:1:fd:FD:tol", True),
        ("ol", b"FLASHTnT:1:fd:FD:tol", False),
        ("prsm_fdr", b"FLASHTnT:1:prsm_fdr", True),
        # legacy leading colon is ignored
        (":prsm_fdr", b"FLASHTnT:1:prsm_fdr", True),
        # a trailing ':' names a top-level section
        ("fd:", b"FLASHTnT:1:fd:FD:tol", True),
        ("fd:FD:", b"FLASHTnT:1:fd:FD:tol", True),
        ("fd:", b"FLASHTnT:1:fdr", False),
        ("fd:", b"FLASHTnT:1:prsm_fdr", False),
        ("FD:", b"FLASHTnT:1:fd:FD:tol", False),
        ("fd:", b"FLASHTnT:1:tag:fd:x", False),
    ],
)
def test_matches_topp_parameter(pattern, key, expected):
    assert _matches_topp_parameter(pattern, key) is expected


@pytest.mark.parametrize("key", [b"FLASHTnT:1:fd:FD:tol", "FLASHTnT:1:fd:FD:tol"])
def test_matches_str_and_bytes_keys(key):
    """pyOpenMS up to 3.5 gives Param keys as bytes, 3.6 (nanobind) as str."""
    assert _matches_topp_parameter("tol", key) is True
    assert _matches_topp_parameter("fd:", key) is True
    assert _matches_topp_parameter("x", key) is False


def test_tags_and_text_from_either_pyopenms():
    param = MagicMock()
    param.getTags.return_value = [b"input file", "advanced"]
    assert _tags(param, "Tool:1:in") == ["input file", "advanced"]
    assert _txt(b"name") == "name" and _txt("name") == "name"


def test_valid_strings_of_a_boolean_parameter():
    """pyOpenMS 3.6 raises TypeError for valid_strings of a boolean entry."""
    class BoolEntry:
        value = True

        @property
        def valid_strings(self):
            raise TypeError("boolean parameter has no string restrictions")

    class StrEntry:
        value = "a"
        valid_strings = [b"a", "b"]

    assert _valid_strings(BoolEntry()) == []
    assert _valid_strings(StrEntry()) == ["a", "b"]
