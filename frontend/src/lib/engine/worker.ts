// The engine worker: the OpenMS WebAssembly module in a module Web Worker, so
// the page never waits for it. The page sends {id, op, args}; the worker
// answers {id, ok: true, result} or {id, ok: false, error, fatal}. `fatal`
// means the module trapped (a RuntimeError or abort) and the worker is done for.
// The worker opens the same workspace store (OPFS) as the page.

import { openStore, type Store } from "../storage/store";
import { loadOpenMS, type OpenMS } from "./openms";
import { OPS, type OpName } from "./ops";

export type InitRequest = { id: 0; op: "init"; baseUrl: string; threads: number };
export type CallRequest = { id: number; op: OpName; args: unknown[] };
export type Response = { id: number; ok: true; result: unknown } | { id: number; ok: false; error: string; fatal: boolean };

let ready: Promise<{ O: OpenMS; store: Store }> | null = null;

const post = (r: Response) => (self as unknown as Worker).postMessage(r);

/** Requests run one after the other, as the module is one heap */
let queue: Promise<unknown> = Promise.resolve();

self.onmessage = (event: MessageEvent<InitRequest | CallRequest>) => {
  const req = event.data;
  queue = queue.then(async () => {
    try {
      if (req.op === "init") {
        const r = req as InitRequest;
        ready ??= Promise.all([loadOpenMS(new URL("openms/openms.mjs", r.baseUrl).href, r.threads), openStore()]).then(([O, store]) => ({ O, store }));
        const { O } = await ready;
        post({ id: req.id, ok: true, result: O.getThreadingInfo() });
        return;
      }
      if (!ready) throw new Error("The engine is not initialised.");
      const { O, store } = await ready;
      const op = OPS[(req as CallRequest).op] as (...a: unknown[]) => unknown;
      if (!op) throw new Error(`Unknown operation ${req.op}`);
      post({ id: req.id, ok: true, result: await op(O, store, ...(req as CallRequest).args) });
    } catch (e) {
      // Errors thrown by the code are Errors; a trapped module throws a RuntimeError or a non-Error
      const fatal = !(e instanceof Error) || e.name === "RuntimeError" || /Aborted\(/.test(e.message);
      post({ id: req.id, ok: false, error: e instanceof Error ? e.message : String(e), fatal });
    }
  });
};
