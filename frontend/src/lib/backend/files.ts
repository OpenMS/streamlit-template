// Files in the workspace store: listing for the upload pages, ZIP archives
// for the downloads, and browser downloads.

import { strToU8, unzip, zip, type Unzipped } from "fflate";
import { basename, join, walk, type Store } from "../storage/store";
import type { FileEntry } from "../types";

export function humanSize(n: number): string {
  for (const unit of ["B", "KB", "MB", "GB"]) {
    if (n < 1024 || unit === "GB") return unit === "B" ? `${n.toFixed(0)} B` : `${n.toFixed(1)} ${unit}`;
    n /= 1024;
  }
  return `${n.toFixed(1)} GB`;
}

/** The files of a directory (not below), for the file lists of the upload pages */
export async function listFiles(store: Store, dir: string, filter: (name: string) => boolean = () => true): Promise<FileEntry[]> {
  return (await store.list(dir))
    .filter((e) => e.kind === "file" && filter(e.name))
    .map((e) => ({ name: e.name, path: join(dir, e.name), size: humanSize(e.size), reference: false }));
}

export const accepts = (name: string, types: string[]) => !types.length || types.some((t) => name.toLowerCase().endsWith(`.${t.toLowerCase().replace(/^\./, "")}`));

export const safeName = (name: string) => !!name && !/[\\/\0]/.test(name) && name !== "." && name !== "..";

/** Copies picked or dropped files into a directory; returns what was added and skipped */
export async function addFiles(store: Store, dir: string, files: Iterable<File>, types: string[]) {
  const added: string[] = [];
  const skipped: string[] = [];
  for (const f of files) {
    if (!safeName(f.name) || !accepts(f.name, types)) {
      skipped.push(f.name);
      continue;
    }
    await store.write(join(dir, f.name), f);
    added.push(f.name);
  }
  return { added, skipped };
}

/** A ZIP of the files below dir (paths relative to it, under `prefix`), optionally filtered */
export async function zipDir(store: Store, dir: string, o: { prefix?: string; include?: (rel: string) => boolean } = {}): Promise<Blob> {
  const entries: Record<string, Uint8Array> = {};
  for (const rel of await walk(store, dir)) {
    if (o.include && !o.include(rel)) continue;
    entries[o.prefix ? `${o.prefix}/${rel}` : rel] = (await store.read(join(dir, rel)))!;
  }
  return zipEntries(entries);
}

export function zipEntries(entries: Record<string, Uint8Array | string>): Promise<Blob> {
  const data = Object.fromEntries(Object.entries(entries).map(([k, v]) => [k, typeof v === "string" ? strToU8(v) : v]));
  return new Promise((resolve, reject) =>
    zip(data, { level: 6 }, (err, out) => (err ? reject(err) : resolve(new Blob([out as Uint8Array<ArrayBuffer>], { type: "application/zip" })))),
  );
}

export async function unzipBlob(blob: Blob): Promise<Unzipped> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  return new Promise((resolve, reject) => unzip(bytes, (err, out) => (err ? reject(err) : resolve(out))));
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export const saveText = (text: string, filename: string, type = "text/plain") => saveBlob(new Blob([text], { type }), filename);

/** Saves a stored file as a download */
export async function saveFile(store: Store, path: string) {
  const f = await store.file(path);
  if (!f) throw new Error(`File not found: ${path}`);
  saveBlob(f, basename(path));
}
