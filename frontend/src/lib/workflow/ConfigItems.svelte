<script lang="ts">
  // Renders a list of configure items (server/workflow_spec.py); runs of
  // consecutive Tab items become one tab bar, as st.tabs() does.
  import Self from "./ConfigItems.svelte";
  import Tabs from "../components/Tabs.svelte";
  import Markdown from "../components/Markdown.svelte";
  import MultiSelect from "../components/MultiSelect.svelte";
  import ToppParams from "./ToppParams.svelte";
  import WidgetInput from "./WidgetInput.svelte";

  let {
    items,
    values,
    advanced,
    setValue,
    setTopp,
  }: {
    items: any[];
    values: Record<string, any>;
    advanced: boolean;
    setValue: (key: string, v: any) => void;
    setTopp: (item: any, key: string, v: any) => void;
  } = $props();

  type Group = { tabs: any[] } | { item: any };
  const groups = $derived.by(() => {
    const out: Group[] = [];
    for (const it of items) {
      const prev = out[out.length - 1];
      if (it.type === "tab") {
        if (prev && "tabs" in prev) prev.tabs.push(it);
        else out.push({ tabs: [it] });
      } else out.push({ item: it });
    }
    return out;
  });

  function visible(it: any) {
    const c = it.visible_if;
    if (!c) return true;
    const v = values[c.key];
    if ("equals" in c) return v === c.equals;
    if ("in" in c) return c.in.includes(v);
    return !!v;
  }
</script>

<div class="flex flex-col gap-5">
  {#each groups as g}
    {#if "tabs" in g}
      <Tabs labels={g.tabs.map((t) => t.label)}>
        {#snippet children(active: number)}
          <Self items={g.tabs[active].items} {values} {advanced} {setValue} {setTopp} />
        {/snippet}
      </Tabs>
    {:else if visible(g.item)}
      {@const it = g.item}
      {#if it.type === "select-files"}
        <div>
          <div class="label">{it.name || it.key}</div>
          {#if !it.state.options.length}
            <div class="alert alert-warning">No {it.name || it.key} files. Add some on the File Upload page.</div>
          {:else if it.multiple}
            <MultiSelect label={it.name || it.key} options={it.state.options} value={values[it.key] ?? []} onchange={(v) => setValue(it.key, v)} />
          {:else}
            <select class="input" value={values[it.key]} onchange={(e) => setValue(it.key, e.currentTarget.value)}>
              {#each it.state.options as o}<option value={o.value}>{o.label}</option>{/each}
            </select>
          {/if}
        </div>
      {:else if it.type === "widget"}
        <div class="max-w-md">
          <WidgetInput
            name={it.name || it.key}
            value={values[it.key] ?? it.state.value}
            help={it.help}
            widgetType={it.widget_type}
            options={it.options}
            min={it.min_value}
            max={it.max_value}
            step={it.step_size}
            onchange={(v) => setValue(it.key, v)}
          />
        </div>
      {:else if it.type === "topp"}
        <ToppParams schema={it.schema} {advanced} displayToolName={it.display_tool_name} onchange={(k, v) => setTopp(it, k, v)} />
      {:else if it.type === "python"}
        {#if !it.schema.available}
          <div class="alert alert-error">Python tool {it.script} not found in src/python-tools.</div>
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
      {:else if it.type === "markdown"}
        <Markdown source={it.text} />
      {/if}
    {/if}
  {/each}
</div>
