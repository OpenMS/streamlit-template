<script lang="ts">
  // Plotly figure with the app's image export format (show_fig()).
  import { onDestroy } from "svelte";
  import { app } from "../state.svelte";

  let {
    data,
    layout = {},
    filename = "figure",
    height = 420,
    onclick,
    onselected,
  }: {
    data: any[];
    layout?: Record<string, any>;
    filename?: string;
    height?: number;
    onclick?: (e: any) => void;
    onselected?: (e: any) => void;
  } = $props();

  let el: HTMLDivElement;
  let Plotly: any = null;

  const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;

  $effect(() => {
    const fig = { data, layout, format: app.imageFormat, height };
    (async () => {
      Plotly ??= (await import("plotly.js-dist-min")).default;
      const base = {
        margin: { l: 60, r: 20, t: 40, b: 50 },
        height: fig.height,
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: dark ? "#e6e8ef" : "#1d2130" },
        xaxis: { gridcolor: dark ? "#2d3242" : "#e5e7ef" },
        yaxis: { gridcolor: dark ? "#2d3242" : "#e5e7ef" },
      };
      const merged = { ...base, ...fig.layout, xaxis: { ...base.xaxis, ...(fig.layout.xaxis ?? {}) }, yaxis: { ...base.yaxis, ...(fig.layout.yaxis ?? {}) } };
      await Plotly.react(el, fig.data, merged, {
        responsive: true,
        displaylogo: false,
        toImageButtonOptions: { format: fig.format, filename },
      });
      (el as any).removeAllListeners?.("plotly_click");
      (el as any).removeAllListeners?.("plotly_selected");
      if (onclick) (el as any).on("plotly_click", onclick);
      if (onselected) (el as any).on("plotly_selected", onselected);
    })();
  });

  onDestroy(() => Plotly?.purge(el));
</script>

<div bind:this={el} class="w-full"></div>
