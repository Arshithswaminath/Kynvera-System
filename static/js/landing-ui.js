/**
 * Classic / Bold / Motion landing UI switcher.
 * Persists choice in localStorage; updates nav anchors and theme-color.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'kynvera-landing-ui';
  var CLASSIC = 'classic';
  var BOLD = 'bold';
  var MOTION = 'motion';

  var UIS = [CLASSIC, BOLD, MOTION];

  var PANEL_IDS = {
    classic: 'landing-ui-classic',
    bold: 'landing-ui-bold',
    motion: 'landing-ui-motion'
  };

  var NAV_HREFS = {
    classic: ['#applications', '#platform', '#how-it-works', '#pricing', '#faqs'],
    bold: ['#b-applications', '#b-platform', '#b-how-it-works', '#b-pricing', '#b-faqs'],
    motion: ['#m-applications', '#m-platform', '#m-how-it-works', '#m-pricing', '#m-faqs']
  };

  var THEME = {
    classic: '#E8E8E7',
    bold: '#ff8e68',
    motion: '#fdf7f0'
  };

  var heroGrid = (function () {
    var hero = null;
    var pointerAttached = false;
    var pointerInside = false;
    var raf = 0;
    var reduceMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    var coarsePointerQuery = window.matchMedia('(pointer: coarse)');
    var prefersReducedMotion = reduceMotionQuery.matches;
    var isCoarsePointer = coarsePointerQuery.matches;

    var current = { x: 0.5, y: 0.5, dx: 0, dy: 0, glow: 0 };
    var target = { x: 0.5, y: 0.5, dx: 0, dy: 0, glow: 0 };

    function clamp(value, min, max) {
      return Math.min(max, Math.max(min, value));
    }

    function applyState() {
      if (!hero) return;
      hero.style.setProperty('--grid-x', (current.x * 100).toFixed(2) + '%');
      hero.style.setProperty('--grid-y', (current.y * 100).toFixed(2) + '%');
      hero.style.setProperty('--grid-dx', current.dx.toFixed(2) + 'px');
      hero.style.setProperty('--grid-dy', current.dy.toFixed(2) + 'px');
      hero.style.setProperty('--grid-glow', current.glow.toFixed(3));
    }

    function resetTarget() {
      target.x = 0.5;
      target.y = 0.5;
      target.dx = 0;
      target.dy = 0;
      target.glow = 0;
    }

    function cancelTick() {
      if (!raf) return;
      window.cancelAnimationFrame(raf);
      raf = 0;
    }

    function tick() {
      raf = 0;

      if (!pointerInside) {
        var now = window.performance && window.performance.now ? window.performance.now() : Date.now();
        var t = now * 0.00028;
        target.x = clamp(0.5 + Math.sin(t) * 0.32, 0.08, 0.92);
        target.y = clamp(0.72 + Math.cos(t * 0.72) * 0.14, 0.44, 0.95);
        target.dx = Math.sin(t * 1.25) * 18;
        target.dy = Math.cos(t * 0.94) * 12;
        target.glow = 0.46 + ((Math.sin(t * 1.8) + 1) * 0.16);
      }

      current.x += (target.x - current.x) * 0.16;
      current.y += (target.y - current.y) * 0.16;
      current.dx += (target.dx - current.dx) * 0.14;
      current.dy += (target.dy - current.dy) * 0.14;
      current.glow += (target.glow - current.glow) * 0.14;

      applyState();

      var stillMoving =
        Math.abs(target.x - current.x) > 0.001 ||
        Math.abs(target.y - current.y) > 0.001 ||
        Math.abs(target.dx - current.dx) > 0.02 ||
        Math.abs(target.dy - current.dy) > 0.02 ||
        Math.abs(target.glow - current.glow) > 0.01;

      if (!pointerInside || stillMoving) raf = window.requestAnimationFrame(tick);
    }

    function queueTick() {
      if (!raf) raf = window.requestAnimationFrame(tick);
    }

    function onPointerMove(event) {
      if (!hero) return;
      pointerInside = true;
      var rect = hero.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      var nx = clamp((event.clientX - rect.left) / rect.width, 0, 1);
      var ny = clamp((event.clientY - rect.top) / rect.height, 0, 1);

      target.x = nx;
      target.y = ny;
      target.dx = (nx - 0.5) * 38;
      target.dy = (ny - 0.5) * 28;
      target.glow = 1;
      queueTick();
    }

    function onPointerEnter() {
      pointerInside = true;
      target.glow = 1;
      queueTick();
    }

    function onPointerLeave() {
      pointerInside = false;
      queueTick();
    }

    function onMotionPreferenceChange(event) {
      prefersReducedMotion = event.matches;
      if (prefersReducedMotion) {
        detach();
      } else {
        attach();
      }
    }

    function onCoarsePointerChange(event) {
      isCoarsePointer = event.matches;
      if (isCoarsePointer) {
        detach();
      } else {
        attach();
      }
    }

    function attach() {
      hero = document.querySelector('#landing-ui-bold .lb-hero');
      if (!hero || pointerAttached || prefersReducedMotion || isCoarsePointer) return;

      hero.addEventListener('pointerenter', onPointerEnter);
      hero.addEventListener('pointermove', onPointerMove);
      hero.addEventListener('pointerleave', onPointerLeave);
      pointerAttached = true;
      pointerInside = false;
      queueTick();
    }

    function detach() {
      if (hero && pointerAttached) {
        hero.removeEventListener('pointerenter', onPointerEnter);
        hero.removeEventListener('pointermove', onPointerMove);
        hero.removeEventListener('pointerleave', onPointerLeave);
      }

      pointerAttached = false;
      pointerInside = false;
      hero = document.querySelector('#landing-ui-bold .lb-hero');
      resetTarget();
      current.x = 0.5;
      current.y = 0.5;
      current.dx = 0;
      current.dy = 0;
      current.glow = 0;
      cancelTick();
      applyState();
    }

    if (typeof reduceMotionQuery.addEventListener === 'function') {
      reduceMotionQuery.addEventListener('change', onMotionPreferenceChange);
      coarsePointerQuery.addEventListener('change', onCoarsePointerChange);
    } else if (typeof reduceMotionQuery.addListener === 'function') {
      reduceMotionQuery.addListener(onMotionPreferenceChange);
      coarsePointerQuery.addListener(onCoarsePointerChange);
    }

    return {
      setActive: function (active) {
        if (active) {
          attach();
        } else {
          detach();
        }
      }
    };
  })();

  function normalise(ui) {
    return UIS.indexOf(ui) === -1 ? CLASSIC : ui;
  }

  /* ?ui=classic|bold|motion pins a design for review links; it wins over the
     stored preference for this page view but is not persisted. */
  function readForced() {
    try {
      var ui = new URLSearchParams(window.location.search).get('ui');
      return UIS.indexOf(ui) === -1 ? null : ui;
    } catch (err) {
      return null;
    }
  }

  function readStored() {
    var forced = readForced();
    if (forced) return forced;
    try {
      return normalise(localStorage.getItem(STORAGE_KEY));
    } catch (err) {
      return CLASSIC;
    }
  }

  function persist(ui) {
    try {
      localStorage.setItem(STORAGE_KEY, ui);
    } catch (err) {
      /* ignore quota / private mode */
    }
  }

  function setThemeColor(ui) {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', THEME[ui] || THEME.classic);
  }

  function updateNavHrefs(ui) {
    var hrefs = NAV_HREFS[ui] || NAV_HREFS.classic;
    var groups = [
      document.querySelectorAll('.l-nav-links [data-landing-nav-link]'),
      document.querySelectorAll('.l-nav-drawer [data-landing-nav-link]')
    ];
    groups.forEach(function (links) {
      links.forEach(function (link, index) {
        if (hrefs[index]) link.setAttribute('href', hrefs[index]);
      });
    });
  }

  function syncToggle(ui) {
    var toggles = document.querySelectorAll('[data-landing-ui-toggle]');
    toggles.forEach(function (btn) {
      var target = btn.getAttribute('data-landing-ui-toggle');
      var active = target === ui;
      btn.setAttribute('aria-pressed', String(active));
      btn.classList.toggle('is-active', active);
    });
  }

  function apply(ui, options) {
    var next = normalise(ui);

    document.body.setAttribute('data-landing-ui', next);
    document.documentElement.removeAttribute('data-landing-ui-boot');

    UIS.forEach(function (name) {
      var panel = document.getElementById(PANEL_IDS[name]);
      if (panel) panel.hidden = name !== next;
    });

    updateNavHrefs(next);
    syncToggle(next);
    setThemeColor(next);
    persist(next);

    if (options && options.scrollTop) {
      window.scrollTo({ top: 0, behavior: 'auto' });
    }

    document.dispatchEvent(
      new CustomEvent('kynvera:landing-ui', { detail: { ui: next } })
    );
  }

  function init() {
    if (!document.body.classList.contains('landing')) return;
    if (!document.getElementById('landing-ui-bold')) return;

    document.addEventListener('kynvera:landing-ui', function (event) {
      var activeUi = event && event.detail && event.detail.ui;
      heroGrid.setActive(activeUi === BOLD);
    });

    apply(readStored(), { scrollTop: false });

    document.addEventListener('click', function (event) {
      var btn = event.target.closest && event.target.closest('[data-landing-ui-toggle]');
      if (!btn) return;
      event.preventDefault();
      apply(btn.getAttribute('data-landing-ui-toggle'), { scrollTop: true });

      var nav = document.getElementById('l-nav');
      if (nav) {
        nav.classList.remove('is-open');
        var toggle = document.getElementById('l-nav-toggle');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.KynveraLandingUI = { apply: apply, read: readStored };
})();
