<script lang="ts">
  // StreamlitUI.parameter_section: advanced toggle, threads, presets, the
  // workflow's configure items, and parameter reset/export/import.
  import * as WF from "../backend/workflow";
  import { saveBlob, saveText } from "../backend/files";
  import { engine } from "../engine/client";
  import { app, store, toast, toastError } from "../state.svelte";
  import ConfigItems from "./ConfigItems.svelte";
  import type { Tool, WorkflowSpec } from "./spec";

  let { ws, spec }: { ws: string; spec: WorkflowSpec } = $props();

  let cfg = $state<Awaited<ReturnType<typeof WF.configure>> | null>(null);
  let values = $state<Record<string, any>>({});
  let error = $state("");
  let advanced = $state(localStorage.getItem("advanced-params") === "true");
  let importInput = $state<HTMLInputElement>();
  const presets = $derived(WF.presetList(spec));

  $effect(() => {
    try {
      localStorage.setItem("advanced-params", String(advanced));
    } catch {}
  });

  async function load() {
    try {
      cfg = await WF.configure(store, ws, spec);
      values = { ...cfg.values, max_threads: cfg.max_threads };
      error = "";
    } catch (e: any) {
      error = e.message;
    }
  }
  load();

  async function setValue(key: string, v: any) {
    values[key] = v;
    try {
      await WF.saveParams(store, ws, spec, { [key]: v });
    } catch (e) {
      toastError(e);
    }
  }

  async function setTool(item: Tool & { schema: WF.ToolSchema }, key: string, v: any) {
    try {
      item.schema = await WF.saveTool(store, ws, spec, item, { [key]: v });
    } catch (e) {
      toastError(e);
    }
  }

  async function preset(name: string) {
    try {
      await WF.applyPreset(store, ws, spec, name);
      await load();
      toast(`Applied preset: ${name}`);
    } catch (e) {
      toastError(e);
    }
  }

  async function reset() {
    if (!confirm("Reset all parameters of this workflow to their defaults?")) return;
    try {
      const backup = await WF.resetParams(store, ws, spec);
      await load();
      toast(backup ? `Parameters reset to defaults, previous file kept as ${backup}` : "Parameters reset to defaults");
    } catch (e) {
      toastError(e);
    }
  }

  async function exportParams() {
    try {
      saveBlob(await WF.exportParams(store, ws, spec), "parameters.json");
    } catch (e) {
      toastError(e);
    }
  }

  async function methodSummary() {
    try {
      const version = await engine.call("openms.version").catch(() => "");
      saveText(await WF.methodSummary(store, ws, spec, version), "method-summary.md", "text/markdown");
    } catch (e) {
      toastError(e);
    }
  }

  async function importParams() {
    const f = importInput?.files?.[0];
    if (!f) return;
    try {
      await WF.importParams(store, ws, spec, f);
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
    {#if error.includes("default parameters")}<button class="btn btn-danger ml-2" onclick={reset}>⚠️ Reset parameters to defaults</button>{/if}
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
        <span class="label" title="Threads OpenMS uses for a run (needs a cross-origin isolated page).">Threads</span>
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

    {#if presets.length}
      <div>
        <div class="font-semibold">Parameter presets</div>
        <div class="mb-2 text-sm muted">Click a preset to apply optimized parameters.</div>
        <div class="flex flex-wrap gap-2">
          {#each presets as p}
            <button class="btn" title={p.description} onclick={() => preset(p.name)}>{p.name}</button>
          {/each}
        </div>
      </div>
    {/if}

    <ConfigItems items={cfg.items} {values} {advanced} {setValue} {setTool} />

    <div class="flex flex-wrap gap-2 border-t pt-4" style="border-color: var(--border)">
      <button class="btn btn-danger" onclick={reset}>⚠️ Load default parameters</button>
      <button class="btn" onclick={exportParams}>⬇️ Export parameters</button>
      <button class="btn" onclick={methodSummary}>📑 Method summary</button>
      <button class="btn" onclick={() => importInput?.click()}>⬆️ Import parameters</button>
      <input bind:this={importInput} type="file" accept=".json" class="hidden" onchange={importParams} />
    </div>
  </div>
{/if}
