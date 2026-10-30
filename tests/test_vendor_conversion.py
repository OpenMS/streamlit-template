"""
Converting Thermo .raw and Bruker .d input to mzML.

``CommandExecutor.convert_to_mzml()`` passes mzML through, runs FileConverter
on .raw and ``src/python-tools/bruker_to_mzml.py`` on .d, keeps the result
under ``<workflow_dir>/converted-mzML`` and reuses it while it is newer than
the input. ``extract_bruker_zip()`` unpacks the zipped .d folders an online
user uploads, because a browser cannot upload a folder.
"""
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Import with `streamlit` and `pyopenms` mocked at the sys.modules level,
# mirroring tests/test_command_executor_run_python.py.
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}


_original_streamlit = sys.modules.get("streamlit")
_original_pyopenms = sys.modules.get("pyopenms")
sys.modules["streamlit"] = mock_streamlit
if _original_pyopenms is None:
    sys.modules["pyopenms"] = MagicMock()

from src.workflow.ParameterManager import ParameterManager
from src.workflow.CommandExecutor import CommandExecutor
from src.workflow.vendor_files import extract_bruker_zip, vendor_format

if _original_streamlit is not None:
    sys.modules["streamlit"] = _original_streamlit
else:
    sys.modules.pop("streamlit", None)
if _original_pyopenms is None:
    sys.modules.pop("pyopenms", None)

for _key in list(sys.modules.keys()):
    if _key.startswith("src.workflow"):
        sys.modules.pop(_key, None)

DDA_TEST_D = Path(PROJECT_ROOT, "tests", "data", "dda_test.d")
SCRIPT = Path(PROJECT_ROOT, "src", "python-tools", "bruker_to_mzml.py")


def _executor(tmp_path):
    executor = CommandExecutor(tmp_path, MagicMock(), ParameterManager(tmp_path))

    def fake_topp(tool, input_output, custom_params={}, tool_instance_name=None):
        Path(input_output["out"][0]).write_text("converted")
        return True

    def fake_python(script_file, input_output={}):
        Path(input_output["out"]).write_text("converted")
        return True

    executor.run_topp = MagicMock(side_effect=fake_topp)
    executor.run_python = MagicMock(side_effect=fake_python)
    return executor


@pytest.mark.parametrize(
    "name, kind",
    [("a.mzML", None), ("a.raw", "raw"), ("a.RAW", "raw"), ("a.d", "d"), ("a.D", "d"), ("a.d.zip", None)],
)
def test_vendor_format(name, kind):
    assert vendor_format(name) == kind


def test_mzml_passes_through_without_running_anything(tmp_path):
    executor = _executor(tmp_path)
    assert executor.convert_to_mzml(["/data/a.mzML"]) == ["/data/a.mzML"]
    executor.run_topp.assert_not_called()
    executor.run_python.assert_not_called()


def test_raw_is_converted_with_fileconverter(tmp_path):
    raw = tmp_path / "run1.RAW"
    raw.write_text("raw")
    executor = _executor(tmp_path)

    result = executor.convert_to_mzml([str(raw)])

    out = tmp_path / "converted-mzML" / "run1.mzML"
    assert result == [str(out)]
    assert out.read_text() == "converted"
    tool, io = executor.run_topp.call_args.args[:2]
    assert tool == "FileConverter"
    assert io["in"] == [str(raw)]
    # Written under a temporary name and renamed once complete.
    assert io["out"][0].endswith(".part.mzML")
    assert not Path(io["out"][0]).exists()


def test_d_folder_is_converted_with_the_python_tool(tmp_path):
    d = tmp_path / "run2.d"
    d.mkdir()
    executor = _executor(tmp_path)

    result = executor.convert_to_mzml([str(d), "/data/b.mzML"])

    assert result == [str(tmp_path / "converted-mzML" / "run2.mzML"), "/data/b.mzML"]
    script, io = executor.run_python.call_args.args[:2]
    assert script == "bruker_to_mzml"
    assert io["in"] == str(d)


