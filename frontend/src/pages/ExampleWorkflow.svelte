<script lang="ts">
  // content/run_example_workflow.py: count spectra in the selected files.
  import * as W from "../lib/backend/workspaces";
  import { tablePage } from "../lib/backend/tables";
  import { engine } from "../lib/engine/client";
  import { join } from "../lib/storage/store";
  import { app, store, toast, toastError } from "../lib/state.svelte";
  import MultiSelect from "../lib/components/MultiSelect.svelte";
  import StaticTable from "../lib/components/StaticTable.svelte";

  let files = $state<string[]>([]);
  let selected = $state<string[]>([]);
  let runs = $state<string[]>([]);
  let run = $state("");
  let result = $state<any>(null);
  let busy = $state(false);

  W.mzmlFiles(store, app.workspace).then((fs) => (files = fs.map((f) => f.name)));
  W.getParams(store, app.workspace).then((p) => (selected = p["example-workflow-selected-mzML-files"] ?? []));
  const loadRuns = () =>
    W.exampleRuns(store, app.workspace).then((r) => {
      runs = r;
      run = runs[0] ?? "";
    });
  loadRuns();

  $effect(() => {
    if (run)
      tablePage(store, join(W.exampleRunDir(app.workspace, run), "result.tsv"), { limit: 1000 }).then(
        (t) => (result = { columns: t.columns.map((c) => c.name), rows: t.rows }),
      );
    else result = null;
  });

  async function start() {
    busy = true;
    try {
      await W.runExampleWorkflow(store, app.workspace, selected.filter((s) => files.includes(s)), (path) => engine.call("mzml.countSpectra", path));
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
    <p class="muted">A workflow with mzML files and an input form: reads each selected file with OpenMS and counts its spectra.</p>
  </div>
  <div class="card flex flex-col gap-3">
    <div class="label">Input mzML files</div>
    <MultiSelect label="input mzML files" options={files.map((f) => ({ value: f, label: f }))} value={selected} onchange={(v) => (selected = v)} />
    <div class="flex gap-2">
      <button class="btn" onclick={() => W.putParams(store, app.workspace, { "example-workflow-selected-mzML-files": selected }).then(() => toast("Parameters saved"))}>Save parameters</button>
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
