import { describe, expect, it } from "vitest";
import { tablePage, tableRows } from "../src/lib/backend/tables";
import { MemoryStore } from "../src/lib/storage/store";

describe("result tables", () => {
  it("pages, sorts and filters a TSV", async () => {
    const store = new MemoryStore();
    await store.write("r.tsv", "name\tvalue\na\t3\nb\t1\nc\t2\nab\tnan\n");
    const all = await tablePage(store, "r.tsv", { sort: "value", desc: true });
    expect(all.columns).toEqual([{ name: "name", numeric: false }, { name: "value", numeric: true }]);
    expect(all.rows).toEqual([["a", 3], ["c", 2], ["b", 1], ["ab", null]]);
    const q = await tablePage(store, "r.tsv", { q: "a", limit: 1 });
    expect([q.total, q.unfiltered, q.rows]).toEqual([2, 4, [["a", 3]]]);
    expect((await tableRows(store, "r.tsv", [2, 0], ["value"])).rows).toEqual([[2], [3]]);
  });
});
