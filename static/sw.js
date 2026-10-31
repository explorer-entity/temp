const CACHE_NAME = 'smriti-v2';
const urlsToCache = [
  '/',
  '/games/story_detective.html',
  '/games/word_picture_match.html',
  '/ask-smriti-demo.html',
  '/caregiver-dashboard.html',
  '/manifest.json'
];

self.addEventListener('install', function(event) {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache)));
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
    ))
  );
});

self.addEventListener('fetch', function(event) {
  if (event.request.method !== 'GET') return; // never cache API POSTs
  event.respondWith(caches.match(event.request).then(response => response || fetch(event.request)));
});
