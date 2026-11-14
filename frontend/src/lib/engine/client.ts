// The page's side of the engine. `engine` is the interactive worker (toolbox,
// viewer, tool parameters), started on first use and restarted after a trap.
// A workflow run gets a worker of its own (startRun), so the pages stay
// responsive during a run, and stopping the run stops that worker.

import type { CallRequest, InitRequest, Response } from "./worker";
import type { OpArgs, OpName, OpResult } from "./ops";

export class EngineError extends Error {
  constructor(
    message: string,
    readonly fatal: boolean,
  ) {
    super(message);
  }
}

export type ThreadingInfo = { threaded: boolean; available: boolean; numThreads: number };

export class EngineWorker {
  private worker: Worker;
  private next = 1;
  private calls = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>();
  readonly info: Promise<ThreadingInfo>;
  dead = false;

  constructor(threads: number) {
    this.worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    this.worker.onmessage = (e: MessageEvent<Response>) => {
      const r = e.data;
      const call = this.calls.get(r.id);
      if (!call) return;
      this.calls.delete(r.id);
      if (r.ok) call.resolve(r.result);
      else {
        if (r.fatal) this.dead = true;
        call.reject(new EngineError(r.error, r.fatal));
      }
    };
    this.worker.onerror = (e) => {
      e.preventDefault();
      this.fail(new EngineError(e.message || "The OpenMS engine could not be started.", true));
    };
    this.info = this.send<ThreadingInfo>({ id: 0, op: "init", baseUrl: new URL(import.meta.env.BASE_URL, location.href).href, threads });
  }

  private send<T>(req: InitRequest | CallRequest): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.calls.set(req.id, { resolve, reject });
      this.worker.postMessage(req);
    });
  }

  call<K extends OpName>(op: K, ...args: OpArgs<K>): Promise<OpResult<K>> {
    // Arguments are plain data; a JSON copy also unwraps Svelte state proxies, which postMessage cannot clone
    const plain = JSON.parse(JSON.stringify(args));
    return this.info.then(() => this.send<OpResult<K>>({ id: this.next++, op, args: plain }));
  }

  private fail(e: Error) {
    this.dead = true;
    for (const c of this.calls.values()) c.reject(e);
    this.calls.clear();
  }

  terminate() {
    this.worker.terminate();
    this.fail(new EngineError("Stopped", false));
  }
}

/** Threads for the module: they need a cross-origin isolated page (see public/coi-sw.js) */
export function threadCount(max: number) {
  if (!globalThis.crossOriginIsolated) return 0;
  return Math.max(1, Math.min(max, navigator.hardwareConcurrency || 1));
}

let maxThreads = 4;
let interactive: EngineWorker | null = null;

export function setMaxThreads(n: number) {
  maxThreads = n;
}

export const engine = {
  call<K extends OpName>(op: K, ...args: OpArgs<K>): Promise<OpResult<K>> {
    if (!interactive || interactive.dead) interactive = new EngineWorker(threadCount(maxThreads));
    return interactive.call(op, ...args);
  },
};

const tools = new Map<string, Promise<OpResult<"tool.params">>>();

/** A tool's parameters, read from the module once per page */
export function toolParams(name: string) {
  let p = tools.get(name);
  if (!p) {
    p = engine.call("tool.params", name);
    p.catch(() => tools.delete(name));
    tools.set(name, p);
  }
  return p;
}

export type Run = { done: Promise<OpResult<"workflow.run">>; stop: () => void };

/** Starts a workflow run in a worker of its own */
export function startRun(slug: string, workflowDir: string, threads: number): Run {
  const w = new EngineWorker(threadCount(threads));
  const done = w.call("workflow.run", slug, workflowDir).finally(() => w.terminate());
  return { done, stop: () => w.terminate() };
}
