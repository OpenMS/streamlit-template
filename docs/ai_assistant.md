# Working with an AI assistant

Any AI assistant that speaks the Model Context Protocol (MCP), such as Claude,
can work in your workspace: add input files, set up and start a workflow,
follow the run and read the results. Everything it does happens in the same
workspace you see in the browser, so you can open the workflow's pages at any
time and carry on where it stopped.

The assistant sees each table and plot of a run's Results page the way you do.
It looks at all of them, talks the findings over with you in its own chat, and
opens in the app the view that shows what it is talking about.

For now this is a developer feature: the **AI assistant** panel shows once
developer mode is unlocked (⚙️ Settings, **Developer password**).

## Connect

Unlock developer mode, open **AI assistant** in the sidebar and click **Connect an AI assistant**.

- **Online**, click **Create connection**. You get the server address and a
  ready-made command or configuration for your assistant. The connection
  works for this workspace only and ends after a day; **Disconnect** in the
  sidebar ends it at once. Anyone who has it can add files to the workspace,
  run its workflows and read its results, so do not share it.
- **In the app on your computer**, your assistant starts the connection
  itself. Copy the command or the configuration into your assistant; no
  data leaves your computer.

**Claude Science** adds the app as a custom connector: in Claude Science open
**Settings > Connectors > Add connector** and copy the fields from the
**Claude Science** tab.

- Online, choose **Remote** and enter the name and the link. The link holds
  the connection, so keep it to yourself like the rest of the connection.
- In the app on your computer, choose **Local command** and enter the name,
  the command, and (under **Advanced settings**) the arguments and the
  environment variable. Claude Science runs a local connector in its
  sandbox; if the assistant reports that it cannot write to the workspace,
  give Claude Science read and write access to the workspace folder the tab
  names.

Claude Science asks before it uses each of the app's tools until you set them
to **Always allow** on the connector's page.

With Claude Code, for example, paste the command into a terminal, start
Claude Code and ask it to "run the workflow on the example files and
summarize the results".

## What the assistant can do

| | |
|---|---|
| Look around | the app's workflows, their inputs, settings, presets and each tool's parameters |
| Add data | upload files, import from a link (PRIDE accessions, Zenodo, Figshare, S3 or Swift folders, OneDrive, any file URL), remove files |
| Run | change settings, apply presets, start a run with chosen files, follow it, read its log, stop it |
| Look at results | every table and plot of a run's Results page as you see it: a table's size, columns, value ranges and first rows, a plot's axes and data (and the picture where the server can draw one), and what a plot shows for rows picked in a table |
| Result files | list runs and result files, read tables page by page, download files, read the processing report |
| Show you | save views of the Results page that show what its answer rests on (the tables and plots, up to five runs side by side or one below the other, what each opens zoomed to, selected and annotated, and up to five points of explanation), and open the configure, run or results page in the app you have open with a note on what to look at |
| Hand over | give you a link that opens the workspace on the configure, run or results page |

## Follow along

Keep the app open in the workspace while the assistant works. Whenever it has
something to show you (the settings it chose, the run it started, the result it
is talking about) the app opens that page by itself, picks that run and shows
the assistant's note.

The views an assistant saves for an answer are added to the Results page's
view bar with 🤖. Above its tables and plots a view shows your question and
the assistant's explanation, and each run it compares is drawn under its name.
The view opens with the zoom, selection and annotations the assistant chose;
↺ brings them back after you changed them. You cannot change an assistant's
view, but you can duplicate it (✏️, **Duplicate to edit**) or delete it. The
views of the newest answer are in the bar; those of earlier questions move to
**More**. An assistant changes or deletes only views it saved itself.
It shows only what the assistant decides to show; the
rest of its work stays out of your way. Turn **Follow the assistant** off in
the sidebar's **AI assistant** panel to keep the page you are on.

The sidebar panel lists what an assistant did lately. A run it starts is
started the way the Run button starts it, so it shows on the workflow's Run
page like one you start yourself, and its processing report records the files,
tools and settings of that run as for any other run. Settings it changes show
on the configure page once you reload it.

## Limits

An assistant works only inside the workspace it is connected to. It can
neither run commands on the server nor read other workspaces. Uploads, the
workspace size and the run time have the same limits as in the browser; one
upload call takes up to 64 MB, so larger files are sent in parts or imported
from a link.

Looking at the tables and plots needs a Results page built from components (see
below); for other workflows the assistant reads the result files. Without an
image engine on the server it sees at most 60 points per plot axis and the
first rows of a table, so for exact numbers it reads the result files.

## For app developers

The tools are in `src/agent_access/` (`tools.py`, Streamlit-free). Online, the
workspace sync service answers MCP requests at `/sync/mcp` (Streamable HTTP,
JSON responses, no session) and at `/sync/mcp/c/<token>`, the same with the
token in the link for clients that take a URL only (Claude Science's Remote
connectors; the access log leaves the token out), so any replica can serve any request and no new
deployment is needed. In the local app, `python -m src.agent_access.stdio`
serves the same tools over stdio.

`agent_access` in `settings.json`:

```json
"agent_access": {
    "enabled": true,
    "developer_only": true,
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
- `developer_only` (default `true`) shows the panel, and lets the app follow
  the assistant, only in a session that unlocked developer mode.
- A Results page built from components lets the assistant look at it:
  `COMPONENTS`, `PRESETS` and `renderers()` (name -> function that draws the
  component) on the workflow class, and optionally `ANALYSES`, `available()`
  and `RESULTS_LAYOUT` (the view file, default `layouts/results.json`), as in
  `src/Workflow.py`. `look_at_results` runs the renderers in a Streamlit test
  session in a process of its own and reports what they drew; components that
  only a browser draws (Insight components) are named with a pointer to the
  run's files. Plots come as pictures where plotly can write images (kaleido
  installed), else as their data.
- Tokens are stored hashed with the sync tokens, as `kind: agent`, and open
  only `/sync/mcp` and result downloads.
