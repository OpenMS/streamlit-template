<script lang="ts">
  // content/file_upload.py: mzML files of the workspace for the pyOpenMS pages.
  import * as W from "../lib/backend/workspaces";
  import { addFiles, humanSize } from "../lib/backend/files";
  import { join } from "../lib/storage/store";
  import { app, store, toast, toastError } from "../lib/state.svelte";
  import FileInput from "../lib/components/FileInput.svelte";
  import type { FileEntry } from "../lib/types";

  let files = $state<FileEntry[] | null>(null);
  let loading = $state(false);

  const load = () =>
    W.mzmlFiles(store, app.workspace)
      .then((fs) => (files = fs.map((f) => ({ ...f, size: humanSize(f.size) }))))
      .catch(toastError);
  load();

  async function example() {
    loading = true;
    try {
      await W.loadExampleMzml(store, app.workspace);
      await load();
      toast("Example data loaded");
    } catch (e) {
      toastError(e);
    } finally {
      loading = false;
    }
  }
</script>

<div class="flex flex-col gap-4">
  <div>
    <h1 class="h1">📂 File Upload</h1>
    <p class="muted">mzML files for the OpenMS example pages of this workspace.</p>
  </div>
  <div>
    <button class="btn" disabled={loading} onclick={example}>{loading ? "Loading…" : "Load example data"}</button>
  </div>
  {#if files}
    <FileInput
      name="mzML"
      fileTypes={["mzML"]}
      {files}
      onupload={async (f) => {
        const r = await addFiles(store, join(app.workspace, W.MZML_DIR), f, ["mzML"]).catch(toastError);
        await load();
        if (r) toast(`Added ${r.added.length} file(s)`);
      }}
      onremove={async (f) => {
        await W.deleteMzml(store, app.workspace, f.name).catch(toastError);
        await load();
      }}
      onremoveall={async () => {
        await W.deleteMzml(store, app.workspace).catch(toastError);
        await load();
      }}
    />
  {/if}
</div>
