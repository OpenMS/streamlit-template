<script lang="ts">
  // One of the five pages of a TOPP workflow (content/topp_workflow_*.py).
  import { api, enc } from "../lib/api";
  import { app } from "../lib/state.svelte";
  import UploadSection from "../lib/workflow/UploadSection.svelte";
  import ConfigureSection from "../lib/workflow/ConfigureSection.svelte";
  import RunSection from "../lib/workflow/RunSection.svelte";
  import ResultsSection from "../lib/workflow/ResultsSection.svelte";
  import DownloadSection from "../lib/workflow/DownloadSection.svelte";

  let { slug, section }: { slug: string; section: "upload" | "configure" | "run" | "results" | "download" } = $props();

  const titles = { upload: "File Upload", configure: "Configure", run: "Run", results: "Results", download: "Download" };
  const spec = api.get(`/ws/${enc(app.workspace)}/wf/${slug}`);
</script>

{#await spec}
  <p class="muted">Loading…</p>
{:then spec}
  <div class="mb-4">
    <div class="text-sm muted">{spec.name}</div>
    <h1 class="h1">{titles[section]}</h1>
    {#if section === "upload" && spec.description}<p class="muted">{spec.description}</p>{/if}
  </div>
  {#if section === "upload"}
    <UploadSection {slug} {spec} />
  {:else if section === "configure"}
    <ConfigureSection {slug} {spec} />
  {:else if section === "run"}
    <RunSection {slug} />
  {:else if section === "results"}
    <ResultsSection {slug} {spec} />
  {:else}
    <DownloadSection {slug} />
  {/if}
{:catch e}
  <div class="alert alert-error">{e.message}</div>
{/await}
