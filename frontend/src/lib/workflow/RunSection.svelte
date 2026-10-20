<script lang="ts">
  // StreamlitUI.execution_section: summary, start/stop, live log with level
  // and line count, and the outcome of the last run. The run goes on while
  // the app is open in this tab (on any page); closing the tab ends it.
  import { onDestroy } from "svelte";
  import * as WF from "../backend/workflow";
  import { store, toastError } from "../state.svelte";
  import type { LogLevelName } from "./logger";
  import type { WorkflowSpec } from "./spec";

  let { ws, spec }: { ws: string; spec: WorkflowSpec } = $props();

  let level = $state<LogLevelName>((localStorage.getItem("log-level") as LogLevelName) ?? "minimal");
  let lines = $state(Number(localStorage.getItem("log-lines") ?? 100));
  let st = $state<WF.Status | null>(null);
  let summary = $state<any>(null);
  let busy = $state(false);
  let timer: ReturnType<typeof setTimeout> | undefined;
  let pre: HTMLPreElement | undefined = $state();

  async function poll() {
    clearTimeout(timer);
    try {
      st = await WF.status(store, ws, spec, level, lines);
    } catch (e) {
      toastError(e);
    }
    if (st?.running) timer = setTimeout(poll, 1000);
  }

  $effect(() => {
    try {
      localStorage.setItem("log-level", level);
      localStorage.setItem("log-lines", String(lines));
    } catch {}
    void level, lines;
    poll();
  });

  $effect(() => {
    void st?.log;
    if (pre && st?.running) pre.scrollTop = pre.scrollHeight;
  });

  onDestroy(() => clearTimeout(timer));

  $effect(() => {
    WF.paramSummary(store, ws, spec).then((s) => (summary = s)).catch(() => {});
  });

  async function start() {
    busy = true;
    try {
      await WF.startWorkflow(store, ws, spec);
      setTimeout(poll, 300);
    } catch (e) {
      toastError(e);
    } finally {
      busy = false;
    }
  }

  async function stop() {
    busy = true;
    try {
      await WF.stopWorkflow(store, ws, spec);
      await poll();
    } catch (e) {
      toastError(e);
    } finally {
      busy = false;
    }
  }

  const fmt = (v: any) => (Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : String(v));
</script>

<div class="flex flex-col gap-4">
  {#if summary}
    <details class="card">
      <summary class="cursor-pointer font-semibold">Summary</summary>
      <div class="mt-2 grid gap-3 text-sm md:grid-cols-3">
        {#each [["General", summary.general], ["OpenMS Tools", summary.tools], ["Steps", summary.steps]] as [title, group]}
          {#if Object.keys(group).length}
            <div>
              <div class="font-semibold">{title}</div>
              {#each Object.entries(group) as [k, v]}
                {#if v && typeof v === "object" && !Array.isArray(v)}
                  <div class="mt-1 font-medium">{k}</div>
                  {#each Object.entries(v) as [kk, vv]}<div class="pl-3"><span class="muted">{kk}:</span> <b>{fmt(vv)}</b></div>{/each}
                {:else}
                  <div><span class="muted">{k}:</span> <b>{fmt(v)}</b></div>
                {/if}
              {/each}
            </div>
          {/if}
        {/each}
      </div>
    </details>
  {/if}

  <div class="grid items-end gap-3 md:grid-cols-3">
    <div>
      {#if st?.running}
        <button class="btn btn-primary w-full" disabled={busy} onclick={stop}>Stop Workflow</button>
      {:else}
        <button class="btn btn-primary w-full" disabled={busy} onclick={start}>Start Workflow</button>
      {/if}
    </div>
    <label>
      <span class="label">log details</span>
      <select class="input" bind:value={level}>
        <option>minimal</option>
        <option>commands and run times</option>
        <option>all</option>
      </select>
    </label>
    <label>
      <span class="label">lines to show</span>
      <select class="input" bind:value={lines}>
        {#each [50, 100, 200, 500, 0] as n}<option value={n}>{n || "all"}</option>{/each}
      </select>
    </label>
  </div>

  {#if st}
    {#if st.running}
      <div class="alert alert-info flex items-center gap-2"><span class="animate-spin">⏳</span> <b>Workflow running…</b></div>
    {:else if st.outcome === "finished"}
      <div class="alert alert-success"><b>Workflow completed successfully.</b></div>
    {:else if st.outcome === "cancelled"}
      <div class="alert alert-warning"><b>Workflow was cancelled.</b></div>
    {:else if st.outcome === "error"}
      <div class="alert alert-error"><b>Errors occurred, check log file.</b></div>
    {/if}
    {#if st.log}
      {#if st.log_time && !st.running}<div class="text-sm font-semibold">Workflow log file: {st.log_time}</div>{/if}
      <pre bind:this={pre} class="code max-h-[60vh]">{st.log}</pre>
    {/if}
  {/if}
</div>
