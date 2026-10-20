<script lang="ts">
  // Renders markdown shipped with the app (docs/, workflow descriptions).
  import { marked } from "marked";
  let { source }: { source: string } = $props();
  const html = $derived(marked.parse(source ?? "", { async: false }) as string);
</script>

<div class="prose-md">{@html html}</div>
