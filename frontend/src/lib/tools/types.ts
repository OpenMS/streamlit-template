// A tool: the counterpart of a TOPP tool for the workflows of this app. It
// declares its parameters (shown on the configure page and stored as TOPP
// parameters are, "<instance>": {"<param:path>": value}) and runs one command
// on the OpenMS WebAssembly module, as run_topp runs one TOPP command line.

import type { DefaultParamHandler } from "../../../public/openms/openms";
import type { OpenMS } from "../engine/openms";
import type { Store } from "../storage/store";
import type { ParamDef, ParamType } from "../workflow/params";

export type ToolEnv = {
  O: OpenMS;
  store: Store;
  /** Level 2 is the tool's own output (the "all" log), as a TOPP tool's stdout */
  log: (message: string, level?: number) => void;
};

export type ToolDef = {
  name: string;
  description: string;
  /** The parameters; read once per page from the module (as -write_ini) */
  params: (O: OpenMS) => ParamDef[];
  /** The io keys (as -in/-out) the tool takes; "many" accepts several files in one command */
  io: Record<string, { output?: boolean; many?: boolean }>;
  /** One command: each io key with its file(s), and the effective parameter values */
  run: (env: ToolEnv, io: Record<string, string[]>, values: Record<string, unknown>) => Promise<void>;
};

const TYPES: Record<string, ParamType> = {
  int: "int",
  double: "double",
  string: "string",
  bool: "bool",
  "int[]": "int-list",
  "double[]": "double-list",
  "string[]": "string-list",
};

/**
 * The defaults of an OpenMS algorithm as parameters of a section, e.g. the
 * mass trace detection as "algorithm:mtd". Keys in `skip` are left out.
 */
export function algorithmParams(
  O: OpenMS,
  algorithm: keyof OpenMS,
  section: string,
  o: { skip?: string[]; sectionDescription?: string } = {},
): ParamDef[] {
  const handler = new (O[algorithm] as unknown as new () => DefaultParamHandler)();
  const param = handler.getDefaults();
  try {
    return param
      .getEntries()
      .filter((e) => e.type !== "empty" && !o.skip?.includes(e.name))
      .map((e) => ({
        key: section ? `${section}:${e.name}` : e.name,
        type: TYPES[e.type] ?? "string",
        default: e.type === "bool" ? String(e.value) : e.value,
        description: e.description,
        validStrings: e.type === "bool" ? undefined : (e.validStrings ?? undefined),
        min: e.min ?? undefined,
        max: e.max ?? undefined,
        advanced: e.tags.includes("advanced"),
        section,
        sectionDescription: o.sectionDescription,
      }));
  } finally {
    param.delete();
    handler.delete();
  }
}

/** The values of one section, without its prefix and with bools as booleans, for setParameterValues */
export function sectionValues(defs: ParamDef[], values: Record<string, unknown>, section: string, exclude: string[] = []) {
  const out: Record<string, number | string | boolean | number[] | string[]> = {};
  for (const d of defs) {
    if (d.section !== section) continue;
    const name = d.key.slice(section.length + 1);
    if (exclude.includes(name)) continue;
    const v = values[d.key];
    out[name] = d.type === "bool" ? v === "true" || v === true : (v as any);
  }
  return out;
}

/** Copies a stored file into the module's file system; returns its path there */
export async function stageIn(env: ToolEnv, path: string): Promise<string> {
  const bytes = await env.store.read(path);
  if (!bytes) throw new Error(`Input file not found: ${path}`);
  const local = `/work/${path}`;
  env.O.FS.mkdirTree(local.slice(0, local.lastIndexOf("/")), 0o777);
  env.O.FS.writeFile(local, bytes);
  return local;
}

/** A path in the module's file system to write `path` to; stageOut then stores it */
export function localPath(env: ToolEnv, path: string): string {
  const local = `/work/out/${path}`;
  env.O.FS.mkdirTree(local.slice(0, local.lastIndexOf("/")), 0o777);
  return local;
}

export async function stageOut(env: ToolEnv, local: string, path: string) {
  await env.store.write(path, env.O.FS.readFile(local) as Uint8Array);
  env.O.FS.unlink(local);
}

export function unlink(env: ToolEnv, local: string) {
  try {
    env.O.FS.unlink(local);
  } catch {
    /* already gone */
  }
}
