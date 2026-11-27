// The steps workflows can run (ctx.runStep), by name: this app's counterpart
// of src/python-tools. Add a file here and list it below.

import type { StepDef } from "../lib/workflow/step";
import { example } from "./example";
import { export_consensus_feature_df } from "./export_consensus_feature_df";

export const STEPS: Record<string, StepDef> = Object.fromEntries([example, export_consensus_feature_df].map((s) => [s.name, s]));

export function getStep(name: string): StepDef {
  const s = STEPS[name];
  if (!s) throw new Error(`Unknown step ${name}`);
  return s;
}
