<script lang="ts">
  import type { Snippet } from "svelte";
  let { labels, children, active = $bindable(0) }: { labels: string[]; children: Snippet<[number]>; active?: number } = $props();
</script>

<div>
  <div class="mb-3 flex flex-wrap gap-1 border-b" style="border-color: var(--border)" role="tablist">
    {#each labels as label, i}
      <button
        role="tab"
        aria-selected={active === i}
        class="-mb-px border-b-2 px-3 py-1.5 text-sm font-medium"
        style={active === i ? "border-color: var(--accent); color: var(--accent)" : "border-color: transparent"}
        onclick={() => (active = i)}>{label}</button
      >
    {/each}
  </div>
  {@render children(active)}
</div>
