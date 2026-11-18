<script lang="ts">
  // Small tables that are already in the browser (toolbox results), with
  // client-side sorting, paging and CSV export (show_table()).
  import { saveText } from "../backend/files";

  let { columns, rows, filename = "table", pageSize = 25 }: { columns: string[]; rows: any[][]; filename?: string; pageSize?: number } = $props();

  let sortCol = $state(-1);
  let desc = $state(false);
  let pageIdx = $state(0);

  const sorted = $derived.by(() => {
    if (sortCol < 0) return rows;
    const s = [...rows].sort((a, b) => {
      const x = a[sortCol], y = b[sortCol];
      if (typeof x === "number" && typeof y === "number") return x - y;
      return String(x).localeCompare(String(y));
    });
    return desc ? s.reverse() : s;
  });
  const pages = $derived(Math.max(1, Math.ceil(sorted.length / pageSize)));
  const visible = $derived(sorted.slice(pageIdx * pageSize, (pageIdx + 1) * pageSize));

  function csv() {
    const esc = (v: any) => {
      let s = v === null || v === undefined ? "" : String(v);
      // keep spreadsheet programs from evaluating cell content as formulas
      if (/^[=+\-@]/.test(s) && isNaN(Number(s))) s = "'" + s;
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    saveText([columns, ...sorted].map((r) => r.map(esc).join(",")).join("\n"), `${filename}.csv`, "text/csv");
  }

  function fmt(v: any) {
    if (typeof v === "number" && !Number.isInteger(v)) return Number(v.toPrecision(8)).toString();
    return v ?? "";
  }
</script>

<div class="flex flex-col gap-2">
  <div class="overflow-auto rounded-md border" style="border-color: var(--border)">
    <table class="w-full border-collapse text-sm">
      <thead style="background: var(--panel)">
        <tr>
          {#each columns as c, i}
            <th class="cursor-pointer whitespace-nowrap border-b px-2 py-1.5 text-left font-semibold select-none" style="border-color: var(--border)" onclick={() => { desc = sortCol === i ? !desc : false; sortCol = i; }}>
              {c}{sortCol === i ? (desc ? " ▼" : " ▲") : ""}
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each visible as row}
          <tr class="border-b" style="border-color: var(--border)">
            {#each row as v}<td class="whitespace-nowrap px-2 py-1" class:text-right={typeof v === "number"}>{fmt(v)}</td>{/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <div class="flex items-center gap-2 text-sm">
    {#if pages > 1}
      <button class="btn" disabled={pageIdx === 0} onclick={() => pageIdx--}>‹</button>
      <span>Page {pageIdx + 1} of {pages}</span>
      <button class="btn" disabled={pageIdx >= pages - 1} onclick={() => pageIdx++}>›</button>
    {/if}
    <span class="muted">{rows.length.toLocaleString()} rows</span>
    <span class="flex-1"></span>
    <button class="btn" onclick={csv}>⬇️ CSV</button>
  </div>
</div>
