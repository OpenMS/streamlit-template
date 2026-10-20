<script lang="ts">
  // content/peptide_mz_calculator.py
  import { api } from "../lib/api";
  import StaticTable from "../lib/components/StaticTable.svelte";

  let sequence = $state("PEPTIDE");
  let minCharge = $state(1);
  let maxCharge = $state(4);
  let result = $state<any>(null);
  let error = $state("");
  let busy = $state(false);

  const examples = ["PEPTIDE", "M(Oxidation)PEPTIDE", "C(Carbamidomethyl)PEPTIDE", ".(Acetyl)PEPTIDE", "PEPTIDE[+15.995]", "PEPS(Phospho)TIDE"];

  async function calc() {
    busy = true;
    try {
      result = await api.post("/tools/mz", { sequence, min_charge: minCharge, max_charge: maxCharge });
      error = "";
    } catch (e: any) {
      error = e.message;
      result = null;
    } finally {
      busy = false;
    }
  }
</script>

<div class="flex max-w-4xl flex-col gap-4">
  <div>
    <h1 class="h1">⚖️ Peptide m/z Calculator</h1>
    <p class="muted">Calculate theoretical mass-to-charge ratios (m/z) for peptides with and without modifications.</p>
  </div>
  <details class="card text-sm">
    <summary class="cursor-pointer font-semibold">📚 Sequence format</summary>
    <ul class="mt-2 list-disc pl-6">
      <li>Modifications in parentheses: <code>M(Oxidation)PEPTIDE</code>, <code>C(Carbamidomethyl)</code>, <code>(UNIMOD:4)</code></li>
      <li>Terminal modifications with dots: <code>.(Acetyl)PEPTIDE</code>, <code>PEPTIDE(Amidated).</code></li>
      <li>Mass deltas in square brackets: <code>PEPTIDE[+15.995]</code></li>
    </ul>
  </details>
  <div class="card grid gap-3 md:grid-cols-[1fr_8rem_8rem_auto] md:items-end">
    <label><span class="label">Peptide sequence</span><input class="input font-mono" bind:value={sequence} onkeydown={(e) => e.key === "Enter" && calc()} /></label>
    <label><span class="label">Min charge</span><input class="input" type="number" min="1" max="20" bind:value={minCharge} /></label>
    <label><span class="label">Max charge</span><input class="input" type="number" min="1" max="20" bind:value={maxCharge} /></label>
    <button class="btn btn-primary" disabled={busy || !sequence.trim()} onclick={calc}>Calculate</button>
  </div>
  <div class="flex flex-wrap gap-1 text-sm">
    <span class="muted">Examples:</span>
    {#each examples as ex}<button class="btn px-2 py-0.5 font-mono text-xs" onclick={() => ((sequence = ex), calc())}>{ex}</button>{/each}
  </div>
  {#if error}<div class="alert alert-error">{error}</div>{/if}
  {#if result}
    {@const first = Object.values(result.charge_results)[0] as any}
    <div class="grid gap-3 sm:grid-cols-3">
      <div class="card"><div class="text-sm muted">Monoisotopic mass</div><div class="text-xl font-semibold">{first.monoisotopic_mass.toFixed(6)} Da</div></div>
      <div class="card"><div class="text-sm muted">Molecular formula</div><div class="text-xl font-semibold">{first.molecular_formula}</div></div>
      <div class="card"><div class="text-sm muted">Length</div><div class="text-xl font-semibold">{first.sequence_length} AA</div></div>
    </div>
    <StaticTable
      columns={["Charge", "m/z"]}
      rows={Object.entries(result.charge_results).map(([z, r]: [string, any]) => [Number(z), Number(r.mz_ratio.toFixed(6))])}
      filename="peptide-mz"
    />
    {#if first.aa_composition}
      <div class="text-sm"><span class="font-semibold">Amino acid composition:</span>
        {Object.entries(first.aa_composition).map(([a, n]) => `${a}: ${n}`).join(", ")}</div>
    {/if}
  {/if}
</div>
