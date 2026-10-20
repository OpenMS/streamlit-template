<script lang="ts">
  // content/run_example_workflow.py: count spectra in the selected files.
  import { api, enc } from "../lib/api";
  import { app, toastError } from "../lib/state.svelte";
  import MultiSelect from "../lib/components/MultiSelect.svelte";
  import StaticTable from "../lib/components/StaticTable.svelte";

  const ws = `/ws/${enc(app.workspace)}`;
  let files = $state<string[]>([]);
  let selected = $state<string[]>([]);
  let runs = $state<string[]>([]);
  let run = $state("");
  let result = $state<any>(null);
  let busy = $state(false);

  api.get(`${ws}/mzml`).then((r) => (files = r.files.map((f: any) => f.name)));
  api.get(`${ws}/params`).then((p) => (selected = p["example-workflow-selected-mzML-files"] ?? []));
  const loadRuns = () => api.get(`${ws}/example-workflow/results`).then((r) => { runs = r.runs; run = runs[0] ?? ""; });
  loadRuns();

  $effect(() => {
    if (run) api.get(`${ws}/example-workflow/results/${enc(run)}`).then((r) => (result = r));
    else result = null;
  });

  async function start() {
    busy = true;
    try {
      await api.post(`${ws}/example-workflow`, { files: selected.filter((s) => files.includes(s)) });
      await loadRuns();
    } catch (e) {
      toastError(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="flex max-w-3xl flex-col gap-4">
  <div>
    <h1 class="h1">Workflow</h1>
    <p class="muted">A workflow with mzML files and an input form: reads each selected file with pyOpenMS and counts its spectra.</p>
  </div>
  <div class="card flex flex-col gap-3">
    <div class="label">Input mzML files</div>
    <MultiSelect label="input mzML files" options={files.map((f) => ({ value: f, label: f }))} value={selected} onchange={(v) => (selected = v)} />
    <div class="flex gap-2">
      <button class="btn" onclick={() => api.put(`${ws}/params`, { values: { "example-workflow-selected-mzML-files": selected } })}>Save parameters</button>
      <button class="btn btn-primary" disabled={busy || !selected.length} onclick={start}>{busy ? "Running…" : "Run workflow"}</button>
    </div>
  </div>
  {#if runs.length}
    <label class="max-w-sm"><span class="label">Result set</span>
      <select class="input" bind:value={run}>{#each runs as r}<option>{r}</option>{/each}</select>
    </label>
    {#if result}<StaticTable columns={result.columns} rows={result.rows} filename="result-{run}" />{/if}
  {:else}
    <div class="alert alert-info">No results to show yet. Please run a workflow first!</div>
  {/if}
</div>
