// Locates the bundled app payload (embedded Python, app sources, TOPP tools,
// share/OpenMS) and starts Streamlit from it. Kept free of Electron imports so
// the CI smoke test can exercise exactly the environment the shell uses.
const fs = require("fs");
const net = require("net");
const path = require("path");
const http = require("http");
const { spawn, execFileSync } = require("child_process");

const isWindows = process.platform === "win32";

// Folder holding app.py, the python-<version> folder, TOPP executables and share/.
function payloadDir(resourcesPath, isPackaged) {
  if (process.env.OPENMS_APP_PAYLOAD) return path.resolve(process.env.OPENMS_APP_PAYLOAD);
  if (isPackaged) return path.join(resourcesPath, "app-payload");
  // Development: run straight from the repository checkout.
  return path.resolve(__dirname, "..", "..");
}

// The embedded interpreter is python-<version>/python.exe; fall back to the
// python on PATH when running from a checkout.
function pythonExecutable(payload) {
  const embedded = fs
    .readdirSync(payload, { withFileTypes: true })
    .filter((d) => d.isDirectory() && /^python-\d/.test(d.name))
    .map((d) => path.join(payload, d.name, isWindows ? "python.exe" : "bin/python3"))
    .find((p) => fs.existsSync(p));
  return embedded || (isWindows ? "python" : "python3");
}

function readSettings(payload) {
  return JSON.parse(fs.readFileSync(path.join(payload, "settings.json"), "utf8"));
}

// Same environment the MSI's .bat file sets up: TOPP tools next to app.py,
// OPENMS_DATA_PATH pointing at share/OpenMS, and every THIRDPARTY tool folder
// (Comet, Percolator, Sirius, ...) on PATH.
function appEnvironment(payload, workspacesDir) {
  const env = { ...process.env };
  const pathKey = Object.keys(env).find((k) => k.toUpperCase() === "PATH") || "PATH";
  const extraPath = [payload];

  const dataPath = path.join(payload, "share", "OpenMS");
  if (fs.existsSync(dataPath)) {
    env.OPENMS_DATA_PATH = dataPath;
    const thirdParty = path.join(dataPath, "THIRDPARTY");
    if (fs.existsSync(thirdParty)) {
      for (const d of fs.readdirSync(thirdParty, { withFileTypes: true })) {
        if (d.isDirectory()) extraPath.push(path.join(thirdParty, d.name));
      }
    }
  }
  env[pathKey] = [...extraPath, env[pathKey] || ""].join(path.delimiter);

  if (workspacesDir) env.LOCAL_WORKSPACES_DIR = workspacesDir;
  env.PYTHONUNBUFFERED = "1";
  env.PYTHONNOUSERSITE = "1";
  return env;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

// Start `streamlit run app.py local` bound to loopback on the given port.
function startStreamlit({ payload, port, env, logStream }) {
  const args = [
    "-m", "streamlit", "run", "app.py", "local",
    "--server.headless", "true",
    "--server.address", "127.0.0.1",
    "--server.port", String(port),
    "--browser.gatherUsageStats", "false",
  ];
  const child = spawn(pythonExecutable(payload), args, {
    cwd: payload,
    env,
    windowsHide: true,
    // Own process group on POSIX so killTree can signal the whole tree.
    detached: !isWindows,
  });
  if (logStream) {
    child.stdout.pipe(logStream, { end: false });
    child.stderr.pipe(logStream, { end: false });
  }
  return child;
}

function healthOk(port) {
  return new Promise((resolve) => {
    const req = http.get(
      { host: "127.0.0.1", port, path: "/_stcore/health", timeout: 2000 },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      }
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

// Resolves once Streamlit answers its health endpoint; rejects if the process
// exits first or the timeout passes.
function waitForServer(child, port, timeoutMs = 180000) {
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = (fn, arg) => {
      if (done) return;
      done = true;
      clearInterval(timer);
      fn(arg);
    };
    child.once("exit", (code) => finish(reject, new Error(`Streamlit exited with code ${code}`)));
    const started = Date.now();
    const timer = setInterval(async () => {
      if (await healthOk(port)) finish(resolve);
      else if (Date.now() - started > timeoutMs)
        finish(reject, new Error("Streamlit did not become ready in time"));
    }, 500);
  });
}

// Kill Streamlit and everything it started: workflow processes and the TOPP
// tools they run.
function killTree(child) {
  if (!child || child.exitCode !== null || child.pid === undefined) return;
  try {
    if (isWindows) {
      execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      process.kill(-child.pid, "SIGTERM");
    }
  } catch (_) {
    // Already gone.
  }
}

module.exports = {
  appEnvironment,
  freePort,
  killTree,
  payloadDir,
  pythonExecutable,
  readSettings,
  startStreamlit,
  waitForServer,
};
