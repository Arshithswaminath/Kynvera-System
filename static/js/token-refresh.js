/**
 * Proactive access-token refresh.
 *
 * The reactive refresh-on-401 logic in api-client.js / dashboard.js only
 * fires after a request has already failed, and several module shells
 * (Assets, Procurement, Devices, Ticketing) build auth headers directly
 * with no 401 handling at all — so a page left open past the access
 * token's ~1h lifetime shows an expired-token error instead of quietly
 * refreshing. This script decodes the token's own `exp` claim and
 * refreshes it in the background shortly before it lapses, so an active
 * session never hits a live 401 in the first place. It's independent of
 * api-client.js/dashboard.js so it works on every page regardless of
 * which (if any) fetch wrapper that page uses.
 */
(function () {
  'use strict';

  function base64UrlDecode(str) {
    str = str.replace(/-/g, '+').replace(/_/g, '/');
    while (str.length % 4) str += '=';
    try {
      return decodeURIComponent(
        atob(str)
          .split('')
          .map(function (c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
          })
          .join('')
      );
    } catch (e) {
      return null;
    }
  }

  function getTokenExpiryMs(token) {
    if (!token) return null;
    var parts = token.split('.');
    if (parts.length !== 3) return null;
    var payloadJson = base64UrlDecode(parts[1]);
    if (!payloadJson) return null;
    try {
      var claims = JSON.parse(payloadJson);
      return claims.exp ? claims.exp * 1000 : null;
    } catch (e) {
      return null;
    }
  }

  var refreshTimer = null;
  var refreshInFlight = null;

  function doRefresh() {
    if (refreshInFlight) return refreshInFlight;

    var refreshToken = localStorage.getItem('refresh_token');
    var headers = { 'Content-Type': 'application/json' };
    if (refreshToken) headers['Authorization'] = 'Bearer ' + refreshToken;

    refreshInFlight = fetch('/api/auth/refresh', {
      method: 'POST',
      headers: headers,
      credentials: 'include'
    })
      .then(function (res) {
        if (!res.ok) return null;
        return res.json();
      })
      .then(function (data) {
        if (data && data.access_token) {
          localStorage.setItem('access_token', data.access_token);
          schedule(data.access_token);
        }
      })
      .catch(function () {
        /* Network hiccup — a later reactive refresh (on the next failed
           request) or a page reload will still recover. */
      })
      .finally(function () {
        refreshInFlight = null;
      });

    return refreshInFlight;
  }

  function schedule(token) {
    if (refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
    var expMs = getTokenExpiryMs(token);
    if (!expMs) return;

    var lifetimeMs = expMs - Date.now();
    if (lifetimeMs <= 0) {
      // Already expired (e.g. laptop was asleep) — refresh right away.
      doRefresh();
      return;
    }
    // Refresh 5 minutes ahead of expiry, or halfway through the token's
    // life if it's configured shorter than 10 minutes.
    var leadMs = Math.min(5 * 60 * 1000, lifetimeMs / 2);
    var delay = Math.max(0, lifetimeMs - leadMs);
    refreshTimer = setTimeout(doRefresh, delay);
  }

  function init() {
    var token = localStorage.getItem('access_token');
    if (token) schedule(token);
  }

  // setTimeout can be throttled or effectively paused in a backgrounded
  // tab; re-check as soon as the tab is visible again so a long-idle tab
  // still refreshes before its next real API call.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') init();
  });

  init();
})();
