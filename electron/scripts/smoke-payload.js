// CI smoke test for a staged or installed app payload, run with the exact
// environment the Electron shell builds:
//   node scripts/smoke-payload.js <payload dir> [TOPP tool ...]
// It checks that pyOpenMS imports and reads an mzML file, that every listed
// TOPP tool starts from Python the way the workflow executor calls it, and
// that the Streamlit server comes up.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const payload = require("../src/payload");

async function main() {
  const [dir, ...tools] = process.argv.slice(2);
  if (!dir) throw new Error("usage: smoke-payload.js <payload dir> [TOPP tool ...]");
  const payloadDir = path.resolve(dir);
  const workspaces = fs.mkdtempSync(path.join(os.tmpdir(), "openms-app-smoke-"));
  const env = payload.appEnvironment(payloadDir, workspaces);
  const python = payload.pythonExecutable(payloadDir);

  const check = (name, code) => {
    const r = spawnSync(python, ["-c", code], { cwd: payloadDir, env, encoding: "utf8" });
    process.stdout.write(r.stdout || "");
    if (r.status !== 0) {
      process.stderr.write(r.stderr || String(r.error || ""));
      throw new Error(`${name} failed`);
    }
    console.log(`ok: ${name}`);
  };

  check(
    "pyOpenMS",
    `import glob, pyopenms
print("pyOpenMS", pyopenms.__version__)
files = sorted(glob.glob("example-data/mzML/*.mzML"))
if files:
    exp = pyopenms.MSExperiment()
    pyopenms.MzMLFile().load(files[0], exp)
    print(files[0], exp.getNrSpectra(), "spectra")`
  );

  for (const tool of tools) {
    check(
      `TOPP ${tool}`,
      `import os, subprocess, tempfile
ini = os.path.join(tempfile.mkdtemp(), "${tool}.ini")
subprocess.run(["${tool}", "-write_ini", ini], check=True, capture_output=True)
assert os.path.getsize(ini) > 0`
    );
  }

  const port = await payload.freePort();
  const server = payload.startStreamlit({ payload: payloadDir, port, env, logStream: process.stdout });
  try {
    await payload.waitForServer(server, port, 300000);
    console.log("ok: Streamlit server");
  } finally {
    payload.killTree(server);
  }
}

main().then(
  () => process.exit(0),
  (err) => {
    console.error(err.message);
    process.exit(1);
  }
);
