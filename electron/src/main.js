// Electron shell for OpenMS Streamlit apps: starts the bundled Streamlit
// server, shows it in an app window, and stops the server (and any running
// TOPP tools) when the window closes.
const fs = require("fs");
const path = require("path");
const { app, BrowserWindow, dialog, shell } = require("electron");
const payload = require("./payload");
const { checkForUpdate } = require("./update-check");

// Set by the CI smoke test: exit 0 once the app page has loaded, 1 on failure.
const SMOKE_TEST = process.env.OPENMS_APP_SMOKE_TEST === "1";

let server = null;
let mainWindow = null;

if (!app.requestSingleInstanceLock()) {
  // A second launch would share the same workspaces; focus the first instead.
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  app.whenReady().then(start);
}

const LOADING_PAGE =
  "data:text/html;charset=utf-8," +
  encodeURIComponent(`<!doctype html><html><body style="margin:0;height:100vh;display:flex;
align-items:center;justify-content:center;font-family:sans-serif;color:#29379b">
<div>Starting&hellip;</div></body></html>`);

async function start() {
  const payloadDir = payload.payloadDir(process.resourcesPath, app.isPackaged);
  const settings = payload.readSettings(payloadDir);
  const title = settings["app-name"] || app.getName();

  const logDir = path.join(app.getPath("userData"), "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const logFile = path.join(logDir, "streamlit.log");
  const logStream = fs.createWriteStream(logFile, { flags: "w" });

  mainWindow = new BrowserWindow({
    title,
    width: 1400,
    height: 900,
    autoHideMenuBar: true,
    icon: path.join(__dirname, "..", "build", "icon.ico"),
    webPreferences: { contextIsolation: true, sandbox: true },
  });
  mainWindow.on("page-title-updated", (e) => e.preventDefault());
  await mainWindow.loadURL(LOADING_PAGE);

  try {
    const port = await payload.freePort();
    const workspacesDir = path.join(app.getPath("userData"), "workspaces");
    const env = payload.appEnvironment(payloadDir, workspacesDir);
    server = payload.startStreamlit({ payload: payloadDir, port, env, logStream });
    await payload.waitForServer(server, port);
    const appUrl = `http://127.0.0.1:${port}/`;
    keepLinksInsideApp(mainWindow, appUrl);
    await mainWindow.loadURL(appUrl);
    if (SMOKE_TEST) smokeTestPassesOnceWorkspaceExists(workspacesDir, logFile);
    // Streamlit exiting later (crash, killed) leaves a dead page; say so.
    server.once("exit", (code) => {
      if (!quitting) failed(`The app stopped unexpectedly (exit code ${code}).`, logFile);
    });
  } catch (err) {
    failed(err.message, logFile);
    return;
  }

  if (!SMOKE_TEST) notifyAboutUpdate(settings);
}

// The page has rendered once page_setup() created the default workspace in
// the user profile, which proves the LOCAL_WORKSPACES_DIR override took.
function smokeTestPassesOnceWorkspaceExists(workspacesDir, logFile) {
  const marker = path.join(workspacesDir, "default", "mzML-files");
  const started = Date.now();
  const timer = setInterval(() => {
    if (fs.existsSync(marker)) {
      clearInterval(timer);
      console.log(`Smoke test passed: ${marker} exists`);
      quit(0);
    } else if (Date.now() - started > 120000) {
      clearInterval(timer);
      failed(`No workspace appeared at ${marker}`, logFile);
    }
  }, 500);
}

// Links to anything other than the local server open in the default browser.
function keepLinksInsideApp(win, appUrl) {
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(appUrl)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(appUrl)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });
}

async function notifyAboutUpdate(settings) {
  const update = await checkForUpdate(settings);
  if (!update || !mainWindow) return;
  const { response } = await dialog.showMessageBox(mainWindow, {
    type: "info",
    message: `A new version (${update.version}) is available.`,
    detail: `You are running ${settings.version}. The installer is on the release page.`,
    buttons: ["Open release page", "Later"],
    defaultId: 0,
    cancelId: 1,
  });
  if (response === 0) shell.openExternal(update.url);
}

function failed(message, logFile) {
  if (SMOKE_TEST) {
    console.error(message);
    try {
      console.error(fs.readFileSync(logFile, "utf8"));
    } catch (_) {}
    quit(1);
    return;
  }
  dialog.showErrorBox("The app could not start", `${message}\n\nDetails are in:\n${logFile}`);
  quit(1);
}

let quitting = false;
function quit(code) {
  quitting = true;
  payload.killTree(server);
  app.exit(code);
}

app.on("window-all-closed", () => quit(0));
app.on("before-quit", () => {
  quitting = true;
  payload.killTree(server);
});
