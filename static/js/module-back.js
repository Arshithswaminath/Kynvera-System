/**
 * Shared back-link behaviour for module navigation.
 * Prefer same-origin history.back(); otherwise follow the link href (fallback).
 */
(function () {
  if (window.__kynveraModuleBackBound) return;
  window.__kynveraModuleBackBound = true;

  var SELECTOR = [
    '[data-module-back]',
    'a.module-back-link',
    'a.back-btn',
    'a.back-btn-proc',
    'a.back-link',
    'a.if-back-btn',
    'a.hh-back',
    'a.sb-back-link'
  ].join(',');

  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest(SELECTOR);
    if (!a) return;
    if (a.getAttribute('data-no-history-back') === '1') return;
    var ref = document.referrer || '';
    var here = window.location.href.split('#')[0];
    if (ref && ref.indexOf(window.location.origin) === 0 && ref.split('#')[0] !== here) {
      e.preventDefault();
      history.back();
    }
  });
})();
