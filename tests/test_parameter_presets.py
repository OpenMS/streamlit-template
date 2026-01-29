"""
Tests for the parameter presets functionality.

This module verifies that the preset system correctly loads preset definitions,
retrieves preset names and descriptions, and applies presets to session state.
"""
import os
import sys
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Create mock for streamlit before importing ParameterManager
mock_streamlit = MagicMock()
mock_streamlit.session_state = {}
sys.modules['streamlit'] = mock_streamlit

# Create mock for pyopenms
mock_pyopenms = MagicMock()
mock_pyopenms.__version__ = "2.9.1"
sys.modules['pyopenms'] = mock_pyopenms

# Now import after mocks are set up
from src.workflow.ParameterManager import ParameterManager


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary workflow directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_dir = Path(tmpdir) / "test-workflow"
        workflow_dir.mkdir()
        ini_dir = workflow_dir / "ini"
        ini_dir.mkdir()
        yield workflow_dir


@pytest.fixture
def sample_presets():
    """Sample presets data for testing."""
    return {
        "test-workflow": {
            "Preset A": {
                "_description": "Description for Preset A",
                "ToolA": {
                    "param1": 10.0,
                    "param2": "value2"
                },
                "ToolB": {
                    "param3": 5
                }
            },
            "Preset B": {
                "_description": "Description for Preset B",
                "ToolA": {
                    "param1": 20.0
                },
                "_general": {
                    "general_param": "general_value"
                }
            },
            "Preset No Description": {
                "ToolA": {
                    "param1": 30.0
                }
            }
        },
        "other-workflow": {
            "Other Preset": {
                "_description": "This belongs to another workflow"
            }
        }
    }


@pytest.fixture(autouse=True)
def reset_streamlit_state():
    """Reset mock streamlit session state before each test."""
    mock_streamlit.session_state.clear()
    yield


@pytest.fixture
def temp_cwd():
    """Change to a temporary directory for tests that create files.

    This prevents tests from affecting the actual project root's presets.json.
    """
    original_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        yield tmpdir
        os.chdir(original_cwd)


