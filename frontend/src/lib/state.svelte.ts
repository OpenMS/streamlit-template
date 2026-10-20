// App-wide state: the current route, the workspace and app settings.
//
// The route lives in the URL hash (#/topp-workflow/configure) and the
// workspace in the ?workspace= query parameter, as in the Streamlit app, so
// a link opens the same page of the same workspace.

import { api } from "./api";

export type Settings = {
  app_name: string;
  version: string;
  github_user: string;
  repository_name: string;
  legal_links: Record<string, string>;
  enable_workspaces: boolean;
  max_threads: number;
  cpu_count: number;
  location: string;
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
  imageFormat: (localStorage.getItem("image-format") as "svg" | "png") || "svg",
  // Bumped whenever workspace content changes underneath the open page
  // (switching workspace, loading a demo) so pages reload their data.
  epoch: 0,
});

window.addEventListener("hashchange", () => (app.route = readRoute()));

export function navigate(route: string) {
  location.hash = `#/${route}`;
}

export function setWorkspace(name: string) {
  const url = new URL(location.href);
  url.searchParams.set("workspace", name);
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

export async function loadSettings() {
  app.settings = await api.get<Settings>("/settings");
  document.title = app.settings.app_name;
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
