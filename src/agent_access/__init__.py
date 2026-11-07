"""Let AI assistants work in a workspace through the Model Context Protocol.

An assistant (Claude Desktop, Claude Code or any other MCP client) connects
to one workspace and can list the app's workflows and their settings, add
input files, start, follow and stop runs, and read their results, the same
things a person does on the workflow pages.

Two ways in, one set of tools (``tools.py``):

- Online, the workspace sync service serves MCP over Streamable HTTP at
  ``/sync/mcp`` (``src/sync/server.py``). The person creates a token in the
  sidebar (**AI assistant**), and the token decides the workspace.
- In the local app, ``python -m src.agent_access.stdio --workspace NAME``
  serves the same tools over stdio to an assistant on the same computer.

Everything here is importable without Streamlit except ``ui.py``: the tools
run in the sync service, which has no Streamlit session.
"""
