# Working with an AI assistant

An AI assistant that speaks the Model Context Protocol (MCP), such as Claude,
can work in your workspace: add input files, set up and start a workflow,
follow the run and read the results. Everything it does happens in the same
workspace you see in the browser, so you can open the workflow's pages at any
time and carry on where it stopped.

## Connect

Open **AI assistant** in the sidebar and click **Connect an AI assistant**.

- **Online**, click **Create connection**. You get the server address and a
  ready-made command or configuration for your assistant. The connection
  works for this workspace only and ends after a day; **Disconnect** in the
  sidebar ends it at once. Anyone who has it can add files to the workspace,
  run its workflows and read its results, so do not share it.
- **In the app on your computer**, your assistant starts the connection
  itself. Copy the command or the configuration into your assistant; no
  data leaves your computer.

With Claude Code, for example, paste the command into a terminal, start
Claude Code and ask it to "run the workflow on the example files and
summarize the results".

## What the assistant can do

| | |
|---|---|
| Look around | the app's workflows, their inputs, settings, presets and each tool's parameters |
| Add data | upload files, import from a link (PRIDE accessions, Zenodo, Figshare, S3 or Swift folders, OneDrive, any file URL), remove files |
| Run | change settings, apply presets, start a run with chosen files, follow it, read its log, stop it |
| Results | list runs and result files, read tables page by page, download files, read the processing report |
| Hand over | give you a link that opens the workspace on the configure, run or results page |

The sidebar panel lists what an assistant did lately. A run it starts shows on
the workflow's Run page like one you start yourself. Settings it changes show
on the configure page once you reload it.

## Limits

An assistant works only inside the workspace it is connected to. It can
neither run commands on the server nor read other workspaces. Uploads, the
workspace size and the run time have the same limits as in the browser; one
upload call takes up to 64 MB, so larger files are sent in parts or imported
from a link.

## For app developers

The tools are in `src/agent_access/` (`tools.py`, Streamlit-free). Online, the
workspace sync service answers MCP requests at `/sync/mcp` (Streamable HTTP,
JSON responses, no session), so any replica can serve any request and no new
deployment is needed. In the local app, `python -m src.agent_access.stdio`
serves the same tools over stdio.

`agent_access` in `settings.json`:

```json
"agent_access": {
    "enabled": true,
    "token_ttl_hours": 24,
    "calls_per_minute": 120,
    "max_upload_mb": 64,
    "max_import_gb": 20,
    "public_url": "",
    "workflows": {
        "topp-workflow": {
            "class": "src.Workflow:Workflow",
            "description": "What the workflow does, in one sentence.",
            "configure_page": "content/topp_workflow_parameter.py",
            "run_page": "content/topp_workflow_execution.py",
            "results_page": "content/topp_workflow_results.py"
        }
    }
}
```

- `workflows` lists what an assistant may run, by workflow folder. A value
  may also be just `"module:Class"`; without the key, `workspace_sync.workflows`
  is used. Inputs and their file types come from `app.yaml`.
- `configure_page` lets the assistant learn a workflow's defaults in a
  workspace that never showed the configure page: it is shown once, without a
  browser, and writes the settings as it does for a person.
- The pages give the links that `get_app_link`, `start_run` and
  `get_run_status` return.
- Tokens are stored hashed with the sync tokens, as `kind: agent`, and open
  only `/sync/mcp` and result downloads.
