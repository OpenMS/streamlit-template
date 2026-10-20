<script lang="ts">
  // content/documentation.py: the docs/*.md chapters, rendered in the app.
  import { api } from "../lib/api";
  import Markdown from "../lib/components/Markdown.svelte";

  let chapters = $state<{ title: string; file: string }[]>([]);
  let file = $state(localStorage.getItem("doc-chapter") ?? "");
  let md = $state("");

  api.get("/docs").then((c) => {
    chapters = c;
    if (!c.some((x: any) => x.file === file)) file = c[0]?.file ?? "";
  });

  $effect(() => {
    if (!file) return;
    try {
      localStorage.setItem("doc-chapter", file);
    } catch {}
    api.get(`/docs/${encodeURIComponent(file)}`).then((d) => (md = d.markdown));
  });
</script>

<h1 class="h1">Documentation</h1>
<label class="mb-4 block max-w-lg">
  <span class="label">Content</span>
  <select class="input" bind:value={file}>
    {#each chapters as c}<option value={c.file}>{c.title}</option>{/each}
  </select>
</label>
<div class="max-w-4xl"><Markdown source={md} /></div>
