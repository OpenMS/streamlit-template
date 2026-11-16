from src.common.common import page_setup
from src.Workflow import Workflow
from src.workflow import guide


params = page_setup()

wf = Workflow()

guide.page_intro("The results of a run, arranged in views. Pick the run above the views; "
                 "✏️ arranges them, **+** makes a view of your own.")

wf.show_results_section()

guide.next_steps(
    wf,
    (guide.EXPORT, "Take the files of a run with you."),
    (guide.DESCRIBE, "Add files or change the settings for another run."),
)
