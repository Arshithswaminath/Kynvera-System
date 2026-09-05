/**
 * Jump the HR form viewport to the top when switching Step 1 / Step 2.
 * scrollIntoView on the panel leaves the page at the Continue-button offset.
 */
(function (global) {
  function hrScrollFormToTop() {
    try {
      if (global.document && global.document.activeElement && global.document.activeElement.blur) {
        global.document.activeElement.blur();
      }
    } catch (_) {}
    var jump = function () {
      if (global.scrollTo) {
        try {
          global.scrollTo({ top: 0, left: 0, behavior: 'auto' });
        } catch (_) {
          global.scrollTo(0, 0);
        }
      }
      if (global.document) {
        if (global.document.documentElement) global.document.documentElement.scrollTop = 0;
        if (global.document.body) global.document.body.scrollTop = 0;
      }
      var el =
        (global.document && (global.document.querySelector('.page') || global.document.body)) ||
        null;
      while (el && el !== global.document.documentElement) {
        if (el.scrollTop) el.scrollTop = 0;
        el = el.parentElement;
      }
    };
    jump();
    if (typeof global.requestAnimationFrame === 'function') {
      global.requestAnimationFrame(function () {
        jump();
        global.requestAnimationFrame(jump);
      });
    }
  }
  global.hrScrollFormToTop = hrScrollFormToTop;
})(typeof window !== 'undefined' ? window : this);
