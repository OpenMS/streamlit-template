<script lang="ts">
  // content/simple_workflow.py: tracked parameters and a quick computation.
  import { api, enc } from "../lib/api";
  import { app } from "../lib/state.svelte";
  import StaticTable from "../lib/components/StaticTable.svelte";

  const ws = `/ws/${enc(app.workspace)}`;
  let x = $state<number | null>(null);
  let y = $state<number | null>(null);
  let table = $state<any>(null);

  api.get(`${ws}/params`).then((p) => {
    x = p["example-x-dimension"];
    y = p["example-y-dimension"];
  });

  $effect(() => {
    if (x === null || y === null || x < 1 || y < 1 || x > 20 || y > 20) return;
    api.put(`${ws}/params`, { values: { "example-x-dimension": x, "example-y-dimension": y } });
    api.get(`/simple-workflow?x=${x}&y=${y}`).then((t) => (table = t));
  });
</script>

<div class="flex max-w-3xl flex-col gap-4">
  <div>
    <h1 class="h1">Simple Workflow</h1>
    <p class="muted">Example for a simple workflow with quick execution times. The dimensions are saved in the workspace.</p>
  </div>
  <div class="flex gap-3">
    <label class="w-36"><span class="label">x dimension</span><input class="input" type="number" min="1" max="20" bind:value={x} /></label>
    <label class="w-36"><span class="label">y dimension</span><input class="input" type="number" min="1" max="20" bind:value={y} /></label>
  </div>
  {#if table}<StaticTable columns={table.columns} rows={table.rows} filename="random-table" />{/if}
</div>
