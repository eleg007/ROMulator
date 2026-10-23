// Service Worker for caching proxied content to reduce data costs
const CACHE_NAME = 'cuban-proxy-cache-v1';
const CACHE_EXPIRY = 24 * 60 * 60 * 1000; // 24 hours in milliseconds

// Install event - set up cache
self.addEventListener('install', (event) => {
    console.log('Service Worker installed');
    self.skipWaiting();
});

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch event - intercept and cache proxy requests
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // Only cache proxy requests
    if (url.pathname.startsWith('/proxy')) {
        event.respondWith(
            caches.open(CACHE_NAME).then((cache) => {
                return cache.match(event.request).then((cachedResponse) => {
                    
                    // Check if cached response exists and is not expired
                    if (cachedResponse) {
                        const cachedDate = new Date(cachedResponse.headers.get('date'));
                        const now = new Date();
                        
                        if (now - cachedDate < CACHE_EXPIRY) {
                            console.log('Serving from cache:', event.request.url);
                            return cachedResponse;
                        } else {
                            console.log('Cache expired for:', event.request.url);
                        }
                    }
                    
                    // Fetch from network and cache
                    return fetch(event.request).then((networkResponse) => {
                        // Only cache successful responses
                        if (networkResponse && networkResponse.status === 200) {
                            cache.put(event.request, networkResponse.clone());
                        }
                        return networkResponse;
                    }).catch((error) => {
                        console.error('Fetch failed:', error);
                        // If network fails and we have a cached version (even expired), use it
                        if (cachedResponse) {
                            console.log('Network failed, using expired cache');
                            return cachedResponse;
                        }
                        throw error;
                    });
                });
            })
        );
    }
});
