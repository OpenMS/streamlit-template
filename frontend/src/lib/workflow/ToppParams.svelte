<script lang="ts">
  // StreamlitUI.input_TOPP: every parameter of a TOPP tool's .ini, grouped by
  // section, advanced ones behind the page's toggle. Non-default values are
  // marked and can be reset one by one.
  import type { ToppParam } from "../types";
  import MultiSelect from "../components/MultiSelect.svelte";

  let {
    schema,
    advanced,
    displayToolName = true,
    onchange,
  }: {
    schema: { tool: string; instance: string; available: boolean; params: ToppParam[] };
    advanced: boolean;
    displayToolName?: boolean;
    onchange: (key: string, value: any) => void;
  } = $props();

  let filter = $state("");

  const visible = $derived(
    schema.params.filter(
      (p) =>
        (advanced || (!p.advanced && p.included)) &&
        (!filter || p.key.toLowerCase().includes(filter.toLowerCase()) || p.description.toLowerCase().includes(filter.toLowerCase())),
    ),
  );
  const sections = $derived.by(() => {
    const m = new Map<string, ToppParam[]>();
    for (const p of visible) {
      const s = p.section || "General";
      if (!m.has(s)) m.set(s, []);
      m.get(s)!.push(p);
    }
    return [...m.entries()];
  });
  const hidden = $derived(schema.params.length - schema.params.filter((p) => !p.advanced && p.included).length);
  const modified = $derived(schema.params.filter((p) => JSON.stringify(p.value) !== JSON.stringify(p.default)).length);

  function step(p: ToppParam) {
    if (p.type === "int") return 1;
    const v = Math.abs(Number(p.value));
    return v > 0 && v < 1 ? 10 ** Math.floor(Math.log10(v)) : "any";
  }

  function setNumber(p: ToppParam, s: string) {
    if (s === "") return;
    const v = p.type === "int" ? parseInt(s, 10) : parseFloat(s);
    if (!Number.isNaN(v)) onchange(p.key, v);
  }

  const isModified = (p: ToppParam) => JSON.stringify(p.value) !== JSON.stringify(p.default);
</script>

{#if !schema.available}
  <div class="alert alert-error">
    TOPP tool <b>{schema.tool}</b> not found. Install OpenMS and make sure its tools are on PATH.
  </div>
{:else}
  <div class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center gap-2">
      {#if displayToolName}<span class="font-semibold">{schema.instance}</span>{/if}
      <span class="text-xs muted">
        {schema.params.length} parameters{#if !advanced && hidden > 0}, {hidden} advanced hidden{/if}{#if modified > 0}, {modified} changed{/if}
      </span>
      <span class="flex-1"></span>
      <input class="input max-w-56" placeholder="Filter parameters" bind:value={filter} aria-label="Filter {schema.instance} parameters" />
    </div>
    {#each sections as [section, params]}
      <div>
        {#if section !== "General" || sections.length > 1}
          <div class="mb-1 text-sm font-semibold">{section.replaceAll(":", " › ")}</div>
          {#if params[0]?.section_description}<div class="mb-1 text-xs muted">{params[0].section_description}</div>{/if}
        {/if}
        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {#each params as p (p.key)}
            <div title={p.description}>
              <div class="mb-1 flex items-center gap-1 text-sm font-medium">
                <span class="truncate">{p.name}</span>
                {#if p.advanced}<span class="rounded px-1 text-[10px] muted" style="background: var(--code-bg)">advanced</span>{/if}
                {#if isModified(p)}
                  <button class="ml-auto text-xs underline muted" title="Reset to {JSON.stringify(p.default)}" onclick={() => onchange(p.key, p.default)}>reset</button>
                {/if}
              </div>
              {#if p.type === "bool"}
                <label class="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={p.value === "true" || p.value === true} onchange={(e) => onchange(p.key, e.currentTarget.checked ? "true" : "false")} />
                  {p.value === "true" || p.value === true ? "on" : "off"}
                </label>
              {:else if p.type === "string" && p.valid_strings.length}
                <select class="input" value={p.value} onchange={(e) => onchange(p.key, e.currentTarget.value)} aria-label={p.name}>
                  {#each p.valid_strings as v}<option value={v}>{v}</option>{/each}
                </select>
              {:else if p.type === "string"}
                <input class="input" value={p.value} onchange={(e) => onchange(p.key, e.currentTarget.value)} aria-label={p.name} />
              {:else if p.type === "int" || p.type === "double"}
                <input
                  class="input"
                  type="number"
                  value={p.value}
                  step={step(p)}
                  min={p.min ?? undefined}
                  max={p.max ?? undefined}
                  onchange={(e) => setNumber(p, e.currentTarget.value)}
                  aria-label={p.name}
                />
              {:else if p.valid_strings.length}
                <MultiSelect
                  label={p.name}
                  options={[...p.valid_strings].sort().map((v) => ({ value: v, label: v }))}
                  value={p.value}
                  onchange={(v) => onchange(p.key, v)}
                />
              {:else}
                <textarea
                  class="input font-mono"
                  rows="3"
                  value={(p.value ?? []).join("\n")}
                  onchange={(e) => onchange(p.key, e.currentTarget.value.split("\n").filter((x: string) => x.trim()))}
                  aria-label={p.name}
                ></textarea>
                <div class="text-xs muted">One entry per line.</div>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {:else}
      <div class="text-sm muted">No parameters match.</div>
    {/each}
  </div>
{/if}
