<script lang="ts">
  // The workflow's results page: one registered component per ResultView.
  import { resultComponents } from "../results/registry";
  import type { WorkflowSpec } from "./spec";

  let { workflowDir, spec }: { workflowDir: string; spec: WorkflowSpec } = $props();
</script>

<div class="flex flex-col gap-6">
  {#each spec.results as view}
    {@const Comp = resultComponents[view.component]}
    <section>
      {#if view.title}<h2 class="h2">{view.title}</h2>{/if}
      {#if Comp}
        <Comp {workflowDir} {...view.props} />
      {:else}
        <div class="alert alert-error">No result component named "{view.component}" in frontend/src/lib/results/registry.ts.</div>
      {/if}
    </section>
  {:else}
    <div class="alert alert-info">This workflow defines no result views.</div>
  {/each}
</div>
