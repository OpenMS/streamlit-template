<script lang="ts">
  // content/file_upload.py: mzML files of the workspace for the pyOpenMS pages.
  import { api, enc } from "../lib/api";
  import { app, toast, toastError } from "../lib/state.svelte";
  import FileInput from "../lib/components/FileInput.svelte";
  import type { FileEntry } from "../lib/types";

  const base = `/ws/${enc(app.workspace)}/mzml`;
  let files = $state<FileEntry[] | null>(null);

  const load = () => api.get(base).then((r) => (files = r.files)).catch(toastError);
  load();
</script>

<div class="flex flex-col gap-4">
  <div>
    <h1 class="h1">📂 File Upload</h1>
    <p class="muted">mzML files for the pyOpenMS example pages of this workspace.</p>
  </div>
  <div>
    <button class="btn" onclick={async () => { await api.post(`${base}/example`).catch(toastError); await load(); toast("Example data loaded"); }}>Load example data</button>
  </div>
  {#if files}
    <FileInput
      name="mzML"
      fileTypes={["mzML"]}
      {files}
      onupload={async (f) => { const r = await api.upload(base, f).catch(toastError); await load(); if (r) toast(`Added ${r.added.length} file(s)`); }}
      onlocal={async (paths, copy) => { await api.post(`${base}/local`, { paths, copy_files: copy }).catch(toastError); await load(); }}
      onremove={async (f) => { await api.del(`${base}?name=${enc(f.name)}`).catch(toastError); await load(); }}
      onremoveall={async () => { await api.del(base).catch(toastError); await load(); }}
    />
  {/if}
</div>
