import sys
import os
import json
import shutil
from pathlib import Path
import pytest
from unittest.mock import patch

# Add src/ to path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from workflow.ParameterManager import ParameterManager
from workflow.CommandExecutor import CommandExecutor
import pyopenms as poms


class DummyLogger:
    def log(self, msg, level=1):
        print(f"[LOG-{level}] {msg}")


def test_end_to_end_boolean_flag_handling(tmp_path):
    # SETUP
    tool = "FeatureFinderMetabo"
    ini_dir = tmp_path / "ini"
    ini_dir.mkdir(parents=True)

    # Create a valid OpenMS .ini XML file
    param = poms.Param()
    param.setValue("algorithm:ffm:masstrace_snr_filtering", True, "")
    param.setValue("algorithm:ffm:elution_peak_detection", False, "")
    param.setValue("in", "input.mzML", "")
    param.setValue("out", "output.featureXML", "")
    poms.ParamXMLFile().store(str(ini_dir / f"{tool}.ini"), param)

    # Save mock params.json
    params = {
        tool: {
            "algorithm.ffm.masstrace_snr_filtering": True,
            "algorithm.ffm.elution_peak_detection": False,
            "in": "input.mzML",
            "out": "output.featureXML"
        }
    }
    with open(tmp_path / "params.json", "w") as f:
        json.dump(params, f)

    # INIT PARAMETER MANAGER + EXECUTOR
    pm = ParameterManager(tmp_path)
    ce = CommandExecutor(tmp_path, DummyLogger(), pm)

    # Simulate inputs
    input_output = {
        "in": ["input.mzML"],
        "out": ["output.featureXML"]
    }

    # MOCK run_command to intercept CLI
    with patch.object(ce, 'run_command') as mock_run:
        ce.run_topp(tool, input_output)

        # EXTRACT generated command
        command = mock_run.call_args[0][0]

        # ASSERTIONS
        assert tool in command, "Tool name missing from CLI"
        assert "-in" in command and "input.mzML" in command
        assert "-out" in command and "output.featureXML" in command
        assert "-algorithm.ffm.masstrace_snr_filtering" in command, "True flag missing"
        assert "-algorithm:ffm:elution_peak_detection" not in command, "False flag should be omitted"
        print("\n✅ Generated command:", " ".join(command))

    # CLEANUP
    shutil.rmtree(tmp_path, ignore_errors=True)
