// The TOPP workflow framework on the page's side, for one workflow in one
// workspace: input files, the configure page resolved against params.json,
// presets, runs, logs and results. The counterpart of WorkflowManager's
// show_*_section methods and StreamlitUI.

import { STEPS } from "../../steps";
import { exampleUrl, fetchBytes, presets, settings } from "../assets";
import { startRun, toolParams, type Run } from "../engine/client";
import { basename, join, walk, type Store } from "../storage/store";
import { LOG_FILES, appendToLogs, CANCELLED_MARKER, classifyLogOutcome, type LogLevelName, type Outcome } from "../workflow/logger";
import {
  InvalidParameterFile,
  applyPreset as applyPresetTo,
  effectiveDefaults,
  effectiveValues,
  matches,
  readParams,
  registerCustomDefaults,
  setToolValues,
  summary,
  updateParams,
  writeParams,
  type StoredParams,
} from "../workflow/params";
import { stepKey } from "../workflow/step";
import { slugOf, toolInstance, type ConfigItem, type Markdown, type SelectFiles, type Step, type Tool, type Widget, type WorkflowSpec } from "../workflow/spec";
import type { FileEntry, ToppParam } from "../types";
import { accepts, addFiles, listFiles, zipDir } from "./files";

export const workflowDir = (ws: string, spec: WorkflowSpec) => join(ws, slugOf(spec.name));
const inputDir = (ws: string, spec: WorkflowSpec, key: string) => join(workflowDir(ws, spec), "input-files", key);

// ------------------------------------------------------------ input files

const uploadOf = (spec: WorkflowSpec, key: string) => {
  const u = spec.upload.find((u) => u.key === key);
  if (!u) throw new Error(`No upload ${key} in this workflow`);
  return u;
};

const onlyExamples = (files: FileEntry[], fallback: string[] = []) =>
  !!fallback.length && files.map((f) => f.name).sort().join("\n") === fallback.map(basename).sort().join("\n");

/** The input files of an upload; with none yet, the upload's example files (as upload_widget's fallback) */
export async function inputFiles(store: Store, ws: string, spec: WorkflowSpec, key: string) {
  const u = uploadOf(spec, key);
  const dir = inputDir(ws, spec, key);
  let files = await listFiles(store, dir);
  if (!files.length && u.fallback?.length) {
    for (const path of u.fallback) await store.write(join(dir, basename(path)), await fetchBytes(exampleUrl(path)));
    files = await listFiles(store, dir);
  }
  return { files, only_example: onlyExamples(files, u.fallback) };
}

export async function uploadInputFiles(store: Store, ws: string, spec: WorkflowSpec, key: string, files: File[]) {
  const u = uploadOf(spec, key);
  const dir = inputDir(ws, spec, key);
  // New files replace the example files
  if (onlyExamples(await listFiles(store, dir), u.fallback) && files.some((f) => accepts(f.name, u.fileTypes))) await store.remove(dir);
  return addFiles(store, dir, files, u.fileTypes);
}

export const removeInputFiles = (store: Store, ws: string, spec: WorkflowSpec, key: string, name?: string) =>
  store.remove(name === undefined ? inputDir(ws, spec, key) : join(inputDir(ws, spec, key), name));

export const inputZip = (store: Store, ws: string, spec: WorkflowSpec) => zipDir(store, join(workflowDir(ws, spec), "input-files"));

// ------------------------------------------------------------- configure

export type ToolSchema = { tool: string; instance: string; available: boolean; params: ToppParam[] };
export type StepSchema = { step: string; available: boolean; params: StepParam[] };
export type StepParam = {
  key: string;
  name: string;
  help: string;
  value: unknown;
  default: unknown;
  widget_type: string;
  options: unknown[] | null;
  min: number | null;
  max: number | null;
  step_size: number;
  advanced: boolean;
};

export type Resolved =
  | (SelectFiles & { options: { value: string; label: string }[]; value: unknown })
  | (Widget & { value: unknown })
  | (Tool & { schema: ToolSchema })
  | (Step & { schema: StepSchema })
  | Markdown
  | { kind: "tab"; title: string; items: Resolved[] };

