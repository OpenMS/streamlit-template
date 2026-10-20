// The workspace file system, in the browser's origin private file system
// (OPFS): real directories and files that persist across visits and never
// leave the machine. The layout is the Streamlit template's, so a workspace
// exported as ZIP opens in either app:
//
//   <workspace>/params.json                 general page parameters
//   <workspace>/mzML-files/                 files of the pyOpenMS pages
//   <workspace>/<workflow-slug>/params.json workflow parameters
//   <workspace>/<workflow-slug>/input-files/<key>/, results/, logs/
//
// The same interface has an in-memory implementation, used where OPFS is
// missing and by the tests in Node.

export type Entry = { name: string; kind: "file" | "dir"; size: number; mtime: number };
export type Data = Uint8Array | string | Blob;

export interface Store {
  read(path: string): Promise<Uint8Array | null>;
  readText(path: string): Promise<string | null>;
  /** A File (a Blob with name and date), for downloads and workers; null if absent */
  file(path: string): Promise<File | null>;
  write(path: string, data: Data): Promise<void>;
  /** Directory entries, sorted by name; [] if the directory does not exist */
  list(dir: string): Promise<Entry[]>;
  remove(path: string): Promise<void>;
  exists(path: string): Promise<boolean>;
}

export function split(path: string): string[] {
  const parts = path.split("/").filter((p) => p && p !== ".");
  if (parts.some((p) => p === "..")) throw new Error(`Invalid path: ${path}`);
  return parts;
}

export const join = (...parts: string[]) => parts.flatMap(split).join("/");
export const basename = (path: string) => split(path).at(-1) ?? "";
export const dirname = (path: string) => split(path).slice(0, -1).join("/");
export const stem = (path: string) => basename(path).replace(/\.[^.]*$/, "");

async function bytesOf(data: Data): Promise<Uint8Array> {
  if (typeof data === "string") return new TextEncoder().encode(data);
  if (data instanceof Uint8Array) return data;
  return new Uint8Array(await data.arrayBuffer());
}

/** All files below dir, as paths relative to it */
export async function walk(store: Store, dir: string): Promise<string[]> {
  const out: string[] = [];
  for (const e of await store.list(dir)) {
    if (e.kind === "file") out.push(e.name);
    else for (const sub of await walk(store, join(dir, e.name))) out.push(`${e.name}/${sub}`);
  }
  return out;
}

export async function readJSON<T>(store: Store, path: string): Promise<T | null> {
  const text = await store.readText(path);
  return text === null ? null : (JSON.parse(text) as T);
}

export const writeJSON = (store: Store, path: string, value: unknown) =>
  store.write(path, JSON.stringify(value, null, 4));

// ------------------------------------------------------------------ OPFS

class OpfsStore implements Store {
  constructor(private root: FileSystemDirectoryHandle) {}

  private async dir(parts: string[], create: boolean): Promise<FileSystemDirectoryHandle | null> {
    let d = this.root;
    for (const p of parts) {
      try {
        d = await d.getDirectoryHandle(p, { create });
      } catch {
        return null;
      }
    }
    return d;
  }

  private async handle(path: string): Promise<FileSystemFileHandle | null> {
    const parts = split(path);
    const d = await this.dir(parts.slice(0, -1), false);
    if (!d) return null;
    try {
      return await d.getFileHandle(parts.at(-1)!);
    } catch {
      return null;
    }
  }

  async file(path: string) {
    const h = await this.handle(path);
    return h ? h.getFile() : null;
  }

  async read(path: string) {
    const f = await this.file(path);
    return f ? new Uint8Array(await f.arrayBuffer()) : null;
  }

  async readText(path: string) {
    const f = await this.file(path);
    return f ? f.text() : null;
  }

  async write(path: string, data: Data) {
    const parts = split(path);
    const d = (await this.dir(parts.slice(0, -1), true))!;
    const h = await d.getFileHandle(parts.at(-1)!, { create: true });
    if ("createWritable" in h) {
      const w = await h.createWritable();
      await w.write(data instanceof Uint8Array ? (data as Uint8Array<ArrayBuffer>) : data);
      await w.close();
    } else {
      // Safari before 18.4 writes OPFS files only through sync handles, in workers
      const sync = await (h as any).createSyncAccessHandle();
      const bytes = await bytesOf(data);
      sync.truncate(0);
      sync.write(bytes, { at: 0 });
      sync.close();
    }
  }

  async list(dir: string) {
    const d = await this.dir(split(dir), false);
    if (!d) return [];
    const out: Entry[] = [];
    for await (const [name, h] of (d as any).entries() as AsyncIterable<[string, FileSystemHandle]>) {
      if (h.kind === "file") {
        const f = await (h as FileSystemFileHandle).getFile();
        out.push({ name, kind: "file", size: f.size, mtime: f.lastModified });
      } else out.push({ name, kind: "dir", size: 0, mtime: 0 });
    }
    return out.sort((a, b) => a.name.localeCompare(b.name));
  }

  async remove(path: string) {
    const parts = split(path);
    const d = await this.dir(parts.slice(0, -1), false);
    if (!d || !parts.length) return;
    try {
      await d.removeEntry(parts.at(-1)!, { recursive: true });
    } catch {
      /* absent */
    }
  }

  async exists(path: string) {
    const parts = split(path);
    if (await this.handle(path)) return true;
    return (await this.dir(parts, false)) !== null;
  }
}

// ---------------------------------------------------------------- memory

export class MemoryStore implements Store {
  files = new Map<string, { data: Uint8Array; mtime: number }>();

  async read(path: string) {
    return this.files.get(join(path))?.data ?? null;
  }
  async readText(path: string) {
    const d = await this.read(path);
    return d ? new TextDecoder().decode(d) : null;
  }
  async file(path: string) {
    const f = this.files.get(join(path));
    return f ? new File([f.data as Uint8Array<ArrayBuffer>], basename(path), { lastModified: f.mtime }) : null;
  }
  async write(path: string, data: Data) {
    this.files.set(join(path), { data: await bytesOf(data), mtime: Date.now() });
  }
  async list(dir: string) {
    const prefix = join(dir) ? `${join(dir)}/` : "";
    const seen = new Map<string, Entry>();
    for (const [p, f] of this.files) {
      if (!p.startsWith(prefix)) continue;
      const [name, ...rest] = p.slice(prefix.length).split("/");
      if (!seen.has(name))
        seen.set(name, rest.length ? { name, kind: "dir", size: 0, mtime: 0 } : { name, kind: "file", size: f.data.length, mtime: f.mtime });
    }
    return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
  }
  async remove(path: string) {
    const p = join(path);
    for (const k of [...this.files.keys()]) if (k === p || k.startsWith(`${p}/`)) this.files.delete(k);
  }
  async exists(path: string) {
    const p = join(path);
    return [...this.files.keys()].some((k) => k === p || k.startsWith(`${p}/`));
  }
}

let shared: Promise<Store> | null = null;

/** The origin's store: OPFS where the browser has it, else memory (lost on reload) */
export function openStore(): Promise<Store> {
  return (shared ??= (async () => {
    try {
      return new OpfsStore(await navigator.storage.getDirectory());
    } catch {
      return new MemoryStore();
    }
  })());
}

export const persistent = async () => !((await openStore()) instanceof MemoryStore);
