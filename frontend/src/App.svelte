<script lang="ts">
  import { onMount } from "svelte";
  import { app, init, navigate, toasts } from "./lib/state.svelte";
  import { sections } from "./nav";
  import Sidebar from "./lib/components/Sidebar.svelte";

  let error = $state("");
  let ready = $state(false);
  let menuOpen = $state(false);

  onMount(() => {
    init()
      .then(() => (ready = true))
      .catch((e) => (error = `The app could not start: ${e.message}`));
  });

  const nav = $derived(sections(app.settings?.app_name ?? "OpenMS WebApp"));
  const page = $derived(nav.flatMap((s) => s.pages).find((p) => p.route === app.route));

  $effect(() => {
    // unknown route: back to the start page
    if (ready && !page) navigate("quickstart");
  });
</script>

<div class="flex min-h-screen">
  <aside
    class="fixed inset-y-0 left-0 z-30 w-72 shrink-0 overflow-y-auto border-r transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0"
    class:-translate-x-full={!menuOpen}
    style="border-color: var(--border); background: var(--panel)"
  >
    {#if ready}<Sidebar {nav} onnavigate={() => (menuOpen = false)} />{/if}
  </aside>

  <main class="min-w-0 flex-1 px-4 py-6 md:px-10">
    <button class="btn mb-4 md:hidden" onclick={() => (menuOpen = !menuOpen)} aria-label="Menu">☰ Menu</button>
    {#if error}
      <div class="alert alert-error">{error}</div>
    {:else if !ready}
      <p class="muted">Loading…</p>
    {:else}
      {#if !crossOriginIsolated}
        <div class="alert alert-warning mb-4">
          This page is not cross-origin isolated, so OpenMS cannot start its threads and may not load. Open the app with
          <code>python serve.py</code> (or <code>npm run dev</code>), which sends the headers it needs.
        </div>
      {/if}
      {#if !app.persistent}
        <div class="alert alert-warning mb-4">This browser gives the app no persistent storage: workspaces are lost when the page closes.</div>
      {/if}
      {#if page}
        {#key `${page.route}|${app.workspace}|${app.epoch}`}
          <page.component {...page.props ?? {}} />
        {/key}
      {/if}
    {/if}
  </main>
</div>

<div class="fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
  {#each toasts as t (t.id)}
    <div class="alert alert-{t.kind} shadow-md" style="background: var(--bg)" role="status">{t.text}</div>
  {/each}
</div>
