<script lang="ts">
  // content/isotope_pattern_generator.py
  import { engine } from "../lib/engine/client";
  import Plot from "../lib/components/Plot.svelte";
  import StaticTable from "../lib/components/StaticTable.svelte";

  const METHODS = [
    { id: "formula", label: "Elemental formula", placeholder: "C6H12O6", example: "C100H150N26O30S" },
    { id: "peptide", label: "Peptide / protein sequence", placeholder: "PEPTIDE", example: "PEPTIDEK" },
    { id: "mass", label: "Mass (averagine)", placeholder: "1500", example: "2500" },
  ];
  let method = $state<"formula" | "peptide" | "mass">("formula");
  let value = $state("C100H150N26O30S");
  let fine = $state(false);
  let result = $state<any>(null);
  let error = $state("");

  const m = $derived(METHODS.find((x) => x.id === method)!);
  const peaks = $derived(
    result ? result.mzs.map((mz: number, i: number) => [mz, result.intensities[i]]).filter((p: number[]) => p[1] > 1e-6) : [],
  );

  async function run() {
    try {
      result = await engine.call("toolbox.isotopePattern", { method, value, fine });
      error = "";
    } catch (e: any) {
      error = e.message;
      result = null;
    }
  }
</script>

<div class="flex max-w-5xl flex-col gap-4">
  <div>
    <h1 class="h1">📶 Isotopic Pattern Calculator</h1>
    <p class="muted">Isotopic distributions from a formula, a sequence or a mass, computed with OpenMS.</p>
  </div>
  <div class="card grid gap-3 md:grid-cols-[14rem_1fr_auto_auto] md:items-end">
    <label><span class="label">Input method</span>
      <select class="input" bind:value={method} onchange={() => (value = m.example)}>{#each METHODS as x}<option value={x.id}>{x.label}</option>{/each}</select>
    </label>
    <label><span class="label">{m.label}</span><input class="input font-mono" bind:value={value} placeholder={m.placeholder} onkeydown={(e) => e.key === "Enter" && run()} /></label>
    {#if method !== "mass"}
      <label class="flex items-center gap-2 pb-2 text-sm" title="FineIsotopePatternGenerator resolves isotopic fine structure"><input type="checkbox" bind:checked={fine} /> Fine structure</label>
    {:else}<span></span>{/if}
    <button class="btn btn-primary" onclick={run}>Calculate</button>
  </div>
  {#if error}<div class="alert alert-error">{error}</div>{/if}
  {#if result}
    <div class="grid gap-3 sm:grid-cols-3">
      <div class="card"><div class="text-sm muted">Monoisotopic mass</div><div class="text-xl font-semibold">{result.monoisotopic_mass?.toFixed(5)} Da</div></div>
      <div class="card"><div class="text-sm muted">Average mass</div><div class="text-xl font-semibold">{result.average_mass?.toFixed(5)} Da</div></div>
      <div class="card"><div class="text-sm muted">Formula</div><div class="text-xl font-semibold">{result.formula ?? "–"}</div></div>
    </div>
    <Plot
      filename="isotope-pattern"
      data={[{ type: "bar", x: peaks.map((p: number[]) => p[0]), y: peaks.map((p: number[]) => p[1] * 100), width: fine ? 0.002 : 0.05, hovertemplate: "m/z %{x:.5f}<br>%{y:.2f} %<extra></extra>" }]}
      layout={{ title: { text: result.source_type }, xaxis: { title: { text: "m/z" } }, yaxis: { title: { text: "relative intensity (%)" } } }}
    />
    <StaticTable columns={["m/z", "relative intensity (%)"]} rows={peaks.map((p: number[]) => [Number(p[0].toFixed(6)), Number((p[1] * 100).toFixed(4))])} filename="isotope-pattern" />
  {/if}
</div>
