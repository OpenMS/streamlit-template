<script lang="ts">
  // CPU, memory and disk of this machine (monitor_hardware/monitor_storage).
  import { onDestroy } from "svelte";
  import { api } from "../api";
  import { app } from "../state.svelte";

  type Sys = { cpu: number; ram_used: number; ram_total: number; disk_free: number; disk_total: number };
  let sys = $state<Sys | null>(null);

  async function poll() {
    try {
      sys = await api.get<Sys>(`/system?workspace=${encodeURIComponent(app.workspace)}`);
    } catch {
      sys = null;
    }
  }
  poll();
  const timer = setInterval(poll, 5000);
  onDestroy(() => clearInterval(timer));

  const gb = (b: number) => (b / 1024 ** 3).toFixed(1);
</script>

{#if sys}
  <details class="border-t pt-3 text-xs" style="border-color: var(--border)">
    <summary class="cursor-pointer text-sm font-semibold">📊 Resource utilization</summary>
    <div class="mt-2 grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
      <span>CPU</span>
      <meter min="0" max="100" value={sys.cpu} title="{sys.cpu.toFixed(0)} %"></meter>
      <span>Memory</span>
      <span>{gb(sys.ram_used)} / {gb(sys.ram_total)} GB</span>
      <span>Disk free</span>
      <span>{gb(sys.disk_free)} / {gb(sys.disk_total)} GB</span>
    </div>
  </details>
{/if}
