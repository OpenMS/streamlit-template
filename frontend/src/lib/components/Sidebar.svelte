<script lang="ts">
  // Navigation plus the sidebar of src/common/common.py:render_sidebar():
  // workspace switch/create/delete, demo data, and display settings.
  import { api } from "../api";
  import { app, navigate, setImageFormat, setWorkspace, toast, toastError } from "../state.svelte";
  import type { Section } from "../../nav";
  import ResourceMonitor from "./ResourceMonitor.svelte";

  let { nav, onnavigate }: { nav: Section[]; onnavigate?: () => void } = $props();

  let workspaces = $state<string[]>([]);
  let demos = $state<string[]>([]);
  let newName = $state("");
  let selectedDemo = $state("");

  async function refresh() {
    try {
      const r = await api.get<{ workspaces: string[]; demos: string[] }>("/workspaces");
      workspaces = r.workspaces;
      demos = r.demos;
      if (!selectedDemo && demos.length) selectedDemo = demos[0];
      if (!workspaces.includes(app.workspace)) {
        // opened by link to a workspace that does not exist yet: create it
        await api.post("/workspaces", { name: app.workspace });
        workspaces = [...workspaces, app.workspace].sort();
      }
    } catch (e) {
      toastError(e);
    }
  }
  refresh();

  async function create() {
    const name = newName.trim();
    if (!name) return;
    try {
      await api.post("/workspaces", { name });
      newName = "";
      await refresh();
      setWorkspace(name);
      toast(`Workspace ${name} created`);
    } catch (e) {
      toastError(e);
    }
  }

  async function remove() {
    if (!confirm(`Delete workspace "${app.workspace}" and all its files?`)) return;
    try {
      await api.del(`/workspaces/${encodeURIComponent(app.workspace)}`);
      await refresh();
      setWorkspace(workspaces.find((w) => w !== app.workspace) ?? "default");
      toast("Workspace deleted");
    } catch (e) {
      toastError(e);
    }
  }

  async function loadDemo() {
    if (!confirm(`Replace the content of "${app.workspace}" with the demo "${selectedDemo}"?`)) return;
    try {
      await api.post(`/workspaces/${encodeURIComponent(app.workspace)}/load-demo`, { demo: selectedDemo });
      app.epoch++;
      toast(`Loaded demo ${selectedDemo}`);
    } catch (e) {
      toastError(e);
    }
  }
</script>

<div class="flex flex-col gap-5 p-4">
  <a href="#/quickstart" class="flex items-center gap-2" onclick={onnavigate}>
    <img src="/assets/openms-logo.svg" alt="OpenMS" class="h-9 w-9" />
    <span class="font-semibold leading-tight">{app.settings?.app_name ?? "OpenMS WebApp"}</span>
  </a>

  <nav class="flex flex-col gap-3">
    {#each nav as section}
      <div>
        <div class="mb-1 text-xs font-semibold uppercase tracking-wide muted">{section.title}</div>
        {#each section.pages as p}
          <button
            class="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-[var(--bg)]"
            class:font-semibold={app.route === p.route}
            style={app.route === p.route ? "background: var(--bg); color: var(--accent)" : ""}
            onclick={() => {
              navigate(p.route);
              onnavigate?.();
            }}
          >
            <span class="w-5 text-center">{p.icon}</span>{p.title}
          </button>
        {/each}
      </div>
    {/each}
  </nav>

  {#if app.settings?.enable_workspaces}
    <details open class="border-t pt-3" style="border-color: var(--border)">
      <summary class="cursor-pointer text-sm font-semibold">🖥️ Workspaces</summary>
      <div class="mt-2 flex flex-col gap-2">
        <select class="input" value={app.workspace} onchange={(e) => setWorkspace(e.currentTarget.value)} aria-label="Workspace">
          {#each workspaces as w}<option value={w}>{w}</option>{/each}
        </select>
        <div class="flex gap-1">
          <input class="input" placeholder="new workspace" bind:value={newName} onkeydown={(e) => e.key === "Enter" && create()} />
          <button class="btn" onclick={create} disabled={!newName.trim()}>Create</button>
        </div>
        <button class="btn btn-danger" onclick={remove}>⚠️ Delete workspace</button>
        {#if demos.length}
          <div class="flex gap-1">
            <select class="input" bind:value={selectedDemo} aria-label="Demo">
              {#each demos as d}<option value={d}>{d}</option>{/each}
            </select>
            <button class="btn" onclick={loadDemo}>Load demo</button>
          </div>
        {/if}
      </div>
    </details>
  {/if}

  <details class="border-t pt-3" style="border-color: var(--border)">
    <summary class="cursor-pointer text-sm font-semibold">⚙️ Settings</summary>
    <div class="mt-2 flex flex-col gap-2 text-sm">
      <label>
        <span class="label">Image export format</span>
        <select class="input" value={app.imageFormat} onchange={(e) => setImageFormat(e.currentTarget.value as "svg" | "png")}>
          <option value="svg">svg</option>
          <option value="png">png</option>
        </select>
      </label>
    </div>
  </details>

  <ResourceMonitor />

  <div class="border-t pt-3 text-xs muted" style="border-color: var(--border)">
    <div>Runs locally on this computer. Version {app.settings?.version}</div>
    {#if app.settings}
      <div class="mt-1 flex gap-2">
        {#each Object.entries(app.settings.legal_links) as [k, url]}
          <a href={url} target="_blank" rel="noreferrer" class="underline">{k}</a>
        {/each}
      </div>
    {/if}
  </div>
</div>
