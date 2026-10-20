<script lang="ts">
  // content/run_subprocess.py: run a task outside the page on a workspace
  // file and show its output. In the browser, the counterpart of a
  // subprocess is the engine's Web Worker: the page stays responsive while it
  // runs, as longer tasks (the workflow's tools) do.
  import * as W from "../lib/backend/workspaces";
  import { engine } from "../lib/engine/client";
  import { app, store, toastError } from "../lib/state.svelte";

  let files = $state<{ name: string; path: string }[]>([]);
  let file = $state("");
  let result = $state<{ command: string; seconds: string; log: string } | null>(null);
  let busy = $state(false);

  W.mzmlFiles(store, app.workspace).then((fs) => {
    files = fs;
    file = files[0]?.name ?? "";
  });

  async function run() {
    busy = true;
    result = null;
    const f = files.find((x) => x.name === file)!;
    const start = performance.now();
    try {
      const log = await engine.call("mzml.extractIds", f.path);
      result = { command: `grep idRef ${f.name}.mzML (in the engine worker)`, seconds: ((performance.now() - start) / 1000).toFixed(2), log };
    } catch (e) {
      toastError(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="flex max-w-4xl flex-col gap-4">
  <div>
    <h1 class="h1">Run in the background</h1>
    <p class="muted">
      Extracts the IDs of the selected mzML file in a Web Worker, outside the page, and shows the output: the browser's counterpart of the subprocess of the
      Streamlit app. Longer running tasks, such as the workflow's tools, work the same way.
    </p>
  </div>
  {#if !files.length}
    <div class="alert alert-info">No mzML files in this workspace. Add some on the OpenMS Workflow File Upload page.</div>
  {:else}
    <div class="flex items-end gap-2">
      <label class="w-80"><span class="label">Please select file</span><select class="input" bind:value={file}>{#each files as f}<option>{f.name}</option>{/each}</select></label>
      <button class="btn btn-primary" disabled={busy} onclick={run}>{busy ? "Running…" : "Extract ids"}</button>
    </div>
  {/if}
  {#if result}
    <pre class="code">Running: {result.command}</pre>
    <div class="alert alert-success">Finished in {result.seconds} s</div>
    <pre class="code max-h-[50vh]">{result.log || "No idRef lines in this file."}</pre>
  {/if}
</div>
