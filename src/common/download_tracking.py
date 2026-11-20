"""Report file downloads to Matomo, once the visitor has agreed to tracking.

Every download a visitor starts in the app is sent to Matomo as a download
(the *Downloads* report under Behaviour), named by the app's host and the
file name, so each web app's downloads show up under its own address:

    https://<app host>/download/<file name>

Covered are the files the browser saves from the page and from its
components, whatever made them:

- ``st.download_button`` (results, ZIPs, reports, tables, figures),
- links to a file (``st.link_button`` to the installers of a release,
  markdown links to a file),
- files saved inside a component frame, such as the CSV, Excel and image
  downloads of the OpenMS-Insight tables and plots, and the image download
  of Plotly charts.

The script runs in the app's own window (the frame of ``components.html``
is on the same origin). It listens for clicks on download links in the
page and in every same-origin frame, and wraps ``HTMLAnchorElement.click``
for links the page clicks without adding them to the document, which is
how Streamlit saves the file of a download button. Its file name then comes
from the ``Content-Disposition`` of a ``HEAD`` request for the media file.

Hits go to the trackers the Matomo Tag Manager container created (through
``_paq`` while none exists yet, which keeps them until one does), together with a ``_mtm``
event named ``download`` that a container trigger can use. Nothing is sent
without consent: ``page_setup()`` adds the script only after the visitor
agreed to Matomo in the consent banner. ``analytics.matomo.track_downloads``
set to ``false`` in settings.json turns it off.
"""

import json

# File types a plain link counts as a download for (Matomo's own list, plus
# the formats of mass spectrometry data and results).
DOWNLOAD_EXTENSIONS = [
    "7z", "appimage", "bz2", "consensusxml", "csv", "d", "deb", "dmg", "docx",
    "exe", "fasta", "featurexml", "gz", "html", "idxml", "jpeg", "jpg", "json",
    "md", "msi", "mzid", "mzml", "mztab", "mzxml", "parquet", "pdf", "pkg",
    "png", "raw", "sdrf", "sif", "svg", "tar", "tgz", "traml", "tsv", "txt",
    "webp", "xls", "xlsx", "xml", "xz", "yaml", "yml", "zip",
]


def tracking_enabled(settings: dict) -> bool:
    """Whether downloads are reported (Matomo on, downloads not switched off)."""
    matomo = settings.get("analytics", {}).get("matomo", {})
    return bool(matomo.get("enabled")) and matomo.get("track_downloads", True) is not False


def tracker_script(app_name: str) -> str:
    """The page that installs the download tracking in the app's window, once."""
    config = json.dumps({"app": app_name, "extensions": DOWNLOAD_EXTENSIONS})
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

  // A download of the same file within a second is the same download seen twice.
  function send(name, url) {{
    name = (name || "").trim() || "download";
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

  // A Streamlit media file is named in its Content-Disposition.
  function sendMedia(url, fallback) {{
    fetch(url, {{method: "HEAD", credentials: "same-origin"}}).then(function (r) {{
      var cd = r.headers.get("Content-Disposition") || "";
      var m = /filename\\*=utf-8''([^;]+)/i.exec(cd) || /filename="([^"]+)"/i.exec(cd);
      send(m ? decodeURIComponent(m[1]) : fallback, url);
    }}).catch(function () {{ send(fallback, url); }});
  }}

  function isDownload(a) {{
    var href = a.getAttribute("href") || "";
    if (!href || href.charAt(0) === "#" || /^(javascript|mailto|tel):/i.test(href)) return false;
    if (a.hasAttribute("download")) return true;
    if (/\\/media\\//.test(href) || /\\/releases\\/download\\//.test(href)) return true;
    return extensions.test(fileOf(a.href));
  }}

  function report(a) {{
    if (!isDownload(a)) return;
    var url = a.href;
    var name = a.getAttribute("download") || "";
    if (!name && /\\/media\\//.test(url) && url.indexOf(win.location.origin) === 0) {{
      sendMedia(url, fileOf(url));
    }} else {{
      send(name || fileOf(url), url);
    }}
  }}

  // A frame keeps its window when its first blank page is replaced by the
  // component's page, so the document is marked, not the window.
  function watch(w) {{
    try {{
      if (!w) return;
      var doc = w.document;
      if (doc && !doc.__openmsDownloadWatched) {{
        doc.__openmsDownloadWatched = true;
        // Links in the document: a visitor's click, or a component that adds
        // a link and clicks it.
        doc.addEventListener("click", function (ev) {{
          var a = ev.target && ev.target.closest && ev.target.closest("a[href]");
          if (a) report(a);
        }}, true);
      }}
      // Links clicked without being in the document (Streamlit's download button).
      var proto = w.HTMLAnchorElement.prototype;
      if (!proto.__openmsDownloadWatched) {{
        proto.__openmsDownloadWatched = true;
        var click = proto.click;
        proto.click = function () {{
          try {{ if (!this.isConnected) report(this); }} catch (e) {{}}
          return click.apply(this, arguments);
        }};
      }}
    }} catch (e) {{ /* a frame of another origin */ }}
  }}

  function watchFrame(f) {{
    var hook = function () {{ try {{ watch(f.contentWindow); }} catch (e) {{}} }};
    f.addEventListener("load", hook);
    hook();
  }}

  watch(win);
  Array.prototype.forEach.call(win.document.querySelectorAll("iframe"), watchFrame);
  new win.MutationObserver(function (records) {{
    records.forEach(function (r) {{
      r.addedNodes.forEach(function (n) {{
        if (n.nodeType !== 1) return;
        if (n.tagName === "IFRAME") watchFrame(n);
        if (n.querySelectorAll) Array.prototype.forEach.call(n.querySelectorAll("iframe"), watchFrame);
      }});
    }});
  }}).observe(win.document.body, {{childList: true, subtree: true}});
}})();
</script></body></html>
"""
