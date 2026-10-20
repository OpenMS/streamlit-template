<script lang="ts">
  // content/simple_workflow.py: tracked parameters and a quick computation
  // (a table of standard normal random numbers, as np.random.randn).
  import * as W from "../lib/backend/workspaces";
  import { app, store } from "../lib/state.svelte";
  import StaticTable from "../lib/components/StaticTable.svelte";

  let x = $state<number | null>(null);
  let y = $state<number | null>(null);
  let table = $state<{ columns: string[]; rows: number[][] } | null>(null);

  W.getParams(store, app.workspace).then((p) => {
    x = p["example-x-dimension"];
    y = p["example-y-dimension"];
  });

  const randn = () => Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random());

  $effect(() => {
    if (x === null || y === null || x < 1 || y < 1 || x > 20 || y > 20) return;
    W.putParams(store, app.workspace, { "example-x-dimension": x, "example-y-dimension": y });
    table = {
      columns: Array.from({ length: y }, (_, j) => String(j)),
      rows: Array.from({ length: x }, () => Array.from({ length: y as number }, randn)),
    };
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
