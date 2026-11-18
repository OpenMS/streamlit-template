<script lang="ts">
  // StreamlitUI.input_widget: one value, rendered by widget_type ("auto"
  // infers it from the default and the options).
  import MultiSelect from "../components/MultiSelect.svelte";

  let {
    name,
    value,
    help = "",
    widgetType = "auto",
    options = null,
    min = null,
    max = null,
    step = null,
    onchange,
  }: {
    name: string;
    value: any;
    help?: string;
    widgetType?: string;
    options?: any[] | null;
    min?: number | null;
    max?: number | null;
    step?: number | null;
    onchange: (v: any) => void;
  } = $props();

  const kind = $derived.by(() => {
    if (widgetType !== "auto") return widgetType;
    if (typeof value === "boolean") return "checkbox";
    if (options && Array.isArray(value)) return "multiselect";
    if (options) return "selectbox";
    if (typeof value === "number") return "number";
    if (typeof value === "string" && value.length > 30) return "textarea";
    return "text";
  });
  const isInt = $derived(typeof value === "number" && Number.isInteger(value) && (step === null || Number.isInteger(step)));

  function num(s: string) {
    if (s === "") return;
    const v = isInt ? parseInt(s, 10) : parseFloat(s);
    if (!Number.isNaN(v)) onchange(v);
  }
</script>

<div title={help}>
  {#if kind === "checkbox"}
    <label class="flex items-center gap-2 pt-6 text-sm font-medium">
      <input type="checkbox" checked={!!value} onchange={(e) => onchange(e.currentTarget.checked)} />
      {name}
    </label>
  {:else}
    <label class="label" for={null}>{name}</label>
    {#if kind === "selectbox"}
      <select class="input" value={value} onchange={(e) => onchange(options![e.currentTarget.selectedIndex])} aria-label={name}>
        {#each options ?? [] as o}<option value={o}>{o}</option>{/each}
      </select>
    {:else if kind === "multiselect"}
      <MultiSelect label={name} options={(options ?? []).map((o) => ({ value: o, label: String(o) }))} value={value ?? []} {onchange} />
    {:else if kind === "slider"}
      <div class="flex items-center gap-2">
        <input type="range" class="flex-1" min={min ?? 0} max={max ?? 100} step={step ?? 1} {value} oninput={(e) => num(e.currentTarget.value)} aria-label={name} />
        <span class="w-12 text-right text-sm tabular-nums">{value}</span>
      </div>
    {:else if kind === "number"}
      <input class="input" type="number" min={min ?? undefined} max={max ?? undefined} step={step ?? (isInt ? 1 : "any")} {value} onchange={(e) => num(e.currentTarget.value)} aria-label={name} />
    {:else if kind === "textarea"}
      <textarea class="input" rows="3" {value} onchange={(e) => onchange(e.currentTarget.value)} aria-label={name}></textarea>
    {:else if kind === "password"}
      <input class="input" type="password" {value} onchange={(e) => onchange(e.currentTarget.value)} aria-label={name} />
    {:else}
      <input class="input" {value} onchange={(e) => onchange(e.currentTarget.value)} aria-label={name} />
    {/if}
  {/if}
  {#if help && kind !== "checkbox"}<div class="mt-0.5 text-xs muted">{help}</div>{/if}
</div>
