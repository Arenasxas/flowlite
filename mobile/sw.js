// Modo sin conexión: la app abre aunque no haya internet (grabar necesita internet para transcribir,
// pero lo grabado queda guardado y se transcribe al volver la conexión).
// Cambiar VERSION en cada publicación: la app avisa "Hay una versión nueva".
const VERSION = "flowlite-2.2.3";
const FILES = ["./", "index.html", "app.css", "app.js", "ai.js", "store.js", "drive.js", "record.js", "repaso.js", "config.js",
  "manifest.json", "icons/icon-192.png", "icons/icon-512.png", "shared/cuaderno.js", "shared/prompts.json", "shared/page.html"];

self.addEventListener("install", (e) => e.waitUntil(caches.open(VERSION).then((c) => c.addAll(FILES))));
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return; // las APIs (Groq, Gemini, Drive) van directo
  e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request)));
});
