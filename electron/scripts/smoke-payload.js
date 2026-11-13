// CI smoke test for a staged or installed app payload, run with the exact
// environment the Electron shell builds:
//   node scripts/smoke-payload.js <payload dir> [TOPP tool ...]
// It checks that pyOpenMS imports and reads an mzML file, that every listed
// TOPP tool starts from Python the way the workflow executor calls it, that
// FileConverter (when listed) converts a Thermo .raw file, and that the
// Streamlit server comes up.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const payload = require("../src/payload");

// A small Thermo .raw file from OpenMS's test data (tools/ci/fetch_thermo_assets.sh).
const RAW_URL = "https://archive.openms.de/openms/testfiles/Angiotensin_AllScans.raw";
const RAW_SHA256 = "3a0236f719e7c91e3c958f57f4e66ae422803ec3e6a997b9af4d2af395332b9f";

async function main() {
  const [dir, ...tools] = process.argv.slice(2);
  if (!dir) throw new Error("usage: smoke-payload.js <payload dir> [TOPP tool ...]");
  const payloadDir = path.resolve(dir);
  const workspaces = fs.mkdtempSync(path.join(os.tmpdir(), "openms-app-smoke-"));
  const env = payload.appEnvironment(payloadDir, workspaces);
  const python = payload.pythonExecutable(payloadDir);

  // A check that exits with SKIPPED could not run (e.g. its test file did not download).
  const SKIPPED = 77;
  const check = (name, code) => {
    const r = spawnSync(python, ["-c", code], { cwd: payloadDir, env, encoding: "utf8" });
    process.stdout.write(r.stdout || "");
    if (r.status === SKIPPED) {
      console.log(`skipped: ${name}`);
      return;
    }
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

  if (tools.includes("FileConverter")) {
    // A real Thermo .raw file through FileConverter, the way convert_to_mzml
    // calls it: OpenMS's built-in reader on the bundled .NET runtime, named
    // explicitly because Windows defaults to ThermoRawFileParser. Only an
    // OpenMS without that reader converts with its default.
    check(
      "Thermo .raw conversion",
      `import hashlib, os, subprocess, sys, tempfile, time
import pyopenms, requests
url = "${RAW_URL}"
tmp = tempfile.mkdtemp()
raw = os.path.join(tmp, "test.raw")
for attempt in range(5):
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        open(raw, "wb").write(resp.content)
        break
    except Exception as e:
        print("download failed:", e)
        time.sleep(10 * (attempt + 1))
else:
    # A release must not ship untested; elsewhere an outage of the file's host only skips the check.
    if os.environ.get("GITHUB_EVENT_NAME") == "release":
        sys.exit("could not download the Thermo test file")
    print("::warning::could not download the Thermo test file; .raw conversion not tested")
    sys.exit(${SKIPPED})
assert hashlib.sha256(open(raw, "rb").read()).hexdigest() == "${RAW_SHA256}", "test file checksum"
out = os.path.join(tmp, "test.mzML")
ini = os.path.join(tmp, "FileConverter.ini")
subprocess.run(["FileConverter", "-write_ini", ini], check=True, capture_output=True)
reader = []
managed = os.path.isdir(os.path.join(os.environ["OPENMS_DATA_PATH"], "openms_thermo_bridge", "managed"))
has_reader = 'inprocess' in open(ini, encoding="utf-8").read()
assert has_reader == managed, f"FileConverter's built-in Thermo reader ({has_reader}) and its managed assemblies ({managed}) disagree"
if has_reader:
    reader = ["-RawToMzML:reader", "inprocess"]
print("reader:", reader[1] if reader else "FileConverter's default")
r = subprocess.run(["FileConverter", "-in", raw, "-out", out, *reader], capture_output=True, text=True)
print(r.stdout[-3000:], r.stderr[-3000:])
assert r.returncode == 0, f"FileConverter exited with {r.returncode}"
exp = pyopenms.MSExperiment()
pyopenms.MzMLFile().load(out, exp)
print("converted", exp.getNrSpectra(), "spectra")
assert exp.getNrSpectra() > 0`
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
