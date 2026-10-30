// The workflow log, in <workflow-dir>/logs/ as the Streamlit Logger writes it:
// level 0 goes to minimal.log, <= 1 also to commands-and-run-times.log,
// <= 2 also to all.log. The run page reads the outcome from the markers.

import { join, type Store } from "../storage/store";

export const LOG_FILES = {
  minimal: "minimal.log",
  "commands and run times": "commands-and-run-times.log",
  all: "all.log",
} as const;
export type LogLevelName = keyof typeof LOG_FILES;

export const FINISHED_MARKER = "WORKFLOW FINISHED";
export const CANCELLED_MARKER = "WORKFLOW CANCELLED";
export type Outcome = "finished" | "cancelled" | "error";

/** As classify_log_outcome: cancelled wins (a dying step may log an error first), then finished */
export function classifyLogOutcome(content: string): Outcome {
  if (content.includes(CANCELLED_MARKER)) return "cancelled";
  if (content.includes(FINISHED_MARKER)) return "finished";
  return "error";
}

const FILES = Object.values(LOG_FILES);

export class Logger {
  private text: string[] = ["", "", ""];
  private pending: Promise<void> = Promise.resolve();
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private store: Store,
    private workflowDir: string,
    /** How long writes are batched (ms); 0 writes every message at once */
    private delay = 300,
  ) {}

  /** Starts empty logs (a new run) */
  async reset() {
    this.text = ["", "", ""];
    await this.store.remove(join(this.workflowDir, "logs"));
  }

  log(message: string, level = 0) {
    const line = `${message}\n\n`;
    if (level === 0) this.text[0] += line;
    if (level <= 1) this.text[1] += line;
    if (level <= 2) this.text[2] += line;
    if (this.delay === 0) void this.flush();
    else this.timer ??= setTimeout(() => void this.flush(), this.delay);
  }

  /** Writes the logs; resolves once everything logged so far is stored */
  flush(): Promise<void> {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    const snapshot = [...this.text];
    this.pending = this.pending.then(() =>
      Promise.all(FILES.map((f, i) => (snapshot[i] ? this.store.write(join(this.workflowDir, "logs", f), snapshot[i]) : undefined))).then(() => {}),
    );
    return this.pending;
  }
}

/** Appends a line to every log file of a workflow, e.g. the cancellation marker after the run's worker was stopped */
export async function appendToLogs(store: Store, workflowDir: string, message: string) {
  for (const f of FILES) {
    const path = join(workflowDir, "logs", f);
    const text = (await store.readText(path)) ?? "";
    await store.write(path, `${text}${message}\n\n`);
  }
}
