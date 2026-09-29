// Local plain-HTTP front for a live deployment, used by check.mjs --live when
// the session sits behind an HTTPS proxy.
//
// In Claude Code cloud sessions the browser's HTTPS traffic is intercepted by
// an upstream proxy that answers WebSocket upgrades with 400, and a Streamlit
// page cannot run without its /_stcore/stream socket. A CONNECT tunnel opened
// from Node is passed through untouched, so the browser talks to
// http://localhost:<port> and this forwarder carries every request, WebSocket
// included, to the real host over such a tunnel. TLS to the deployment is
// still verified here against the system CA store.
import http from "node:http";
import tls from "node:tls";

function tunnel(proxy, host) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: proxy.hostname, port: proxy.port, method: "CONNECT", path: `${host}:443` });
    req.once("connect", (res, socket) => {
      if (res.statusCode !== 200) return reject(new Error(`proxy CONNECT ${res.statusCode}`));
      const t = tls.connect({ socket, servername: host, ALPNProtocols: ["http/1.1"] }, () => resolve(t));
      t.once("error", reject);
    });
    req.once("error", reject);
    req.end();
  });
}

// Present the request to the deployment as if the browser were on its origin.
function upstreamHeaders(headers, host, localOrigin) {
  const h = { ...headers, host };
  if (h.origin === localOrigin) h.origin = `https://${host}`;
  if (h.referer?.startsWith(localOrigin)) h.referer = `https://${host}` + h.referer.slice(localOrigin.length);
  return h;
}

export async function startForwarder(liveUrl, proxyUrl) {
  const host = new URL(liveUrl).hostname;
  const proxy = new URL(proxyUrl);
  let localOrigin = "";
  const server = http.createServer(async (req, res) => {
    try {
      const socket = await tunnel(proxy, host);
      const up = http.request(
        { createConnection: () => socket, method: req.method, path: req.url, headers: upstreamHeaders(req.headers, host, localOrigin) },
        (upRes) => {
          const headers = { ...upRes.headers };
          if (headers.location?.startsWith(`https://${host}`)) headers.location = localOrigin + headers.location.slice(`https://${host}`.length);
          res.writeHead(upRes.statusCode, headers);
          upRes.pipe(res);
        },
      );
      up.on("error", () => res.destroy());
      req.pipe(up);
    } catch (e) {
      res.writeHead(502, { "content-type": "text/plain" }).end(`forwarder: ${e.message}`);
    }
  });
  server.on("upgrade", async (req, client, head) => {
    try {
      const socket = await tunnel(proxy, host);
      const headers = upstreamHeaders(req.headers, host, localOrigin);
      socket.write(
        `${req.method} ${req.url} HTTP/1.1\r\n` +
          Object.entries(headers).map(([k, v]) => `${k}: ${v}`).join("\r\n") +
          "\r\n\r\n",
      );
      if (head?.length) socket.write(head);
      socket.pipe(client);
      client.pipe(socket);
      socket.on("error", () => client.destroy());
      client.on("error", () => socket.destroy());
    } catch {
      client.destroy();
    }
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  localOrigin = `http://localhost:${server.address().port}`;
  return { url: localOrigin + new URL(liveUrl).pathname, close: () => server.close() };
}
