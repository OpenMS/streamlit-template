<script lang="ts">
  // The example workflow's results (src/Workflow.py results()): consensus
  // feature table; selected rows are plotted as grouped intensity bars.
  import { tablePage, tableRows } from "../backend/tables";
  import { join } from "../storage/store";
  import { store } from "../state.svelte";
  import Plot from "../components/Plot.svelte";
  import TableView from "./TableView.svelte";

  let { workflowDir, file }: { workflowDir: string; file: string } = $props();
  const path = $derived(join(workflowDir, file));

  let total = $state<number | null>(null);
  let missing = $state(false);
  let selected = $state<number[]>([]);
  let bars = $state<any[]>([]);

  $effect(() => {
    tablePage(store, path, { limit: 1 })
      .then((p) => (total = p.total))
      .catch(() => (missing = true));
  });

  $effect(() => {
    const rows = [...selected];
    if (!rows.length) {
      bars = [];
      return;
    }
    tableRows(store, path, rows).then((r) => {
      // metabolite, charge, rt, mz, quality, then one intensity column per file
      const samples = r.columns.slice(5);
      bars = r.rows.map((row: any[]) => ({ type: "bar", name: String(row[0]), x: samples, y: row.slice(5) }));
    });
  });
</script>

{#if missing}
  <div class="alert alert-warning">No consensus feature file found. Please run workflow first.</div>
{:else}
  {#if total !== null}
    <div class="mb-3">
      <div class="text-sm muted">number of consensus features</div>
      <div class="text-3xl font-semibold">{total.toLocaleString()}</div>
    </div>
  {/if}
  <div class="grid gap-4 xl:grid-cols-2">
    <TableView {workflowDir} {file} selectable bind:selected />
    <div>
      {#if bars.length}
        <Plot data={bars} layout={{ barmode: "group", yaxis: { title: { text: "intensity" } } }} filename="consensus-feature-intensities" />
      {:else}
        <div class="alert alert-info">💡 Select one or more rows in the table to show a barplot with intensities.</div>
      {/if}
    </div>
  </div>
{/if}
