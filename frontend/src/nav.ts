// Page registry, the Svelte counterpart of the `pages` dict in app.py.
// A derived app edits this file: add, remove or reorder sections and pages.

import type { Component } from "svelte";

import Quickstart from "./pages/Quickstart.svelte";
import Documentation from "./pages/Documentation.svelte";
import Digest from "./pages/Digest.svelte";
import MzCalculator from "./pages/MzCalculator.svelte";
import IsotopePattern from "./pages/IsotopePattern.svelte";
import Fragmentation from "./pages/Fragmentation.svelte";
import WorkflowPage from "./pages/WorkflowPage.svelte";
import MzmlUpload from "./pages/MzmlUpload.svelte";
import MzmlViewer from "./pages/MzmlViewer.svelte";
import ExampleWorkflow from "./pages/ExampleWorkflow.svelte";
import ExampleDownload from "./pages/ExampleDownload.svelte";
import SimpleWorkflow from "./pages/SimpleWorkflow.svelte";
import RunSubprocess from "./pages/RunSubprocess.svelte";

export type Page = {
  route: string;
  title: string;
  icon: string;
  component: Component<any>;
  props?: Record<string, unknown>;
};

export type Section = { title: string; pages: Page[] };

/** The four (five) pages of a TOPP workflow, as in content/topp_workflow_*.py */
function workflowPages(slug: string): Page[] {
  return [
    { route: `${slug}/upload`, title: "File Upload", icon: "📁", component: WorkflowPage, props: { slug, section: "upload" } },
    { route: `${slug}/configure`, title: "Configure", icon: "⚙️", component: WorkflowPage, props: { slug, section: "configure" } },
    { route: `${slug}/run`, title: "Run", icon: "🚀", component: WorkflowPage, props: { slug, section: "run" } },
    { route: `${slug}/results`, title: "Results", icon: "📊", component: WorkflowPage, props: { slug, section: "results" } },
    { route: `${slug}/download`, title: "Download", icon: "⬇️", component: WorkflowPage, props: { slug, section: "download" } },
  ];
}

export function sections(appName: string): Section[] {
  return [
    {
      title: appName,
      pages: [
        { route: "quickstart", title: "Quickstart", icon: "👋", component: Quickstart },
        { route: "documentation", title: "Documentation", icon: "📖", component: Documentation },
      ],
    },
    {
      title: "pyOpenMS Toolbox",
      pages: [
        { route: "digest", title: "In Silico Digest", icon: "✂️", component: Digest },
        { route: "mz-calculator", title: "m/z Calculator", icon: "⚖️", component: MzCalculator },
        { route: "isotope-pattern", title: "Isotopic Pattern Calculator", icon: "📶", component: IsotopePattern },
        { route: "fragmentation", title: "Fragment Ion Generation", icon: "💥", component: Fragmentation },
      ],
    },
    { title: "TOPP Workflow Framework", pages: workflowPages("topp-workflow") },
    {
      title: "pyOpenMS Workflow",
      pages: [
        { route: "mzml/upload", title: "File Upload", icon: "📂", component: MzmlUpload },
        { route: "mzml/view", title: "View MS data", icon: "👀", component: MzmlViewer },
        { route: "mzml/workflow", title: "Run Workflow", icon: "⚙️", component: ExampleWorkflow },
        { route: "mzml/download", title: "Download Results", icon: "⬇️", component: ExampleDownload },
      ],
    },
    {
      title: "Others Topics",
      pages: [
        { route: "simple-workflow", title: "Simple Workflow", icon: "⚙️", component: SimpleWorkflow },
        { route: "run-subprocess", title: "Run Subprocess", icon: "🖥️", component: RunSubprocess },
      ],
    },
  ];
}
