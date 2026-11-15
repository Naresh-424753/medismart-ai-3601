// Minimal service worker: makes the app installable and keeps the app shell available offline.
// It NEVER caches API calls or anything cross-origin, so no medical data is stored by the worker.
const V = "ms-shell-v1";
self.addEventListener("install", (e) => { e.waitUntil(caches.open(V).then((c) => c.addAll(["/", "/manifest.webmanifest", "/icon-192.png"])).then(() => self.skipWaiting())); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== V).map((k) => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", (e) => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== self.location.origin) return;
  if (r.mode === "navigate") { e.respondWith(fetch(r).catch(() => caches.match("/"))); return; }
  if (u.pathname.startsWith("/assets/")) { // hashed build files: cache-first
    e.respondWith(caches.match(r).then((hit) => hit || fetch(r).then((res) => { const cp = res.clone(); caches.open(V).then((c) => c.put(r, cp)); return res; })));
  }
});
