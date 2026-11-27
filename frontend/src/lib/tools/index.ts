// The tools workflows can run (ctx.runTool), by name. A derived app adds its
// own here.

import { FeatureFinderMetabo } from "./FeatureFinderMetabo";
import { FeatureLinkerUnlabeledKD } from "./FeatureLinkerUnlabeledKD";
import type { ToolDef } from "./types";

export const TOOLS: Record<string, ToolDef> = Object.fromEntries([FeatureFinderMetabo, FeatureLinkerUnlabeledKD].map((t) => [t.name, t]));

export function getTool(name: string): ToolDef {
  const t = TOOLS[name];
  if (!t) throw new Error(`Unknown tool ${name}`);
  return t;
}
