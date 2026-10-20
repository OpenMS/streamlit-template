<script lang="ts">
  // Any TSV/CSV/JSON file of the workflow directory as a paginated table:
  // the file is parsed once, and only the visible page is rendered.
  import { tablePage } from "../backend/tables";
  import { saveFile } from "../backend/files";
  import { join } from "../storage/store";
  import { store, toastError } from "../state.svelte";
  import DataTable from "../components/DataTable.svelte";

  let { workflowDir, file, selected = $bindable<number[]>([]), selectable = false, caption = "" }: {
    workflowDir: string;
    file: string;
    selected?: number[];
    selectable?: boolean;
    caption?: string;
  } = $props();

  const path = $derived(join(workflowDir, file));
  const fetchPage = (offset: number, limit: number, sort: string | null, desc: boolean, q: string) => tablePage(store, path, { offset, limit, sort, desc, q });
</script>

<DataTable {fetchPage} {selectable} bind:selected ondownload={() => saveFile(store, path).catch(toastError)} {caption} />
