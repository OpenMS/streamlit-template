import sys
from pathlib import Path
import json

# Ensure the src directory is in the path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.workflow.ParameterManager import ParameterManager

# Initialize Parameter Manager
pm = ParameterManager(workflow_dir=Path("./workflow"))

#  Define sample parameters
sample_params = {
    "enable_feature": True,
    "mode": "strict",
    "debug": False
}

# Save parameters using the new direct method
pm.save_parameters_direct(sample_params)

#  Verify saved data
with open(pm.params_file, "r", encoding="utf-8") as f:
    loaded_params = json.load(f)

print(" Saved Parameters:", json.dumps(loaded_params, indent=4))

#  Debugging: Ensure 'enable_feature' is present
assert "enable_feature" in loaded_params, "❌ 'enable_feature' is missing in params.json!"
assert isinstance(loaded_params["enable_feature"], bool), "❌ enable_feature is not a boolean!"
print("🎯 All tests passed!")
