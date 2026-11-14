<script lang="ts">
  // content/raw_data_viewer.py: spectra table, spectrum plot, TIC/BPC and a
  // binned peak map, read by OpenMS in the engine worker.
  import * as W from "../lib/backend/workspaces";
  import { engine } from "../lib/engine/client";
  import { app, store } from "../lib/state.svelte";
  import Plot from "../lib/components/Plot.svelte";
  import Tabs from "../lib/components/Tabs.svelte";
  import StaticTable from "../lib/components/StaticTable.svelte";

  let files = $state<{ name: string; path: string }[]>([]);
  let file = $state("");
  let overview = $state<any>(null);
  let spectrumIdx = $state<number | null>(null);
  let spectrum = $state<any>(null);
  let peakmap = $state<any>(null);
  let msLevel = $state(1);
  let cutoff = $state(5000);
  let error = $state("");
  let loading = $state(false);

  const path = $derived(files.find((f) => f.name === file)?.path ?? "");

  W.mzmlFiles(store, app.workspace).then((fs) => {
    files = fs;
    file = files[0]?.name ?? "";
  });
  W.getParams(store, app.workspace).then((p) => (cutoff = p["2D-map-intensity-cutoff"] ?? 5000));

  $effect(() => {
    if (!path) return;
    loading = true;
    overview = null;
    spectrum = null;
    peakmap = null;
    engine
      .call("mzml.overview", path)
      .then((o) => {
        overview = o;
        spectrumIdx = o.spectra[0]?.index ?? null;
        error = "";
      })
      .catch((e) => (error = e.message))
      .finally(() => (loading = false));
  });

  $effect(() => {
    if (!path || spectrumIdx === null) return;
    engine.call("mzml.spectrum", path, spectrumIdx).then((s) => (spectrum = s)).catch((e) => (error = e.message));
  });

  function loadPeakmap() {
    peakmap = null;
    W.putParams(store, app.workspace, { "2D-map-intensity-cutoff": cutoff });
    engine.call("mzml.peakMap", { path, ms_level: msLevel, intensity_cutoff: cutoff }).then((p) => (peakmap = p)).catch((e) => (error = e.message));
  }

  const spectraCols = ["index", "RT", "MS level", "precursor m/z", "max intensity m/z", "peaks", "TIC"];
</script>

<div class="flex flex-col gap-4">
  <h1 class="h1">👀 View MS data</h1>
  {#if !files.length}
    <div class="alert alert-info">No mzML files in this workspace. Add some on the File Upload page.</div>
  {:else}
    <label class="max-w-md"><span class="label">Choose a file</span>
      <select class="input" bind:value={file}>{#each files as f}<option value={f.name}>{f.name}</option>{/each}</select>
    </label>
    {#if error}<div class="alert alert-error">{error}</div>{/if}
    {#if loading}<p class="muted">Reading {file}…</p>{/if}
    {#if overview}
      <Tabs labels={["📈 Spectra", "📊 TIC / BPC", "🗺️ Peak map"]}>
        {#snippet children(active: number)}
          {#if active === 0}
            <div class="grid gap-4 xl:grid-cols-2">
              <div>
                <label class="mb-2 block max-w-xs"><span class="label">Spectrum</span>
                  <select class="input" bind:value={spectrumIdx}>
                    {#each overview.spectra as s}<option value={s.index}>#{s.index} · MS{s["MS level"]} · RT {s.RT.toFixed(2)}</option>{/each}
                  </select>
                </label>
                <StaticTable columns={spectraCols} rows={overview.spectra.map((s: any) => spectraCols.map((c) => s[c]))} filename="{file}-spectra" />
              </div>
              {#if spectrum}
                <Plot
                  filename="{file}-spectrum-{spectrum.index}"
                  data={[{ type: "scatter", mode: "lines", x: spectrum.mz.flatMap((m: number) => [m, m, null]), y: spectrum.intensity.flatMap((i: number) => [0, i, null]), line: { width: 1 }, hoverinfo: "x+y" }]}
                  layout={{ title: { text: `MS${spectrum.ms_level} spectrum @ RT ${spectrum.rt.toFixed(2)} s${spectrum.precursor_mz ? `, precursor ${spectrum.precursor_mz.toFixed(4)}` : ""}` }, xaxis: { title: { text: "m/z" } }, yaxis: { title: { text: "intensity" } }, showlegend: false }}
                />
              {/if}
            </div>
          {:else if active === 1}
            <Plot
              filename="{file}-tic-bpc"
              data={Object.entries(overview.chromatograms).flatMap(([lvl, c]: [string, any]) => [
                { type: "scatter", mode: "lines", name: `TIC MS${lvl}`, x: c.rt, y: c.tic },
                { type: "scatter", mode: "lines", name: `BPC MS${lvl}`, x: c.rt, y: c.bpc, visible: "legendonly" },
              ])}
              layout={{ xaxis: { title: { text: "retention time (s)" } }, yaxis: { title: { text: "intensity" } } }}
            />
          {:else}
            <div class="mb-3 flex flex-wrap items-end gap-3">
              <label><span class="label">MS level</span><select class="input" bind:value={msLevel}><option value={1}>MS1</option><option value={2}>MS2</option></select></label>
              <label><span class="label">Intensity cutoff</span><input class="input" type="number" min="0" bind:value={cutoff} /></label>
              <button class="btn btn-primary" onclick={loadPeakmap}>Show peak map</button>
            </div>
            {#if peakmap}
              <div class="mb-1 text-sm muted">{peakmap.rt.length.toLocaleString()} binned points from {peakmap.total_peaks.toLocaleString()} peaks</div>
              <Plot
                height={560}
                filename="{file}-peakmap"
                data={[{ type: "scattergl", mode: "markers", x: peakmap.rt, y: peakmap.mz, marker: { size: 3, color: peakmap.intensity.map((v: number) => Math.log10(v + 1)), colorscale: "Viridis", colorbar: { title: { text: "log10 int." } } }, hovertemplate: "RT %{x:.2f}<br>m/z %{y:.4f}<extra></extra>" }]}
                layout={{ xaxis: { title: { text: "retention time (s)" } }, yaxis: { title: { text: "m/z" } } }}
              />
            {/if}
          {/if}
        {/snippet}
      </Tabs>
    {/if}
  {/if}
</div>
