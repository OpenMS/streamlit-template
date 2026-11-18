<script lang="ts">
  // content/download_section.py: download or delete result sets.
  import * as W from "../lib/backend/workspaces";
  import { saveBlob, zipDir } from "../lib/backend/files";
  import { app, store, toastError } from "../lib/state.svelte";

  let runs = $state<string[] | null>(null);
  const load = () => W.exampleRuns(store, app.workspace).then((r) => (runs = r));
  load();

  async function download(run: string) {
    try {
      saveBlob(await zipDir(store, W.exampleRunDir(app.workspace, run)), `${run}.zip`);
    } catch (e) {
      toastError(e);
    }
  }

  async function remove(run: string) {
    if (!confirm(`Delete ${run}?`)) return;
    await store.remove(W.exampleRunDir(app.workspace, run)).catch(toastError);
    await load();
  }
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
          <td class="px-2"><button class="btn" onclick={() => download(run)}>Download ⬇️</button></td>
          <td class="px-2"><button class="btn btn-danger" onclick={() => remove(run)}>🗑️ Delete</button></td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