export async function toolSchema(item: Tool, stored: StoredParams): Promise<ToolSchema> {
  const instance = toolInstance(item);
  let defs;
  try {
    defs = await toolParams(item.tool);
  } catch {
    return { tool: item.tool, instance, available: false, params: [] };
  }
  defs = defs.filter((d) => !(item.excludeParameters ?? []).some((p) => matches(p, d.key)));
  const defaults = effectiveDefaults(defs, stored, instance);
  const values = effectiveValues(defs, stored, instance);
  const user = stored[instance] ?? {};
  return {
    tool: item.tool,
    instance,
    available: true,
    params: defs.map((d) => ({
      key: d.key,
      name: d.key.split(":").at(-1)!,
      type: d.type,
      value: values[d.key],
      default: defaults[d.key],
      valid_strings: d.validStrings ?? [],
      description: d.description,
      advanced: d.advanced,
      included: !item.includeParameters?.length || item.includeParameters.some((p) => matches(p, d.key)),
      section: item.displaySubsections === false ? "" : d.section,
      section_description: d.sectionDescription ?? "",
      modified: d.key in user,
      min: d.min ?? null,
      max: d.max ?? null,
    })),
  };
}

function stepSchema(item: Step, stored: StoredParams): StepSchema {
  const step = STEPS[item.step];
  if (!step) return { step: item.step, available: false, params: [] };
  return {
    step: item.step,
    available: true,
    params: step.DEFAULTS.filter((d) => !d.hide).map((d) => {
      const key = stepKey(item.step, d.key);
      return {
        key,
        name: d.name ?? d.key,
        help: d.help ?? "",
        value: key in stored ? stored[key] : d.value,
        default: d.value,
        widget_type: d.widget_type ?? "auto",
        options: d.options ?? null,
        min: d.min ?? null,
        max: d.max ?? null,
        step_size: d.step_size ?? 1,
        advanced: d.advanced ?? false,
      };
    }),
  };
}

async function selectable(store: Store, ws: string, spec: WorkflowSpec, key: string) {
  return (await listFiles(store, inputDir(ws, spec, key))).map((f) => ({ value: f.path, label: f.name }));
}

async function resolve(store: Store, ws: string, spec: WorkflowSpec, items: ConfigItem[], stored: StoredParams): Promise<Resolved[]> {
  const out: Resolved[] = [];
  for (const it of items) {
    if (it.kind === "tab") out.push({ kind: "tab", title: it.title, items: await resolve(store, ws, spec, it.items, stored) });
    else if (it.kind === "select-files") {
      const options = await selectable(store, ws, spec, it.key);
      const paths = options.map((o) => o.value);
      let value = stored[it.key] ?? (it.multiple ? [] : (paths[0] ?? null));
      if (Array.isArray(value)) value = value.filter((v) => paths.includes(v));
      else if (!paths.includes(value)) value = paths[0] ?? null;
      out.push({ ...it, options, value });
    } else if (it.kind === "widget") {
      let value = it.key in stored ? stored[it.key] : it.default;
      if (value == null && it.options) value = it.widgetType === "multiselect" ? [] : it.options[0];
      out.push({ ...it, value });
    } else if (it.kind === "tool") out.push({ ...it, schema: await toolSchema(it, stored) });
    else if (it.kind === "step") out.push({ ...it, schema: stepSchema(it, stored) });
    else out.push(it);
  }
  return out;
}

function* resolvedLeaves(items: Resolved[]): Generator<Resolved> {
  for (const it of items) {
    if (it.kind === "tab") yield* resolvedLeaves(it.items);
    else yield it;
  }
}

/**
 * The configure page with every widget's current value. Defaults of widgets
 * never touched are stored, as rendering them does in Streamlit (execute()
 * reads ctx.params[key] and expects the key), and so are custom tool defaults.
 */
export async function configure(store: Store, ws: string, spec: WorkflowSpec) {
  const wd = workflowDir(ws, spec);
  const stored = await readParams(store, wd);
  let changed = false;
  for (const it of walkTools(spec.configure)) changed = registerCustomDefaults(stored, toolInstance(it), it.customDefaults) || changed;
  const items = await resolve(store, ws, spec, spec.configure, stored);
  for (const it of resolvedLeaves(items)) {
    if ((it.kind === "widget" || it.kind === "select-files") && !(it.key in stored)) {
      stored[it.key] = it.value;
      changed = true;
    }
    if (it.kind === "step")
      for (const p of it.schema.params)
        if (!(p.key in stored)) {
          stored[p.key] = p.value;
          changed = true;
        }
  }
  if (changed) await writeParams(store, wd, stored);
  return {
    items,
    max_threads: stored.max_threads ?? settings.max_threads.local,
    values: Object.fromEntries(Object.entries(stored).filter(([k, v]) => !k.startsWith("_") && (typeof v !== "object" || v === null || Array.isArray(v)))),
  };
}

