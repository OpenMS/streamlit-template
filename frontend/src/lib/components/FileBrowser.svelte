<script lang="ts">
  // Picks files or folders on this computer through the local server (the
  // browser itself cannot reveal file paths). Replaces the tkinter dialogs.
  import { api } from "../api";

  type Entry = { name: string; path: string; dir: boolean; size?: number; selectable: boolean };

  let {
    open = $bindable(false),
    fileTypes = [],
    onpick,
  }: { open?: boolean; fileTypes?: string[]; onpick: (paths: string[]) => void } = $props();

  let path = $state(localStorage.getItem("file-browser-dir") ?? "");
  let listing = $state<{ path: string; parent: string | null; entries: Entry[] } | null>(null);
  let picked = $state<string[]>([]);
  let error = $state("");

  async function go(p: string) {
    try {
      listing = await api.get(`/fs?path=${encodeURIComponent(p)}&file_types=${encodeURIComponent(fileTypes.join(","))}`);
      path = listing!.path;
      picked = [];
      error = "";
      try {
        localStorage.setItem("file-browser-dir", path);
      } catch {}
    } catch (e: any) {
      error = e.message;
    }
  }

  $effect(() => {
    if (open && !listing) go(path);
  });

  function toggle(p: string) {
    picked = picked.includes(p) ? picked.filter((x) => x !== p) : [...picked, p];
  }

  function done(paths: string[]) {
    onpick(paths);
    open = false;
  }
</script>

{#if open}
  <div class="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
    <div class="card flex max-h-[85vh] w-full max-w-2xl flex-col gap-3" style="background: var(--bg)">
      <div class="flex items-center justify-between">
        <h3 class="font-semibold">Select {fileTypes.length ? fileTypes.join(", ") : ""} files on this computer</h3>
        <button class="btn" onclick={() => (open = false)} aria-label="Close">✕</button>
      </div>
      <div class="flex gap-2">
        <button class="btn" disabled={!listing?.parent} onclick={() => listing?.parent && go(listing.parent)} title="Parent folder">⬆</button>
        <input class="input" bind:value={path} onkeydown={(e) => e.key === "Enter" && go(path)} aria-label="Folder path" />
        <button class="btn" onclick={() => go(path)}>Go</button>
      </div>
      {#if error}<div class="alert alert-error">{error}</div>{/if}
      <div class="min-h-48 flex-1 overflow-auto rounded-md border" style="border-color: var(--border)">
        {#each listing?.entries ?? [] as e}
          <div class="flex items-center gap-2 border-b px-2 py-1 text-sm" style="border-color: var(--border)">
            {#if e.selectable}
              <input type="checkbox" checked={picked.includes(e.path)} onchange={() => toggle(e.path)} aria-label="Select {e.name}" />
            {:else}<span class="w-[13px]"></span>{/if}
            {#if e.dir}
              <button class="flex-1 text-left hover:underline" onclick={() => go(e.path)}>📁 {e.name}</button>
            {:else}
              <span class="flex-1">📄 {e.name}</span>
              <span class="text-xs muted">{((e.size ?? 0) / 1024 / 1024).toFixed(1)} MB</span>
            {/if}
          </div>
        {:else}
          <div class="p-3 text-sm muted">No matching files in this folder.</div>
        {/each}
      </div>
      <div class="flex justify-end gap-2">
        <button class="btn" onclick={() => done([path])} title="Add every matching file in the current folder">Add whole folder</button>
        <button class="btn btn-primary" disabled={!picked.length} onclick={() => done(picked)}>Add {picked.length || ""} selected</button>
      </div>
    </div>
  </div>
{/if}
