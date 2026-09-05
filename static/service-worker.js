// Minimal service worker so the browser considers this an installable PWA.
// Caches the app shell (HTML) for a smoother repeat-open experience.
// Live weather data still requires an internet connection.

const CACHE_NAME = "weathergpt-shell-v1";
const APP_SHELL = ["/", "/static/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Network-first for API calls (always want fresh weather data),
  // cache-first for the app shell itself.
  if (event.request.url.includes("/api/")) {
    return; // let it hit the network normally
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
