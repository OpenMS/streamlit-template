<script lang="ts">
  // Upload widget (StreamlitUI.upload_widget in local mode): add files from
  // this computer by drag and drop, by the file browser, or by folder path,
  // copied into the workspace or referenced in place.
  import type { FileEntry } from "../types";
  import FileBrowser from "./FileBrowser.svelte";

  let {
    name,
    fileTypes,
    files,
    onlyExample = false,
    onupload,
    onlocal,
    onremove,
    onremoveall,
  }: {
    name: string;
    fileTypes: string[];
    files: FileEntry[];
    onlyExample?: boolean;
    onupload: (files: File[]) => Promise<void>;
    onlocal: (paths: string[], copy: boolean) => Promise<void>;
    onremove: (f: FileEntry) => Promise<void>;
    onremoveall: () => Promise<void>;
  } = $props();

  let copy = $state(true);
  let browsing = $state(false);
  let folder = $state("");
  let busy = $state(false);
  let dragging = $state(false);
  let input: HTMLInputElement;

  const accept = $derived(fileTypes.map((t) => "." + t).join(","));

  async function run(fn: () => Promise<void>) {
    busy = true;
    try {
      await fn();
    } finally {
      busy = false;
    }
  }

  function dropped(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    const list = Array.from(e.dataTransfer?.files ?? []);
    if (list.length) run(() => onupload(list));
  }
</script>

<div class="grid gap-4 md:grid-cols-2">
  <div
    class="card flex flex-col items-center justify-center gap-2 border-dashed text-center"
    style={dragging ? "border-color: var(--accent)" : ""}
    role="region"
    aria-label="Drop files here"
    ondragover={(e) => {
      e.preventDefault();
      dragging = true;
    }}
    ondragleave={() => (dragging = false)}
    ondrop={dropped}
  >
    <div class="font-semibold">Add {name} from your computer</div>
    <div class="text-sm muted">Drop {fileTypes.join(", ")} files here, or</div>
    <div class="flex flex-wrap justify-center gap-2">
      <button class="btn btn-primary" disabled={busy} onclick={() => (browsing = true)}>📁 Browse this computer</button>
      <button class="btn" disabled={busy} onclick={() => input.click()}>Upload files</button>
    </div>
    <input
      bind:this={input}
      type="file"
      multiple
      {accept}
      class="hidden"
      onchange={() => input.files?.length && run(() => onupload(Array.from(input.files!)))}
    />
  </div>

  <div class="card flex flex-col gap-2">
    <div class="font-semibold">Or add {name} files from a local folder</div>
    <div class="flex gap-2">
      <input class="input" placeholder="/path/to/folder" bind:value={folder} aria-label="Folder path" />
      <button class="btn" disabled={busy || !folder.trim()} onclick={() => run(() => onlocal([folder.trim()], copy))}>Add</button>
    </div>
    <label class="flex items-center gap-2 text-sm">
      <input type="checkbox" bind:checked={copy} /> Make a copy of files
    </label>
    {#if !copy}
      <div class="alert alert-warning">
        Files will be referenced in place instead of copied into the workspace. Moving or deleting them breaks the workspace.
      </div>
    {/if}
  </div>
</div>

<FileBrowser bind:open={browsing} {fileTypes} onpick={(paths) => run(() => onlocal(paths, copy))} />

<div class="mt-4">
  {#if files.length}
    <div class="mb-2 flex items-center gap-2">
      <span class="font-semibold">{name} files ({files.length})</span>
      {#if onlyExample}<span class="text-sm muted">· example data, replaced by the first file you add</span>{/if}
      <span class="flex-1"></span>
      <button class="btn btn-danger" disabled={busy} onclick={() => confirm(`Remove all ${name} files?`) && run(onremoveall)}>Remove all</button>
    </div>
    <div class="overflow-auto rounded-md border" style="border-color: var(--border)">
      <table class="w-full text-sm">
        <tbody>
          {#each files as f}
            <tr class="border-b" style="border-color: var(--border)">
              <td class="px-2 py-1">{f.name}</td>
              <td class="px-2 py-1 muted">{f.reference ? "referenced: " + f.path : "copied"}</td>
              <td class="px-2 py-1 text-right muted">{f.missing ? "missing" : f.size}</td>
              <td class="w-10 px-2 py-1 text-right">
                <button class="btn" disabled={busy} onclick={() => run(() => onremove(f))} aria-label="Remove {f.name}">🗑️</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <div class="alert alert-info">No {name} files yet.</div>
  {/if}
</div>
