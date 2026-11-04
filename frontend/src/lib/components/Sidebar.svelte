<script lang="ts">
  // Navigation plus the sidebar of src/common/common.py:render_sidebar():
  // workspace switch/create/delete, demo data and display settings, and
  // the workspace's way out of this browser: export, import and share.
  import { logoUrl } from "../assets";
  import { saveBlob } from "../backend/files";
  import { exportWorkspace, importWorkspace, sharingEnabled, shareWorkspace } from "../backend/share";
  import * as W from "../backend/workspaces";
  import { app, navigate, setImageFormat, setWorkspace, store, toast, toastError } from "../state.svelte";
  import type { Section } from "../../nav";
  import ResourceMonitor from "./ResourceMonitor.svelte";

  let { nav, onnavigate }: { nav: Section[]; onnavigate?: () => void } = $props();

  let workspaces = $state<string[]>([]);
  const demos = W.demos();
  let newName = $state("");
  let selectedDemo = $state(demos[0] ?? "");
  let importInput = $state<HTMLInputElement>();
  let shareInputs = $state(false);
  let sharing = $state(false);
  let shareLink = $state("");

  async function refresh() {
    try {
      workspaces = await W.listWorkspaces(store);
      if (!workspaces.includes(app.workspace)) {
        // opened by link to a workspace that does not exist yet: create it
        await W.createWorkspace(store, app.workspace);
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
      await W.createWorkspace(store, name);
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
      await W.deleteWorkspace(store, app.workspace);
      const next = workspaces.find((w) => w !== app.workspace) ?? "default";
      await W.createWorkspace(store, next);
      await refresh();
      setWorkspace(next);
      toast("Workspace deleted");
    } catch (e) {
      toastError(e);
    }
  }

  async function loadDemo() {
    if (!confirm(`Replace the content of "${app.workspace}" with the demo "${selectedDemo}"?`)) return;
    try {
      await W.loadDemo(store, app.workspace, selectedDemo);
      app.epoch++;
      toast(`Loaded demo ${selectedDemo}`);
    } catch (e) {
      toastError(e);
    }
  }

  async function exportZip() {
    try {
      saveBlob(await exportWorkspace(store, app.workspace, { inputs: true }), `${app.workspace}.zip`);
    } catch (e) {
      toastError(e);
    }
  }

  async function importZip() {
    const f = importInput?.files?.[0];
    if (!f) return;
    try {
      const name = await importWorkspace(store, f);
      await refresh();
      setWorkspace(name);
      toast(`Opened workspace ${name}`);
    } catch (e) {
      toastError(e);
    } finally {
      if (importInput) importInput.value = "";
    }
  }

  async function share() {
    const what = shareInputs ? "its parameters, results and input files" : "its parameters and results";
    if (!confirm(`Upload workspace "${app.workspace}" (${what}) to ${app.settings?.share_url} for a share link?`)) return;
    sharing = true;
    try {
      shareLink = await shareWorkspace(store, app.workspace, { inputs: shareInputs });
      await navigator.clipboard?.writeText(shareLink).catch(() => {});
      toast("Workspace uploaded; the link is copied.");
    } catch (e) {
      toastError(e);
    } finally {
      sharing = false;
    }
  }
</script>

<div class="flex flex-col gap-5 p-4">
  <a href="#/quickstart" class="flex items-center gap-2" onclick={onnavigate}>
    <img src={logoUrl} alt="OpenMS" class="h-9 w-9" />
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
        <div class="flex gap-1">
          <button class="btn flex-1" onclick={exportZip} title="Save the whole workspace as a ZIP file">⬇️ Export</button>
          <button class="btn flex-1" onclick={() => importInput?.click()} title="Open a workspace ZIP file as a new workspace">⬆️ Import</button>
          <input bind:this={importInput} type="file" accept=".zip" class="hidden" onchange={importZip} />
        </div>
        {#if sharingEnabled()}
          <div class="flex flex-col gap-1 rounded-md border p-2" style="border-color: var(--border)">
            <button class="btn" onclick={share} disabled={sharing}>{sharing ? "Uploading…" : "🔗 Share workspace"}</button>
            <label class="flex items-center gap-2 text-xs">
              <input type="checkbox" bind:checked={shareInputs} /> include input files
            </label>
            {#if shareLink}
              <input class="input text-xs" readonly value={shareLink} onfocus={(e) => e.currentTarget.select()} aria-label="Share link" />
            {/if}
            <div class="text-xs muted">Nothing leaves this browser until you click Share.</div>
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
    <div>Runs in this browser on this computer. Version {app.settings?.version}</div>
    {#if app.settings}
      <div class="mt-1 flex gap-2">
        {#each Object.entries(app.settings.legal_links) as [k, url]}
          <a href={url} target="_blank" rel="noreferrer" class="underline">{k}</a>
        {/each}
      </div>
    {/if}
  </div>
</div>
