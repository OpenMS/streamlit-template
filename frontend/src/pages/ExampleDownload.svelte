<script lang="ts">
  // content/download_section.py: download or delete result sets.
  import { api, download, enc } from "../lib/api";
  import { app, toastError } from "../lib/state.svelte";

  const ws = `/ws/${enc(app.workspace)}`;
  let runs = $state<string[] | null>(null);
  api.get(`${ws}/example-workflow/results`).then((r) => (runs = r.runs));
</script>

<h1 class="h1">Download Results</h1>
{#if runs === null}
  <p class="muted">Loading…</p>
{:else if !runs.length}
  <div class="alert alert-error">No results to show yet. Please run a workflow first!</div>
{:else}
  <table class="max-w-2xl text-sm">
    <thead><tr><th class="px-2 py-1 text-left">Run</th><th></th><th></th></tr></thead>
    <tbody>
      {#each runs as run}
        <tr class="border-t" style="border-color: var(--border)">
          <td class="px-2 py-2">{run}</td>
          <td class="px-2"><button class="btn" onclick={() => download(`${ws}/example-workflow/results/${enc(run)}/zip`)}>Download ⬇️</button></td>
          <td class="px-2">
            <button class="btn btn-danger" onclick={async () => { if (confirm(`Delete ${run}?`)) runs = (await api.del(`${ws}/example-workflow/results/${enc(run)}`).catch(toastError))?.runs ?? runs; }}>🗑️ Delete</button>
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