function* walkTools(items: ConfigItem[]): Generator<Tool> {
  for (const it of items) {
    if (it.kind === "tab") yield* walkTools(it.items);
    else if (it.kind === "tool") yield it;
  }
}

/** Stores values of one tool instance (non-defaults only); returns its new schema */
export async function saveTool(store: Store, ws: string, spec: WorkflowSpec, item: Tool, values: Record<string, unknown>) {
  const defs = await toolParams(item.tool);
  const stored = await updateParams(store, workflowDir(ws, spec), (p) => setToolValues(defs, p, toolInstance(item), values));
  return toolSchema(item, stored);
}

/** General widgets, file selections, step parameters and max_threads */
export async function saveParams(store: Store, ws: string, spec: WorkflowSpec, values: Record<string, unknown>) {
  await updateParams(store, workflowDir(ws, spec), (p) => {
    for (const [k, v] of Object.entries(values)) {
      if (k.startsWith("_") || (k === "max_threads" && !Number.isInteger(v))) continue;
      p[k] = v;
    }
  });
}

/** As reset_to_default_parameters: the old file is kept as params.json.bak-<time> */
export async function resetParams(store: Store, ws: string, spec: WorkflowSpec): Promise<string | null> {
  const wd = workflowDir(ws, spec);
  const old = await store.read(join(wd, "params.json"));
  let backup: string | null = null;
  if (old) {
    backup = `params.json.bak-${new Date().toISOString().replace(/[:.]/g, "-")}`;
    await store.write(join(wd, backup), old);
  }
  await writeParams(store, wd, {});
  return backup;
}

export async function exportParams(store: Store, ws: string, spec: WorkflowSpec): Promise<Blob> {
  return new Blob([JSON.stringify(await readParams(store, workflowDir(ws, spec)), null, 4)], { type: "application/json" });
}

