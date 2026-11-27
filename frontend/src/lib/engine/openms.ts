// The OpenMS WebAssembly module (public/openms/, see scripts/fetch-openms.mjs).

import type { MainModule } from "../../../public/openms/openms";

export type OpenMS = MainModule;

/** Loads the module; the URL is resolved at run time, not bundled */
export async function loadOpenMS(url: string, numThreads?: number): Promise<OpenMS> {
  const mod = await import(/* @vite-ignore */ url);
  const O: OpenMS = await mod.default({
    print: () => {},
    printErr: (line: string) => console.warn(`[OpenMS] ${line}`),
    ...(numThreads ? { numThreads } : {}),
  });
  O.setLogEnabled("info", false);
  return O;
}

/** Runs fn and deletes the Embind objects it registered, also on errors */
export function scoped<T>(fn: (keep: <H extends { delete(): void }>(h: H) => H) => T): T {
  const handles: { delete(): void }[] = [];
  try {
    return fn((h) => (handles.push(h), h));
  } finally {
    for (const h of handles.reverse()) h.delete();
  }
}
