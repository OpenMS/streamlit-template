import sys
from pathlib import Path
import json

# Ensure the src directory is in the path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.workflow.ParameterManager import ParameterManager

# Initialize Parameter Manager
pm = ParameterManager(workflow_dir=Path("./workflow"))

#  Create a sample `params.json`
sample_params = {
    "enable_feature": True,
    "mode": "strict",
    "debug": False
}
with open(pm.params_file, "w", encoding="utf-8") as f:
    json.dump(sample_params, f, indent=4)

# Load the parameters
loaded_params = pm.get_parameters_from_json()

print("✅ Loaded Parameters:", json.dumps(loaded_params, indent=4))

# Validate the loaded parameters
assert loaded_params == sample_params, "❌ Parameters did NOT load correctly!"
print("🎯 All tests passed! Parameters load correctly from JSON.")
