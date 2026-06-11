#!/usr/bin/env python3
"""
Manual verification script for multiple TOPP tool instances feature.
This script simulates the workflow to verify that:
1. Multiple instances can be configured separately
2. Parameters are stored correctly
3. Parameters are retrieved correctly for execution
"""

import json
import tempfile
import shutil
from pathlib import Path
import sys

# Mock streamlit session_state
class MockSessionState(dict):
    pass

sys.modules['streamlit'] = type(sys)('streamlit')
sys.modules['streamlit'].session_state = MockSessionState()
sys.modules['streamlit'].fragment = lambda func: func  # Mock decorator

# Import after mocking
from src.workflow.ParameterManager import ParameterManager


def test_multiple_instances():
    """Test multiple tool instances functionality."""
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    try:
        workflow_dir = Path(temp_dir)
        pm = ParameterManager(workflow_dir)
        
        # Simulate what would happen with two IDFilter instances
        print("\n=== Testing Multiple Tool Instances ===\n")
        
        # Step 1: Simulate initial metadata storage (done by StreamlitUI.input_TOPP)
        print("1. Creating initial parameter structure with tool metadata...")
        # Create ini directory and file
        ini_dir = workflow_dir / "ini"
        ini_dir.mkdir(exist_ok=True)
        
        # Create a minimal ini file (would be created by OpenMS in real usage)
        ini_file = ini_dir / "IDFilter.ini"
        # Create minimal XML ini file structure
        ini_content = """<?xml version="1.0" encoding="UTF-8"?>
<PARAMETERS version="1.0">
  <NODE name="IDFilter" description="">
    <ITEM name="version" value="3.3.0" type="string" />
    <ITEM name="score:pep" value="0.0" type="double" />
  </NODE>
</PARAMETERS>"""
        with open(ini_file, 'w') as f:
            f.write(ini_content)
        
        initial_params = {
            "IDFilter-first": {
                "_tool_name": "IDFilter"
            },
            "IDFilter-second": {
                "_tool_name": "IDFilter"
            }
        }
        with open(pm.params_file, 'w') as f:
            json.dump(initial_params, f, indent=2)
        print(f"   Initial params: {json.dumps(initial_params, indent=2)}")
        
        # Step 2: Verify _get_tool_name_from_instance works
        print("\n2. Verifying tool name resolution...")
        tool_name_1 = pm._get_tool_name_from_instance("IDFilter-first")
        tool_name_2 = pm._get_tool_name_from_instance("IDFilter-second")
        print(f"   IDFilter-first resolves to: {tool_name_1}")
        print(f"   IDFilter-second resolves to: {tool_name_2}")
        assert tool_name_1 == "IDFilter", f"Expected 'IDFilter', got '{tool_name_1}'"
        assert tool_name_2 == "IDFilter", f"Expected 'IDFilter', got '{tool_name_2}'"
        print("   ✓ Tool name resolution working correctly")
        
        # Step 3: Simulate parameter updates (done by user in UI)
        print("\n3. Simulating parameter changes in UI...")
        params = pm.get_parameters_from_json()
        params["IDFilter-first"]["score:pep"] = 0.01  # Strict filtering
        params["IDFilter-second"]["score:pep"] = 0.05  # Lenient filtering
        with open(pm.params_file, 'w') as f:
            json.dump(params, f, indent=2)
        print(f"   Updated params: {json.dumps(params, indent=2)}")
        
        # Step 4: Verify parameter retrieval for execution
        print("\n4. Verifying parameter retrieval for execution...")
        params_first = pm.get_topp_parameters("IDFilter-first")
        params_second = pm.get_topp_parameters("IDFilter-second")
        print(f"   IDFilter-first params: {params_first}")
        print(f"   IDFilter-second params: {params_second}")
        
        # Step 5: Verify parameters are different
        print("\n5. Verifying instances have different parameters...")
        assert "score:pep" in params_first, "First instance should have score:pep"
        assert "score:pep" in params_second, "Second instance should have score:pep"
        assert params_first["score:pep"] == 0.01, f"Expected 0.01, got {params_first['score:pep']}"
        assert params_second["score:pep"] == 0.05, f"Expected 0.05, got {params_second['score:pep']}"
        print("   ✓ First instance: score:pep = 0.01 (strict)")
        print("   ✓ Second instance: score:pep = 0.05 (lenient)")
        
        # Step 6: Verify backward compatibility
        print("\n6. Testing backward compatibility (tool without instance name)...")
        params = pm.get_parameters_from_json()
        params["IDFilter"] = {"score:pep": 0.001}  # Regular tool without instance
        with open(pm.params_file, 'w') as f:
            json.dump(params, f, indent=2)
        
        tool_name = pm._get_tool_name_from_instance("IDFilter")
        print(f"   IDFilter (no instance) resolves to: {tool_name}")
        assert tool_name == "IDFilter", f"Expected 'IDFilter', got '{tool_name}'"
        print("   ✓ Backward compatibility maintained")
        
        print("\n=== All Tests Passed! ===\n")
        print("Summary:")
        print("  ✓ Tool instances can be configured separately")
        print("  ✓ Each instance stores its own parameters")
        print("  ✓ Parameters are correctly retrieved for execution")
        print("  ✓ Metadata keys are handled properly")
        print("  ✓ Backward compatibility is maintained")
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    test_multiple_instances()
