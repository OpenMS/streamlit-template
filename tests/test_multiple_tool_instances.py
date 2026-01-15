"""
Tests for multiple TOPP tool instances functionality.

This module verifies that the same TOPP tool can be used multiple times
with different configurations using the tool_instance_name parameter.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import json
import tempfile
import shutil

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Create mock for pyopenms to avoid dependency on actual OpenMS installation
mock_pyopenms = MagicMock()
mock_pyopenms.__version__ = "2.9.1"
sys.modules['pyopenms'] = mock_pyopenms

from src.workflow.ParameterManager import ParameterManager


@pytest.fixture
def temp_workflow_dir():
    """Create a temporary workflow directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_streamlit_state():
    """Mock Streamlit session state."""
    return {}


def test_tool_instance_name_storage(temp_workflow_dir, mock_streamlit_state):
    """Test that tool instance names are correctly stored and retrieved."""
    with patch('streamlit.session_state', mock_streamlit_state):
        pm = ParameterManager(temp_workflow_dir)
        
        # Simulate storing parameters for two instances of the same tool
        workflow_stem = temp_workflow_dir.stem
        
        # First instance: IDFilter-first
        mock_streamlit_state[f"{workflow_stem}-TOPP-IDFilter-first:1:score:psm"] = 0.05
        
        # Second instance: IDFilter-second
        mock_streamlit_state[f"{workflow_stem}-TOPP-IDFilter-second:1:score:psm"] = 0.01
        
        # Create mock ini file
        ini_dir = temp_workflow_dir / "ini"
        ini_dir.mkdir(parents=True, exist_ok=True)
        (ini_dir / "IDFilter.ini").touch()
        
        # Mock pyopenms Param and ParamXMLFile
        mock_param = MagicMock()
        mock_param.keys.return_value = [
            b"IDFilter:1:score:psm"
        ]
        mock_param.getValue.return_value = 0.0  # Default value
        
        with patch('pyopenms.Param', return_value=mock_param):
            with patch('pyopenms.ParamXMLFile') as mock_xml:
                mock_xml_instance = MagicMock()
                mock_xml.return_value = mock_xml_instance
                
                # Save parameters
                pm.save_parameters()
        
        # Verify that parameters were saved correctly
        assert pm.params_file.exists()
        with open(pm.params_file, 'r') as f:
            saved_params = json.load(f)
        
        # Check that both instances are stored separately
        assert "IDFilter-first" in saved_params
        assert "IDFilter-second" in saved_params
        assert saved_params["IDFilter-first"]["score:psm"] == 0.05
        assert saved_params["IDFilter-second"]["score:psm"] == 0.01


def test_get_tool_name_from_instance(temp_workflow_dir):
    """Test that _get_tool_name_from_instance correctly resolves tool names."""
    pm = ParameterManager(temp_workflow_dir)
    
    # Create mock ini file
    ini_dir = temp_workflow_dir / "ini"
    ini_dir.mkdir(parents=True, exist_ok=True)
    (ini_dir / "IDFilter.ini").touch()
    
    # Test 1: Instance name is the tool name itself
    assert pm._get_tool_name_from_instance("IDFilter") == "IDFilter"
    
    # Test 2: Instance name with metadata in params file
    params_data = {
        "IDFilter-first": {
            "_tool_name": "IDFilter",
            "score:psm": 0.05
        }
    }
    with open(pm.params_file, 'w') as f:
        json.dump(params_data, f)
    
    assert pm._get_tool_name_from_instance("IDFilter-first") == "IDFilter"


def test_get_topp_parameters_with_instance(temp_workflow_dir):
    """Test that get_topp_parameters works with tool instances."""
    pm = ParameterManager(temp_workflow_dir)
    
    # Create mock ini file and params file
    ini_dir = temp_workflow_dir / "ini"
    ini_dir.mkdir(parents=True, exist_ok=True)
    (ini_dir / "IDFilter.ini").touch()
    
    # Create params file with two instances
    params_data = {
        "IDFilter-first": {
            "_tool_name": "IDFilter",
            "score:psm": 0.05
        },
        "IDFilter-second": {
            "_tool_name": "IDFilter",
            "score:psm": 0.01
        }
    }
    with open(pm.params_file, 'w') as f:
        json.dump(params_data, f)
    
    # Mock pyopenms
    mock_param = MagicMock()
    mock_param.keys.return_value = [
        b"IDFilter:1:score:psm"
    ]
    mock_param.getValue.return_value = 0.0  # Default value
    
    with patch('pyopenms.Param', return_value=mock_param):
        with patch('pyopenms.ParamXMLFile') as mock_xml:
            mock_xml_instance = MagicMock()
            mock_xml.return_value = mock_xml_instance
            
            # Get parameters for first instance
            params_first = pm.get_topp_parameters("IDFilter-first")
            assert params_first["score:psm"] == 0.05
            
            # Get parameters for second instance
            params_second = pm.get_topp_parameters("IDFilter-second")
            assert params_second["score:psm"] == 0.01


