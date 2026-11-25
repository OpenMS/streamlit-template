from src.common.common import page_setup
from src.Workflow import Workflow
from src.workflow import guide


params = page_setup()

wf = Workflow()

guide.page_intro(
    "Pick the MS data to analyse and say what to do with it. The steps below follow "
    "that choice; **Run analysis** at the bottom starts the run.",
    background=(
        "The example workflow detects features (the signals of one compound across "
        "the chromatographic peak) in each file with **FeatureFinderMetabo**, links "
        "the same feature across files with **FeatureLinkerUnlabeledKD**, and can "
        "run a custom Python step on the linked features. Each start is kept as its "
        "own run."
    ),
)

# Your analysis: the files, what to do with them, one sentence on what a start does
wf.analysis_section()

# The steps the analysis runs, one numbered tab each
wf.show_parameter_section()

guide.next_steps(
    wf,
    (guide.RUN, "Start the analysis with these settings."),
    (guide.EXPLORE, "Look at the results of earlier runs."),
)

# A bar at the bottom of the window: straight on to Run analysis, which
# starts the workflow at once
wf.show_run_button(summary=wf.summary())
