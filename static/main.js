// Minimal client placeholder (expand later)

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/service-worker.js').then(() => {
      console.info('Service worker registered');
    }).catch((err) => {
      console.warn('Service worker failed', err);
    });
  });
}