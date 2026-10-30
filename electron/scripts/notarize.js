// electron-builder afterSign hook: notarizes and staples the signed macOS app
// before it goes into the dmg. Replaces electron-builder's own notarization,
// which fails the whole build (after the long signing step) when a single
// stapler call loses its connection to Apple; here each step is retried.
// Credentials, as for electron-builder: APPLE_API_KEY (path to the .p8),
// APPLE_API_KEY_ID and APPLE_API_ISSUER, or APPLE_ID,
// APPLE_APP_SPECIFIC_PASSWORD and APPLE_TEAM_ID.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

function run(cmd, args) {
  const r = spawnSync(cmd, args, { stdio: "inherit" });
  if (r.status !== 0) throw new Error(`${cmd} ${args[0]} failed (${r.status ?? r.error})`);
}

function sleep(seconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, seconds * 1000);
}

function retry(name, attempts, fn) {
  for (let i = 1; ; i++) {
    try {
      return fn();
    } catch (err) {
      if (i === attempts) throw err;
      const wait = 15 * 2 ** (i - 1);
      console.log(`  • ${name} failed (${err.message}), retrying in ${wait}s`);
      sleep(wait);
    }
  }
}

function credentials() {
  const env = process.env;
  if (env.APPLE_API_KEY) {
    return ["--key", env.APPLE_API_KEY, "--key-id", env.APPLE_API_KEY_ID, "--issuer", env.APPLE_API_ISSUER];
  }
  if (env.APPLE_ID) {
    return ["--apple-id", env.APPLE_ID, "--password", env.APPLE_APP_SPECIFIC_PASSWORD, "--team-id", env.APPLE_TEAM_ID];
  }
  return null;
}

exports.default = async function notarize(context) {
  if (context.electronPlatformName !== "darwin") return;
  const auth = credentials();
  if (!auth) {
    console.log("  • skipped notarization: no Apple credentials");
    return;
  }
  const app = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "notarize-"));
  const zip = path.join(dir, `${path.basename(app, ".app")}.zip`);
  try {
    run("ditto", ["-c", "-k", "--sequesterRsrc", "--keepParent", app, zip]);
    console.log(`  • notarizing ${app}`);
    const result = retry("notarytool submit", 3, () => {
      const r = spawnSync("xcrun", ["notarytool", "submit", zip, ...auth, "--wait", "--output-format", "json"], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "inherit"],
      });
      if (r.status !== 0 && !(r.stdout || "").includes('"status"')) throw new Error(`notarytool submit failed (${r.status ?? r.error})`);
      return JSON.parse(r.stdout);
    });
    console.log(`  • notarization ${result.id}: ${result.status}`);
    if (result.status !== "Accepted") {
      // Rejected by Apple: retrying would not help; print why.
      spawnSync("xcrun", ["notarytool", "log", result.id, ...auth], { stdio: "inherit" });
      throw new Error(`notarization ${result.status}`);
    }
    retry("stapler staple", 5, () => run("xcrun", ["stapler", "staple", app]));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
};
