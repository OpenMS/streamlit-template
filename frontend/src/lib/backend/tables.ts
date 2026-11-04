// Tables of result files (tsv, csv, json), parsed once per file version and
// paged in the page, so a table component renders only the visible rows.

import type { Store } from "../storage/store";
import type { TablePage } from "../types";

type Frame = { columns: { name: string; numeric: boolean }[]; rows: any[][] };
const cache = new Map<string, Frame>();

function parseDelimited(text: string, sep: string): Frame {
  const lines = text.split(/\r?\n/).filter((l) => l.length);
  const unquote = (s: string) => (s.length > 1 && s.startsWith('"') && s.endsWith('"') ? s.slice(1, -1).replace(/""/g, '"') : s);
  const header = lines[0]?.split(sep).map(unquote) ?? [];
  const raw = lines.slice(1).map((l) => l.split(sep).map(unquote));
  const numeric = header.map((_, j) => raw.every((r) => r[j] === undefined || r[j] === "" || r[j] === "nan" || !Number.isNaN(Number(r[j]))));
  const rows = raw.map((r) => header.map((_, j) => (numeric[j] ? (r[j] === "" || r[j] === "nan" || r[j] === undefined ? null : Number(r[j])) : (r[j] ?? null))));
  return { columns: header.map((name, j) => ({ name, numeric: numeric[j] })), rows };
}

export function parseTable(name: string, text: string): Frame {
  const ext = name.toLowerCase().split(".").at(-1);
  if (ext === "tsv" || ext === "txt" || ext === "tab") return parseDelimited(text, "\t");
  if (ext === "csv") return parseDelimited(text, ",");
  if (ext === "json") {
    const records: Record<string, unknown>[] = JSON.parse(text);
    const names = [...new Set(records.flatMap((r) => Object.keys(r)))];
    const rows = records.map((r) => names.map((n) => r[n] ?? null));
    return { columns: names.map((name, j) => ({ name, numeric: rows.every((r) => r[j] === null || typeof r[j] === "number") })), rows };
  }
  throw new Error(`Unsupported table format: .${ext}`);
}

export async function loadTable(store: Store, path: string): Promise<Frame> {
  const f = await store.file(path);
  if (!f) throw new Error("File not found. Run the workflow first.");
  const key = `${path}|${f.lastModified}|${f.size}`;
  let frame = cache.get(key);
  if (!frame) {
    frame = parseTable(path, await f.text());
    if (cache.size >= 8) cache.delete(cache.keys().next().value!);
    cache.set(key, frame);
  }
  return frame;
}

export type PageRequest = { offset?: number; limit?: number; sort?: string | null; desc?: boolean; q?: string | null };

/** One page, filtered (any cell contains q) and sorted; row_ids are the rows' original indices */
export async function tablePage(store: Store, path: string, r: PageRequest = {}): Promise<TablePage> {
  const frame = await loadTable(store, path);
  let ids = frame.rows.map((_, i) => i);
  if (r.q) {
    const q = r.q.toLowerCase();
    ids = ids.filter((i) => frame.rows[i].some((v) => v !== null && String(v).toLowerCase().includes(q)));
  }
  const col = r.sort ? frame.columns.findIndex((c) => c.name === r.sort) : -1;
  if (col >= 0) {
    const dir = r.desc ? -1 : 1;
    const cmp = (a: any, b: any) => (a === b ? 0 : a === null ? 1 : b === null ? -1 : a < b ? -dir : dir);
    ids.sort((a, b) => cmp(frame.rows[a][col], frame.rows[b][col]) || a - b);
  }
  const offset = r.offset ?? 0;
  const limit = Math.max(1, Math.min(r.limit ?? 50, 1000));
  const page = ids.slice(offset, offset + limit);
  return { columns: frame.columns, rows: page.map((i) => frame.rows[i]), row_ids: page, total: ids.length, unfiltered: frame.rows.length };
}

export async function tableRows(store: Store, path: string, rows: number[], columns?: string[]) {
  const frame = await loadTable(store, path);
  const idx = columns ? columns.map((c) => frame.columns.findIndex((x) => x.name === c)).filter((j) => j >= 0) : frame.columns.map((_, j) => j);
  const ids = rows.filter((r) => r >= 0 && r < frame.rows.length);
  return { columns: idx.map((j) => frame.columns[j].name), rows: ids.map((i) => idx.map((j) => frame.rows[i][j])), row_ids: ids };
}
