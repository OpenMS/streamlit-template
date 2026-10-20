<script lang="ts">
  // OpenMS-Insight components, rendered by Insight's own Vue bundle.
  //
  // Each component is an iframe of the bundle, which expects to be a Streamlit
  // custom component. This host speaks that protocol to it: it answers
  // componentReady and setComponentValue with streamlit:render messages, whose
  // arguments the local server computes by running the dashboard through
  // Insight's unchanged Python bridge (server/insight.py).
  import { api, enc } from "../api";
  import { app } from "../state.svelte";

  let { slug, dashboard }: { slug: string; dashboard: string } = $props();

  type Frame = { key: string; height: number | null; args: Record<string, unknown>; dfs: { key: string; value: Record<string, string> }[] };

  // One viewer session per page load, so selections survive switching pages
  const session = ((globalThis as any).__insightSession ??= crypto.randomUUID());

  // Raw: the messages posted to the iframes must be structured-clonable, not proxies
  let frames = $state.raw<Frame[]>([]);
  let available = $state<boolean | null>(null);
  let error = $state("");
  const heights = $state<Record<string, number>>({});
  const iframes: Record<string, HTMLIFrameElement> = {};
  const ready = new Set<string>();

  const bytes = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

  function theme() {
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const css = getComputedStyle(document.documentElement);
    const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
    return {
      base: dark ? "dark" : "light",
      primaryColor: v("--accent", "#29379b"),
      backgroundColor: v("--bg", dark ? "#12141b" : "#ffffff"),
      secondaryBackgroundColor: v("--panel", dark ? "#1b1e28" : "#f6f7fb"),
      textColor: v("--text", dark ? "#e6e8ef" : "#1d2130"),
      font: "sans serif",
    };
  }

  function send(frame: Frame) {
    const win = iframes[frame.key]?.contentWindow;
    if (!win || !ready.has(frame.key)) return;
    win.postMessage(
      {
        type: "streamlit:render",
        args: frame.args,
        dfs: frame.dfs.map((d) => ({
          key: d.key,
          value: { data: { data: bytes(d.value.data), index: bytes(d.value.index), columns: bytes(d.value.columns) } },
        })),
        disabled: false,
        theme: theme(),
      },
      "*",
    );
  }

  // Requests run one at a time, as Streamlit runs one script at a time; values
  // that arrive meanwhile are coalesced per component.
  let busy = false;
  const pending = new Map<string, unknown>();

  async function run(update?: { key: string; value: unknown }) {
    const base = `/ws/${enc(app.workspace)}/wf/${slug}/insight`;
    try {
      const r = await api.post(base, { dashboard, session, ...(update ?? {}) });
      available = r.available;
      frames = r.components;
      error = "";
      for (const f of frames) send(f);
    } catch (e: any) {
      error = e.message;
    }
  }

  async function drain() {
    if (busy) return;
    busy = true;
    try {
      while (pending.size) {
        const [key, value] = pending.entries().next().value!;
        pending.delete(key);
        await run({ key, value });
      }
    } finally {
      busy = false;
    }
  }

  function onMessage(ev: MessageEvent) {
    const msg = ev.data;
    if (!msg?.isStreamlitMessage) return;
    const key = Object.keys(iframes).find((k) => iframes[k]?.contentWindow === ev.source);
    if (!key) return;
    if (msg.type === "streamlit:componentReady") {
      ready.add(key);
      const f = frames.find((f) => f.key === key);
      if (f) send(f);
    } else if (msg.type === "streamlit:setFrameHeight") {
      heights[key] = msg.height;
    } else if (msg.type === "streamlit:setComponentValue") {
      pending.set(key, msg.value);
      drain();
    }
  }

  $effect(() => {
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  });

  $effect(() => {
    void app.workspace;
    void app.epoch;
    ready.clear();
    run();
  });
</script>

{#if available === false}
  <div class="alert alert-info">
    This view uses OpenMS-Insight, which is not installed. Install it with
    <code class="code">pip install openms-insight</code> and restart the app.
  </div>
{:else if error}
  <div class="alert alert-error">{error}</div>
{:else if available && !frames.length}
  <div class="alert alert-warning">Nothing to show yet. Please run the workflow first.</div>
{/if}

<div class="flex flex-col gap-3">
  {#each frames as frame (frame.key)}
    <iframe
      bind:this={iframes[frame.key]}
      src="/insight-component/index.html"
      title={frame.key}
      class="w-full rounded border-0"
      style="height: {heights[frame.key] ?? frame.height ?? 400}px"
    ></iframe>
  {/each}
</div>
