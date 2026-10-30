import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadOpenMS, type OpenMS } from "../src/lib/engine/openms";
import { MemoryStore } from "../src/lib/storage/store";

const root = (p: string) => fileURLToPath(new URL(`../${p}`, import.meta.url));

let module: Promise<OpenMS> | null = null;
/** The module of public/openms (npm install fetches it) */
export const openms = () => (module ??= loadOpenMS(root("public/openms/openms.mjs")));

/** A store with the example mzML files as a workflow's input files */
export async function storeWithExamples(dir: string) {
  const store = new MemoryStore();
  const paths = [];
  for (const name of ["Blank", "Control", "Pool", "Treatment"]) {
    const path = `${dir}/${name}.mzML`;
    await store.write(path, readFileSync(root(`../example-data/mzML/${name}.mzML`)));
    paths.push(path);
  }
  return { store, paths };
}
