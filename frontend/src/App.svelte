<script lang="ts">
  import { onMount } from "svelte";
  import { app, loadSettings, navigate, toasts } from "./lib/state.svelte";
  import { sections } from "./nav";
  import Sidebar from "./lib/components/Sidebar.svelte";

  let error = $state("");
  let menuOpen = $state(false);

  onMount(() => {
    loadSettings().catch((e) => (error = `Cannot reach the local server: ${e.message}`));
  });

  const nav = $derived(sections(app.settings?.app_name ?? "OpenMS WebApp"));
  const page = $derived(nav.flatMap((s) => s.pages).find((p) => p.route === app.route));

  $effect(() => {
    // unknown route: back to the start page
    if (app.settings && !page) navigate("quickstart");
  });
</script>

<div class="flex min-h-screen">
  <aside
    class="fixed inset-y-0 left-0 z-30 w-72 shrink-0 overflow-y-auto border-r transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0"
    class:-translate-x-full={!menuOpen}
    style="border-color: var(--border); background: var(--panel)"
  >
    <Sidebar {nav} onnavigate={() => (menuOpen = false)} />
  </aside>

  <main class="min-w-0 flex-1 px-4 py-6 md:px-10">
    <button class="btn mb-4 md:hidden" onclick={() => (menuOpen = !menuOpen)} aria-label="Menu">☰ Menu</button>
    {#if error}
      <div class="alert alert-error">{error}</div>
    {:else if !app.settings}
      <p class="muted">Loading…</p>
    {:else if page}
      {#key `${page.route}|${app.workspace}|${app.epoch}`}
        <page.component {...page.props ?? {}} />
      {/key}
    {/if}
  </main>
</div>

<div class="fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
  {#each toasts as t (t.id)}
    <div class="alert alert-{t.kind} shadow-md" style="background: var(--bg)" role="status">{t.text}</div>
  {/each}
</div>
