/**
 * console-guard.js
 * Silences verbose debug output (console.log / console.debug / console.info)
 * when the page is served from a non-development origin.
 *
 * To enable verbose logging locally, open DevTools and run:
 *   window.__INJAAZ_DEBUG__ = true; location.reload();
 *
 * Errors and warnings are always preserved so real problems surface.
 */
(function () {
  'use strict';

  // Keep debug logging in local development environments
  var devHosts = ['localhost', '127.0.0.1', '0.0.0.0'];
  var isLocal = devHosts.indexOf(location.hostname) !== -1;
  var isDebug = isLocal || window.__INJAAZ_DEBUG__ === true;

  if (!isDebug) {
    var noop = function () {};
    console.log   = noop;
    console.debug = noop;
    console.info  = noop;
    // console.warn and console.error are kept intentionally
  }
})();
