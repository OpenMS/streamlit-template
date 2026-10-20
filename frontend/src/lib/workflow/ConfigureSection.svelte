<script lang="ts">
  // StreamlitUI.parameter_section: advanced toggle, threads, presets, the
  // workflow's configure items, and parameter reset/export/import.
  import { api, download, enc, saveText } from "../api";
  import { app, toast, toastError } from "../state.svelte";
  import ConfigItems from "./ConfigItems.svelte";

  let { slug, spec }: { slug: string; spec: any } = $props();

  const base = $derived(`/ws/${enc(app.workspace)}/wf/${slug}`);
  let cfg = $state<any>(null);
  let values = $state<Record<string, any>>({});
  let error = $state("");
  let advanced = $state(localStorage.getItem("advanced-params") === "true");
  let importInput = $state<HTMLInputElement>();

  $effect(() => {
    try {
      localStorage.setItem("advanced-params", String(advanced));
    } catch {}
  });

  async function load() {
    try {
      cfg = await api.get(`${base}/configure`);
      const v: Record<string, any> = { ...cfg.values, max_threads: cfg.max_threads };
      // seed widget values that are not stored yet with their defaults
      const seed = (items: any[]) => {
        for (const it of items) {
          if (it.type === "tab") seed(it.items);
          else if ((it.type === "widget" || it.type === "select-files") && !(it.key in v)) v[it.key] = it.state.value;
          else if (it.type === "python") for (const p of it.schema.params) if (!(p.key in v)) v[p.key] = p.value;
        }
      };
      seed(cfg.items);
      values = v;
      error = "";
    } catch (e: any) {
      error = e.message;
    }
  }
  load();

  async function setValue(key: string, v: any) {
    values[key] = v;
    try {
      await api.put(`${base}/params`, { values: { [key]: v } });
    } catch (e) {
      toastError(e);
    }
  }

  async function setTopp(item: any, key: string, v: any) {
    try {
      item.schema = await api.put(`${base}/topp/${enc(item.tool_instance_name || item.tool)}`, { values: { [key]: v } });
    } catch (e) {
      toastError(e);
    }
  }

  async function preset(name: string) {
    try {
      await api.post(`${base}/presets/${enc(name)}`);
      await load();
      toast(`Applied preset: ${name}`);
    } catch (e) {
      toastError(e);
    }
  }

  async function reset() {
    if (!confirm("Reset all parameters of this workflow to their defaults?")) return;
    try {
      const r = await api.post(`${base}/params/reset`);
      await load();
      toast(r.backup ? `Parameters reset to defaults, previous file kept as ${r.backup}` : "Parameters reset to defaults");
    } catch (e) {
      toastError(e);
    }
  }

  async function methodSummary() {
    try {
      saveText(await api.get<string>(`${base}/method-summary`), "method-summary.md", "text/markdown");
    } catch (e) {
      toastError(e);
    }
  }

  async function importParams() {
    const f = importInput?.files?.[0];
    if (!f) return;
    try {
      await api.upload(`${base}/params/import`, [f], "file");
      await load();
      toast("Parameters imported");
    } catch (e) {
      toastError(e);
    } finally {
      if (importInput) importInput.value = "";
    }
  }
</script>

{#if error}
  <div class="alert alert-error">
    {error}
    {#if error.includes("reset")}<button class="btn btn-danger ml-2" onclick={reset}>⚠️ Reset parameters to defaults</button>{/if}
  </div>
{:else if !cfg}
  <p class="muted">Loading parameters…</p>
{:else}
  <div class="flex flex-col gap-5">
    <div class="flex flex-wrap items-end gap-6">
      <label class="flex items-center gap-2 text-sm font-medium">
        <input type="checkbox" role="switch" bind:checked={advanced} /> Show advanced parameters
      </label>
      <label class="w-40">
        <span class="label" title="Maximum threads for parallel processing. Threads are distributed between parallel commands and per-tool thread allocation.">Threads</span>
        <input
          class="input"
          type="number"
          min="1"
          max={app.settings?.cpu_count}
          value={values.max_threads}
          onchange={(e) => {
            const n = parseInt(e.currentTarget.value, 10);
            if (n >= 1) setValue("max_threads", n);
          }}
        />
      </label>
    </div>

    {#if spec.presets.length}
      <div>
        <div class="font-semibold">Parameter presets</div>
        <div class="mb-2 text-sm muted">Click a preset to apply optimized parameters.</div>
        <div class="flex flex-wrap gap-2">
          {#each spec.presets as p}
            <button class="btn" title={p.description} onclick={() => preset(p.name)}>{p.name}</button>
          {/each}
        </div>
      </div>
    {/if}

    <ConfigItems items={cfg.items} {values} {advanced} {setValue} {setTopp} />

    <div class="flex flex-wrap gap-2 border-t pt-4" style="border-color: var(--border)">
      <button class="btn btn-danger" onclick={reset}>⚠️ Load default parameters</button>
      <button class="btn" onclick={() => download(`${base}/params/export`)}>⬇️ Export parameters</button>
      <button class="btn" onclick={methodSummary}>📑 Method summary</button>
      <button class="btn" onclick={() => importInput?.click()}>⬆️ Import parameters</button>
      <input bind:this={importInput} type="file" accept=".json" class="hidden" onchange={importParams} />
    </div>
  </div>
{/if}