def test_backward_compatibility(temp_workflow_dir, mock_streamlit_state):
    """Test that existing code without tool_instance_name still works."""
    with patch('streamlit.session_state', mock_streamlit_state):
        pm = ParameterManager(temp_workflow_dir)
        
        # Simulate storing parameters for a tool without instance name
        workflow_stem = temp_workflow_dir.stem
        mock_streamlit_state[f"{workflow_stem}-TOPP-IDFilter:1:score:psm"] = 0.05
        
        # Create mock ini file
        ini_dir = temp_workflow_dir / "ini"
        ini_dir.mkdir(parents=True, exist_ok=True)
        (ini_dir / "IDFilter.ini").touch()
        
        # Mock pyopenms
        mock_param = MagicMock()
        mock_param.keys.return_value = [
            b"IDFilter:1:score:psm"
        ]
        mock_param.getValue.return_value = 0.0  # Default value
        
        with patch('pyopenms.Param', return_value=mock_param):
            with patch('pyopenms.ParamXMLFile') as mock_xml:
                mock_xml_instance = MagicMock()
                mock_xml.return_value = mock_xml_instance
                
                # Save parameters
                pm.save_parameters()
        
        # Verify parameters were saved under the tool name
        with open(pm.params_file, 'r') as f:
            saved_params = json.load(f)
        
        assert "IDFilter" in saved_params
        assert saved_params["IDFilter"]["score:psm"] == 0.05


def test_run_topp_with_instance_name():
    """Test that run_topp correctly uses tool_instance_name."""
    from src.workflow.CommandExecutor import CommandExecutor
    from src.workflow.Logger import Logger
    
    with tempfile.TemporaryDirectory() as temp_dir:
        workflow_dir = Path(temp_dir)
        (workflow_dir / "pids").mkdir(parents=True, exist_ok=True)
        (workflow_dir / "ini").mkdir(parents=True, exist_ok=True)
        (workflow_dir / "IDFilter.ini").touch()
        
        # Create mock parameter manager
        mock_pm = MagicMock()
        mock_pm.get_parameters_from_json.return_value = {
            "IDFilter-first": {
                "_tool_name": "IDFilter",
                "score:psm": 0.05
            },
            "IDFilter-second": {
                "_tool_name": "IDFilter",
                "score:psm": 0.01
            }
        }
        mock_pm.ini_dir = workflow_dir / "ini"
        
        # Create mock logger
        mock_logger = MagicMock()
        
        # Create executor
        executor = CommandExecutor(workflow_dir, mock_logger, mock_pm)
        
        # Mock run_command to capture the command
        captured_commands = []
        
        def mock_run_command(cmd):
            captured_commands.append(cmd)
        
        executor.run_command = mock_run_command
        
        # Test running with first instance
        executor.run_topp(
            "IDFilter",
            {"in": ["input.idXML"], "out": ["output.idXML"]},
            tool_instance_name="IDFilter-first"
        )
        
        # Verify command includes parameters from first instance
        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert "IDFilter" in cmd
        assert "-score:psm" in cmd
        assert "0.05" in cmd
        
        # Clear and test with second instance
        captured_commands.clear()
        executor.run_topp(
            "IDFilter",
            {"in": ["input.idXML"], "out": ["output.idXML"]},
            tool_instance_name="IDFilter-second"
        )
        
        # Verify command includes parameters from second instance
        assert len(captured_commands) == 1
        cmd = captured_commands[0]
        assert "IDFilter" in cmd
        assert "-score:psm" in cmd
        assert "0.01" in cmd
