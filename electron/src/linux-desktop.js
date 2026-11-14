// Desktop integration for the Linux AppImage. An AppImage started directly
// has no .desktop entry, so the dock and taskbar show a generic icon. On each
// start this writes (or refreshes) a per-user entry pointing at the AppImage,
// with the icon copied out of the mounted image, which disappears when the
// app exits.
const fs = require("fs");
const os = require("os");
const path = require("path");

function desktopEntry({ name, exec, icon, wmClass, comment }) {
  const quote = (s) => `"${s.replace(/(["`$\\])/g, "\\$1")}"`;
  return [
    "[Desktop Entry]",
    "Type=Application",
    `Name=${name}`,
    comment ? `Comment=${comment}` : null,
    `Exec=${quote(exec)} %U`,
    `Icon=${icon}`,
    "Terminal=false",
    "Categories=Science;",
    `StartupWMClass=${wmClass}`,
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
  fs.writeFileSync(file, data);
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
