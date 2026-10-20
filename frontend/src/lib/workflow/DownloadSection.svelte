<script lang="ts">
  // StreamlitUI.results_download_section: every result file, singly or as a
  // ZIP of the chosen folders.
  import { api, downloadPost, enc } from "../api";
  import { app, toastError } from "../state.svelte";
  import MultiSelect from "../components/MultiSelect.svelte";

  let { slug }: { slug: string } = $props();
  const base = $derived(`/ws/${enc(app.workspace)}/wf/${slug}`);

  let files = $state<any[] | null>(null);
  let chosen = $state<string[]>([]);
  let zipping = $state(false);

  api
    .get(`${base}/results/files`)
    .then((r) => {
      files = r.files;
      chosen = [...new Set<string>(r.files.map((f: any) => f.folder))];
    })
    .catch(toastError);

  const folders = $derived([...new Set<string>((files ?? []).map((f) => f.folder))].sort());

  async function zip() {
    zipping = true;
    try {
      await downloadPost(`${base}/results/zip`, { folders: chosen }, `${slug}-results.zip`);
    } catch (e) {
      toastError(e);
    } finally {
      zipping = false;
    }
  }
</script>

{#if files === null}
  <p class="muted">Loading…</p>
{:else if !files.length}
  <div class="alert alert-info">No results to download yet. Run the workflow first.</div>
{:else}
  <div class="flex flex-col gap-4">
    <div class="overflow-auto rounded-md border" style="border-color: var(--border)">
      <table class="w-full text-sm">
        <thead style="background: var(--panel)">
          <tr><th class="px-2 py-1 text-left">Folder</th><th class="px-2 py-1 text-left">File</th><th class="px-2 py-1 text-right">Size</th><th class="px-2 py-1 text-left">Modified</th><th></th></tr>
        </thead>
        <tbody>
          {#each files as f}
            <tr class="border-t" style="border-color: var(--border)">
              <td class="px-2 py-1">{f.folder}</td>
              <td class="px-2 py-1">{f.folder === "." ? f.path : f.path.slice(f.folder.length + 1)}</td>
              <td class="px-2 py-1 text-right">{f.size}</td>
              <td class="px-2 py-1">{f.modified}</td>
              <td class="px-2 py-1 text-right"><a class="btn" href={`/api${base}/results/file?path=${enc(f.path)}`} download>⬇️</a></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class="card flex max-w-md flex-col gap-2">
      <div class="font-semibold">ZIP archive</div>
      <MultiSelect label="Folders" options={folders.map((f) => ({ value: f, label: f }))} value={chosen} onchange={(v) => (chosen = v)} />
      <button class="btn btn-primary" disabled={!chosen.length || zipping} onclick={zip}>{zipping ? "Compressing…" : "📦 Download ZIP"}</button>
    </div>
  </div>
{/if}
