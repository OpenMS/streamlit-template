// Tells the user when the app's GitHub repository has a newer release. It
// never downloads anything; the user follows the link to the release page.
const https = require("https");

function numericParts(version) {
  const match = String(version || "").match(/\d+(\.\d+)*/);
  return match ? match[0].split(".").map(Number) : null;
}

// True when `latest` is a strictly higher version than `current`. Tags such as
// "OpenDDA-1.2" compare by their numeric part; unparsable versions never notify.
function isNewer(latest, current) {
  const a = numericParts(latest);
  const b = numericParts(current);
  if (!a || !b) return false;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] || 0;
    const y = b[i] || 0;
    if (x !== y) return x > y;
  }
  return false;
}

function fetchLatestRelease(owner, repo) {
  return new Promise((resolve) => {
    const req = https.get(
      {
        host: "api.github.com",
        path: `/repos/${owner}/${repo}/releases/latest`,
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
  const owner = settings["github-user"];
  const repo = settings["repository-name"];
  if (!owner || !repo) return null;
  const release = await fetchLatestRelease(owner, repo);
  if (!release || !isNewer(release.tag_name, settings.version)) return null;
  return { version: release.tag_name, url: release.html_url };
}

module.exports = { checkForUpdate, isNewer };
