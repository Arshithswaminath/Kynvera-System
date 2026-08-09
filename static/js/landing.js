/**
 * Kynvera landing page interactions: application tabs, nav state, mobile drawer.
 * No dependencies; loaded with `defer` from templates/landing.html.
 */
(function () {
  'use strict';

  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  function initTabs() {
    var tablist = document.querySelector('[role="tablist"]');
    if (!tablist) return;

    var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
    if (!tabs.length) return;

    function select(tab, focus) {
      tabs.forEach(function (item) {
        var selected = item === tab;
        item.setAttribute('aria-selected', String(selected));
        item.tabIndex = selected ? 0 : -1;

        var panel = document.getElementById(item.getAttribute('aria-controls'));
        if (panel) panel.hidden = !selected;
      });
      if (focus) tab.focus();
    }

    tabs.forEach(function (tab, index) {
      tab.addEventListener('click', function () {
        select(tab, false);
      });

      tab.addEventListener('keydown', function (event) {
        var step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (step) {
          event.preventDefault();
          select(tabs[(index + step + tabs.length) % tabs.length], true);
        } else if (event.key === 'Home' || event.key === 'End') {
          event.preventDefault();
          select(event.key === 'Home' ? tabs[0] : tabs[tabs.length - 1], true);
        }
      });
    });
  }

  function initNav() {
    var nav = document.getElementById('l-nav');
    if (!nav) return;

    var toggle = document.getElementById('l-nav-toggle');
    var drawer = document.getElementById('l-nav-drawer');
    var sectionObserver = null;

    function navLinks() {
      return Array.prototype.slice.call(
        nav.querySelectorAll('.l-nav-links [data-landing-nav-link]')
      );
    }

    function closeDrawer() {
      nav.classList.remove('is-open');
      if (toggle) toggle.setAttribute('aria-expanded', 'false');
    }

    if (toggle && drawer) {
      toggle.addEventListener('click', function () {
        var open = nav.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', String(open));
      });
      drawer.addEventListener('click', function (event) {
        if (event.target.tagName === 'A' || event.target.closest('[data-landing-ui-toggle]')) {
          if (event.target.tagName === 'A') closeDrawer();
        }
      });
      document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closeDrawer();
      });
    }

    var sentinel = document.createElement('div');
    sentinel.setAttribute('aria-hidden', 'true');
    sentinel.style.cssText = 'position:absolute;top:0;left:0;width:1px;height:1px;';
    document.body.appendChild(sentinel);

    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (entries) {
        nav.classList.toggle('is-stuck', !entries[0].isIntersecting);
      }).observe(sentinel);

      function bindSectionSpy() {
        if (sectionObserver) {
          sectionObserver.disconnect();
          sectionObserver = null;
        }

        var links = navLinks();
        var sections = links
          .map(function (link) {
            var id = link.getAttribute('href');
            return id && id.charAt(0) === '#' ? document.querySelector(id) : null;
          })
          .filter(Boolean);

        if (!sections.length) return;

        sectionObserver = new IntersectionObserver(
          function (entries) {
            entries.forEach(function (entry) {
              if (!entry.isIntersecting) return;
              links.forEach(function (link) {
                link.classList.toggle(
                  'is-active',
                  link.getAttribute('href') === '#' + entry.target.id
                );
              });
            });
          },
          { rootMargin: '-45% 0px -50% 0px' }
        );
        sections.forEach(function (section) {
          sectionObserver.observe(section);
        });
      }

      bindSectionSpy();
      document.addEventListener('kynvera:landing-ui', bindSectionSpy);
    }

    return closeDrawer;
  }

  function initAnchors(closeDrawer) {
    document.addEventListener('click', function (event) {
      var link = event.target.closest && event.target.closest('a[href^="#"]');
      if (!link) return;

      var id = link.getAttribute('href');
      if (!id || id === '#') return;

      var target = document.querySelector(id);
      if (!target) return;

      event.preventDefault();
      if (closeDrawer) closeDrawer();

      target.scrollIntoView({
        behavior: reducedMotion.matches ? 'auto' : 'smooth',
        block: 'start'
      });
      history.replaceState(null, '', id);
    });
  }

  function init() {
    initTabs();
    initAnchors(initNav());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
