/**
 * Shared back-link behaviour for contextual "back to where I came from" buttons.
 * Prefer same-origin history.back() (keeps scroll/filter state); otherwise follow
 * the link href (fallback).
 *
 * Elements carrying [data-module-back] are always excluded, even when they also
 * carry one of the classes below — module_back_link.html's breadcrumb reuses
 * classes like .back-btn purely for hero styling (see module_back_extra_class),
 * so the class alone can't distinguish "styled like a back button" from "is the
 * page's breadcrumb". The breadcrumb always points at a fixed parent page
 * (module_back_url) and must always follow its href: routing it through
 * history.back() too meant it and a detail page's own "Back to X" button could
 * ping-pong between each other forever instead of the breadcrumb ever reaching
 * its real, fixed destination.
 */
(function () {
  if (window.__kynveraModuleBackBound) return;
  window.__kynveraModuleBackBound = true;

  var SELECTOR = [
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
    if (a.hasAttribute('data-module-back')) return;
    if (a.getAttribute('data-no-history-back') === '1') return;
    var ref = document.referrer || '';
    var here = window.location.href.split('#')[0];
    if (ref && ref.indexOf(window.location.origin) === 0 && ref.split('#')[0] !== here) {
      e.preventDefault();
      history.back();
    }
  });
})();
