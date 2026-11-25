from src.common.common import page_setup
from src.Workflow import Workflow
from src.workflow import guide


params = page_setup()

wf = Workflow()

guide.page_intro("The run started on **Describe experiment**: its progress, its log and, once it "
                 "is done, the report of what was done to each file.")

# A finished run links to Explore results (Workflow.results_page)
wf.show_execution_section()

guide.next_steps(
    wf,
    (guide.EXPLORE, "See the features of the finished run."),
    (guide.DESCRIBE, "Change the files or the settings and start again."),
)
