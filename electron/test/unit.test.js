const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { isNewer } = require("../src/update-check");
const payload = require("../src/payload");

test("isNewer compares the numeric part of tags", () => {
  assert.equal(isNewer("OpenDDA-1.2", "1.1"), true);
  assert.equal(isNewer("v1.10.0", "1.9"), true);
  assert.equal(isNewer("1.1", "OpenDDA-1.1"), false);
  assert.equal(isNewer("1.0", "1.1"), false);
  assert.equal(isNewer("latest", "1.1"), false);
});

test("appEnvironment mirrors the MSI launcher", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "payload-"));
  fs.mkdirSync(path.join(dir, "share", "OpenMS", "THIRDPARTY", "Comet"), { recursive: true });
  fs.mkdirSync(path.join(dir, "share", "OpenMS", "THIRDPARTY", "Percolator"), { recursive: true });
  const env = payload.appEnvironment(dir, "/tmp/ws");
  const pathKey = Object.keys(env).find((k) => k.toUpperCase() === "PATH");
  const entries = env[pathKey].split(path.delimiter);
  assert.equal(env.OPENMS_DATA_PATH, path.join(dir, "share", "OpenMS"));
  assert.equal(env.LOCAL_WORKSPACES_DIR, "/tmp/ws");
  assert.equal(entries[0], dir);
  assert.ok(entries.includes(path.join(dir, "share", "OpenMS", "THIRDPARTY", "Comet")));
  assert.ok(entries.includes(path.join(dir, "share", "OpenMS", "THIRDPARTY", "Percolator")));
});

test("pythonExecutable prefers the embedded interpreter", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "payload-"));
  const exe = process.platform === "win32" ? "python.exe" : path.join("bin", "python3");
  fs.mkdirSync(path.dirname(path.join(dir, "python-3.11.0", exe)), { recursive: true });
  fs.writeFileSync(path.join(dir, "python-3.11.0", exe), "");
  assert.equal(payload.pythonExecutable(dir), path.join(dir, "python-3.11.0", exe));
});
