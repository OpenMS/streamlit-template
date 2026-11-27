<script lang="ts">
  // StreamlitUI.file_upload_section: one upload widget per Upload item, plus
  // a download of all input files.
  import * as WF from "../backend/workflow";
  import { saveBlob } from "../backend/files";
  import { store, toast, toastError } from "../state.svelte";
  import FileInput from "../components/FileInput.svelte";
  import Tabs from "../components/Tabs.svelte";
  import type { FileEntry } from "../types";
  import type { Upload, WorkflowSpec } from "./spec";

  let { ws, spec }: { ws: string; spec: WorkflowSpec } = $props();

  let state = $state<Record<string, { files: FileEntry[]; only_example: boolean }>>({});

  async function load(key: string) {
    try {
      state[key] = await WF.inputFiles(store, ws, spec, key);
    } catch (e) {
      toastError(e);
    }
  }
  $effect(() => {
    for (const u of spec.upload) load(u.key);
  });

  function handlers(u: Upload) {
    return {
      onupload: async (files: File[]) => {
        try {
          const r = await WF.uploadInputFiles(store, ws, spec, u.key, files);
          await load(u.key);
          if (r.added.length) toast(`Added ${r.added.length} file(s)`);
          if (r.skipped.length) toast(`Skipped ${r.skipped.join(", ")}: not ${u.fileTypes.join("/")}`, "warning");
        } catch (e) {
          toastError(e);
        }
      },
      onremove: async (f: FileEntry) => {
        await WF.removeInputFiles(store, ws, spec, u.key, f.name).catch(toastError);
        await load(u.key);
      },
      onremoveall: async () => {
        await WF.removeInputFiles(store, ws, spec, u.key).catch(toastError);
        await load(u.key);
      },
    };
  }

  async function downloadAll() {
    try {
      saveBlob(await WF.inputZip(store, ws, spec), `${ws}-input-files.zip`);
    } catch (e) {
      toastError(e);
    }
  }
</script>

{#snippet widget(u: Upload)}
  {#if state[u.key]}
    <FileInput name={u.name || u.key} fileTypes={u.fileTypes} files={state[u.key].files} onlyExample={state[u.key].only_example} {...handlers(u)} />
  {:else}
    <p class="muted">Loading files…</p>
  {/if}
{/snippet}

<div class="flex flex-col gap-4">
  {#if spec.upload.length > 1}
    <Tabs labels={spec.upload.map((u) => u.name || u.key)}>
      {#snippet children(active: number)}{@render widget(spec.upload[active])}{/snippet}
    </Tabs>
  {:else if spec.upload.length}
    {@render widget(spec.upload[0])}
  {/if}
  <div>
    <button class="btn" onclick={downloadAll}>⬇️ Download files</button>
  </div>
</div>
