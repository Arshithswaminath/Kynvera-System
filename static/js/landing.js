/* Kynvera public landing page — progressive enhancement only.
   The page is fully readable and navigable with this file absent. */
(function () {
  'use strict';

  var reduceMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* --- Sticky nav: transparent at top; solid frost once scrolled so links stay readable --- */
  var nav = document.getElementById('lp-nav');
  if (nav) {
    var syncNav = function () {
      nav.classList.toggle('is-stuck', window.scrollY > 8);
    };
    syncNav();
    window.addEventListener('scroll', syncNav, { passive: true });
  }

  /* --- Mobile nav toggle --- */
  var toggle = document.getElementById('lp-nav-toggle');
  var links = document.getElementById('lp-nav-links');

  if (toggle && links) {
    var setOpen = function (open) {
      toggle.setAttribute('aria-expanded', String(open));
      links.classList.toggle('is-open', open);
    };

    toggle.addEventListener('click', function () {
      setOpen(toggle.getAttribute('aria-expanded') !== 'true');
    });

    links.addEventListener('click', function (event) {
      if (event.target.closest('a')) setOpen(false);
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
        setOpen(false);
        toggle.focus();
      }
    });

    document.addEventListener('click', function (event) {
      if (toggle.getAttribute('aria-expanded') !== 'true') return;
      if (!event.target.closest('#lp-nav-links') && !event.target.closest('#lp-nav-toggle')) {
        setOpen(false);
      }
    });
  }

  /* --- Scroll reveal ---
     The .lp-reveal class is added here rather than in the markup so that
     content is never hidden when JS is unavailable or IO is unsupported.
     A hard safety net reveals everything after 2.5s regardless, so a throttled
     background tab or a starved observer can never leave the page blank. */
  if (!reduceMotion && 'IntersectionObserver' in window) {
    var targets = document.querySelectorAll(
      '.lp-section .lp-eyebrow, .lp-section .lp-h2, .lp-section .lp-lead,' +
      '.lp-benefit, .lp-mock-frame, .lp-features-bento > *, .lp-modules-bento > *,' +
      '.lp-interop-tile, .lp-proof-bento > *, .lp-tier, .lp-cta-band'
    );

    var revealAll = function () {
      targets.forEach(function (el) {
        el.classList.add('is-in');
      });
    };

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '160px 0px 160px 0px', threshold: 0 });

    targets.forEach(function (el, index) {
      el.classList.add('lp-reveal');
      // Nudge siblings apart so a grid row cascades rather than popping.
      el.style.transitionDelay = (index % 4) * 60 + 'ms';
      observer.observe(el);
    });

    window.setTimeout(revealAll, 2500);
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') revealAll();
    });
    window.addEventListener('beforeprint', revealAll);
  }
})();
