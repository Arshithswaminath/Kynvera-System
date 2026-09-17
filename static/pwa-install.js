// Service worker registration (install / download UI removed)
//
// Skipped on local dev hosts: its scope (/static/) covers every page on the
// origin once registered from any page (e.g. the dashboard), which makes
// local JS/CSS edits look like they never took effect until it's manually
// unregistered. Any previously-registered worker is also torn down here so
// local testing doesn't need a manual DevTools cleanup step.
const _isLocalDevHost = ['localhost', '127.0.0.1'].includes(window.location.hostname);

if ('serviceWorker' in navigator && !_isLocalDevHost) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/static/service-worker.js')
      .then((registration) => {
        setInterval(() => registration.update(), 60 * 60 * 1000);

        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              if (confirm('A new version of Kynvera is available. Reload to update?')) {
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
} else if ('serviceWorker' in navigator && _isLocalDevHost) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((reg) => reg.unregister());
  });
  caches.keys().then((names) => names.forEach((name) => caches.delete(name)));
}

window.KynveraPWA = {
  update: () => navigator.serviceWorker.ready.then((registration) => registration.update()),
  unregister: () => navigator.serviceWorker.ready.then((registration) => registration.unregister()),
  getInstallStatus: () => window.matchMedia('(display-mode: standalone)').matches,
  clearCache: async () => {
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames.map((name) => caches.delete(name)));
  },
};
