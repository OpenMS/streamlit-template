<script lang="ts">
  // Multi-select as a checkbox list with select-all, for file pickers and
  // TOPP list parameters with valid strings.
  let {
    options,
    value,
    onchange,
    label = "",
  }: { options: { value: any; label: string }[]; value: any[]; onchange: (v: any[]) => void; label?: string } = $props();

  const all = $derived(options.length > 0 && options.every((o) => value.includes(o.value)));

  function toggle(v: any) {
    onchange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  }
</script>

<div class="rounded-md border" style="border-color: var(--border); background: var(--bg)" role="group" aria-label={label}>
  {#if options.length > 1}
    <label class="flex items-center gap-2 border-b px-2 py-1 text-xs muted" style="border-color: var(--border)">
      <input type="checkbox" checked={all} onchange={() => onchange(all ? [] : options.map((o) => o.value))} /> select all
    </label>
  {/if}
  <div class="max-h-48 overflow-auto">
    {#each options as o}
      <label class="flex items-center gap-2 px-2 py-0.5 text-sm">
        <input type="checkbox" checked={value.includes(o.value)} onchange={() => toggle(o.value)} />
        {o.label}
      </label>
    {:else}
      <div class="px-2 py-1 text-sm muted">No options</div>
    {/each}
  </div>
</div>
