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

from src.workflow.StreamlitUI import _matches_topp_parameter

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
