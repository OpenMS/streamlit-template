// Tells the user when the app's GitHub repository has a newer release. It
// never downloads anything; the user follows the link to the release page.
// Every failure (offline, rate limit, unexpected answer) means "no update".
const https = require("https");

// "OpenDDA-1.3.0", "v2.0.0-beta.2" or "2.0.0-alpha" -> {core: [2,0,0], pre: ["alpha"]}.
// The version starts at the first digit, so app-name prefixes are ignored;
// build metadata ("+...") is dropped. Null for a tag without a version.
function parseVersion(text) {
  const match = String(text || "").match(/(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]+))?/);
  if (!match) return null;
  return {
    core: match[1].split(".").map(Number),
    pre: match[2] ? match[2].split(".") : [],
  };
}

function compareIdentifiers(a, b) {
  const na = /^\d+$/.test(a);
  const nb = /^\d+$/.test(b);
  if (na && nb) return Number(a) - Number(b);
  if (na !== nb) return na ? -1 : 1; // numeric identifiers sort before words
  return a < b ? -1 : a > b ? 1 : 0;
}

// Semantic-versioning order: 1.2 == 1.2.0, and a pre-release sorts before its
// final release (2.0.0-alpha < 2.0.0-alpha.2 < 2.0.0-beta < 2.0.0-rc.1 < 2.0.0).
function compareVersions(a, b) {
  for (let i = 0; i < Math.max(a.core.length, b.core.length); i++) {
    const d = (a.core[i] || 0) - (b.core[i] || 0);
    if (d !== 0) return d;
  }
  if (!a.pre.length || !b.pre.length) return b.pre.length - a.pre.length;
  for (let i = 0; i < Math.max(a.pre.length, b.pre.length); i++) {
    if (i >= a.pre.length) return -1;
    if (i >= b.pre.length) return 1;
    const d = compareIdentifiers(a.pre[i], b.pre[i]);
    if (d !== 0) return d;
  }
  return 0;
}

// True when `latest` is a strictly higher version than `current`; unparsable
// versions never notify.
function isNewer(latest, current) {
  const a = parseVersion(latest);
  const b = parseVersion(current);
  return Boolean(a && b && compareVersions(a, b) > 0);
}

function isPrerelease(release) {
  const v = parseVersion(release.tag_name);
  return Boolean(release.prerelease || (v && v.pre.length));
}

// The release to offer someone running `current`, or null. A final release is
// offered to everyone; a pre-release (by its tag or GitHub's flag) only to
// someone already running a pre-release, so alpha testers hear of newer
// alphas and betas while everyone else waits for the final release.
function pickUpdate(releases, current) {
  const mine = parseVersion(current);
  if (!mine || !Array.isArray(releases)) return null;
  const wantsPrereleases = mine.pre.length > 0;
  let best = null;
  for (const release of releases) {
    if (!release || release.draft || !release.tag_name) continue;
    if (isPrerelease(release) && !wantsPrereleases) continue;
    const v = parseVersion(release.tag_name);
    if (!v || compareVersions(v, mine) <= 0) continue;
    if (!best || compareVersions(v, best.v) > 0) best = { v, release };
  }
  return best && { version: best.release.tag_name, url: best.release.html_url };
}

function fetchReleases(owner, repo) {
  return new Promise((resolve) => {
    const req = https.get(
      {
        host: "api.github.com",
        path: `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/releases?per_page=30`,
        headers: { "User-Agent": "openms-app-update-check", Accept: "application/vnd.github+json" },
        timeout: 10000,
      },
      (res) => {
        let body = "";
        res.on("data", (c) => (body += c));
        res.on("end", () => {
          try {
            resolve(res.statusCode === 200 ? JSON.parse(body) : null);
          } catch (_) {
            resolve(null);
          }
        });
      }
    );
    req.on("error", () => resolve(null));
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
  });
}

// Returns {version, url} for a newer release, or null (also when offline).
async function checkForUpdate(settings) {
  try {
    const owner = settings["github-user"];
    const repo = settings["repository-name"];
    if (!owner || !repo) return null;
    return pickUpdate(await fetchReleases(owner, repo), settings.version);
  } catch (_) {
    return null;
  }
}

// A small notice in the bottom right corner of the app window, drawn over the
// page instead of a dialog so it never blocks work. "Download" opens the
// release page in the browser (keepLinksInsideApp sends window.open there),
// "×" closes it. Text goes in through textContent, never as HTML.
function noticeScript(update, current) {
  const data = JSON.stringify({ version: update.version, url: update.url, current });
  return `(() => {
  const d = ${data};
  if (document.getElementById("openms-update-notice")) return;
  const box = document.createElement("div");
  box.id = "openms-update-notice";
  box.setAttribute("role", "status");
  const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  box.style.cssText = [
    "position:fixed", "right:16px", "bottom:16px", "z-index:2147483647",
    "max-width:340px", "padding:12px 14px", "border-radius:8px",
    "font:14px/1.4 'Source Sans Pro',system-ui,sans-serif",
    "box-shadow:0 4px 16px rgba(0,0,0,.25)",
    dark ? "background:#262730;color:#fafafa;border:1px solid #3d3f4a"
         : "background:#ffffff;color:#31333f;border:1px solid #d6d6d9",
  ].join(";");
  const title = document.createElement("div");
  title.style.cssText = "font-weight:600;margin-right:20px";
  title.textContent = "A new version is available: " + d.version;
  const detail = document.createElement("div");
  detail.style.cssText = "opacity:.75;margin:2px 0 10px";
  detail.textContent = "You are running " + d.current + ".";
  const link = document.createElement("a");
  link.href = d.url;
  link.textContent = "Download";
  link.style.cssText = "display:inline-block;padding:4px 12px;border-radius:6px;background:#29379b;color:#fff;text-decoration:none;font-weight:600";
  link.addEventListener("click", (e) => { e.preventDefault(); window.open(d.url); box.remove(); });
  const close = document.createElement("button");
  close.textContent = "\\u00d7";
  close.setAttribute("aria-label", "Close");
  close.style.cssText = "position:absolute;top:4px;right:8px;border:0;background:none;color:inherit;font-size:20px;cursor:pointer;opacity:.6";
  close.addEventListener("click", () => box.remove());
  box.append(close, title, detail, link);
  document.body.appendChild(box);
})();`;
}

module.exports = { checkForUpdate, isNewer, pickUpdate, parseVersion, noticeScript };
