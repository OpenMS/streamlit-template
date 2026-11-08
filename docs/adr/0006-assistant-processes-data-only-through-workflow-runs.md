# The AI assistant processes data only through workflow runs

An AI assistant answering a question about a workspace processes data only by starting runs of the app's workflows: a baseline run, then follow-up runs that change settings, add an analysis, or add files or experiments. It runs no TOPP tool outside a workflow and no code of its own. What it hands the person is an assistant view, a layout of the workflow's own components with zoom, selection and annotations. The processing report therefore stays what it always was: the workflows and parameters that processed the data, the same for a person's runs and an assistant's.

## Considered Options

- **Single TOPP tools on the server, outside a workflow.** This was built and dropped. It created a second way of running things, with results on a page of their own and steps no person could rerun, extend or start from.
- **Code in the agent's own environment (pyOpenMS, pandas) on a run's result files.** This was rejected. Its results could be neither drawn by the workflow's components nor recorded as processing, so an answer would rest on steps the app cannot show. It was also more than an assistant needs to choose and present results.
