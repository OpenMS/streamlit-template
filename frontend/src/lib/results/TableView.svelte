<script lang="ts">
  // Any TSV/CSV in the workflow directory as a server-paginated table.
  import { api, enc } from "../api";
  import { app } from "../state.svelte";
  import DataTable from "../components/DataTable.svelte";

  let { slug, file, selected = $bindable<number[]>([]), selectable = false, caption = "" }: {
    slug: string;
    file: string;
    selected?: number[];
    selectable?: boolean;
    caption?: string;
  } = $props();

  const base = $derived(`/ws/${enc(app.workspace)}/wf/${slug}`);
  const fetchPage = (offset: number, limit: number, sort: string | null, desc: boolean, q: string) =>
    api.get(`${base}/table?path=${enc(file)}&offset=${offset}&limit=${limit}${sort ? `&sort=${enc(sort)}&desc=${desc}` : ""}${q ? `&q=${enc(q)}` : ""}`);
  const href = $derived(file.startsWith("results/") ? `/api${base}/results/file?path=${enc(file.slice(8))}` : "");
</script>

<DataTable {fetchPage} {selectable} bind:selected downloadHref={href} {caption} />
