// Workspaces (the sidebar of page_setup) and the pages outside the workflow
// framework: workspace parameters of default-parameters.json (save_params),
// the workspace's mzML files and the example mzML workflow's results.
//
// A workspace is a top-level folder of the store, laid out as in the Streamlit
// app (see storage/store.ts).

import { defaultParameters, demoWorkspaces, exampleFiles, exampleUrl, fetchBytes } from "../assets";
import { basename, join, readJSON, writeJSON, type Store } from "../storage/store";
import { safeName } from "./files";

export const MZML_DIR = "mzML-files";
export const EXAMPLE_RESULTS = "mzML-workflow-results";

export async function listWorkspaces(store: Store): Promise<string[]> {
  const names = (await store.list("")).filter((e) => e.kind === "dir" && !e.name.startsWith(".")).map((e) => e.name);
  if (names.length) return names;
  await createWorkspace(store, "default");
  return ["default"];
}

/** Creates the workspace if it does not exist (as page_setup does for the one in the URL) */
export async function createWorkspace(store: Store, name: string) {
  if (!safeName(name) || name.startsWith(".")) throw new Error("Workspace names cannot contain '/' or '\\' or start with '.'");
  if (!(await store.exists(join(name, "params.json")))) await writeJSON(store, join(name, "params.json"), defaultParameters);
}

export const deleteWorkspace = (store: Store, name: string) => store.remove(name);

export const demos = () => Object.keys(demoWorkspaces()).sort();

/** Replaces the workspace's content with a demo workspace (the sidebar's "Load Demo Data") */
export async function loadDemo(store: Store, name: string, demo: string) {
  const files = demoWorkspaces()[demo];
  if (!files) throw new Error(`Demo ${demo} not found`);
  const fetched = await Promise.all(files.map(async ([rel, url]) => [rel, await fetchBytes(url)] as const));
  await store.remove(name);
  for (const [rel, bytes] of fetched) await store.write(join(name, rel), bytes);
  await createWorkspace(store, name);
}

// ------------------------------------------------------------ parameters

/** The workspace's params.json, else default-parameters.json */
export async function getParams(store: Store, ws: string): Promise<Record<string, any>> {
  return { ...defaultParameters, ...((await readJSON(store, join(ws, "params.json"))) ?? {}) };
}

/** As save_params(): only keys of default-parameters.json are kept */
export async function putParams(store: Store, ws: string, values: Record<string, unknown>) {
  const params = await getParams(store, ws);
  for (const [k, v] of Object.entries(values)) if (k in defaultParameters) params[k] = v;
  await writeJSON(store, join(ws, "params.json"), params);
  return params;
}

// ------------------------------------------------------------ mzML files

export async function mzmlFiles(store: Store, ws: string) {
  const dir = join(ws, MZML_DIR);
  return (await store.list(dir))
    .filter((e) => e.kind === "file" && e.name.endsWith(".mzML"))
    .map((e) => ({ name: e.name.replace(/\.mzML$/, ""), path: join(dir, e.name), size: e.size, reference: false }));
}

export async function mzmlPath(store: Store, ws: string, name: string) {
  const f = (await mzmlFiles(store, ws)).find((f) => f.name === name);
  if (!f) throw new Error(`No mzML file ${name} in this workspace`);
  return f.path;
}

export async function loadExampleMzml(store: Store, ws: string) {
  for (const path of exampleFiles("example-data/mzML")) await store.write(join(ws, MZML_DIR, basename(path)), await fetchBytes(exampleUrl(path)));
}

export async function deleteMzml(store: Store, ws: string, name?: string) {
  await store.remove(name === undefined ? join(ws, MZML_DIR) : join(ws, MZML_DIR, `${name}.mzML`));
}

// ------------------------------------------------- example mzML workflow

/** content/run_example_workflow.py: the number of spectra of each file, in mzML-workflow-results/<time>/result.tsv */
export async function runExampleWorkflow(store: Store, ws: string, files: string[], countSpectra: (path: string) => Promise<number>) {
  if (!files.length) throw new Error("Select some mzML files.");
  await putParams(store, ws, { "example-workflow-selected-mzML-files": files });
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  const run = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}_${p(d.getMinutes())}_${p(d.getSeconds())}`;
  const counts: number[] = [];
  for (const name of files) counts.push(await countSpectra(await mzmlPath(store, ws, name)));
  const lines = ["filenames\tnumber of spectra", ...files.map((f, i) => `${f}\t${counts[i]}`)];
  await store.write(join(ws, EXAMPLE_RESULTS, run, "result.tsv"), `${lines.join("\n")}\n`);
  return run;
}

export async function exampleRuns(store: Store, ws: string) {
  return (await store.list(join(ws, EXAMPLE_RESULTS)))
    .filter((e) => e.kind === "dir")
    .map((e) => e.name)
    .sort()
    .reverse();
}

export const exampleRunDir = (ws: string, run: string) => join(ws, EXAMPLE_RESULTS, run);
