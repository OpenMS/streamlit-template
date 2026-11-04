// One run of a workflow (in its own Web Worker, see engine/worker.ts), as
// WorkflowManager.workflow_process: fresh logs and results/, then execute(),
// and the "WORKFLOW FINISHED" marker only when it returned true.

import type { OpenMS } from "../engine/openms";
import { join, type Store } from "../storage/store";
import { RunContext } from "./context";
import { FINISHED_MARKER, Logger, classifyLogOutcome, type Outcome } from "./logger";
import { readParams } from "./params";
import type { WorkflowSpec } from "./spec";

export async function runWorkflow(O: OpenMS, store: Store, spec: WorkflowSpec, workflowDir: string, logDelay = 300): Promise<Outcome> {
  const logger = new Logger(store, workflowDir, logDelay);
  await logger.reset();
  try {
    logger.log("STARTING WORKFLOW");
    await store.remove(join(workflowDir, "results"));
    const params = await readParams(store, workflowDir);
    const ok = await spec.execute(new RunContext(O, store, workflowDir, params, logger));
    if (ok === true) logger.log(FINISHED_MARKER);
  } catch (e) {
    logger.log(`ERROR: ${e instanceof Error ? e.message : String(e)}`);
    if (e instanceof Error && e.stack) logger.log(e.stack, 2);
  }
  await logger.flush();
  return classifyLogOutcome((await store.readText(join(workflowDir, "logs", "minimal.log"))) ?? "");
}
