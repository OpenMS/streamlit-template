// What a workflow's execute() gets: the counterpart of the WorkflowManager
// members execution() uses (self.params, self.logger, self.file_manager,
// self.executor), with the same contracts:
//
//   self.params[key]                       ctx.params[key]
//   self.logger.log(msg, level)            ctx.log(msg, level)
//   file_manager.get_files(f, type, dir)   ctx.getFiles(f, type, dir)
//   executor.run_topp(tool, io)            await ctx.runTool(tool, io)
//   executor.run_python(script, io)        await ctx.runStep(step, io)
//
// runTool and runStep return false when the command failed; execute() returns
// true only if every one of them succeeded.

import { getStep } from "../../steps";
import type { OpenMS } from "../engine/openms";
import { basename, join, type Store } from "../storage/store";
import { getTool } from "../tools";
import type { Logger } from "./logger";
import { effectiveDefaults, effectiveValues, type StoredParams } from "./params";
import { stepKey } from "./step";

export type IO = Record<string, string | (string | string[])[]>;

const seconds = (start: number) => ((performance.now() - start) / 1000).toFixed(2);
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

export class RunContext {
  constructor(
    readonly O: OpenMS,
    readonly store: Store,
    /** The workflow directory in the store, e.g. "default/topp-workflow" */
    readonly workflowDir: string,
    readonly params: StoredParams,
    readonly logger: Logger,
  ) {}

  log(message: string, level = 0) {
    this.logger.log(message, level);
  }

  /**
   * As FileManager.get_files: file paths with their type changed and/or moved
   * to results/<resultsDir>/ ("auto": a random name); `collect` folds them
   * into one entry, for a tool taking all of them in one command.
   */
  getFiles(files: string | string[] | string[][], fileType?: string, resultsDir?: string, collect?: false): string[];
  getFiles(files: string | string[] | string[][], fileType: string | undefined, resultsDir: string | undefined, collect: true): string[][];
  getFiles(files: string | string[] | string[][], fileType?: string, resultsDir?: string, collect = false): string[] | string[][] {
    let list: string[] = typeof files === "string" ? [files] : Array.isArray(files[0]) ? (files[0] as string[]) : (files as string[]);
    list = list.filter((f) => typeof f === "string" && f);
    if (!list.length) throw new Error(`No files found, can not set file type ${fileType}, results_dir ${resultsDir} and collect ${collect}.`);
    if (fileType !== undefined) list = list.map((f) => f.replace(/(\.[^./]*)?$/, `.${fileType.replace(/^\./, "")}`));
    if (resultsDir !== undefined) {
      const dir = resultsDir === "auto" || resultsDir === "" ? Math.random().toString(36).slice(2, 6) : resultsDir;
      list = list.map((f) => join(this.workflowDir, "results", dir, basename(f)));
    }
    return collect ? [list] : list;
  }

  /**
   * Runs a tool once per input file, as run_topp: the n-th entry of every io
   * key goes into the n-th command; keys with one entry are reused for every
   * command. `instance` is the name its parameters are stored under
   * (tool_instance_name): pass the same one as to Tool() on the configure page.
   */
  async runTool(name: string, io: IO, o: { instance?: string } = {}): Promise<boolean> {
    const tool = getTool(name);
    const instance = o.instance ?? name;
    const lists = Object.fromEntries(Object.entries(io).map(([k, v]) => [k, typeof v === "string" ? [v] : v]));
    const n = Math.max(...Object.values(lists).map((l) => l.length));
    for (const [k, l] of Object.entries(lists))
      if (l.length !== 1 && l.length !== n) throw new Error(`Inconsistent number of files: ${k} has ${l.length}, others ${n}.`);

    const defs = tool.params(this.O);
    const values = effectiveValues(defs, this.params, instance);
    const defaults = effectiveDefaults(defs, {}, instance);
    const changed = Object.entries(values).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(defaults[k]));

    if (n > 1) this.log(`Running ${n} commands...`, 1);
    for (let i = 0; i < n; i++) {
      const files = Object.fromEntries(Object.entries(lists).map(([k, l]) => [k, [l.length === 1 ? l[0] : l[i]].flat()]));
      const command = [
        name,
        ...Object.entries(files).flatMap(([k, fs]) => [`-${k}`, ...fs]),
        ...changed.flatMap(([k, v]) => [`-${k}`, ...[v].flat().map(String)]),
      ].join(" ");
      this.log(`Running command:\n${command}\nWaiting for command to finish...`, 1);
      const start = performance.now();
      try {
        await tool.run({ O: this.O, store: this.store, log: (m, level = 2) => this.log(m, level) }, files, values);
      } catch (e) {
        this.log(`ERRORS OCCURRED:\n${message(e)}`, 2);
        this.log(`Process failed:\n${command}\n${message(e)}`, 1);
        return false;
      }
      this.log(`Process finished:\n${command}\nTotal time to run command: ${seconds(start)} seconds`, 1);
    }
    return true;
  }

  /** Runs a step of src/steps with its stored parameters and the given files, as run_python */
  async runStep(name: string, io: IO = {}): Promise<boolean> {
    const step = getStep(name);
    const params: Record<string, unknown> = {};
    for (const d of step.DEFAULTS) {
      const key = stepKey(name, d.key);
      params[d.key] = key in this.params ? this.params[key] : d.value;
    }
    Object.assign(params, io);
    this.log(`Running step:\n${name}.ts\nWaiting for step to finish...`, 1);
    const start = performance.now();
    try {
      await step.run({ O: this.O, store: this.store, log: (m) => this.log(m, 2) }, params);
    } catch (e) {
      this.log(`ERRORS OCCURRED:\n${message(e)}`, 2);
      this.log(`Step failed:\n${name}.ts\n${message(e)}`, 1);
      return false;
    }
    this.log(`Process finished:\n${name}.ts\nTotal time to run command: ${seconds(start)} seconds`, 1);
    return true;
  }
}
