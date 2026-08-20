"""
``StreamlitUI._read_params_for_update()`` — the read half of the two
read-modify-write-back sites inside ``_input_TOPP_impl()``.

Both of them merge into what they read and write the result straight back, and
they run on *every* ``input_TOPP()`` of *every* ``configure()`` render. A
tolerant empty dict there is the erasure bug at its highest frequency: it would
be written over ``_defaults``, ``_flag_params`` and every other tool's values
while looking like a successful save.

Raising alone is not enough at this site, which is why it has its own method and
its own tests. The contract is:

* an unreadable file skips the write entirely, so the bytes on disk stay
  recoverable, and surfaces an error with a way forward;
* the way forward preserves the previous file rather than deleting it — the
  most common cause of an unreadable params.json on a shared filesystem is a
  healthy params.json behind a storage blip;
* a failure that is expected to clear by itself does *not* offer that reset at
  all, because taking it during a Ganesha restart is what would destroy an
  intact file;
* an absent file still reads as ``{}``: a first run has no parameters.
"""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Import with `streamlit`, `pyopenms` and `src.common.common` mocked at the
# sys.modules level, mirroring tests/test_topp_flag_parameters.py. The method
# under test only calls st.error / st.button / st.toast / st.stop, and with a
# mocked st.stop() the documented fallback applies: it re-raises rather than
# falling through to the write, which is exactly the property to assert.
# ---------------------------------------------------------------------------
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
    # Pulls in captcha / psutil / pandas and a lot of Streamlit surface; none
    # of it is reachable from the method under test.
    sys.modules["src.common.common"] = MagicMock()

from src.workflow.ParameterManager import (
    InvalidParameterFileError,
    ParameterManager,
    TransientParameterFileError,
)
from src.workflow.StreamlitUI import StreamlitUI

for name, module in _originals.items():
    if module is not None:
        sys.modules[name] = module
    else:
        sys.modules.pop(name, None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)


TOOL_INSTANCE = "FeatureFinderMetabo"

STORED_PARAMS = {
    "_defaults": {TOOL_INSTANCE: {"algorithm:common:noise_threshold_int": 1000.0}},
    "_flag_params": {TOOL_INSTANCE: ["force"]},
    "MetaboliteAdductDecharger": {
        "algorithm:MetaboliteFeatureDeconvolution:charge_max": 2
    },
}


@pytest.fixture(autouse=True)
def reset_streamlit_mock():
    """Fresh session state and a *falsy* st.button between tests."""
    mock_streamlit.reset_mock()
    mock_streamlit.session_state = {}
    # A bare MagicMock() return value is truthy, which would press every button
    # on the page.
    mock_streamlit.button.return_value = False
    yield
    mock_streamlit.reset_mock()
    mock_streamlit.session_state = {}


def _ui(tmp_path):
    """
    A StreamlitUI carrying only the member the method touches.

    __init__ is bypassed: it calls get_parameters_from_json(), which would
    already have absorbed the failure under test.
    """
    ui = object.__new__(StreamlitUI)
    ui.parameter_manager = ParameterManager(tmp_path)
    return ui


def _write_torn_params_file(ui) -> bytes:
    """Leave params.json unparseable but with every original byte on disk."""
    text = json.dumps(STORED_PARAMS, indent=4) + '\n{\n    "_defaults": {\n'
    ui.parameter_manager.params_file.write_text(text, encoding="utf-8")
    return ui.parameter_manager.params_file.read_bytes()


def test_readable_file_is_returned_unchanged(tmp_path):
    ui = _ui(tmp_path)
    ui.parameter_manager.params_file.write_text(
        json.dumps(STORED_PARAMS), encoding="utf-8"
    )

    assert ui._read_params_for_update(TOOL_INSTANCE) == STORED_PARAMS
    mock_streamlit.error.assert_not_called()
    mock_streamlit.stop.assert_not_called()


