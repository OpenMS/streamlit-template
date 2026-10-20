<script lang="ts">
  // One of the five pages of a workflow (content/topp_workflow_*.py).
  import { getWorkflow } from "../workflows";
  import { workflowDir } from "../lib/backend/workflow";
  import { app } from "../lib/state.svelte";
  import UploadSection from "../lib/workflow/UploadSection.svelte";
  import ConfigureSection from "../lib/workflow/ConfigureSection.svelte";
  import RunSection from "../lib/workflow/RunSection.svelte";
  import ResultsSection from "../lib/workflow/ResultsSection.svelte";
  import DownloadSection from "../lib/workflow/DownloadSection.svelte";

  let { slug, section }: { slug: string; section: "upload" | "configure" | "run" | "results" | "download" } = $props();

  const titles = { upload: "File Upload", configure: "Configure", run: "Run", results: "Results", download: "Download" };
  const spec = $derived(getWorkflow(slug));
  const ws = $derived(app.workspace);
</script>

<div class="mb-4">
  <div class="text-sm muted">{spec.name}</div>
  <h1 class="h1">{titles[section]}</h1>
  {#if section === "upload" && spec.description}<p class="muted">{spec.description}</p>{/if}
</div>
{#if section === "upload"}
  <UploadSection {ws} {spec} />
{:else if section === "configure"}
  <ConfigureSection {ws} {spec} />
{:else if section === "run"}
  <RunSection {ws} {spec} />
{:else if section === "results"}
  <ResultsSection workflowDir={workflowDir(ws, spec)} {spec} />
{:else}
  <DownloadSection {ws} {spec} />
{/if}
