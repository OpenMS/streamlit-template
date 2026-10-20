<script lang="ts">
  // StreamlitUI.file_upload_section: one upload widget per Upload item, plus
  // a download of all input files.
  import { api, download, enc } from "../api";
  import { app, toast, toastError } from "../state.svelte";
  import FileInput from "../components/FileInput.svelte";
  import Tabs from "../components/Tabs.svelte";
  import type { FileEntry } from "../types";

  let { slug, spec }: { slug: string; spec: any } = $props();
  const base = $derived(`/ws/${enc(app.workspace)}/wf/${slug}`);

  let state = $state<Record<string, { files: FileEntry[]; only_example: boolean }>>({});

  async function load(key: string) {
    try {
      state[key] = await api.get(`${base}/files/${enc(key)}`);
    } catch (e) {
      toastError(e);
    }
  }
  for (const u of spec.upload) load(u.key);

  function handlers(u: any) {
    return {
      onupload: async (files: File[]) => {
        try {
          const r = await api.upload(`${base}/files/${enc(u.key)}`, files);
          await load(u.key);
          if (r.added.length) toast(`Added ${r.added.length} file(s)`);
          if (r.skipped.length) toast(`Skipped ${r.skipped.join(", ")}: not ${u.file_types.join("/")}`, "warning");
        } catch (e) {
          toastError(e);
        }
      },
      onlocal: async (paths: string[], copy: boolean) => {
        try {
          const r = await api.post(`${base}/files/${enc(u.key)}/local`, { paths, copy_files: copy });
          await load(u.key);
          toast(`Added ${r.added.length} file(s)`);
        } catch (e) {
          toastError(e);
        }
      },
      onremove: async (f: FileEntry) => {
        const q = f.reference ? `path=${enc(f.path)}` : `name=${enc(f.name)}`;
        await api.del(`${base}/files/${enc(u.key)}?${q}`).catch(toastError);
        await load(u.key);
      },
      onremoveall: async () => {
        await api.del(`${base}/files/${enc(u.key)}`).catch(toastError);
        await load(u.key);
      },
    };
  }
</script>

{#snippet widget(u: any)}
  {#if state[u.key]}
    <FileInput name={u.name || u.key} fileTypes={u.file_types} files={state[u.key].files} onlyExample={state[u.key].only_example} {...handlers(u)} />
  {/if}
{/snippet}

<div class="flex flex-col gap-4">
  {#if spec.upload.length > 1}
    <Tabs labels={spec.upload.map((u: any) => u.name || u.key)}>
      {#snippet children(active: number)}{@render widget(spec.upload[active])}{/snippet}
    </Tabs>
  {:else if spec.upload.length}
    {@render widget(spec.upload[0])}
  {/if}
  <div>
    <button class="btn" onclick={() => download(`${base}/input-zip`)}>⬇️ Download files</button>
  </div>
</div>
