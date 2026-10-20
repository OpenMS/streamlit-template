<script lang="ts">
  // monitor_hardware/monitor_storage, for an app that runs in the browser:
  // the browser storage the workspaces use, and the threads OpenMS gets.
  import { onDestroy } from "svelte";
  import { threadCount } from "../engine/client";
  import { app } from "../state.svelte";

  let usage = $state<{ usage: number; quota: number } | null>(null);

  async function poll() {
    try {
      const e = await navigator.storage.estimate();
      usage = { usage: e.usage ?? 0, quota: e.quota ?? 0 };
    } catch {
      usage = null;
    }
  }
  poll();
  const timer = setInterval(poll, 10000);
  onDestroy(() => clearInterval(timer));

  const gb = (b: number) => (b / 1024 ** 3).toFixed(2);
</script>

<details class="border-t pt-3 text-xs" style="border-color: var(--border)">
  <summary class="cursor-pointer text-sm font-semibold">📊 Resource utilization</summary>
  <div class="mt-2 grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
    <span>CPU cores</span>
    <span>{app.settings?.cpu_count}, OpenMS threads: {threadCount(app.settings?.max_threads ?? 4) || "none (page not isolated)"}</span>
    {#if usage}
      <span>Storage</span>
      <meter min="0" max={usage.quota || 1} value={usage.usage} title="{gb(usage.usage)} of {gb(usage.quota)} GB"></meter>
      <span></span>
      <span>{gb(usage.usage)} of {gb(usage.quota)} GB used</span>
    {/if}
  </div>
</details>
