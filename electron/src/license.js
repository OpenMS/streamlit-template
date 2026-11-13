// The license agreement the desktop app shows on its first start. It holds the
// app's own license and, when the payload ships Thermo's RawFileReader (the
// ThermoRawFileParser folder FileConverter uses for .raw files), the terms that
// license requires end users to accept: not to pass RawFileReader on to others.
// Acceptance is stored per agreement text, so a changed text is shown again.
// Kept free of Electron imports for the unit tests; main.js draws the window.
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const THERMO_NOTICE =
  "RawFileReader reading tool. Copyright © 2016 by Thermo Fisher Scientific, Inc. All rights reserved.";

const FALLBACK_LICENSE =
  "Copyright OpenMS Inc. -- Eberhard Karls University Tuebingen, ETH Zurich, and Freie Universitaet Berlin " +
  "2002-present.\nThis software is released under a three-clause BSD license.";

// RawFileReader comes either with ThermoRawFileParser (an OpenMS without the
// built-in reader) or with OpenMS's built-in reader
// (share/OpenMS/openms_thermo_bridge/managed); the first that is there.
function thermoFolder(payload) {
  const share = path.join(payload, "share", "OpenMS");
  for (const dir of [path.join(share, "THIRDPARTY", "ThermoRawFileParser"), path.join(share, "openms_thermo_bridge", "managed")]) {
    if (fs.existsSync(dir)) return dir;
  }
  return null;
}

// Thermo's license terms: ThermoRawFileParser keeps them in its folder,
// OpenMS installs them for its built-in reader in share/OpenMS/LICENSES.
function thermoTerms(payload, folder) {
  const candidates = [
    path.join(folder, "THERMO_LICENSE"),
    path.join(payload, "share", "OpenMS", "LICENSES", "ThermoRawFileReader-License.doc"),
  ];
  return candidates.find((f) => fs.existsSync(f)) || null;
}

function appLicense(payload) {
  for (const name of ["LICENSE", "LICENSE.md", "LICENSE.txt"]) {
    try {
      return fs.readFileSync(path.join(payload, name), "utf8").trim();
    } catch (_) {}
  }
  return FALLBACK_LICENSE;
}

// Returns [{ title, text }]: the sections of the agreement, in order.
function agreementSections(payload, appName) {
  const sections = [{ title: `${appName} license`, text: appLicense(payload) }];
  const thermo = thermoFolder(payload);
  if (thermo) {
    const terms = thermoTerms(payload, thermo);
    sections.push({
      title: "Thermo RawFileReader",
      text:
        `${appName} reads Thermo .raw files with RawFileReader, which it includes under a license from ` +
        `Thermo Fisher Scientific.\n${THERMO_NOTICE}\n\n` +
        "By accepting, you agree to the RawFileReader license terms " +
        // Relative to the app's folder: the AppImage mounts it at a new path on every
        // start, and the agreement text must stay the same to stay accepted.
        (terms ? `(${path.relative(payload, terms).split(path.sep).join("/")} in the app's folder) ` : "") +
        "and in particular that you will not redistribute RawFileReader to others.",
    });
  }
  sections.push({
    title: "Other components",
    text:
      `${appName} also includes open-source software from others (Python, Python packages, OpenMS ` +
      "tools and libraries), each under its own license. The About dialog at the bottom of the app's " +
      "sidebar lists them with their license texts.",
  });
  return sections;
}

function digest(sections) {
  return crypto.createHash("sha256").update(JSON.stringify(sections)).digest("hex");
}

function acceptanceFile(userData) {
  return path.join(userData, "license-accepted.json");
}

function isAccepted(userData, sections) {
  try {
    return JSON.parse(fs.readFileSync(acceptanceFile(userData), "utf8")).sha256 === digest(sections);
  } catch (_) {
    return false;
  }
}

function recordAcceptance(userData, sections) {
  fs.mkdirSync(userData, { recursive: true });
  fs.writeFileSync(
    acceptanceFile(userData),
    JSON.stringify({ sha256: digest(sections), accepted: new Date().toISOString() }, null, 1)
  );
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// The agreement page. Its two buttons are links to ANSWER_URL + "accept" or
// "decline", which main.js stops in will-navigate, so the page needs no
// preload script or node access. The .invalid domain never resolves, should
// a navigation ever get through.
const ANSWER_URL = "https://license-answer.invalid/";

function agreementPage(appName, sections) {
  const body = sections
    .map((s) => `<h2>${escapeHtml(s.title)}</h2><pre>${escapeHtml(s.text)}</pre>`)
    .join("");
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(appName)}: license agreement</title>
<style>
:root{color-scheme:light dark;--bg:#fff;--fg:#1f2937;--muted:#6b7280;--box:#f3f4f6;--line:#d1d5db;--accent:#29379b}
@media (prefers-color-scheme:dark){:root{--bg:#0e1117;--fg:#e5e7eb;--muted:#9ca3af;--box:#1f2430;--line:#374151;--accent:#8b9cff}}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
body{display:flex;flex-direction:column}
header{padding:18px 24px 6px}h1{font-size:18px;margin:0 0 4px}header p{margin:0;color:var(--muted)}
main{flex:1;overflow:auto;margin:10px 24px;padding:4px 16px;border:1px solid var(--line);border-radius:8px;background:var(--box)}
h2{font-size:14px;margin:14px 0 6px}pre{white-space:pre-wrap;font:12px/1.45 ui-monospace,Menlo,Consolas,monospace;margin:0 0 8px}
footer{display:flex;justify-content:flex-end;gap:10px;padding:8px 24px 18px}
a.button{padding:8px 18px;border-radius:6px;text-decoration:none;font-weight:600;border:1px solid var(--line);color:var(--fg)}
a.primary{background:var(--accent);border-color:var(--accent);color:#fff}
</style></head><body>
<header><h1>${escapeHtml(appName)} license agreement</h1><p>Please read these terms. ${escapeHtml(appName)} starts once you accept them.</p></header>
<main>${body}</main>
<footer><a class="button" href="${ANSWER_URL}decline">Decline and quit</a><a class="button primary" href="${ANSWER_URL}accept" autofocus>I accept</a></footer>
</body></html>`;
}

module.exports = { ANSWER_URL, THERMO_NOTICE, agreementSections, agreementPage, isAccepted, recordAcceptance, thermoFolder };
