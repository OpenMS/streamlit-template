<script lang="ts">
  // Renders a list of configure items (spec.ts, resolved by backend/workflow.ts); runs of
  // consecutive Tab items become one tab bar, as st.tabs() does.
  import Self from "./ConfigItems.svelte";
  import Tabs from "../components/Tabs.svelte";
  import Markdown from "../components/Markdown.svelte";
  import MultiSelect from "../components/MultiSelect.svelte";
  import ToppParams from "./ToppParams.svelte";
  import WidgetInput from "./WidgetInput.svelte";
  import type { Resolved } from "../backend/workflow";

  let {
    items,
    values,
    advanced,
    setValue,
    setTool,
  }: {
    items: Resolved[];
    values: Record<string, any>;
    advanced: boolean;
    setValue: (key: string, v: any) => void;
    setTool: (item: any, key: string, v: any) => void;
  } = $props();

  type Group = { tabs: any[] } | { item: any };
  const groups = $derived.by(() => {
    const out: Group[] = [];
    for (const it of items) {
      const prev = out[out.length - 1];
      if (it.kind === "tab") {
        if (prev && "tabs" in prev) prev.tabs.push(it);
        else out.push({ tabs: [it] });
      } else out.push({ item: it });
    }
    return out;
  });

  function visible(it: any) {
    const c = it.visibleIf;
    if (!c) return true;
    return values[c.key] === c.equals;
  }
</script>

<div class="flex flex-col gap-5">
  {#each groups as g}
    {#if "tabs" in g}
      <Tabs labels={g.tabs.map((t) => t.title)}>
        {#snippet children(active: number)}
          <Self items={g.tabs[active].items} {values} {advanced} {setValue} {setTool} />
        {/snippet}
      </Tabs>
    {:else if visible(g.item)}
      {@const it = g.item}
      {#if it.kind === "select-files"}
        <div>
          <div class="label">{it.name || it.key}</div>
          {#if !it.options.length}
            <div class="alert alert-warning">No {it.name || it.key} files. Add some on the File Upload page.</div>
          {:else if it.multiple}
            <MultiSelect label={it.name || it.key} options={it.options} value={values[it.key] ?? []} onchange={(v) => setValue(it.key, v)} />
          {:else}
            <select class="input" value={values[it.key]} onchange={(e) => setValue(it.key, e.currentTarget.value)}>
              {#each it.options as o}<option value={o.value}>{o.label}</option>{/each}
            </select>
          {/if}
        </div>
      {:else if it.kind === "widget"}
        <div class="max-w-md">
          <WidgetInput
            name={it.name || it.key}
            value={values[it.key] ?? it.value}
            help={it.help}
            widgetType={it.widgetType}
            options={it.options}
            min={it.min}
            max={it.max}
            step={it.step}
            onchange={(v) => setValue(it.key, v)}
          />
        </div>
      {:else if it.kind === "tool"}
        <ToppParams schema={it.schema} {advanced} displayToolName={it.displayToolName ?? true} onchange={(k, v) => setTool(it, k, v)} />
      {:else if it.kind === "step"}
        {#if !it.schema.available}
          <div class="alert alert-error">Step {it.step} not found in src/steps.</div>
        {:else}
          <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {#each it.schema.params.filter((p: any) => advanced || !p.advanced) as p (p.key)}
              <WidgetInput
                name={p.name}
                value={values[p.key] ?? p.value}
                help={p.help}
                widgetType={p.widget_type}
                options={p.options}
                min={p.min}
                max={p.max}
                step={p.step_size}
                onchange={(v) => setValue(p.key, v)}
              />
            {/each}
          </div>
        {/if}
      {:else if it.kind === "markdown"}
        <Markdown source={it.text} />
      {/if}
    {/if}
  {/each}
</div>
