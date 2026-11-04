<script lang="ts">
  // Upload widget (StreamlitUI.upload_widget): add files from this computer by
  // drag and drop, by picking files, or by picking a folder (its files of the
  // accepted types). Files are copied into the workspace in this browser's
  // storage; they are never sent anywhere.
  import type { FileEntry } from "../types";

  let {
    name,
    fileTypes,
    files,
    onlyExample = false,
    onupload,
    onremove,
    onremoveall,
  }: {
    name: string;
    fileTypes: string[];
    files: FileEntry[];
    onlyExample?: boolean;
    onupload: (files: File[]) => Promise<void>;
    onremove: (f: FileEntry) => Promise<void>;
    onremoveall: () => Promise<void>;
  } = $props();

  let busy = $state(false);
  let dragging = $state(false);
  let input: HTMLInputElement;
  let folderInput: HTMLInputElement;

  const accept = $derived(fileTypes.map((t) => "." + t).join(","));
  const fits = (f: File) => !fileTypes.length || fileTypes.some((t) => f.name.toLowerCase().endsWith(`.${t.toLowerCase()}`));

  async function run(fn: () => Promise<void>) {
    busy = true;
    try {
      await fn();
    } finally {
      busy = false;
    }
  }

  // Dropped folders are read through the entries API, recursively
  async function entryFiles(entry: any): Promise<File[]> {
    if (entry.isFile) return [await new Promise<File>((res, rej) => entry.file(res, rej))];
    const reader = entry.createReader();
    const out: File[] = [];
    for (;;) {
      const batch: any[] = await new Promise((res, rej) => reader.readEntries(res, rej));
      if (!batch.length) return out;
      for (const e of batch) out.push(...(await entryFiles(e)));
    }
  }

  async function dropped(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    const items = Array.from(e.dataTransfer?.items ?? []);
    const entries = items.map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
    const list = entries.length ? (await Promise.all(entries.map(entryFiles))).flat().filter((f) => fits(f) || entries.length === 1) : Array.from(e.dataTransfer?.files ?? []);
    if (list.length) run(() => onupload(list));
  }
</script>

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
  <div class="text-sm muted">Drop {fileTypes.join(", ")} files or folders here, or</div>
  <div class="flex flex-wrap justify-center gap-2">
    <button class="btn btn-primary" disabled={busy} onclick={() => input.click()}>📄 Pick files</button>
    <button class="btn" disabled={busy} onclick={() => folderInput.click()}>📁 Pick a folder</button>
  </div>
  <div class="text-xs muted">Files are copied into this browser's storage and stay on this computer.</div>
  <input bind:this={input} type="file" multiple {accept} class="hidden" onchange={() => input.files?.length && run(() => onupload(Array.from(input.files!)))} />
  <input
    bind:this={folderInput}
    type="file"
    webkitdirectory
    class="hidden"
    onchange={() => folderInput.files?.length && run(() => onupload(Array.from(folderInput.files!).filter(fits)))}
  />
</div>

<div class="mt-4">
  {#if busy}<div class="alert alert-info mb-2">Copying files…</div>{/if}
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
              <td class="px-2 py-1 text-right muted">{f.size}</td>
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
