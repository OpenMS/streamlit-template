// Cross-origin isolation for static hosts that cannot set headers (e.g. GitHub
// Pages). OpenMS runs its threads on SharedArrayBuffer, which a page has only
// with the COOP/COEP headers; this service worker adds them to every response
// of this origin. serve.py and `npm run dev` set the headers themselves, so
// there the page never registers it.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.cache === "only-if-cached" && request.mode !== "same-origin") return;
  if (new URL(request.url).origin !== self.location.origin) return;
  event.respondWith(
    fetch(request).then((response) => {
      if (response.status === 0) return response;
      const headers = new Headers(response.headers);
      headers.set("Cross-Origin-Embedder-Policy", "require-corp");
      headers.set("Cross-Origin-Opener-Policy", "same-origin");
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    }),
  );
});
