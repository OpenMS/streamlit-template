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
        "name": "select something",
        "value": "a",
        "options": ["a", "b", "c"],
    },
    {
        "key": "adavanced-input",
        "name": "advanced parameter",
        "value": 5,
        "step_size": 5,
        "help": "An advanced example parameter.",
        "advanced": True,
    },
    {
        "key": "checkbox", "value": True, "name": "boolean"
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
    # The example workflow passes the consensus feature table and asks for the
    # features with the highest mean intensity ("number of features" of them).
    if params.get("in") and params.get("out"):
        import pandas as pd

        df = pd.read_csv(params["in"][0], sep="\t")
        samples = [c for c in df.columns if c.lower().endswith(".mzml")]
        if samples:
            df.insert(1, "mean intensity", df[samples].mean(axis=1))
            df = df.sort_values("mean intensity", ascending=False)
        df.head(int(params.get("number-slider", 6))).to_csv(params["out"][0], sep="\t", index=False)