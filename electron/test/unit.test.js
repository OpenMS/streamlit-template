const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { isNewer, pickUpdate, noticeScript } = require("../src/update-check");
const payload = require("../src/payload");

test("isNewer compares the version part of tags", () => {
  assert.equal(isNewer("OpenDDA-1.2", "1.1"), true);
  assert.equal(isNewer("v1.10.0", "1.9"), true);
  assert.equal(isNewer("1.1", "OpenDDA-1.1"), false);
  assert.equal(isNewer("1.1.0", "1.1"), false);
  assert.equal(isNewer("1.0", "1.1"), false);
  assert.equal(isNewer("latest", "1.1"), false);
});

test("isNewer orders pre-releases before their final release", () => {
  assert.equal(isNewer("2.0.0", "2.0.0-alpha"), true);
  assert.equal(isNewer("FLASHApp-2.0.0", "2.0.0-alpha"), true);
  assert.equal(isNewer("2.0.0-alpha", "2.0.0"), false);
  assert.equal(isNewer("2.0.0-alpha.2", "2.0.0-alpha"), true);
  assert.equal(isNewer("2.0.0-alpha.10", "2.0.0-alpha.9"), true);
  assert.equal(isNewer("2.0.0-beta", "2.0.0-alpha.3"), true);
  assert.equal(isNewer("2.0.0-rc.1", "2.0.0-beta.2"), true);
  assert.equal(isNewer("2.0.0-alpha", "1.2.0"), true);
  assert.equal(isNewer("2.0.0-alpha", "2.0.0-alpha"), false);
});

test("pickUpdate offers pre-releases only to pre-release users", () => {
  const rel = (tag, extra = {}) => ({ tag_name: tag, html_url: `https://x/${tag}`, ...extra });
  const releases = [rel("2.1.0-beta"), rel("2.0.1", { draft: true }), rel("2.0.0"), rel("2.0.0-alpha"), rel("1.2.0")];
  assert.deepEqual(pickUpdate(releases, "2.0.0-alpha"), { version: "2.1.0-beta", url: "https://x/2.1.0-beta" });
  assert.equal(pickUpdate(releases, "2.0.0"), null);
  assert.equal(pickUpdate(releases, "1.2.0").version, "2.0.0");
  assert.equal(pickUpdate([rel("1.3.0", { prerelease: true })], "1.2.0"), null);
  assert.equal(pickUpdate([rel("2.0.0-alpha")], "2.0.0-alpha"), null);
  assert.equal(pickUpdate(null, "1.0.0"), null);
  assert.equal(pickUpdate({ message: "API rate limit exceeded" }, "1.0.0"), null);
});

test("the update notice is a script that inserts text, not HTML", () => {
  const script = noticeScript({ version: "<img src=x onerror=alert(1)>", url: "https://x" }, "1.0.0");
  assert.doesNotThrow(() => new Function(script));
  assert.ok(!script.includes("innerHTML"));
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

test("appEnvironment puts openms/bin on PATH when present", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "payload-"));
  fs.mkdirSync(path.join(dir, "openms", "bin"), { recursive: true });
  const env = payload.appEnvironment(dir);
  const pathKey = Object.keys(env).find((k) => k.toUpperCase() === "PATH");
  const entries = env[pathKey].split(path.delimiter);
  assert.deepEqual(entries.slice(0, 2), [dir, path.join(dir, "openms", "bin")]);
});

test("pythonExecutable prefers the embedded interpreter", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "payload-"));
  const exe = process.platform === "win32" ? "python.exe" : path.join("bin", "python3");
  fs.mkdirSync(path.dirname(path.join(dir, "python-3.11.0", exe)), { recursive: true });
  fs.writeFileSync(path.join(dir, "python-3.11.0", exe), "");
  assert.equal(payload.pythonExecutable(dir), path.join(dir, "python-3.11.0", exe));
});
