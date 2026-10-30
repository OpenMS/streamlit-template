<script lang="ts">
  // StreamlitUI.results_download_section: every result file, singly or as a
  // ZIP of the chosen folders.
  import * as WF from "../backend/workflow";
  import { humanSize, saveBlob, saveFile } from "../backend/files";
  import { join } from "../storage/store";
  import { store, toastError } from "../state.svelte";
  import MultiSelect from "../components/MultiSelect.svelte";
  import type { WorkflowSpec } from "./spec";

  let { ws, spec }: { ws: string; spec: WorkflowSpec } = $props();

  let files = $state<WF.ResultFile[] | null>(null);
  let chosen = $state<string[]>([]);
  let zipping = $state(false);

  $effect(() => {
    WF.resultFiles(store, ws, spec)
      .then((r) => {
        files = r;
        chosen = [...new Set(r.map((f) => f.folder))];
      })
      .catch(toastError);
  });

  const folders = $derived([...new Set((files ?? []).map((f) => f.folder))].sort());
  const fmtTime = (t: number) => new Date(t).toLocaleString([], { dateStyle: "short", timeStyle: "short" });

  async function zip() {
    zipping = true;
    try {
      saveBlob(await WF.resultsZip(store, ws, spec, chosen), `${ws}-results.zip`);
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
              <td class="px-2 py-1 text-right">{humanSize(f.size)}</td>
              <td class="px-2 py-1">{fmtTime(f.modified)}</td>
              <td class="px-2 py-1 text-right"><button class="btn" onclick={() => saveFile(store, join(WF.workflowDir(ws, spec), "results", f.path)).catch(toastError)} aria-label="Download {f.path}">⬇️</button></td>
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
