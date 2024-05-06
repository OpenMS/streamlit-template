import json
import sys

############################
# default paramter values #
###########################
#
# Mandatory keys for each parameter
# key: a unique identifier
# value: the default value
#
# Optional keys for each parameter
# name: the name of the parameter
# hide: don't show the parameter in the parameter section (e.g. for input/output files)
# options: a list of valid options for the parameter
# min: the minimum value for the parameter (int and float)
# max: the maximum value for the parameter (int and float)
# step_size: the step size for the parameter (int and float)
# help: a description of the parameter
# widget_type: the type of widget to use for the parameter (default: auto)
# advanced: whether or not the parameter is advanced (default: False)

DEFAULTS = [
    {"key": "in", "value": [], "help": "Input files for Python Script.", "hide": True},
    {"key": "out", "value": [], "help": "Output files for Python Script.", "hide": True},
    {
        "key": "number-slider",
        "name": "number of features",
        "value": 6,
        "min": 2,
        "max": 10,
        "help": "How many features to consider.",
        "widget_type": "slider",
        "step_size": 2,
    },
    {
        "key": "selectbox-example",
        "value": "a",
        "options": ["a", "b", "c"],
    },
    {
        "key": "adavanced-input",
        "value": 5,
        "step_size": 5,
        "help": "An advanced example parameter.",
        "advanced": True,
    },
    {
        "key": "checkbox", "value": True
    }
]

def get_params():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r") as f:
            return json.load(f)
    else:
        return {}

if __name__ == "__main__":
    params = get_params()
    # Add code here:
    print("Writing stdout which will get logged...")
    print("Parameters for this example Python tool:")
    print(json.dumps(params, indent=4))