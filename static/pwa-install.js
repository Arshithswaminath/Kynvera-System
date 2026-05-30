// Service worker registration (install / download UI removed)
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/static/service-worker.js')
      .then((registration) => {
        setInterval(() => registration.update(), 60 * 60 * 1000);

        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              if (confirm('A new version of Injaaz is available. Reload to update?')) {
                window.location.reload();
              }
            }
          });
        });
      })
      .catch((error) => {
        console.error('Service Worker registration failed:', error);
      });
  });
}

window.InjaazPWA = {
  update: () => navigator.serviceWorker.ready.then((registration) => registration.update()),
  unregister: () => navigator.serviceWorker.ready.then((registration) => registration.unregister()),
  getInstallStatus: () => window.matchMedia('(display-mode: standalone)').matches,
  clearCache: async () => {
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames.map((name) => caches.delete(name)));
  },
};
