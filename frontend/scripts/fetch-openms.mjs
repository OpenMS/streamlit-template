// Downloads the OpenMS WebAssembly package into public/openms/, where the app
// loads it from. Run by `npm install` (postinstall); does nothing when the
// pinned files are already there.
//
// The package is not on npm yet: it is the build prose-web publishes
// (https://github.com/timosachsenberg/prose-web, OpenMS pull request #10575).
// To move to another build, change SOURCE and the hashes together.

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SOURCE = "https://raw.githubusercontent.com/timosachsenberg/prose-web/da0c786bd5c3ea1d199593d111ff3d5903358d14";
const FILES = {
  "openms.mjs": "c39f7b1100b9ef6644c9752411c1c1deab8a6656ce2f25dd081a7482f32f3077",
  "openms.wasm": "aff839486aa100494faa507a927abe738af99b3a353deb50c3b81bd3a55ac751",
  "openms.d.ts": "37d8f85b2ff282cf1b823b355d145ca8e001ae573ec20d15086c18a87e7c5dfc",
  "package.json": "13f6a77df589d8f6d13114e819e6585e84a54c3df300907812088241c03a0dc5",
  LICENSE: "9cee9ca86c8cd6e32a5a6b27378f5b23ec364eda092013e7ea5c33fc7a633677",
};

const dest = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "openms");
mkdirSync(dest, { recursive: true });
const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

for (const [name, hash] of Object.entries(FILES)) {
  const path = join(dest, name);
  if (existsSync(path) && sha256(readFileSync(path)) === hash) continue;
  process.stdout.write(`OpenMS WebAssembly: fetching ${name} ... `);
  const res = await fetch(`${SOURCE}/${name}`);
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status} from ${SOURCE}`);
  const buf = Buffer.from(await res.arrayBuffer());
  if (sha256(buf) !== hash) throw new Error(`${name}: checksum mismatch, refusing to use it`);
  writeFileSync(path, buf);
  console.log(`${(buf.length / 1e6).toFixed(1)} MB`);
}
