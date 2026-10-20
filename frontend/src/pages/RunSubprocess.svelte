<script lang="ts">
  // content/run_subprocess.py: run an external command on a workspace file.
  import { api, enc } from "../lib/api";
  import { app, toastError } from "../lib/state.svelte";

  const ws = `/ws/${enc(app.workspace)}`;
  let files = $state<string[]>([]);
  let file = $state("");
  let result = $state<any>(null);
  let busy = $state(false);

  api.get(`${ws}/mzml`).then((r) => {
    files = r.files.map((f: any) => f.name);
    file = files[0] ?? "";
  });

  async function run() {
    busy = true;
    result = null;
    try {
      result = await api.post(`${ws}/extract-ids/${enc(file)}`);
    } catch (e) {
      toastError(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="flex max-w-4xl flex-col gap-4">
  <div>
    <h1 class="h1">Run subprocess</h1>
    <p class="muted">Runs an external process ('grep', or 'findstr' on Windows) to extract IDs from the selected mzML file and shows its output. Longer running processes, such as TOPP tools, work the same way.</p>
  </div>
  {#if !files.length}
    <div class="alert alert-info">No mzML files in this workspace. Add some on the pyOpenMS File Upload page.</div>
  {:else}
    <div class="flex items-end gap-2">
      <label class="w-80"><span class="label">Please select file</span><select class="input" bind:value={file}>{#each files as f}<option>{f}</option>{/each}</select></label>
      <button class="btn btn-primary" disabled={busy} onclick={run}>{busy ? "Running…" : "Extract ids"}</button>
    </div>
  {/if}
  {#if result}
    <pre class="code">Running command: {result.command}</pre>
    <div class="alert {result.success ? 'alert-success' : 'alert-error'}">{result.success ? `Finished in ${result.seconds} s` : "The command failed"}</div>
    <pre class="code max-h-[50vh]">{result.log}</pre>
  {/if}
</div>