def test_absent_file_reads_as_empty(tmp_path):
    """A first run has no stored parameters; that is not a failure."""
    ui = _ui(tmp_path)
    assert not ui.parameter_manager.params_file.exists()

    assert ui._read_params_for_update(TOOL_INSTANCE) == {}
    mock_streamlit.error.assert_not_called()
    mock_streamlit.stop.assert_not_called()


def test_unreadable_file_stops_instead_of_returning_an_empty_dict(tmp_path):
    """
    The one thing that must never happen here: returning {} to the caller,
    which merges it and writes it straight back.
    """
    ui = _ui(tmp_path)
    before = _write_torn_params_file(ui)

    with pytest.raises(InvalidParameterFileError):
        ui._read_params_for_update(TOOL_INSTANCE)

    mock_streamlit.stop.assert_called_once()
    assert mock_streamlit.error.called, "the user has to be told why nothing saved"
    assert ui.parameter_manager.params_file.read_bytes() == before, (
        "the unreadable file must be preserved so it can still be repaired"
    )


def test_unreadable_file_offers_a_reset_keyed_per_tool_instance(tmp_path):
    """
    Without an affordance the page stops on every render with no way forward.
    The key has to carry the instance name: this runs once per tool fragment,
    and duplicate widget keys raise.
    """
    ui = _ui(tmp_path)
    _write_torn_params_file(ui)

    with pytest.raises(InvalidParameterFileError):
        ui._read_params_for_update(TOOL_INSTANCE)

    assert mock_streamlit.button.called
    assert TOOL_INSTANCE in mock_streamlit.button.call_args.kwargs["key"]


def test_reset_preserves_the_unreadable_file(tmp_path):
    """
    Pressing reset must not be the data loss. An unreadable params.json is very
    often an intact params.json behind a storage blip, so the previous file is
    moved aside rather than unlinked.
    """
    ui = _ui(tmp_path)
    before = _write_torn_params_file(ui)
    mock_streamlit.button.return_value = True

    with pytest.raises(InvalidParameterFileError):
        ui._read_params_for_update(TOOL_INSTANCE)

    assert not ui.parameter_manager.params_file.exists()
    backups = [p for p in tmp_path.iterdir() if p.name.endswith(".bak")]
    assert len(backups) == 1, f"expected the previous file to be kept, found {backups}"
    assert backups[0].read_bytes() == before


def test_transient_failure_does_not_offer_the_destructive_reset(tmp_path, monkeypatch):
    """
    ESTALE from a restarting NFS export is not corruption. Offering "reset to
    defaults" there invites the user to delete a file that is about to become
    readable again on its own.
    """
    ui = _ui(tmp_path)
    ui.parameter_manager.params_file.write_text(
        json.dumps(STORED_PARAMS), encoding="utf-8"
    )

    def unreachable():
        raise TransientParameterFileError("storage did not answer")

    monkeypatch.setattr(
        ui.parameter_manager, "read_parameters_strict", unreachable
    )

    with pytest.raises(TransientParameterFileError):
        ui._read_params_for_update(TOOL_INSTANCE)

    mock_streamlit.stop.assert_called_once()
    assert mock_streamlit.error.called
    mock_streamlit.button.assert_not_called()
    assert ui.parameter_manager.params_file.exists()


def test_a_failed_reset_is_reported_rather_than_raised(tmp_path, monkeypatch):
    """
    If the reset itself cannot run, the button used to raise, the file stayed,
    and the next render stopped again — an unrecoverable halt of the parameter
    page. The failure has to be surfaced instead.
    """
    ui = _ui(tmp_path)
    _write_torn_params_file(ui)
    mock_streamlit.button.return_value = True

    def refuse():
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr(
        ui.parameter_manager, "reset_to_default_parameters", refuse
    )

    with pytest.raises(InvalidParameterFileError):
        ui._read_params_for_update(TOOL_INSTANCE)

    messages = " ".join(str(call) for call in mock_streamlit.error.call_args_list)
    assert "read-only filesystem" in messages
