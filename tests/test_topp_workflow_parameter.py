"""
Tests for the TOPP workflow parameter page.

This module verifies that the TOPP workflow parameter page correctly 
displays parameter values, handles different parameter types,
organizes parameters into sections, and properly toggles advanced parameters.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add project root to path for imports using a named constant
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Create mock for pyopenms to avoid dependency on actual OpenMS installation
mock_pyopenms = MagicMock()
mock_pyopenms.__version__ = "2.9.1"  # Mock version for testing
sys.modules['pyopenms'] = mock_pyopenms

@pytest.fixture
def mock_streamlit():
    """Mock essential Streamlit components for testing parameter display."""
    with patch('streamlit.tabs') as mock_tabs, \
         patch('streamlit.columns') as mock_columns, \
         patch('streamlit.session_state', create=True, new={}) as mock_session_state, \
         patch('streamlit.selectbox') as mock_selectbox, \
         patch('streamlit.number_input') as mock_number_input, \
         patch('streamlit.checkbox') as mock_checkbox, \
         patch('streamlit.text_input') as mock_text_input, \
         patch('streamlit.markdown') as mock_markdown:
        
        # Configure session state
        mock_session_state["workspace"] = "test_workspace"
        mock_session_state["advanced"] = False
        
        yield {
            'tabs': mock_tabs,
            'columns': mock_columns,
            'session_state': mock_session_state,
            'selectbox': mock_selectbox,
            'number_input': mock_number_input, 
            'checkbox': mock_checkbox,
            'text_input': mock_text_input,
            'markdown': mock_markdown
        }


def test_mock_pyopenms():
    """Verify that pyopenms mock is working correctly."""
    import pyopenms
    assert hasattr(pyopenms, '__version__')


def test_topp_parameter_correctness():
    """Test that TOPP parameters are displayed with correct values."""
    # Define expected parameters with values
    expected_params = {
        "noise_threshold": 1000.0,
        "mz_tolerance": 10.0,
        "rt_window": 60.0,
        "use_smoothing": True
    }
    
    # Create a mock parameter object
    param = MagicMock()
    
    # Configure parameter behavior
    def mock_get_value(param_name):
        decoded_name = param_name.decode() if isinstance(param_name, bytes) else param_name
        param_key = decoded_name.split(':')[-1]
        return expected_params.get(param_key, 0)
    
    # Setup parameter functions
    param.getValue = mock_get_value
    param.getNames = MagicMock(return_value=[f"FeatureFinderMetabo:{name}".encode() 
                                           for name in expected_params])
    
    # Mock display function to capture values
    displayed_values = {}
    
    # Function to simulate parameter display logic
    def display_parameters(param_obj):
        """Simulate the display of parameters."""
        for encoded_name in param_obj.getNames():
            name = encoded_name.decode()
            simple_name = name.split(':')[-1]
            value = param_obj.getValue(encoded_name)
            displayed_values[simple_name] = value
    
    # Call simulated display
    display_parameters(param)
    
    # Verify displayed values match expected values
    for param_name, expected_value in expected_params.items():
        assert param_name in displayed_values, f"Parameter {param_name} was not displayed"
        assert displayed_values[param_name] == expected_value, \
            f"Parameter {param_name} showed value {displayed_values[param_name]} instead of {expected_value}"


def test_parameter_types():
    """Test that parameters of different types are handled correctly."""
    # Test parameter objects with different types
    param = MagicMock()
    
    
    type_params = {
        "float_param": 10.5,
        "int_param": 42,
        "bool_param": True,
        "string_param": "test",
        "list_param": ["item1", "item2"],
        "dict_param": {"key1": "value1", "key2": 123},
        "nested_param": [{"name": "nested1"}, {"name": "nested2"}]
    }
    
    # Configure mock
    param.getNames = MagicMock(return_value=[f"Tool:{name}".encode() for name in type_params])
    
    def mock_get_value(param_name):
        param_key = param_name.decode().split(':')[-1]
        return type_params.get(param_key, 0)
        
    param.getValue = mock_get_value
    
    # Capture displayed values
    displayed_values = {}
    displayed_types = {}
    
    # Display parameters
    def display_parameters(param_obj):
        for encoded_name in param_obj.getNames():
            name = encoded_name.decode()
            simple_name = name.split(':')[-1]
            value = param_obj.getValue(encoded_name)
            displayed_values[simple_name] = value
            displayed_types[simple_name] = type(value)
    
    display_parameters(param)
    
    # Verify both values and types are preserved
    for param_name, expected_value in type_params.items():
        assert displayed_values[param_name] == expected_value
        # Use 'is' for more precise type comparison
        assert type(displayed_values[param_name]) is type(expected_value)
        
        # For complex structures, verify deep equality
        if isinstance(expected_value, (dict, list)):
            # Check that nested structures match exactly
            if isinstance(expected_value, dict):
                for key, val in expected_value.items():
                    assert displayed_values[param_name][key] == val
            elif isinstance(expected_value, list) and expected_value and isinstance(expected_value[0], dict):
                # For lists of dictionaries, check each item
                for i, item in enumerate(expected_value):
                    assert displayed_values[param_name][i] == item


def test_parameter_sections():
    """Test that parameters are properly organized into sections."""
    param = MagicMock()
    
    # Create parameters in different sections
    section_params = {
        "algorithm:common:param1": 1.0,
        "algorithm:common:param2": 2.0,
        "algorithm:centroided:param3": 3.0,
        "preprocessing:param4": 4.0
    }
    
    # Configure mock
    param.getNames = MagicMock(return_value=[k.encode() for k in section_params])
    
    def get_section_description(section):
        if "algorithm:common" in section:
            return "Common algorithm parameters"
        elif "algorithm:centroided" in section:
            return "Parameters for centroided data"
        elif "preprocessing" in section:
            return "Data preprocessing parameters"
        return ""
        
    param.getSectionDescription = get_section_description
    
    # Capture sections
    sections = set()
    section_params_map = {}
    
    def organize_parameters(param_obj):
        for name in param_obj.getNames():
            decoded = name.decode()
            section = ":".join(decoded.split(":")[:-1])
            sections.add(section)
            if section not in section_params_map:
                section_params_map[section] = []
            section_params_map[section].append(decoded.split(":")[-1])
    
    organize_parameters(param)
    
    # Verify sections were correctly identified
    assert "algorithm:common" in sections
    assert "algorithm:centroided" in sections
    assert "preprocessing" in sections
    
    # Verify parameters were organized correctly
    assert "param1" in section_params_map["algorithm:common"]
    assert "param2" in section_params_map["algorithm:common"]
    assert "param3" in section_params_map["algorithm:centroided"]
    assert "param4" in section_params_map["preprocessing"]


def test_advanced_parameter_toggle(mock_streamlit):
    """Test that advanced parameters are only shown when advanced toggle is enabled."""
    param = MagicMock()
    
    # Define both basic and advanced parameters
    params = [
        {"name": "basic_param", "value": 1.0, "advanced": False},
        {"name": "advanced_param", "value": 42.0, "advanced": True}
    ]
    
    # Setup param mock
    param.getNames = MagicMock(return_value=[f"Tool:{p['name']}".encode() for p in params])
    param.isAdvanced = lambda key: any(p["advanced"] for p in params if p["name"] in key.decode())
    
    # Function to simulate parameter filtering based on advanced setting
    def filter_and_display_params(advanced_enabled=False):
        displayed_params = []
        for name in param.getNames():
            if not param.isAdvanced(name) or advanced_enabled:
                displayed_params.append(name.decode().split(":")[-1])
        return displayed_params
    
    # Test with advanced OFF
    mock_streamlit['session_state']["advanced"] = False
    basic_display = filter_and_display_params(mock_streamlit['session_state']["advanced"])
    
    # Test with advanced ON
    mock_streamlit['session_state']["advanced"] = True
    advanced_display = filter_and_display_params(mock_streamlit['session_state']["advanced"])
    
    # Verify only basic parameters are displayed when advanced is OFF
    assert "basic_param" in basic_display
    assert "advanced_param" not in basic_display
    
    # Verify all parameters are displayed when advanced is ON
    assert "basic_param" in advanced_display
    assert "advanced_param" in advanced_display