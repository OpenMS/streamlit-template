"""
Tests for the tool_instance_name functionality.

This module verifies that save_parameters correctly resolves tool instance names
to real tool names when calling create_ini, and that parameters are stored and
retrieved using the instance name as the key.
"""
import os
import sys
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Mock streamlit before importing ParameterManager
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}

_original_streamlit = sys.modules.get('streamlit')
sys.modules['streamlit'] = mock_streamlit

from src.workflow.ParameterManager import ParameterManager

if _original_streamlit is not None:
    sys.modules['streamlit'] = _original_streamlit
else:
    sys.modules.pop('streamlit', None)

# Remove cached src.workflow modules
for _key in list(sys.modules.keys()):
    if _key.startswith('src.workflow'):
        sys.modules.pop(_key, None)


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary workflow directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_dir = Path(tmpdir) / "test-workflow"
        workflow_dir.mkdir()
        ini_dir = workflow_dir / "ini"
        ini_dir.mkdir()
        yield workflow_dir


@pytest.fixture(autouse=True)
def reset_streamlit_state():
    """Reset mock streamlit session state before each test."""
    mock_streamlit.session_state.clear()
    yield


class TestSaveParametersWithInstanceName:
    """Tests for save_parameters correctly resolving tool instance names."""

    def test_save_parameters_uses_real_tool_name_for_create_ini(self, temp_workflow_dir):
        """Test that save_parameters resolves instance name to real tool name
        before calling create_ini."""
        pm = ParameterManager(temp_workflow_dir)

        # Simulate session state with an instance name (IDFilter_step1)
        # that differs from the real tool name (IDFilter)
        mock_streamlit.session_state[f"{pm.topp_param_prefix}IDFilter_step1:1:score:pep"] = 0.05
        # Register instance mapping (as input_TOPP would)
        mock_streamlit.session_state["_topp_tool_instance_map"] = {
            "IDFilter_step1": "IDFilter"
        }

        # Mock create_ini to track calls - return False (tool not found)
        # to prevent further processing that requires actual ini files
        with patch.object(pm, 'create_ini', return_value=False) as mock_create_ini:
            pm.save_parameters()

        # Verify create_ini was called with the REAL tool name, not the instance name
        mock_create_ini.assert_called_once_with("IDFilter")

    def test_save_parameters_without_instance_map_uses_tool_name_directly(self, temp_workflow_dir):
        """Test that save_parameters works normally when no instance map exists
        (backward compatibility)."""
        pm = ParameterManager(temp_workflow_dir)

        # Simulate session state with a normal tool name (no instance mapping)
        mock_streamlit.session_state[f"{pm.topp_param_prefix}IDFilter:1:score:pep"] = 0.05

        with patch.object(pm, 'create_ini', return_value=False) as mock_create_ini:
            pm.save_parameters()

        # Should use the tool name directly
        mock_create_ini.assert_called_once_with("IDFilter")

    def test_save_parameters_stores_under_instance_name(self, temp_workflow_dir):
        """Test that parameters are stored in JSON under the instance name, not
        the real tool name."""
        pm = ParameterManager(temp_workflow_dir)

        # Create a mock ini file for IDFilter
        ini_path = temp_workflow_dir / "ini" / "IDFilter.ini"
        ini_path.touch()

        # Set up instance mapping
        mock_streamlit.session_state["_topp_tool_instance_map"] = {
            "IDFilter_step1": "IDFilter"
        }
        mock_streamlit.session_state[f"{pm.topp_param_prefix}IDFilter_step1:1:score:pep"] = 0.05

        # Mock pyopenms Param and ParamXMLFile to avoid needing real ini files
        mock_param = MagicMock()
        mock_param.getValue.return_value = 0.01  # Different from session state value

        with patch.object(pm, 'create_ini', return_value=True), \
             patch('pyopenms.Param', return_value=mock_param), \
             patch('pyopenms.ParamXMLFile') as mock_xml:
            pm.save_parameters()

        # Load saved parameters
        with open(pm.params_file, "r") as f:
            saved = json.load(f)

        # Parameters should be stored under the instance name
        assert "IDFilter_step1" in saved
        assert saved["IDFilter_step1"]["score:pep"] == 0.05

    def test_save_parameters_multiple_instances_same_tool(self, temp_workflow_dir):
        """Test that two instances of the same tool get separate parameter entries."""
        pm = ParameterManager(temp_workflow_dir)

        ini_path = temp_workflow_dir / "ini" / "IDFilter.ini"
        ini_path.touch()

        # Set up two instances with different parameter values
        mock_streamlit.session_state["_topp_tool_instance_map"] = {
            "IDFilter_step1": "IDFilter",
            "IDFilter_step2": "IDFilter",
        }
        mock_streamlit.session_state[f"{pm.topp_param_prefix}IDFilter_step1:1:score:pep"] = 0.01
        mock_streamlit.session_state[f"{pm.topp_param_prefix}IDFilter_step2:1:score:pep"] = 0.05

        mock_param = MagicMock()
        mock_param.getValue.return_value = 0.0  # Default differs from both

        with patch.object(pm, 'create_ini', return_value=True), \
             patch('pyopenms.Param', return_value=mock_param), \
             patch('pyopenms.ParamXMLFile'):
            pm.save_parameters()

        with open(pm.params_file, "r") as f:
            saved = json.load(f)

        # Both instances should have separate entries
        assert "IDFilter_step1" in saved
        assert "IDFilter_step2" in saved
        assert saved["IDFilter_step1"]["score:pep"] == 0.01
        assert saved["IDFilter_step2"]["score:pep"] == 0.05

    def test_save_parameters_ini_key_maps_instance_to_real_tool(self, temp_workflow_dir):
        """Test that ini_key correctly maps instance name back to real tool name
        for param.getValue lookup."""
        pm = ParameterManager(temp_workflow_dir)

        ini_path = temp_workflow_dir / "ini" / "IDFilter.ini"
        ini_path.touch()

        mock_streamlit.session_state["_topp_tool_instance_map"] = {
            "IDFilter_step1": "IDFilter"
        }
        mock_streamlit.session_state[f"{pm.topp_param_prefix}IDFilter_step1:1:score:pep"] = 0.05

        mock_param = MagicMock()
        mock_param.getValue.return_value = 0.01

        with patch.object(pm, 'create_ini', return_value=True), \
             patch('pyopenms.Param', return_value=mock_param), \
             patch('pyopenms.ParamXMLFile'):
            pm.save_parameters()

        # Verify that param.getValue was called with the REAL tool name key
        # (IDFilter:1:score:pep), not the instance name key (IDFilter_step1:1:score:pep)
        mock_param.getValue.assert_called_with(b"IDFilter:1:score:pep")

    def test_save_parameters_display_keys_skipped_with_instance_name(self, temp_workflow_dir):
        """Test that _display keys are still skipped when using instance names."""
        pm = ParameterManager(temp_workflow_dir)

        ini_path = temp_workflow_dir / "ini" / "IDFilter.ini"
        ini_path.touch()

        mock_streamlit.session_state["_topp_tool_instance_map"] = {
            "IDFilter_step1": "IDFilter"
        }
        mock_streamlit.session_state[f"{pm.topp_param_prefix}IDFilter_step1:1:score:pep"] = 0.05
        mock_streamlit.session_state[f"{pm.topp_param_prefix}IDFilter_step1:1:score:pep_display"] = ["0.05"]

        mock_param = MagicMock()
        mock_param.getValue.return_value = 0.01

        with patch.object(pm, 'create_ini', return_value=True), \
             patch('pyopenms.Param', return_value=mock_param), \
             patch('pyopenms.ParamXMLFile'):
            pm.save_parameters()

        with open(pm.params_file, "r") as f:
            saved = json.load(f)

        # _display key should not be stored
        assert "score:pep_display" not in saved.get("IDFilter_step1", {})
        assert "score:pep" in saved.get("IDFilter_step1", {})


