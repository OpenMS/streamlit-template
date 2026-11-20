"""Report installer downloads to Matomo, once the visitor has agreed to tracking.

Every installer a visitor downloads from the app is sent to Matomo as a
download (the *Downloads* report under Behaviour). A link to a release file
keeps its own URL, which names the app's repository and the release version.
The bundled Windows installer is named by the app's host and the file name:

    https://<app host>/download/<file name>

Covered are the installer buttons of ``src/common/installers.py``: the
``st.link_button`` links to the files of a release, and the
``st.download_button`` of the Windows installer bundled with the image. Other
downloads (results, tables, figures) are not reported.

The script runs in the app's window (the frame of ``components.html`` is on
the same origin). It listens for clicks on links in the page and wraps
``HTMLAnchorElement.click`` for links the page clicks without adding them to
the document, which is how Streamlit saves the file of a download button; that
file's name comes from the ``Content-Disposition`` of a ``HEAD`` request for
the media file. Only files with an installer extension are reported.

Hits go to the trackers the Matomo Tag Manager container created (through
``_paq`` while none exists yet, which keeps them until one does), together
with a ``_mtm`` event named ``download`` that a container trigger can use.
Nothing is sent without consent: ``page_setup()`` adds the script only after
the visitor agreed to Matomo in the consent banner.
``analytics.matomo.track_downloads`` set to ``false`` in settings.json turns
it off.
"""

import json

# File types of the desktop installers.
INSTALLER_EXTENSIONS = ["appimage", "deb", "dmg", "exe", "msi", "pkg", "rpm"]


def tracking_enabled(settings: dict) -> bool:
    """Whether installer downloads are reported (Matomo on, downloads not switched off)."""
    matomo = settings.get("analytics", {}).get("matomo", {})
    return bool(matomo.get("enabled")) and matomo.get("track_downloads", True) is not False


def tracker_script(app_name: str) -> str:
    """The page that installs the installer download tracking in the app's window, once."""
    config = json.dumps({"app": app_name, "extensions": INSTALLER_EXTENSIONS})
    return f"""<!DOCTYPE html>
<html lang="en"><head></head><body><script>
(function () {{
  var win = window.parent;
  if (!win || win.__openmsDownloadTracking) return;
  var config = {config};
  win.__openmsDownloadTracking = config;
  var extensions = new RegExp("\\\\.(" + config.extensions.join("|") + ")$", "i");
  var recent = {{}};

  function fileOf(url) {{
    try {{
      var path = new URL(url, win.location.href).pathname;
      return decodeURIComponent(path.split("/").pop() || "");
    }} catch (e) {{ return ""; }}
  }}

  function isInstaller(name) {{
    return extensions.test(name || "");
  }}

  // A download of the same file within a second is the same download seen twice.
  function send(name, url) {{
    name = (name || "").trim();
    if (!isInstaller(name)) return;
    var key = name + "|" + url;
    var now = Date.now();
    if (recent[key] && now - recent[key] < 1000) return;
    recent[key] = now;
    var http = /^https?:/i.test(url || "") && !/\\/media\\//.test(url);
    var target = http ? url
      : win.location.origin + "/download/" + encodeURIComponent(name);
    var M = win.Matomo;
    var trackers = M && M.getAsyncTrackers ? M.getAsyncTrackers() : [];
    if (trackers.length) {{
      trackers.forEach(function (t) {{ t.trackLink(target, "download"); }});
    }} else if (!win._paq || Array.isArray(win._paq)) {{
      // Kept until the container creates its tracker.
      win._paq = win._paq || [];
      win._paq.push(["trackLink", target, "download"]);
    }}
    win._mtm = win._mtm || [];
    win._mtm.push({{event: "download", downloadApp: config.app,
                    downloadName: name, downloadUrl: target}});
  }}

  // A Streamlit media file (the bundled Windows installer) is named in its
  // Content-Disposition.
  function sendMedia(url, fallback) {{
    fetch(url, {{method: "HEAD", credentials: "same-origin"}}).then(function (r) {{
      var cd = r.headers.get("Content-Disposition") || "";
      // filename* is percent-encoded UTF-8, a plain filename is not.
      var ext = /filename\\*=utf-8''([^;]+)/i.exec(cd);
      var plain = /filename="([^"]+)"/i.exec(cd);
      var name = fallback;
      try {{ name = ext ? decodeURIComponent(ext[1]) : (plain ? plain[1] : fallback); }}
      catch (e) {{ name = plain ? plain[1] : fallback; }}
      send(name, url);
    }}).catch(function () {{}});
  }}

  function report(a) {{
    var href = a.getAttribute("href") || "";
    if (!href || href.charAt(0) === "#" || /^(javascript|mailto|tel):/i.test(href)) return;
    var url = a.href;
    var name = a.getAttribute("download") || fileOf(url);
    if (/\\/media\\//.test(url) && url.indexOf(win.location.origin) === 0) {{
      sendMedia(url, name);
    }} else {{
      send(name, url);
    }}
  }}

  // Links in the page: the installer buttons of a release. A middle click
  // (open in a new tab) fires auxclick, not click.
  function onClick(ev) {{
    if (ev.type === "auxclick" && ev.button !== 1) return;
    var a = ev.target && ev.target.closest && ev.target.closest("a[href]");
    if (a) report(a);
  }}
  win.document.addEventListener("click", onClick, true);
  win.document.addEventListener("auxclick", onClick, true);

  // Links clicked without being in the page (Streamlit's download button).
  var proto = win.HTMLAnchorElement.prototype;
  var click = proto.click;
  proto.click = function () {{
    try {{ if (!this.isConnected) report(this); }} catch (e) {{}}
    return click.apply(this, arguments);
  }};
}})();
</script></body></html>
"""