export async function importParams(store: Store, ws: string, spec: WorkflowSpec, file: File) {
  let data: unknown;
  try {
    data = JSON.parse(await file.text());
  } catch (e: any) {
    throw new Error(`Not a parameter file: ${e.message}`);
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Not a parameter file: expected a JSON object");
  await writeParams(store, workflowDir(ws, spec), data as StoredParams);
}

export const presetList = (spec: WorkflowSpec) =>
  Object.entries(presets[slugOf(spec.name)] ?? {}).map(([name, p]) => ({ name, description: String(p._description ?? "") }));

export async function applyPreset(store: Store, ws: string, spec: WorkflowSpec, name: string) {
  const preset = presets[slugOf(spec.name)]?.[name];
  if (!preset) throw new Error(`No preset ${name}`);
  await updateParams(store, workflowDir(ws, spec), (p) => applyPresetTo(p, preset));
}

export async function paramSummary(store: Store, ws: string, spec: WorkflowSpec) {
  return summary(await readParams(store, workflowDir(ws, spec)));
}

/** The Markdown method summary for publications (export_parameters_markdown) */
export async function methodSummary(store: Store, ws: string, spec: WorkflowSpec, openmsVersion: string) {
  const url = `https://github.com/${settings["github-user"]}/${settings["repository-name"]}`;
  const tools = [...new Set([...walkTools(spec.configure)].map((t) => t.tool))].sort();
  const toolsText = tools.length > 1 ? `${tools.slice(0, -1).join(", ")} and ${tools.at(-1)}` : tools.join("");
  const s = await paramSummary(store, ws, spec);
  const lines = [
    `Data was processed using **${settings["app-name"]}** ([${url}](${url})), a web application based on the OpenMS WebApps framework [1].`,
    "OpenMS ([https://www.openms.de](https://www.openms.de)) is a free and open-source software for LC-MS data analysis [2].",
    `The workflow runs **OpenMS ${openmsVersion}** (WebAssembly) with the tools ${toolsText} as well as custom steps. Non-default parameters are listed in the supplementary section below.`,
    "",
    '[1] Müller, Tom David, et al. "OpenMS WebApps: Building User-Friendly Solutions for MS Analysis." (2025) [https://doi.org/10.1021/acs.jproteome.4c00872](https://doi.org/10.1021/acs.jproteome.4c00872).',
    "",
    '[2] Pfeuffer, Julianus, et al. "OpenMS 3 enables reproducible analysis of large-scale mass spectrometry data." (2024) [https://doi.org/10.1038/s41592-024-02197-7](https://doi.org/10.1038/s41592-024-02197-7).',
    "",
  ];
  for (const [title, group] of [["General", s.general], ["OpenMS Tools", s.tools], ["Steps", s.steps]] as const) {
    if (!Object.keys(group).length) continue;
    lines.push(`**${title}**\n`);
    for (const [k, v] of Object.entries(group)) {
      if (v && typeof v === "object" && !Array.isArray(v)) {
        lines.push(`> **${k}**\n`);
        for (const [kk, vv] of Object.entries(v)) lines.push(`>> ${kk}: **${vv}**\n`);
      } else lines.push(`>> ${k}: **${Array.isArray(v) ? v.join(", ") : v}**\n`);
    }
  }
  return lines.join("\n");
}

// ------------------------------------------------------------------- runs

const runs = new Map<string, Run>();

export type Status = { running: boolean; status: "running" | "idle" | Outcome; outcome: Outcome | null; log: string; log_lines: number; log_time: string | null };

export async function startWorkflow(store: Store, ws: string, spec: WorkflowSpec) {
  const wd = workflowDir(ws, spec);
  if (runs.has(wd)) throw new Error("The workflow is already running");
  const stored = await readParams(store, wd);
  const run = startRun(slugOf(spec.name), wd, Number(stored.max_threads ?? settings.max_threads.local));
  runs.set(wd, run);
  run.done.catch(async (e) => {
    // the worker died (not a cancellation): note it, as an uncaught error is in the log
    if (runs.get(wd) === run && e?.message !== "Stopped") await appendToLogs(store, wd, `ERROR: ${e?.message ?? e}`);
  }).finally(() => runs.get(wd) === run && runs.delete(wd));
}

/** Stops the run's worker and marks the log cancelled (as _stop_local_workflow) */
export async function stopWorkflow(store: Store, ws: string, spec: WorkflowSpec) {
  const wd = workflowDir(ws, spec);
  const run = runs.get(wd);
  if (!run) return false;
  runs.delete(wd);
  run.stop();
  await appendToLogs(store, wd, CANCELLED_MARKER);
  return true;
}

export const isRunning = (ws: string, spec: WorkflowSpec) => runs.has(workflowDir(ws, spec));

export async function status(store: Store, ws: string, spec: WorkflowSpec, level: LogLevelName = "minimal", lines = 100): Promise<Status> {
  const wd = workflowDir(ws, spec);
  const running = runs.has(wd);
  const f = await store.file(join(wd, "logs", LOG_FILES[level] ?? LOG_FILES.minimal));
  const content = f ? await f.text() : "";
  const all = content.split(/(?<=\n)/).filter((l) => l);
  const outcome = content && !running ? classifyLogOutcome(content) : null;
  return {
    running,
    status: running ? "running" : (outcome ?? "idle"),
    outcome,
    log: (lines ? all.slice(-lines) : all).join(""),
    log_lines: all.length,
    log_time: f ? new Date(f.lastModified).toLocaleString() : null,
  };
}

// ---------------------------------------------------------------- results

export type ResultFile = { path: string; folder: string; size: number; modified: number };

export async function resultFiles(store: Store, ws: string, spec: WorkflowSpec): Promise<ResultFile[]> {
  const dir = join(workflowDir(ws, spec), "results");
  const out: ResultFile[] = [];
  for (const rel of await walk(store, dir)) {
    const f = (await store.file(join(dir, rel)))!;
    out.push({ path: rel, folder: rel.includes("/") ? rel.split("/")[0] : ".", size: f.size, modified: f.lastModified });
  }
  return out;
}

export async function resultsZip(store: Store, ws: string, spec: WorkflowSpec, folders: string[] = []) {
  const files = (await resultFiles(store, ws, spec)).filter((f) => !folders.length || folders.includes(f.folder));
  if (!files.length) throw new Error("No results to download yet. Run the workflow first.");
  const keep = new Set(files.map((f) => f.path));
  return zipDir(store, join(workflowDir(ws, spec), "results"), { prefix: "results", include: (rel) => keep.has(rel) });
}

export { InvalidParameterFile };
