// Workflow parameters, stored in <workspace>/<slug>/params.json in the format
// of the Streamlit ParameterManager, so a workspace moves between the apps:
//
//   general widgets   {"<key>": value}
//   steps             {"<step>.ts:<key>": value}          (python tools: "<script>.py:<key>")
//   tools             {"<instance>": {"<param:path>": value}}, non-defaults only
//   custom defaults   {"_defaults": {"<instance>": {...}}}
//
// Effective tool values merge tool defaults < _defaults < stored values, as
// ParameterManager does with the tool's .ini file.

import { join, readJSON, writeJSON, type Store } from "../storage/store";

export type ParamType = "int" | "double" | "string" | "bool" | "int-list" | "double-list" | "string-list";

/** One parameter of a tool, as the tool declares it */
export type ParamDef = {
  key: string;
  type: ParamType;
  default: unknown;
  description: string;
  validStrings?: string[];
  min?: number;
  max?: number;
  advanced: boolean;
  /** Path of the section the parameter is in, e.g. "algorithm:mtd" */
  section: string;
  sectionDescription?: string;
};

export type StoredParams = Record<string, any>;

export class InvalidParameterFile extends Error {}

export const paramsPath = (workflowDir: string) => join(workflowDir, "params.json");

/** Reads params.json; a missing file is {}, an unreadable one an error (never overwritten) */
export async function readParams(store: Store, workflowDir: string): Promise<StoredParams> {
  try {
    return (await readJSON<StoredParams>(store, paramsPath(workflowDir))) ?? {};
  } catch (e: any) {
    throw new InvalidParameterFile(
      `The parameter file of this workflow cannot be read (${e.message}). Nothing was written, so no stored parameters were lost. ` +
        "Repair the file, or load the default parameters to continue.",
    );
  }
}

export const writeParams = (store: Store, workflowDir: string, params: StoredParams) => writeJSON(store, paramsPath(workflowDir), params);

export async function updateParams(store: Store, workflowDir: string, fn: (p: StoredParams) => void) {
  const p = await readParams(store, workflowDir);
  fn(p);
  await writeParams(store, workflowDir, p);
  return p;
}

/** Tool values as stored: bools as TOPP's "true"/"false", lists as arrays */
export function coerce(type: ParamType, value: unknown): unknown {
  if (type === "bool") return value === true || String(value).toLowerCase() === "true" ? "true" : "false";
  if (type === "int") return Math.trunc(Number(value));
  if (type === "double") return Number(value);
  if (type.endsWith("list")) {
    let list = typeof value === "string" ? value.split("\n").filter((v) => v.trim()) : ((value as unknown[]) ?? []);
    if (type === "int-list") list = list.map((v) => Math.trunc(Number(v)));
    else if (type === "double-list") list = list.map(Number);
    else list = list.map(String);
    return list;
  }
  return value == null ? "" : String(value);
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** Effective default of each parameter: the tool's, unless the workflow sets a custom one */
export function effectiveDefaults(defs: ParamDef[], stored: StoredParams, instance: string): Record<string, unknown> {
  const custom = stored._defaults?.[instance] ?? {};
  return Object.fromEntries(defs.map((d) => [d.key, coerce(d.type, d.key in custom ? custom[d.key] : d.default)]));
}

/** Effective values: defaults < _defaults < stored */
export function effectiveValues(defs: ParamDef[], stored: StoredParams, instance: string): Record<string, unknown> {
  const user = stored[instance] ?? {};
  const defaults = effectiveDefaults(defs, stored, instance);
  return Object.fromEntries(defs.map((d) => [d.key, d.key in user ? coerce(d.type, user[d.key]) : defaults[d.key]]));
}

/** Stores the given values, keeping only those that differ from the effective default */
export function setToolValues(defs: ParamDef[], stored: StoredParams, instance: string, values: Record<string, unknown>) {
  const defaults = effectiveDefaults(defs, stored, instance);
  const byKey = new Map(defs.map((d) => [d.key, d]));
  const user = (stored[instance] ??= {});
  for (const [key, raw] of Object.entries(values)) {
    const d = byKey.get(key);
    if (!d) continue;
    const v = coerce(d.type, raw);
    if (same(v, defaults[key])) delete user[key];
    else user[key] = v;
  }
  if (!Object.keys(user).length) delete stored[instance];
}

/** Seeds _defaults from the workflow's customDefaults, as input_TOPP(custom_defaults=) does */
export function registerCustomDefaults(stored: StoredParams, instance: string, custom?: Record<string, unknown>): boolean {
  if (!custom || !Object.keys(custom).length) return false;
  stored._defaults ??= {};
  if (same(stored._defaults[instance], custom)) return false;
  stored._defaults[instance] = { ...custom };
  return true;
}

/** TOPP's suffix matching of exclude_parameters / include_parameters */
export const matches = (pattern: string, key: string) => {
  const p = pattern.replace(/^:+/, "");
  return key === p || key.endsWith(`:${p}`);
};

/** Applies a preset of presets.json: tool values replace the stored ones, "_general" sets widgets */
export function applyPreset(stored: StoredParams, preset: Record<string, any>) {
  for (const [k, v] of Object.entries(preset)) {
    if (k === "_description") continue;
    if (k === "_general") Object.assign(stored, v);
    else stored[k] = { ...(stored[k] ?? {}), ...v };
  }
}

/** Non-default parameters for the run page and the method summary */
export function summary(stored: StoredParams) {
  const general: Record<string, unknown> = {};
  const steps: Record<string, Record<string, unknown>> = {};
  const tools: Record<string, Record<string, unknown>> = {};
  const name = (v: unknown) => (typeof v === "string" && v.includes("/") ? v.split("/").at(-1) : v);
  for (const [k, v] of Object.entries(stored)) {
    if (k.startsWith("_")) continue;
    if (v && typeof v === "object" && !Array.isArray(v)) tools[k] = { ...v };
    else if (/\.(ts|py):/.test(k)) {
      const [script, key] = k.split(/:(.*)/s);
      (steps[script] ??= {})[key] = v;
    } else general[k] = Array.isArray(v) ? v.map(name) : name(v);
  }
  for (const [tool, vals] of Object.entries<Record<string, unknown>>(stored._defaults ?? {})) tools[tool] = { ...vals, ...(tools[tool] ?? {}) };
  return { general, tools, steps };
}
