// The repository files the app is built from, bundled at build time: the same
// settings.json, default-parameters.json, presets.json, docs/ and
// example-data/ the Streamlit app reads at run time.

import settingsJson from "../../../settings.json";
import defaultParams from "../../../default-parameters.json";
import presetsJson from "../../../presets.json";
import logo from "../../../assets/openms_transparent_bg_logo.svg?url";

export type Settings = typeof settingsJson & {
  /** Where "Share workspace" uploads to (see share-server/); sharing is off without it */
  share_url?: string;
};

export const settings: Settings = {
  ...(settingsJson as Settings),
  // a build for a deployment can set the share service without editing settings.json
  ...(import.meta.env.VITE_SHARE_URL ? { share_url: import.meta.env.VITE_SHARE_URL } : {}),
};
export const defaultParameters: Record<string, unknown> = defaultParams;
export const presets: Record<string, Record<string, Record<string, any>>> = presetsJson;
export const logoUrl = logo;

const docs = import.meta.glob("../../../docs/*.md", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

/** The chapters of the Documentation page (content/documentation.py) */
export const DOCS: { title: string; file: string; markdown: string }[] = [
  ["User Guide", "user_guide.md"],
  ["Installation", "installation.md"],
  ["Developers Guide: How to build app based on this template", "build_app.md"],
  ["Developer Guide: Windows Executables", "win_exe_with_embed_py.md"],
  ["Developers Guide: From Notebook to Web App", "notebook_to_webapp.md"],
  ["Developers Guide: Deployment", "deployment.md"],
  ["Developers Guide: Kubernetes Deployment", "kubernetes-deployment.md"],
  ["Svelte App: In-Browser Web App", "svelte_app.md"],
]
  .map(([title, file]) => ({ title, file, markdown: docs[`../../../docs/${file}`] }))
  .filter((d) => d.markdown !== undefined);

// example-data/: fetched into a workspace when asked for (they are not small)
const examples = import.meta.glob("../../../example-data/**/*", { query: "?url", import: "default", eager: true }) as Record<string, string>;

/** "example-data/mzML/Blank.mzML" -> its URL in the build */
export function exampleUrl(path: string): string {
  const url = examples[`../../../${path}`];
  if (!url) throw new Error(`No example file ${path}`);
  return url;
}

/** The example files below a folder of example-data/, e.g. "example-data/mzML" */
export function exampleFiles(dir: string): string[] {
  const prefix = `../../../${dir.replace(/\/$/, "")}/`;
  return Object.keys(examples)
    .filter((k) => k.startsWith(prefix))
    .map((k) => k.slice("../../../".length))
    .sort();
}

/** The demo workspaces of settings.demo_workspaces, as name -> files (path relative to the demo, URL) */
export function demoWorkspaces(): Record<string, [string, string][]> {
  const config: any = settings.demo_workspaces ?? {};
  if (!config.enabled) return {};
  const dirs: string[] = [config.source_dirs ?? config.source_dir ?? "example-data/workspaces"].flat();
  const out: Record<string, [string, string][]> = {};
  for (const dir of dirs) {
    for (const path of exampleFiles(dir)) {
      const [demo, ...rest] = path.slice(dir.replace(/\/$/, "").length + 1).split("/");
      if (!rest.length || rest.at(-1) === ".gitkeep") {
        out[demo] ??= [];
        continue;
      }
      (out[demo] ??= []).push([rest.join("/"), exampleUrl(path)]);
    }
  }
  return out;
}

export async function fetchBytes(url: string): Promise<Uint8Array> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Could not load ${url} (${r.status})`);
  return new Uint8Array(await r.arrayBuffer());
}