class TestParameterManagerPresets:
    """Tests for ParameterManager preset methods."""

    def test_load_presets_returns_empty_when_file_missing(self, temp_workflow_dir, temp_cwd):
        """Test that load_presets returns empty dict when presets.json doesn't exist."""
        pm = ParameterManager(temp_workflow_dir)
        presets = pm.load_presets()
        assert presets == {}

    def test_load_presets_returns_workflow_presets(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that load_presets returns presets for the correct workflow."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)
        presets = pm.load_presets()

        assert "Preset A" in presets
        assert "Preset B" in presets
        assert "Other Preset" not in presets  # From different workflow

    def test_load_presets_handles_invalid_json(self, temp_workflow_dir, temp_cwd):
        """Test that load_presets handles malformed JSON gracefully."""
        with open("presets.json", "w") as f:
            f.write("{ invalid json }")

        pm = ParameterManager(temp_workflow_dir)
        presets = pm.load_presets()

        assert presets == {}

    def test_get_preset_names(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that get_preset_names returns correct list."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)
        names = pm.get_preset_names()

        assert "Preset A" in names
        assert "Preset B" in names
        assert "Preset No Description" in names
        assert "_description" not in names  # Special keys excluded

    def test_get_preset_names_empty_when_no_presets(self, temp_workflow_dir, temp_cwd):
        """Test that get_preset_names returns empty list when no presets exist."""
        pm = ParameterManager(temp_workflow_dir)
        names = pm.get_preset_names()
        assert names == []

    def test_get_preset_description(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that get_preset_description returns correct description."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)

        desc_a = pm.get_preset_description("Preset A")
        assert desc_a == "Description for Preset A"

        desc_b = pm.get_preset_description("Preset B")
        assert desc_b == "Description for Preset B"

    def test_get_preset_description_empty_when_missing(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that get_preset_description returns empty string when no description."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)
        desc = pm.get_preset_description("Preset No Description")

        assert desc == ""

    def test_get_preset_description_empty_for_nonexistent_preset(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that get_preset_description returns empty string for nonexistent preset."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)
        desc = pm.get_preset_description("Nonexistent Preset")

        assert desc == ""

    def test_apply_preset_deletes_session_state_keys(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that apply_preset deletes session_state keys instead of setting them."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)

        # Pre-populate session_state with old values
        mock_streamlit.session_state[f"{pm.topp_param_prefix}ToolA:1:param1"] = 999.0
        mock_streamlit.session_state[f"{pm.topp_param_prefix}ToolA:1:param2"] = "old_value"
        mock_streamlit.session_state[f"{pm.topp_param_prefix}ToolB:1:param3"] = 999

        result = pm.apply_preset("Preset A")

        assert result is True

        # Keys should be DELETED (not set to new values) so widgets re-initialize fresh
        assert f"{pm.topp_param_prefix}ToolA:1:param1" not in mock_streamlit.session_state
        assert f"{pm.topp_param_prefix}ToolA:1:param2" not in mock_streamlit.session_state
        assert f"{pm.topp_param_prefix}ToolB:1:param3" not in mock_streamlit.session_state

    def test_apply_preset_deletes_general_param_keys(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that apply_preset deletes _general parameter keys from session_state."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)

        # Pre-populate session_state with old value
        mock_streamlit.session_state[f"{pm.param_prefix}general_param"] = "old_value"

        result = pm.apply_preset("Preset B")

        assert result is True

        # Key should be DELETED so widget re-initializes fresh
        assert f"{pm.param_prefix}general_param" not in mock_streamlit.session_state

    def test_apply_preset_saves_to_params_file(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that apply_preset saves parameters to params.json."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)
        pm.apply_preset("Preset A")

        # Check params.json was created with correct content
        assert pm.params_file.exists()

        with open(pm.params_file, "r") as f:
            saved_params = json.load(f)

        assert "ToolA" in saved_params
        assert saved_params["ToolA"]["param1"] == 10.0
        assert saved_params["ToolA"]["param2"] == "value2"

    def test_apply_preset_returns_false_for_nonexistent(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that apply_preset returns False for nonexistent preset."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)
        result = pm.apply_preset("Nonexistent Preset")

        assert result is False

    def test_apply_preset_preserves_existing_params(self, temp_workflow_dir, sample_presets, temp_cwd):
        """Test that apply_preset preserves existing parameters not in the preset."""
        with open("presets.json", "w") as f:
            json.dump(sample_presets, f)

        pm = ParameterManager(temp_workflow_dir)

        # Create existing params
        existing_params = {
            "existing_param": "existing_value",
            "ToolA": {
                "existing_tool_param": "value"
            }
        }
        with open(pm.params_file, "w") as f:
            json.dump(existing_params, f)

        pm.apply_preset("Preset A")

        with open(pm.params_file, "r") as f:
            saved_params = json.load(f)

        # Existing params should be preserved
        assert saved_params["existing_param"] == "existing_value"
        # New params from preset should be added
        assert saved_params["ToolA"]["param1"] == 10.0

    def test_clear_parameter_session_state(self, temp_workflow_dir):
        """Test that clear_parameter_session_state removes all parameter keys."""
        pm = ParameterManager(temp_workflow_dir)

        # Add various keys to session_state
        mock_streamlit.session_state[f"{pm.param_prefix}param1"] = "value1"
        mock_streamlit.session_state[f"{pm.param_prefix}param2"] = "value2"
        mock_streamlit.session_state[f"{pm.topp_param_prefix}Tool:1:param"] = 10.0
        mock_streamlit.session_state["unrelated_key"] = "should_remain"

        pm.clear_parameter_session_state()

        # Parameter keys should be deleted
        assert f"{pm.param_prefix}param1" not in mock_streamlit.session_state
        assert f"{pm.param_prefix}param2" not in mock_streamlit.session_state
        assert f"{pm.topp_param_prefix}Tool:1:param" not in mock_streamlit.session_state

        # Unrelated keys should remain
        assert mock_streamlit.session_state["unrelated_key"] == "should_remain"

    def test_clear_parameter_session_state_empty(self, temp_workflow_dir):
        """Test that clear_parameter_session_state handles empty session_state."""
        pm = ParameterManager(temp_workflow_dir)

        # Should not raise even with no matching keys
        pm.clear_parameter_session_state()


class TestWorkflowNameParameter:
    """Tests for the workflow_name parameter in ParameterManager."""

    def test_workflow_name_defaults_to_directory_stem(self, temp_workflow_dir):
        """Test that workflow_name defaults to the directory stem when not provided."""
        pm = ParameterManager(temp_workflow_dir)
        assert pm.workflow_name == "test-workflow"

    def test_workflow_name_can_be_explicitly_set(self, temp_workflow_dir):
        """Test that workflow_name can be explicitly set."""
        pm = ParameterManager(temp_workflow_dir, workflow_name="My Custom Workflow")
        assert pm.workflow_name == "My Custom Workflow"

    def test_load_presets_normalizes_workflow_name(self, temp_workflow_dir, temp_cwd):
        """Test that load_presets normalizes the workflow name for lookup."""
        # Create presets with normalized key
        presets = {
            "my-custom-workflow": {
                "Test Preset": {
                    "_description": "A test preset"
                }
            }
        }
        with open("presets.json", "w") as f:
            json.dump(presets, f)

        # Pass workflow name with spaces and mixed case
        pm = ParameterManager(temp_workflow_dir, workflow_name="My Custom Workflow")
        preset_names = pm.get_preset_names()

        assert "Test Preset" in preset_names

    def test_load_presets_with_original_name_format(self, temp_workflow_dir, temp_cwd):
        """Test that presets can use the same format as WorkflowManager normalization."""
        # This simulates how WorkflowManager passes the name
        presets = {
            "topp-workflow": {
                "Preset X": {"_description": "Test"}
            }
        }
        with open("presets.json", "w") as f:
            json.dump(presets, f)

        # Simulating WorkflowManager passing "TOPP Workflow"
        pm = ParameterManager(temp_workflow_dir, workflow_name="TOPP Workflow")
        preset_names = pm.get_preset_names()

        assert "Preset X" in preset_names


class TestPresetsJsonFormat:
    """Tests for the presets.json format validation."""

    def test_presets_json_structure(self):
        """Test that the actual presets.json file has valid structure."""
        # Look for presets.json in the project root
        presets_path = Path(PROJECT_ROOT) / "presets.json"

        if not presets_path.exists():
            pytest.skip("presets.json not found in project root")

        with open(presets_path, "r") as f:
            presets = json.load(f)

        assert isinstance(presets, dict)

        for workflow_name, workflow_presets in presets.items():
            assert isinstance(workflow_name, str)
            assert isinstance(workflow_presets, dict)

            for preset_name, preset_config in workflow_presets.items():
                assert isinstance(preset_name, str)
                assert isinstance(preset_config, dict)

                for key, value in preset_config.items():
                    # Keys should be strings
                    assert isinstance(key, str)
                    # Values should be either strings (description), dicts (tool params), or primitives
                    if key == "_description":
                        assert isinstance(value, str)
                    elif key == "_general" or not key.startswith("_"):
                        if isinstance(value, dict):
                            # Tool parameters dict
                            for param_name, param_value in value.items():
                                assert isinstance(param_name, str)
