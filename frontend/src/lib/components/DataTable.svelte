<script lang="ts">
  // Server-side paginated, sortable, searchable table. Only the visible page
  // is fetched, as with OpenMS-Insight's Table, so large result files stay fast.
  import type { TablePage as Page } from "../types";

  let {
    fetchPage,
    pageSize = 25,
    selectable = false,
    selected = $bindable<number[]>([]),
    downloadHref = "",
    caption = "",
  }: {
    fetchPage: (offset: number, limit: number, sort: string | null, desc: boolean, q: string) => Promise<Page>;
    pageSize?: number;
    selectable?: boolean;
    selected?: number[];
    downloadHref?: string;
    caption?: string;
  } = $props();

  let page = $state<Page | null>(null);
  let offset = $state(0);
  let sort = $state<string | null>(null);
  let desc = $state(false);
  let q = $state("");
  let qDebounced = $state("");
  let error = $state("");
  let loading = $state(false);
  let timer: ReturnType<typeof setTimeout>;

  $effect(() => {
    const v = q;
    clearTimeout(timer);
    timer = setTimeout(() => {
      qDebounced = v;
      offset = 0;
    }, 250);
  });

  $effect(() => {
    const args = [offset, pageSize, sort, desc, qDebounced] as const;
    loading = true;
    fetchPage(...args)
      .then((p) => {
        page = p;
        error = "";
      })
      .catch((e) => (error = e.message))
      .finally(() => (loading = false));
  });

  function toggleSort(c: string) {
    if (sort === c) desc = !desc;
    else {
      sort = c;
      desc = false;
    }
    offset = 0;
  }

  function toggleRow(id: number) {
    selected = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
  }

  function fmt(v: any, numeric?: boolean) {
    if (v === null || v === undefined) return "";
    if (numeric && typeof v === "number" && !Number.isInteger(v)) return Number(v.toPrecision(7)).toString();
    return String(v);
  }

  const last = $derived(page ? Math.max(0, Math.ceil(page.total / pageSize) - 1) : 0);
</script>

<div class="flex flex-col gap-2">
  <div class="flex flex-wrap items-center gap-2">
    <input class="input max-w-xs" placeholder="Search all columns" bind:value={q} aria-label="Search table" />
    {#if page}
      <span class="text-sm muted">
        {page.total.toLocaleString()} rows{#if page.unfiltered !== undefined && page.unfiltered !== page.total} (of {page.unfiltered.toLocaleString()}){/if}
        {#if selectable && selected.length} · {selected.length} selected
          <button class="underline" onclick={() => (selected = [])}>clear</button>{/if}
      </span>
    {/if}
    {#if loading}<span class="text-xs muted">loading…</span>{/if}
    <span class="flex-1"></span>
    {#if downloadHref}<a class="btn" href={downloadHref} download>⬇️ Download</a>{/if}
  </div>
  {#if caption}<div class="text-sm muted">{caption}</div>{/if}
  {#if error}
    <div class="alert alert-error">{error}</div>
  {:else if page}
    <div class="overflow-auto rounded-md border" style="border-color: var(--border)">
      <table class="w-full border-collapse text-sm">
        <thead style="background: var(--panel)">
          <tr>
            {#if selectable}<th class="w-8"></th>{/if}
            {#each page.columns as c}
              <th class="cursor-pointer whitespace-nowrap border-b px-2 py-1.5 text-left font-semibold select-none" style="border-color: var(--border)" onclick={() => toggleSort(c.name)}>
                {c.name}{sort === c.name ? (desc ? " ▼" : " ▲") : ""}
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each page.rows as row, i}
            {@const id = page.row_ids[i]}
            <tr
              class="border-b hover:bg-[var(--panel)]"
              class:cursor-pointer={selectable}
              style="border-color: var(--border); {selected.includes(id) ? 'background: color-mix(in srgb, var(--accent) 15%, transparent)' : ''}"
              onclick={() => selectable && toggleRow(id)}
            >
              {#if selectable}<td class="px-2"><input type="checkbox" checked={selected.includes(id)} onclick={(e) => e.stopPropagation()} onchange={() => toggleRow(id)} aria-label="Select row" /></td>{/if}
              {#each row as v, j}
                <td class="whitespace-nowrap px-2 py-1" class:text-right={page.columns[j].numeric}>{fmt(v, page.columns[j].numeric)}</td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class="flex items-center gap-2 text-sm">
      <button class="btn" disabled={offset === 0} onclick={() => (offset = 0)}>«</button>
      <button class="btn" disabled={offset === 0} onclick={() => (offset = Math.max(0, offset - pageSize))}>‹</button>
      <span>Page {Math.floor(offset / pageSize) + 1} of {last + 1}</span>
      <button class="btn" disabled={offset / pageSize >= last} onclick={() => (offset += pageSize)}>›</button>
      <button class="btn" disabled={offset / pageSize >= last} onclick={() => (offset = last * pageSize)}>»</button>
    </div>
  {/if}
</div>
