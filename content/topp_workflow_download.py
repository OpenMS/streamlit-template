from src.common.common import page_setup
from src.Workflow import Workflow
from src.workflow import guide


params = page_setup()

wf = Workflow()

guide.page_intro("Every run with its files, settings and processing report: rename a run, "
                 "take its files as a ZIP, or delete it.")

wf.show_results_download_section()

guide.next_steps(
    wf,
    (guide.EXPLORE, "Look at a run's results again."),
)
