import json
import sys
from pyopenms import ConsensusXMLFile, ConsensusMap
from pathlib import Path

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
    {"key": "in", "value": "", "help": "Input consensusXML file.", "hide": True},
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
    cm = ConsensusMap()
    ConsensusXMLFile().load(params["in"], cm)
    df = cm.get_df()
    df = df.rename(columns={col: Path(col).name for col in df.columns})
    df = df.reset_index()
    df = df.drop(columns=["id", "sequence"])
    df.insert(0, "metabolite", df.apply(lambda x: f"{round(x['mz'], 4)}@{round(x['rt'], 2)}", axis=1))
    df.to_csv(Path(params["in"]).with_suffix(".tsv"), sep="\t", index=False)