def test_conversion_is_reused_until_the_input_changes(tmp_path):
    raw = tmp_path / "run1.raw"
    raw.write_text("raw")
    executor = _executor(tmp_path)

    executor.convert_to_mzml([str(raw)])
    executor.convert_to_mzml([str(raw)])
    assert executor.run_topp.call_count == 1

    later = time.time() + 10
    os.utime(raw, (later, later))
    executor.convert_to_mzml([str(raw)])
    assert executor.run_topp.call_count == 2


def test_failed_conversion_returns_none_and_leaves_no_mzml(tmp_path):
    raw = tmp_path / "run1.raw"
    raw.write_text("raw")
    executor = _executor(tmp_path)

    def failing_topp(tool, input_output, custom_params={}, tool_instance_name=None):
        Path(input_output["out"][0]).write_text("truncated")
        return False

    executor.run_topp.side_effect = failing_topp

    assert executor.convert_to_mzml([str(raw)]) is None
    assert list((tmp_path / "converted-mzML").iterdir()) == []


def _zip(path, members):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_zip_with_d_folders_is_unpacked(tmp_path):
    archive = _zip(
        tmp_path / "upload.zip",
        {
            "A.d/analysis.tdf": "a",
            "A.d/analysis.tdf_bin": "b",
            "B.d/analysis.tdf": "c",
            "notes.txt": "skipped",
        },
    )
    files_dir = tmp_path / "files"
    files_dir.mkdir()

    assert extract_bruker_zip(str(archive), files_dir) == ["A.d", "B.d"]
    assert (files_dir / "A.d" / "analysis.tdf_bin").read_text() == "b"
    assert not (files_dir / "notes.txt").exists()


def test_zip_of_d_contents_is_named_after_the_archive(tmp_path):
    archive = _zip(tmp_path / "run7.d.zip", {"analysis.tdf": "a", "analysis.tdf_bin": "b"})
    files_dir = tmp_path / "files"
    files_dir.mkdir()

    assert extract_bruker_zip(str(archive), files_dir) == ["run7.d"]
    assert (files_dir / "run7.d" / "analysis.tdf").exists()


def test_zip_members_cannot_escape_the_upload_folder(tmp_path):
    archive = _zip(tmp_path / "evil.zip", {"X.d/../../escaped.txt": "x", "X.d/analysis.tdf": "a"})
    files_dir = tmp_path / "files"
    files_dir.mkdir()

    extract_bruker_zip(str(archive), files_dir)
    assert not (tmp_path / "escaped.txt").exists()
    assert (files_dir / "X.d" / "analysis.tdf").exists()


def _run_script(tmp_path, d):
    params = tmp_path / "params.json"
    out = tmp_path / "out.mzML"
    params.write_text(json.dumps({"in": str(d), "out": str(out)}))
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(params)], capture_output=True, text=True
    )
    return proc, out


def test_bruker_script_converts_a_tdf_folder(tmp_path):
    pytest.importorskip("timsrust_pyo3")
    poms = pytest.importorskip("pyopenms")

    proc, out = _run_script(tmp_path, DDA_TEST_D)
    assert proc.returncode == 0, proc.stderr

    exp = poms.MSExperiment()
    poms.MzMLFile().load(str(out), exp)
    spectra = list(exp)
    assert [s.getMSLevel() for s in spectra] == [1, 2, 2, 1, 2]
    assert [s.getNativeID() for s in spectra] == [f"scan={i}" for i in range(1, 6)]
    rts = [s.getRT() for s in spectra]
    assert rts == sorted(rts)
    precursor = spectra[1].getPrecursors()[0]
    assert precursor.getMZ() == pytest.approx(500.0)
    assert precursor.getCharge() == 2


def test_bruker_script_rejects_baf_data(tmp_path):
    d = tmp_path / "maxis.d"
    d.mkdir()
    (d / "analysis.baf").write_text("")

    proc, out = _run_script(tmp_path, d)
    assert proc.returncode == 1
    assert "BAF" in proc.stderr and "msconvert" in proc.stderr
    assert not out.exists()
