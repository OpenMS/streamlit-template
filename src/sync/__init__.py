"""Workspace sync between the offline (Electron) app and an online workspace.

The offline app pushes workflow inputs and parameters to a linked online
workspace and pulls workflow results back. Everything in this package is
importable without Streamlit: ``server`` runs as its own process next to the
Streamlit server, and ``client`` is driven from a background thread.
"""
