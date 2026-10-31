const CACHE_NAME = 'smriti-v1';
const urlsToCache = [
  '/static/home.html',
  '/static/games/story_detective.html',
  '/static/ask-smriti-demo.html'
];

self.addEventListener('install', function(event) {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache)));
});

self.addEventListener('fetch', function(event) {
  event.respondWith(caches.match(event.request).then(response => response || fetch(event.request)));
});