class TestGetToppParametersWithInstanceName:
    """Tests for get_topp_parameters with tool_instance_name."""

    def test_get_topp_parameters_with_instance_name(self, temp_workflow_dir):
        """Test that get_topp_parameters uses instance name for JSON lookup."""
        pm = ParameterManager(temp_workflow_dir)

        # Create params.json with instance-keyed parameters
        params = {
            "IDFilter_step1": {
                "score:pep": 0.05
            }
        }
        with open(pm.params_file, "w") as f:
            json.dump(params, f)

        # Create a mock ini file
        ini_path = temp_workflow_dir / "ini" / "IDFilter.ini"
        ini_path.touch()

        mock_param = MagicMock()
        mock_param.keys.return_value = [b"IDFilter:1:score:pep"]
        mock_param.getValue.return_value = 0.01  # default

        with patch('pyopenms.Param', return_value=mock_param), \
             patch('pyopenms.ParamXMLFile'):
            result = pm.get_topp_parameters("IDFilter", tool_instance_name="IDFilter_step1")

        # Should return the instance-specific value
        assert result["score:pep"] == 0.05

    def test_get_topp_parameters_without_instance_name_backward_compat(self, temp_workflow_dir):
        """Test that get_topp_parameters works without instance name (backward compat)."""
        pm = ParameterManager(temp_workflow_dir)

        params = {
            "IDFilter": {
                "score:pep": 0.05
            }
        }
        with open(pm.params_file, "w") as f:
            json.dump(params, f)

        ini_path = temp_workflow_dir / "ini" / "IDFilter.ini"
        ini_path.touch()

        mock_param = MagicMock()
        mock_param.keys.return_value = [b"IDFilter:1:score:pep"]
        mock_param.getValue.return_value = 0.01

        with patch('pyopenms.Param', return_value=mock_param), \
             patch('pyopenms.ParamXMLFile'):
            result = pm.get_topp_parameters("IDFilter")

        assert result["score:pep"] == 0.05
