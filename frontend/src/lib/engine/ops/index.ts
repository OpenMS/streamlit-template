// Everything the page asks of the engine worker, by name. Each op gets the
// module and the workspace store first; the client (client.ts) calls it with
// the remaining arguments: engine.call("mzml.overview", path).

import { getWorkflow } from "../../../workflows";
import type { Store } from "../../storage/store";
import { getTool } from "../../tools";
import { runWorkflow } from "../../workflow/runner";
import type { OpenMS } from "../openms";
import * as mzml from "./mzml";
import * as toolbox from "./toolbox";

export const OPS = {
  "openms.version": (O: OpenMS) => O.getVersion(),
  "toolbox.peptideMz": (O: OpenMS, _s: Store, sequence: string, minCharge: number, maxCharge: number) => toolbox.peptideMz(O, sequence, minCharge, maxCharge),
  "toolbox.enzymes": (O: OpenMS) => toolbox.enzymes(O),
  "toolbox.digest": (O: OpenMS, _s: Store, r: toolbox.DigestRequest) => toolbox.digest(O, r),
  "toolbox.isotopePattern": (O: OpenMS, _s: Store, r: toolbox.IsotopeRequest) => toolbox.isotopePattern(O, r),
  "toolbox.fragments": (O: OpenMS, _s: Store, sequence: string, ionTypes: string[], charges: number[]) => toolbox.fragments(O, sequence, ionTypes, charges),

  "mzml.overview": (O: OpenMS, s: Store, path: string) => mzml.overview(O, s, path),
  "mzml.spectrum": (O: OpenMS, s: Store, path: string, index: number) => mzml.spectrum(O, s, path, index),
  "mzml.peakMap": (O: OpenMS, s: Store, r: mzml.PeakMapRequest) => mzml.peakMap(O, s, r),
  "mzml.countSpectra": (O: OpenMS, s: Store, path: string) => mzml.countSpectra(O, s, path),
  "mzml.extractIds": (_O: OpenMS, s: Store, path: string) => mzml.extractIds(s, path),

  /** A tool's parameters (as -write_ini) */
  "tool.params": (O: OpenMS, _s: Store, name: string) => getTool(name).params(O),
  /** Runs a workflow; only in a run worker of its own, which the page stops to cancel the run */
  "workflow.run": (O: OpenMS, s: Store, slug: string, workflowDir: string) => runWorkflow(O, s, getWorkflow(slug), workflowDir),
};

export type Ops = typeof OPS;
export type OpName = keyof Ops;
type Rest<T> = T extends (O: any, s: any, ...args: infer A) => any ? A : never;
export type OpArgs<K extends OpName> = Rest<Ops[K]>;
export type OpResult<K extends OpName> = Awaited<ReturnType<Ops[K]>>;
