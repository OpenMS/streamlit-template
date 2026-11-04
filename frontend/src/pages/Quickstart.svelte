<script lang="ts">
  import { navigate } from "../lib/state.svelte";
  import { app } from "../lib/state.svelte";

  const PROMPT =
    "Clone https://github.com/OpenMS/streamlit-template into a new folder, then read .claude/skills/notebook-to-webapp/SKILL.md inside that clone and follow it to turn my Jupyter notebook into a web app. Ask me for the path to the notebook, what to call the app, and how each page should look as you build it.";

  let copied = $state(false);
  async function copy() {
    await navigator.clipboard.writeText(PROMPT);
    copied = true;
    setTimeout(() => (copied = false), 2000);
  }
</script>

<div class="flex max-w-4xl flex-col gap-6">
  <div>
    <h1 class="h1">👋 Quick Start</h1>
    <p class="text-lg">Mass spectrometry analysis, as web apps that run in your browser, on your own computer.</p>
    <p class="text-sm muted">
      {app.settings?.app_name}: the Svelte edition of the OpenMS WebApp template, the template behind FLASHApp, Umetaflow and OpenDDA. Everything here
      runs locally: OpenMS itself runs in this browser as WebAssembly, your files are kept in the browser's storage on this machine, and nothing is
      uploaded unless you click "Share workspace".
    </p>
  </div>

  <section class="card flex flex-col gap-2">
    <h2 class="text-lg font-semibold">📓 Turn a Jupyter notebook into an app</h2>
    <p class="text-sm">Paste the prompt below into <b>Claude Code</b>. It reads your notebook and builds the app with you, page by page.</p>
    <pre class="code">{PROMPT}</pre>
    <div class="flex gap-2">
      <button class="btn" onclick={copy}>{copied ? "Copied" : "Copy prompt"}</button>
      <button class="btn" onclick={() => navigate("documentation")}>➡️ Read the walkthrough</button>
    </div>
  </section>

  <section>
    <h2 class="h2">⭐ Features</h2>
    <ul class="list-disc pl-6 text-sm leading-relaxed">
      <li>Simple workflows on <b>OpenMS</b>, compiled to WebAssembly</li>
      <li>Complex workflows built from <b>OpenMS tools</b>, run in a background worker with OpenMS threads</li>
      <li>Workspaces holding input files, parameters and results, in the layout of the Streamlit app, exported and imported as ZIP</li>
      <li>Persistent parameters, presets, and parameter import and export</li>
      <li>No server, account or internet connection needed once loaded; sharing a workspace is one optional click</li>
    </ul>
  </section>

  <section>
    <h2 class="h2">🖥️ Workspaces and settings</h2>
    <p class="text-sm">
      The sidebar holds the <b>workspaces</b> and the <b>settings</b>. A workspace stores the inputs, parameters and results of one analysis; create one per
      project, or load demo data into it. Settings apply to every page, such as the image export format of plots.
    </p>
  </section>

  <section>
    <h2 class="h2">Example pages</h2>
    <h3 class="font-semibold">1. 🚀 TOPP Workflow Framework</h3>
    <p class="text-sm">A standard four-step interface: <b>File Upload</b>, <b>Configure</b> (widgets for every tool parameter, generated from the OpenMS algorithm defaults), <b>Run</b> (start, stop, live log) and <b>Results</b>.</p>
    <div class="my-2 flex flex-wrap gap-2">
      <button class="btn" onclick={() => navigate("topp-workflow/upload")}>➡️ Play with the example workflow</button>
    </div>
    <h3 class="mt-3 font-semibold">2. 🐍 Custom workflows with OpenMS</h3>
    <div class="my-2 flex flex-wrap gap-2">
      <button class="btn" onclick={() => navigate("mzml/upload")}>➡️ Upload mzML files</button>
      <button class="btn" onclick={() => navigate("mzml/view")}>➡️ View MS data</button>
      <button class="btn" onclick={() => navigate("mzml/workflow")}>➡️ Run a small workflow</button>
    </div>
    <h3 class="mt-3 font-semibold">3. 🧰 OpenMS toolbox</h3>
    <div class="my-2 flex flex-wrap gap-2">
      <button class="btn" onclick={() => navigate("digest")}>✂️ In silico digest</button>
      <button class="btn" onclick={() => navigate("mz-calculator")}>⚖️ m/z calculator</button>
      <button class="btn" onclick={() => navigate("isotope-pattern")}>📶 Isotope patterns</button>
      <button class="btn" onclick={() => navigate("fragmentation")}>💥 Fragment ions</button>
    </div>
  </section>
</div>
