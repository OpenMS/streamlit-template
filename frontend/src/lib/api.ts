// Thin fetch wrappers around the local server's /api routes.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  const type = res.headers.get("content-type") ?? "";
  if (type.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export const api = {
  get: <T = any>(path: string) => fetch(`/api${path}`).then((r) => handle<T>(r)),
  post: <T = any>(path: string, body?: unknown) =>
    fetch(`/api${path}`, {
      method: "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then((r) => handle<T>(r)),
  put: <T = any>(path: string, body: unknown) =>
    fetch(`/api${path}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => handle<T>(r)),
  del: <T = any>(path: string) => fetch(`/api${path}`, { method: "DELETE" }).then((r) => handle<T>(r)),
  upload: <T = any>(path: string, files: File[] | FileList, field = "files") => {
    const form = new FormData();
    for (const f of Array.from(files)) form.append(field, f);
    return fetch(`/api${path}`, { method: "POST", body: form }).then((r) => handle<T>(r));
  },
};

/** Trigger a browser download of a GET route. */
export function download(path: string) {
  const a = document.createElement("a");
  a.href = `/api${path}`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** POST a JSON body and save the response as a file. */
export async function downloadPost(path: string, body: unknown, filename: string) {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) await handle(res);
  saveBlob(await res.blob(), filename);
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function saveText(text: string, filename: string, type = "text/plain") {
  saveBlob(new Blob([text], { type }), filename);
}

export const enc = encodeURIComponent;
