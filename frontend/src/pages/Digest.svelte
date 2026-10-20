<script lang="ts">
  // content/digest.py: in silico protein digest with pyOpenMS ProteaseDigestion.
  import { api } from "../lib/api";
  import StaticTable from "../lib/components/StaticTable.svelte";

  const EXAMPLE = `>sp|P02769|ALBU_BOVIN Albumin OS=Bos taurus OX=9913 GN=ALB PE=1 SV=4
MKWVTFISLLLLFSSAYSRGVFRRDTHKSEIAHRFKDLGEEHFKGLVLIAFSQYLQQCPFDEHVKLVNELTEFAKTCVADESHAGCEKSLHTLFGDELCKVASLRETYGDMADCCEKQEPERNECFLSHKDDSPDLPKLKPDPNTLCDEFKADEKKFWGKYLYEIARRHPYFYAPELLYYANKYNGVFQECCQAEDKGACLLPKIETMREKVLASSARQRLRCASIQKFGERALKAWSVARLSQKFPKAEFVEVTKLVTDLTKVHKECCHGDLLECADDRADLAKYICDNQDTISSKLKECCDKPLLEKSHCIAEVEKDAIPENLPPLTADFAEDKDVCKNYQEAKDAFLGSFLYEYSRRHPEYAVSVLLRLAKEYEATLEECCAKDDPHACYSTVFDKLKHLVDEPQNLIKQNCDQFEKLGEYGFQNALIVRYTRKVPQVSTPTLVEVSRSLGKVGTRCCTKPESERMPCTEDYLSLILNRLCVLHEKTPVSEKVTKCCTESLVNRRPCFSALTPDETYVPKAFDEKLFTFHADICTLPDTEKQIKKQTALVELLKHKPKATEEQLKTVMENFVAFVDKCCAADDKEACFAVEGPKLVVSTQTALA`;

  let fasta = $state("");
  let enzymes = $state<string[]>([]);
  let enzyme = $state("Trypsin");
  let missed = $state(2);
  let maxCharges = $state(4);
  let minLen = $state(6);
  let maxLen = $state(50);
  let result = $state<any>(null);
  let error = $state("");
  let busy = $state(false);

  api.get<string[]>("/tools/enzymes").then((e) => (enzymes = e)).catch((e) => (error = e.message));

  async function run() {
    busy = true;
    try {
      result = await api.post("/tools/digest", { fasta, enzyme, missed_cleavages: missed, max_charges: maxCharges, min_length: minLen, max_length: maxLen });
      error = "";
    } catch (e: any) {
      error = e.message;
      result = null;
    } finally {
      busy = false;
    }
  }

  function shade(n: number, max: number) {
    if (!n) return "transparent";
    return `color-mix(in srgb, var(--accent) ${Math.round(20 + (60 * n) / Math.max(1, max))}%, transparent)`;
  }
</script>

<div class="flex max-w-6xl flex-col gap-4">
  <div>
    <h1 class="h1">✂️ In Silico Protein Digest</h1>
    <p class="muted">Digest protein sequences with a protease and list the resulting peptides with their masses.</p>
  </div>
  <div class="card flex flex-col gap-3">
    <label>
      <span class="label">FASTA sequences</span>
      <textarea class="input font-mono" rows="7" bind:value={fasta} placeholder=">sp|P02769|ALBU_BOVIN Albumin ..."></textarea>
    </label>
    <div><button class="btn" onclick={() => (fasta = EXAMPLE)}>Load example (bovine serum albumin)</button></div>
    <div class="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <label><span class="label">Enzyme</span><select class="input" bind:value={enzyme}>{#each enzymes as e}<option>{e}</option>{/each}</select></label>
      <label><span class="label">Max missed cleavages</span><input class="input" type="number" min="0" max="10" bind:value={missed} /></label>
      <label><span class="label">Max charge states</span><input class="input" type="number" min="1" max="10" bind:value={maxCharges} /></label>
      <label><span class="label">Min peptide length</span><input class="input" type="number" min="1" bind:value={minLen} /></label>
      <label><span class="label">Max peptide length</span><input class="input" type="number" min="1" bind:value={maxLen} /></label>
    </div>
    <div><button class="btn btn-primary" disabled={busy || !fasta.trim()} onclick={run}>🧬 Digest proteins</button></div>
  </div>
  {#if error}<div class="alert alert-error">{error}</div>{/if}
  {#if result}
    {#if !result.table.rows.length}
      <div class="alert alert-warning">No peptides were generated, or all were filtered out. Try other parameters.</div>
    {:else}
      <div class="alert alert-success">Parsed {result.n_sequences} protein sequence(s).</div>
      <div class="grid gap-3 sm:grid-cols-4">
        <div class="card"><div class="text-sm muted">Total peptides</div><div class="text-xl font-semibold">{result.stats.total_peptides.toLocaleString()}</div></div>
        <div class="card"><div class="text-sm muted">Unique proteins</div><div class="text-xl font-semibold">{result.stats.unique_proteins}</div></div>
        <div class="card"><div class="text-sm muted">Avg length</div><div class="text-xl font-semibold">{result.stats.avg_peptide_length.toFixed(1)} AA</div></div>
        <div class="card"><div class="text-sm muted">Mass range</div><div class="text-xl font-semibold">{result.stats.mass_range[0].toFixed(0)}–{result.stats.mass_range[1].toFixed(0)} Da</div></div>
      </div>
      <StaticTable columns={result.table.columns} rows={result.table.rows} filename="digest-{enzyme}" />
      <h2 class="h2">🎨 Protein coverage</h2>
      <p class="text-sm muted">Darker residues are covered by more peptides.</p>
      {#each Object.entries(result.coverage) as entry}
        {@const acc = entry[0]}
        {@const info = entry[1] as any}
        {@const max = Math.max(...info.coverage)}
        <div class="card">
          <div class="mb-1 font-semibold">{acc} <span class="text-sm font-normal muted">{info.description}</span>
            <span class="text-sm font-normal muted">· {((100 * info.coverage.filter((c: number) => c > 0).length) / info.coverage.length).toFixed(1)} % covered</span></div>
          <div class="break-all font-mono text-sm leading-6">
            {#each info.sequence.split("") as aa, i}<span title="position {i + 1}: {info.coverage[i]} peptide(s)" style="background: {shade(info.coverage[i], max)}">{aa}</span>{/each}
          </div>
        </div>
      {/each}
    {/if}
  {/if}
</div>
