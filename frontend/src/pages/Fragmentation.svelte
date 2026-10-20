<script lang="ts">
  // content/fragmentation.py: theoretical fragment ions with TheoreticalSpectrumGenerator.
  import { engine } from "../lib/engine/client";
  import { ION_TYPES } from "../lib/engine/ops/toolbox";
  import Plot from "../lib/components/Plot.svelte";
  import StaticTable from "../lib/components/StaticTable.svelte";

  const COLORS: Record<string, string> = { a: "#FF6B6B", b: "#4ECDC4", c: "#45B7D1", x: "#96CEB4", y: "#E5B700", z: "#DDA0DD" };
  const ionTypes = ION_TYPES;
  let sequence = $state("PEPTIDE");
  let selected = $state<string[]>(["b", "y"]);
  let charges = $state<number[]>([1]);
  let result = $state<any>(null);
  let error = $state("");


  async function run() {
    try {
      result = await engine.call("toolbox.fragments", sequence, selected, charges);
      error = "";
    } catch (e: any) {
      error = e.message;
      result = null;
    }
  }

  const traces = $derived.by(() => {
    if (!result) return [];
    const cols: string[] = result.fragments.columns;
    const ix = (n: string) => cols.indexOf(n);
    const byType = new Map<string, any[]>();
    for (const r of result.fragments.rows) {
      const t = r[ix("ion_type")];
      if (!byType.has(t)) byType.set(t, []);
      byType.get(t)!.push(r);
    }
    return [...byType.entries()].map(([t, rows]) => ({
      type: "bar",
      name: `${t}-ions`,
      x: rows.map((r) => r[ix("mz")]),
      y: rows.map((r) => r[ix("intensity")]),
      text: rows.map((r) => r[ix("annotation")]),
      width: 1.5,
      marker: { color: COLORS[t] },
      hovertemplate: "%{text}<br>m/z %{x:.4f}<extra></extra>",
    }));
  });
</script>

<div class="flex max-w-5xl flex-col gap-4">
  <div>
    <h1 class="h1">💥 Fragment Ion Generation</h1>
    <p class="muted">Theoretical MS2 fragment ions of a peptide.</p>
  </div>
  <div class="card flex flex-col gap-3">
    <label><span class="label">Peptide sequence</span><input class="input font-mono" bind:value={sequence} onkeydown={(e) => e.key === "Enter" && run()} /></label>
    <div>
      <div class="label">Ion types</div>
      <div class="flex flex-wrap gap-3">
        {#each Object.entries(ionTypes) as [k, t]}
          <label class="flex items-center gap-1 text-sm" title={t.description}>
            <input type="checkbox" checked={selected.includes(k)} onchange={() => (selected = selected.includes(k) ? selected.filter((x) => x !== k) : [...selected, k])} />
            {t.name}
          </label>
        {/each}
      </div>
    </div>
    <div>
      <div class="label">Charge states</div>
      <div class="flex gap-3">
        {#each [1, 2, 3, 4] as z}
          <label class="flex items-center gap-1 text-sm"><input type="checkbox" checked={charges.includes(z)} onchange={() => (charges = charges.includes(z) ? charges.filter((x) => x !== z) : [...charges, z].sort())} /> {z}+</label>
        {/each}
      </div>
    </div>
    <div><button class="btn btn-primary" onclick={run}>Generate fragments</button></div>
  </div>
  {#if error}<div class="alert alert-error">{error}</div>{/if}
  {#if result}
    <Plot filename="fragment-ions" data={traces} layout={{ barmode: "overlay", xaxis: { title: { text: "m/z" } }, yaxis: { title: { text: "intensity" } } }} />
    <StaticTable columns={result.fragments.columns} rows={result.fragments.rows} filename="fragments-{result.sequence}" />
  {/if}
</div>
