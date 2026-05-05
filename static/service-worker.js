// Service Worker for Injaaz PWA
// Version 1.0.0

const CACHE_NAME = 'injaaz-v1.0.2';
const OFFLINE_URL = '/offline';

// Assets to cache immediately on install
const STATIC_ASSETS = [
  '/',
  '/offline',
  '/manifest.json',
  '/static/mobile_responsive.css',
  '/static/logo.png',
  '/static/main.js',
  '/static/form.js',
  '/static/site_form.js',
  '/static/dropdown_init.js',
  '/static/photo_upload_queue.js',
  '/static/photo_queue_ui.js',
  '/static/photo_upload_queue.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap'
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS.map(url => new Request(url, {cache: 'no-cache'})));
      })
      .catch((error) => {
        console.error('[SW] Cache installation failed:', error);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch event - Network First strategy (online-only, no offline POST queue)
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip chrome extensions and non-http(s) requests
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return;
  }

  // Skip Cloudinary uploads (always need network)
  if (url.hostname.includes('cloudinary.com')) {
    return;
  }

  // POST requests - require network (online-only)
  if (request.method === 'POST') {
    event.respondWith(
      fetch(request.clone())
        .catch(() => {
          // If POST fails, show error (no offline queue)
          return new Response(
            JSON.stringify({
              error: 'Network unavailable',
              message: 'Please check your internet connection and try again'
            }),
            {
              status: 503,
              headers: { 'Content-Type': 'application/json' }
            }
          );
        })
    );
    return;
  }

  // GET requests - Network First with cache fallback for performance
  event.respondWith(
    fetch(request)
      .then((response) => {
        // Do not put HTML document responses in Cache Storage: avoids stale
        // navigations and odd first-load / mobile bfcache behavior with SW.
        const ct = (response.headers.get('content-type') || '');
        const isHtmlDoc =
          request.mode === 'navigate' || ct.indexOf('text/html') !== -1;
        if (response.status === 200 && !isHtmlDoc) {
          const responseToCache = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseToCache);
          });
        }
        return response;
      })
      .catch(async () => {
        // Try cache for static assets
        const cachedResponse = await caches.match(request);
        
        if (cachedResponse) {
          return cachedResponse;
        }
        
        // If HTML page requested, show offline page
        if (request.headers.get('accept').includes('text/html')) {
          const offlineResponse = await caches.match(OFFLINE_URL);
          return offlineResponse || new Response('Offline - Please connect to internet', { status: 503 });
        }
        
        return new Response('Network error', { status: 503 });
      })
  );
});

// Background Sync - Disabled for online-only mode
// Keeping the listener for compatibility but no retry logic
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync not enabled (online-only mode)');
});

async function retrySavedRequests() {
  // No-op for online-only mode
  console.log('[SW] Offline queue disabled (online-only mode)');
}

// Push notification handler
self.addEventListener('push', (event) => {
  const options = {
    body: event.data ? event.data.text() : 'New update available',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'view',
        title: 'View',
        icon: '/static/icons/icon-96x96.png'
      },
      {
        action: 'close',
        title: 'Close',
        icon: '/static/icons/icon-96x96.png'
      }
    ]
  };

  event.waitUntil(
    self.registration.showNotification('Injaaz Report', options)
  );
});

// Notification click handler
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  if (event.action === 'view') {
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

// Message handler for manual cache updates
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CACHE_URLS') {
    event.waitUntil(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.addAll(event.data.urls);
      })
    );
  }
});

console.log('[SW] Service Worker loaded');
