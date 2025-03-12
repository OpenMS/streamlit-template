import sys
from pathlib import Path
import json

# Ensure the src directory is in the path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.workflow.ParameterManager import ParameterManager

# Initialize Parameter Manager
pm = ParameterManager(workflow_dir=Path("./workflow"))

#  Ensure params.json exists before reset
if pm.params_file.exists():
    print("✅ params.json exists before reset.")
else:
    print("⚠️ params.json does not exist before reset. Creating a sample one...")
    with open(pm.params_file, "w", encoding="utf-8") as f:
        json.dump({"sample_key": "sample_value"}, f, indent=4)

# Reset parameters
pm.reset_to_default_parameters()

# Check if params.json was deleted
assert not pm.params_file.exists(), "❌ params.json was NOT deleted!"
print("🎯 All tests passed! Reset functionality works correctly.")
