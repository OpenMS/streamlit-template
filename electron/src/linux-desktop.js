// Desktop integration for the Linux AppImage. An AppImage started directly
// has no .desktop entry, so the dock and taskbar show a generic icon. On each
// start this writes (or refreshes) a per-user entry pointing at the AppImage,
// with the icon copied out of the mounted image, which disappears when the
// app exits.
const fs = require("fs");
const os = require("os");
const path = require("path");

// A value of a desktop entry string field: backslashes and control characters
// escaped as the spec's value types require.
function escapeValue(s) {
  const codes = { "\\": "\\\\", "\n": "\\n", "\t": "\\t", "\r": "\\r" };
  return String(s).replace(/[\\\n\t\r]/g, (c) => codes[c]);
}

// One quoted argument of Exec: the quoting rule escapes " ` $ \, a literal %
// becomes %% so it is not read as a field code, and the string escape rule
// applies on top (so a literal backslash ends up as four).
function execArg(s) {
  return `"${s.replace(/(["`$\\])/g, "\\$1").replace(/%/g, "%%")}"`;
}

function desktopEntry({ name, exec, icon, wmClass, comment }) {
  return [
    "[Desktop Entry]",
    "Type=Application",
    `Name=${escapeValue(name)}`,
    comment ? `Comment=${escapeValue(comment)}` : null,
    `Exec=${escapeValue(execArg(exec))} %U`,
    `Icon=${escapeValue(icon)}`,
    "Terminal=false",
    "Categories=Science;",
    `StartupWMClass=${escapeValue(wmClass)}`,
    "",
  ]
    .filter((line) => line !== null)
    .join("\n");
}

function writeIfChanged(file, data) {
  try {
    if (Buffer.compare(fs.readFileSync(file), Buffer.from(data)) === 0) return;
  } catch {
    // missing: write it
  }
  fs.mkdirSync(path.dirname(file), { recursive: true });
  // Written next to the target and renamed over it, so a desktop that reads
  // the entry or icon meanwhile never sees a partial file.
  const tmp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.tmp`);
  try {
    fs.writeFileSync(tmp, data);
    fs.renameSync(tmp, file);
  } catch (err) {
    fs.rmSync(tmp, { force: true });
    throw err;
  }
}

// Returns the .desktop path written, or null when not running from an AppImage.
function integrateAppImage({ appImage, desktopName, name, iconSource, iconDir, comment }) {
  if (!appImage || !desktopName) return null;
  const id = desktopName.replace(/\.desktop$/, "");
  const icon = path.join(iconDir, `${id}.png`);
  writeIfChanged(icon, fs.readFileSync(iconSource));
  const dataHome = process.env.XDG_DATA_HOME || path.join(os.homedir(), ".local", "share");
  const file = path.join(dataHome, "applications", `${id}.desktop`);
  writeIfChanged(file, desktopEntry({ name, exec: appImage, icon, wmClass: id, comment }));
  return file;
}

module.exports = { desktopEntry, integrateAppImage };
