import sys
import os
from pathlib import Path

# Dynamically add the src folder to sys.path so Python can find it
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

# Now import ParameterManager from the correct module
from workflow.ParameterManager import ParameterManager  

# Create ParameterManager instance
pm = ParameterManager(workflow_dir=Path("./workflow"))

# Path to a sample INI file (Modify if needed)
ini_file_path = "workflow/test.ini"

# Check if the INI file exists before loading
if not Path(ini_file_path).exists():
    print(f"⚠️ Warning: The INI file '{ini_file_path}' does not exist. Creating a sample one...")
    # Create a sample INI file with boolean and string parameters
    ini_content = """<?xml version="1.0" encoding="UTF-8"?>
<PARAMETERS version="2.0">
    <ITEM name="enable_feature" value="true" type="bool"/>
    <ITEM name="debug_mode" value="false" type="bool"/>
    <ITEM name="execution_mode" value="strict" type="string"/>
</PARAMETERS>
"""
    # Write to the file
    Path(ini_file_path).write_text(ini_content, encoding="utf-8")
    print(f"✅ Sample INI file created: {ini_file_path}")

# Test loading from an INI file
params = pm.load_parameters_from_ini(ini_file_path)

# Display the loaded parameters
print("\n✅ Loaded Parameters:")
for key, value in params.items():
    print(f"   - {key}: {value} (Type: {type(value).__name__})")

# Check if booleans are stored correctly
assert isinstance(params.get("enable_feature"), bool), "❌ enable_feature is not a boolean!"
assert isinstance(params.get("debug_mode"), bool), "❌ debug_mode is not a boolean!"
assert isinstance(params.get("execution_mode"), str), "❌ execution_mode is not a string!"

print("\n🎉 All tests passed! Boolean parameters are correctly handled!")
