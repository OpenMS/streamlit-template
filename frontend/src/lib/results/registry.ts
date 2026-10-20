// Result components a workflow's ResultView can name (server/workflow_spec.py).
// A derived app adds its own Svelte components here.
import type { Component } from "svelte";
import TableView from "./TableView.svelte";
import ConsensusFeatures from "./ConsensusFeatures.svelte";

export const resultComponents: Record<string, Component<any>> = {
  table: TableView,
  "consensus-features": ConsensusFeatures,
};
