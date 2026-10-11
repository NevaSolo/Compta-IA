/* Service worker minimal : rend l'application installable et garde la coquille
   (HTML + assets versionnés) pour s'ouvrir sans réseau. Il ne met JAMAIS en
   cache l'API : une écriture comptable ne doit pas venir d'un cache périmé. */
const CACHE = "compta-ia-shell-v1";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) {
    return; // laissé au navigateur
  }

  if (request.mode === "navigate") {
    // Réseau d'abord (toujours la dernière version), coquille en secours hors ligne.
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put("/", copy));
          return response;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    // Fichiers au nom haché : immuables, donc cache d'abord.
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
        return response;
      }))
    );
  }
});
