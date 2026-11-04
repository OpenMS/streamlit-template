// The workflows of this app: one WorkflowSpec per workflow (as one
// WorkflowManager subclass each). Each gets its pages in src/nav.ts.

import { slugOf, type WorkflowSpec } from "../lib/workflow/spec";
import { toppWorkflow } from "./topp-workflow";

export const WORKFLOWS: WorkflowSpec[] = [toppWorkflow];

export function getWorkflow(slug: string): WorkflowSpec {
  const wf = WORKFLOWS.find((w) => slugOf(w.name) === slug);
  if (!wf) throw new Error(`Unknown workflow ${slug}`);
  return wf;
}
