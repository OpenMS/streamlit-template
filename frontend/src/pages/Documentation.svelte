<script lang="ts">
  // content/documentation.py: the docs/*.md chapters, rendered in the app.
  import { DOCS } from "../lib/assets";
  import Markdown from "../lib/components/Markdown.svelte";

  const saved = localStorage.getItem("doc-chapter");
  let file = $state(DOCS.some((d) => d.file === saved) ? saved! : (DOCS[0]?.file ?? ""));
  const md = $derived(DOCS.find((d) => d.file === file)?.markdown ?? "");

  $effect(() => {
    try {
      localStorage.setItem("doc-chapter", file);
    } catch {}
  });
</script>

<h1 class="h1">Documentation</h1>
<label class="mb-4 block max-w-lg">
  <span class="label">Content</span>
  <select class="input" bind:value={file}>
    {#each DOCS as c}<option value={c.file}>{c.title}</option>{/each}
  </select>
</label>
<div class="max-w-4xl"><Markdown source={md} /></div>
