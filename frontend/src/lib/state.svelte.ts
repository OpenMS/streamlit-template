// App-wide state: the current route, the workspace, app settings and the
// workspace store.
//
// The route lives in the URL hash (#/topp-workflow/configure) and the
// workspace in the ?workspace= query parameter, as in the Streamlit app, so
// a link opens the same page of the same workspace in this browser.

import { settings as repoSettings } from "./assets";
import { setMaxThreads } from "./engine/client";
import { openShared } from "./backend/share";
import { createWorkspace } from "./backend/workspaces";
import { MemoryStore, openStore, type Store } from "./storage/store";

export type Settings = {
  app_name: string;
  version: string;
  github_user: string;
  repository_name: string;
  legal_links: Record<string, string>;
  enable_workspaces: boolean;
  max_threads: number;
  cpu_count: number;
  share_url: string | null;
};

function readRoute(): string {
  const h = location.hash.replace(/^#\/?/, "");
  return h || "quickstart";
}

function readWorkspace(): string {
  return new URLSearchParams(location.search).get("workspace") || "default";
}

export const app = $state({
  route: readRoute(),
  workspace: readWorkspace(),
  settings: null as Settings | null,
  /** False when the browser has no persistent storage (files are lost on reload) */
  persistent: true,
  imageFormat: (localStorage.getItem("image-format") as "svg" | "png") || "svg",
  // Bumped whenever workspace content changes underneath the open page
  // (switching workspace, loading a demo) so pages reload their data.
  epoch: 0,
});

/** The workspace store; set by init() before any page renders */
export let store: Store = new MemoryStore();

window.addEventListener("hashchange", () => (app.route = readRoute()));

export function navigate(route: string) {
  location.hash = `#/${route}`;
}

export function setWorkspace(name: string) {
  const url = new URL(location.href);
  url.searchParams.set("workspace", name);
  url.searchParams.delete("shared");
  history.replaceState(null, "", url);
  app.workspace = name;
  app.epoch++;
}

export function setImageFormat(fmt: "svg" | "png") {
  app.imageFormat = fmt;
  try {
    localStorage.setItem("image-format", fmt);
  } catch {
    /* private mode */
  }
}

export async function init() {
  const s = repoSettings;
  app.settings = {
    app_name: s["app-name"],
    version: s.version,
    github_user: s["github-user"],
    repository_name: s["repository-name"],
    legal_links: s.legal_links ?? {},
    enable_workspaces: s.enable_workspaces ?? true,
    max_threads: s.max_threads?.local ?? 4,
    cpu_count: navigator.hardwareConcurrency || 1,
    share_url: s.share_url ?? null,
  };
  document.title = app.settings.app_name;
  setMaxThreads(app.settings.max_threads);
  store = await openStore();
  app.persistent = !(store instanceof MemoryStore);
  if (app.persistent) navigator.storage.persist?.().catch(() => {});

  // A share link: open a copy of the shared workspace
  const shared = new URLSearchParams(location.search).get("shared");
  if (shared) {
    try {
      setWorkspace(await openShared(store, shared));
      toast("Opened the shared workspace as a new workspace in this browser.");
    } catch (e) {
      toastError(e);
    }
  }
  await createWorkspace(store, app.workspace).catch(() => setWorkspace("default"));
}

// ------------------------------------------------------------------ toasts

export type Toast = { id: number; kind: "info" | "success" | "error" | "warning"; text: string };
export const toasts = $state<Toast[]>([]);
let nextToast = 1;

export function toast(text: string, kind: Toast["kind"] = "success") {
  const id = nextToast++;
  toasts.push({ id, kind, text });
  setTimeout(() => {
    const i = toasts.findIndex((t) => t.id === id);
    if (i >= 0) toasts.splice(i, 1);
  }, kind === "error" ? 8000 : 4000);
}

export function toastError(e: unknown) {
  toast(e instanceof Error ? e.message : String(e), "error");
}
