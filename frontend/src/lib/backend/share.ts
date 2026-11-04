// Workspaces leave the browser only on request: as a ZIP the user saves
// (export) and opens again (import), or uploaded to the share service of
// settings.json ("share_url", see share-server/) for a link that opens a copy
// of the workspace in another browser.
//
// A shared workspace holds its parameters, logs and results; input files
// (mzML-files/, input-files/) only when the user includes them.

import { settings } from "../assets";
import { join, walk, type Store } from "../storage/store";
import { safeName, unzipBlob, zipEntries } from "./files";
import { createWorkspace, listWorkspaces } from "./workspaces";

const isInput = (rel: string) => /^mzML-files\//.test(rel) || /^[^/]+\/input-files\//.test(rel);

export async function exportWorkspace(store: Store, ws: string, o: { inputs?: boolean } = {}): Promise<Blob> {
  const entries: Record<string, Uint8Array> = {};
  for (const rel of await walk(store, ws)) {
    if (!o.inputs && isInput(rel)) continue;
    entries[`${ws}/${rel}`] = (await store.read(join(ws, rel)))!;
  }
  return zipEntries(entries);
}

/** Opens an exported workspace under a new name (the name in the ZIP, made unique); returns that name */
export async function importWorkspace(store: Store, zip: Blob, name?: string): Promise<string> {
  const files = await unzipBlob(zip);
  const paths = Object.keys(files).filter((p) => !p.endsWith("/"));
  const roots = new Set(paths.map((p) => p.split("/")[0]));
  if (!paths.length || roots.size !== 1) throw new Error("Not a workspace archive: expected one workspace folder.");
  const [root] = roots;
  const existing = new Set(await listWorkspaces(store));
  let target = name ?? root;
  if (!safeName(target) || target.startsWith(".")) target = "imported";
  for (let i = 2; existing.has(target); i++) target = `${name ?? root}-${i}`;
  for (const p of paths) await store.write(join(target, p.slice(root.length + 1)), files[p]);
  await createWorkspace(store, target);
  return target;
}

export const sharingEnabled = () => !!settings.share_url;

const shareBase = () => settings.share_url!.replace(/\/$/, "");

/** Uploads the workspace; returns the link that opens it */
export async function shareWorkspace(store: Store, ws: string, o: { inputs?: boolean } = {}): Promise<string> {
  if (!sharingEnabled()) throw new Error("Sharing is not set up: settings.json has no share_url.");
  const zip = await exportWorkspace(store, ws, o);
  const r = await fetch(`${shareBase()}/shares`, { method: "POST", headers: { "Content-Type": "application/zip" }, body: zip });
  if (!r.ok) throw new Error(`The share service refused the upload (${r.status} ${await r.text()})`);
  const { id } = await r.json();
  const link = new URL(location.href);
  link.search = "";
  link.searchParams.set("shared", id);
  return link.href;
}

/** Downloads a shared workspace and opens it as a new workspace */
export async function openShared(store: Store, id: string): Promise<string> {
  if (!/^[A-Za-z0-9_-]{6,64}$/.test(id)) throw new Error("Not a valid share link.");
  const r = await fetch(`${shareBase()}/shares/${id}`);
  if (!r.ok) throw new Error(r.status === 404 ? "This shared workspace no longer exists." : `Could not load the shared workspace (${r.status}).`);
  return importWorkspace(store, await r.blob(), `shared-${id.slice(0, 8)}`);
}
