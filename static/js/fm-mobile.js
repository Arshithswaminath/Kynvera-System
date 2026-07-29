/**
 * FM mobile field helpers — offline queue, Capacitor camera, push token, QR.
 * Loaded on scan page and can be included from ticketing templates.
 */
(function (global) {
  'use strict';
  if (global.InjaazFMMobile) return;

  const QUEUE_KEY = 'injaaz_fm_offline_queue_v1';

  function isCapacitor() {
    return !!(global.Capacitor && global.Capacitor.isNativePlatform && global.Capacitor.isNativePlatform());
  }

  function getToken() {
    return localStorage.getItem('access_token') || '';
  }

  // Bearer only when a token exists — keeps the JWT cookie fallback working.
  function authHeaders(extra) {
    const h = Object.assign({}, extra || {});
    const t = getToken();
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
  }

  function loadQueue() {
    try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); }
    catch (_) { return []; }
  }

  function saveQueue(items) {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(items || []));
  }

  function enqueue(item) {
    const q = loadQueue();
    q.push(Object.assign({ id: Date.now() + '_' + Math.random().toString(36).slice(2) }, item));
    saveQueue(q);
    return q.length;
  }

  async function flushQueue() {
    if (!navigator.onLine) return { flushed: 0, remaining: loadQueue().length };
    const q = loadQueue();
    const remaining = [];
    let flushed = 0;
    for (const item of q) {
      try {
        const res = await fetch(item.url, {
          method: item.method || 'POST',
          headers: Object.assign(
            authHeaders({ 'Content-Type': 'application/json' }),
            item.headers || {}
          ),
          body: item.body ? JSON.stringify(item.body) : undefined,
        });
        if (res.ok) flushed += 1;
        else remaining.push(item);
      } catch (_) {
        remaining.push(item);
      }
    }
    saveQueue(remaining);
    return { flushed, remaining: remaining.length };
  }

  async function offlineAwareFetch(url, options) {
    options = options || {};
    const method = (options.method || 'GET').toUpperCase();
    if (!navigator.onLine && method !== 'GET') {
      enqueue({
        url,
        method,
        body: options.body ? (typeof options.body === 'string' ? JSON.parse(options.body) : options.body) : null,
        headers: options.headers || {},
      });
      return { ok: true, offlineQueued: true, data: { success: true, offline_queued: true } };
    }
    try {
      const res = await fetch(url, options);
      let data = {};
      try { data = await res.json(); } catch (_) {}
      return { ok: res.ok, data, status: res.status };
    } catch (err) {
      if (method !== 'GET') {
        enqueue({
          url,
          method,
          body: options.body ? (typeof options.body === 'string' ? JSON.parse(options.body) : options.body) : null,
        });
        return { ok: true, offlineQueued: true, data: { success: true, offline_queued: true } };
      }
      throw err;
    }
  }

  async function takePhoto() {
    if (isCapacitor()) {
      try {
        const { Camera } = global.Capacitor.Plugins;
        const photo = await Camera.getPhoto({
          quality: 80,
          resultType: 'base64',
          source: 'CAMERA',
        });
        return photo.base64String ? ('data:image/jpeg;base64,' + photo.base64String) : null;
      } catch (e) {
        console.warn('Capacitor camera failed', e);
      }
    }
    return null;
  }

  async function scanQr() {
    // Native barcode plugin optional — fall back to page BarcodeDetector
    return null;
  }

  async function registerPushToken(token, platform) {
    if (!token) return;
    await fetch('/api/auth/push-token', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ token, platform: platform || 'android' }),
    });
  }

  global.addEventListener('online', () => { flushQueue(); });
  if (navigator.onLine) setTimeout(() => flushQueue(), 1500);

  global.InjaazFMMobile = {
    enqueue,
    flushQueue,
    offlineAwareFetch,
    takePhoto,
    scanQr,
    registerPushToken,
    isCapacitor,
    loadQueue,
  };
})(typeof window !== 'undefined' ? window : globalThis);
