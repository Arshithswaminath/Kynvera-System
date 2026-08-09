/**
 * Kynvera "Motion" landing — scroll-driven motion engine.
 *
 * Zero dependencies (no GSAP / Lenis CDN) so it matches the existing stack and
 * still works offline. Implements the four reference patterns:
 *   1. fade / rise-in on scroll        -> [data-reveal]
 *   2. scroll-linked word illumination -> [data-words] / [data-words-scroll]
 *   3. hand-drawn SVG line draws       -> .lm-draw
 *   4. pinned scrollytelling           -> [data-anatomy]
 * Plus: count-up stats, crossfade app tabs, animated FAQ, time-aware greeting.
 *
 * Only runs while the Motion panel is the visible landing UI; it tears itself
 * down when the user switches back to Classic or Bold.
 */
(function () {
  'use strict';

  var PANEL_ID = 'landing-ui-motion';
  var WORD_DIM = 0.16;

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  var root = null;
  var active = false;
  var built = false;

  var observers = [];
  var scrollGroups = [];
  var scrollRaf = 0;
  var countTimers = [];

  /* ---------------------------------------------------------------------- */
  /* helpers                                                                 */
  /* ---------------------------------------------------------------------- */

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  /**
   * requestAnimationFrame never fires while the document is hidden, so any
   * setup gated behind it would never run for a page opened in a background
   * tab. Layout is still computed when hidden, so a timeout is a safe stand-in.
   */
  function nextFrame(fn) {
    if (document.hidden) {
      window.setTimeout(fn, 0);
      return;
    }
    window.requestAnimationFrame(fn);
  }

  function easeOutExpo(t) {
    return t >= 1 ? 1 : 1 - Math.pow(2, -10 * t);
  }

  function all(selector) {
    return root ? Array.prototype.slice.call(root.querySelectorAll(selector)) : [];
  }

  function observe(callback, options) {
    if (!('IntersectionObserver' in window)) return null;
    var io = new IntersectionObserver(callback, options);
    observers.push(io);
    return io;
  }

  /* ---------------------------------------------------------------------- */
  /* one-time DOM prep — split words, measure paths, wire controls           */
  /* ---------------------------------------------------------------------- */

  function splitWords() {
    all('[data-words]').forEach(function (el) {
      if (el.dataset.wordsReady) return;

      var words = (el.textContent || '').trim().split(/\s+/);
      var frag = document.createDocumentFragment();

      words.forEach(function (word, index) {
        var span = document.createElement('span');
        span.className = 'lm-word';
        span.textContent = word;
        frag.appendChild(span);
        if (index < words.length - 1) {
          frag.appendChild(document.createTextNode(' '));
        }
      });

      el.textContent = '';
      el.appendChild(frag);
      el.dataset.wordsReady = '1';
    });
  }

  function prepPaths() {
    all('.lm-draw').forEach(function (path) {
      if (path.dataset.drawReady) return;
      if (typeof path.getTotalLength !== 'function') return;

      var length = path.getTotalLength();
      if (!length) return;

      path.style.strokeDasharray = length;
      path.style.strokeDashoffset = length;
      path.dataset.drawLength = length;
      path.dataset.drawReady = '1';
    });
  }

  function drawIn(scope) {
    var paths = scope.classList && scope.classList.contains('lm-draw')
      ? [scope]
      : Array.prototype.slice.call(scope.querySelectorAll('.lm-draw'));

    paths.forEach(function (path, index) {
      if (!path.dataset.drawReady) return;
      path.style.transitionDelay = index * 90 + 'ms';
      path.style.strokeDashoffset = '0';
    });
  }

  /* ---------------------------------------------------------------------- */
  /* 1 — fade / rise-in reveals                                              */
  /* ---------------------------------------------------------------------- */

  function initReveals() {
    var targets = all('[data-reveal]');
    if (!targets.length) return;

    targets.forEach(function (el) {
      var delay = parseInt(el.getAttribute('data-reveal-delay') || '0', 10);
      if (delay) {
        el.style.transitionDelay = delay + 'ms';
      }
    });

    if (!('IntersectionObserver' in window)) {
      targets.forEach(function (el) {
        el.classList.add('is-in');
        drawIn(el);
      });
      return;
    }

    var io = observe(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var el = entry.target;
          el.classList.add('is-in');
          drawIn(el);
          litOnReveal(el);
          io.unobserve(el);
        });
      },
      { rootMargin: '0px 0px -12% 0px', threshold: 0.08 }
    );

    targets.forEach(function (el) {
      io.observe(el);
    });
  }

  /* ---------------------------------------------------------------------- */
  /* 2a — staggered word light-up (hero sub, on reveal)                      */
  /* ---------------------------------------------------------------------- */

  function litOnReveal(el) {
    var host = el.matches('[data-words]:not([data-words-scroll])')
      ? el
      : el.querySelector('[data-words]:not([data-words-scroll])');
    if (!host) return;

    var words = host.querySelectorAll('.lm-word');
    words.forEach(function (word, index) {
      word.style.transitionDelay = 120 + index * 26 + 'ms';
      word.classList.add('is-lit');
    });
  }

  function initStaggeredWords() {
    // Hero sub sits outside a [data-reveal] wrapper — observe it directly.
    all('[data-words]:not([data-words-scroll])').forEach(function (el) {
      if (!('IntersectionObserver' in window)) {
        litOnReveal(el);
        return;
      }
      var io = observe(
        function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            litOnReveal(entry.target);
            io.unobserve(entry.target);
          });
        },
        { rootMargin: '0px 0px -10% 0px', threshold: 0.15 }
      );
      io.observe(el);
    });
  }

  /* ---------------------------------------------------------------------- */
  /* 2b — scroll-linked word illumination (the signature effect)             */
  /* ---------------------------------------------------------------------- */

  function initScrollWords() {
    scrollGroups = all('[data-words-scroll]').map(function (el) {
      return { el: el, words: Array.prototype.slice.call(el.querySelectorAll('.lm-word')) };
    });

    if (!scrollGroups.length) return;

    if (reduceMotion.matches) {
      scrollGroups.forEach(function (group) {
        group.words.forEach(function (word) {
          word.style.opacity = '1';
        });
      });
      return;
    }

    window.addEventListener('scroll', queueScroll, { passive: true });
    window.addEventListener('resize', queueScroll);
    // A tab restored from the background may have scrolled while hidden with
    // rAF suspended, so repaint once it is visible again.
    document.addEventListener('visibilitychange', onVisibility);
    paintScrollWords();
  }

  function onVisibility() {
    if (!document.hidden) queueScroll();
  }

  function paintScrollWords() {
    scrollRaf = 0;
    var viewport = window.innerHeight || 800;

    scrollGroups.forEach(function (group) {
      var rect = group.el.getBoundingClientRect();
      if (!rect.height) return;

      // 0 as the block enters the lower third, 1 once it has cleared the middle.
      var travelled = viewport * 0.82 - rect.top;
      var distance = rect.height + viewport * 0.42;
      var progress = clamp(travelled / distance, 0, 1);

      var count = group.words.length;
      var spread = 6; // how many words are mid-fade at once
      var head = progress * (count + spread);

      group.words.forEach(function (word, index) {
        var lit = clamp(head - index, 0, 1);
        word.style.opacity = (WORD_DIM + (1 - WORD_DIM) * lit).toFixed(3);
      });
    });
  }

  function queueScroll() {
    if (!active || scrollRaf) return;
    scrollRaf = window.requestAnimationFrame(paintScrollWords);
  }

  /* ---------------------------------------------------------------------- */
  /* count-up stats                                                          */
  /* ---------------------------------------------------------------------- */

  function runCountUp(el) {
    var target = parseFloat(el.getAttribute('data-countup'));
    if (isNaN(target)) return;

    // Hidden tabs never tick rAF, which would freeze the counter on "0".
    if (reduceMotion.matches || document.hidden) {
      el.textContent = String(target);
      return;
    }

    var duration = 1250;
    var start = 0;
    var raf = 0;

    function step(now) {
      if (!start) start = now;
      var t = clamp((now - start) / duration, 0, 1);
      el.textContent = String(Math.round(target * easeOutExpo(t)));
      if (t < 1) {
        raf = window.requestAnimationFrame(step);
        countTimers.push(raf);
      }
    }

    el.textContent = '0';
    raf = window.requestAnimationFrame(step);
    countTimers.push(raf);
  }

  function initCountUps() {
    var stats = all('[data-countup]');
    if (!stats.length) return;

    if (!('IntersectionObserver' in window)) return;

    var io = observe(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          runCountUp(entry.target);
          io.unobserve(entry.target);
        });
      },
      { threshold: 0.6 }
    );

    stats.forEach(function (el) {
      io.observe(el);
    });
  }

  /* ---------------------------------------------------------------------- */
  /* device frames — tinted until they wake up in view                       */
  /* ---------------------------------------------------------------------- */

  function initDevices() {
    var devices = all('.lm-device');
    if (!devices.length) return;

    if (!('IntersectionObserver' in window)) {
      devices.forEach(function (el) {
        el.classList.add('is-awake');
      });
      return;
    }

    var io = observe(
      function (entries) {
        entries.forEach(function (entry) {
          entry.target.classList.toggle('is-awake', entry.isIntersecting);
        });
      },
      { threshold: 0.35 }
    );

    devices.forEach(function (el) {
      io.observe(el);
    });
  }

  /* ---------------------------------------------------------------------- */
  /* 4 — pinned scrollytelling                                               */
  /* ---------------------------------------------------------------------- */

  function initAnatomy() {
    var section = root.querySelector('[data-anatomy]');
    if (!section) return;

    var chapters = Array.prototype.slice.call(section.querySelectorAll('.lm-chapter'));
    var organs = Array.prototype.slice.call(section.querySelectorAll('.lm-organ'));
    if (!chapters.length) return;

    function setActive(key) {
      chapters.forEach(function (chapter) {
        chapter.classList.toggle('is-active', chapter.getAttribute('data-chapter') === key);
      });
      organs.forEach(function (organ) {
        organ.classList.toggle('is-active', organ.getAttribute('data-organ') === key);
      });
    }

    if (!('IntersectionObserver' in window)) {
      chapters.forEach(function (chapter) {
        chapter.classList.add('is-active');
      });
      organs.forEach(function (organ) {
        organ.classList.add('is-active');
      });
      return;
    }

    // Whichever chapter is crossing the middle band of the viewport wins.
    var io = observe(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          setActive(entry.target.getAttribute('data-chapter'));
        });
      },
      { rootMargin: '-42% 0px -42% 0px', threshold: 0 }
    );

    chapters.forEach(function (chapter) {
      io.observe(chapter);
    });

    setActive(chapters[0].getAttribute('data-chapter'));
  }

  /* ---------------------------------------------------------------------- */
  /* application tabs — crossfade + gliding pill                             */
  /* ---------------------------------------------------------------------- */

  function initTabs() {
    var tablist = root.querySelector('.lm-tabs');
    if (!tablist) return;

    var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
    var glider = tablist.querySelector('.lm-tab-glider');
    if (!tabs.length) return;

    function moveGlider(tab) {
      if (!glider) return;
      glider.style.width = tab.offsetWidth + 'px';
      glider.style.transform = 'translateX(' + tab.offsetLeft + 'px)';
    }

    function select(tab, focus) {
      tabs.forEach(function (item) {
        var selected = item === tab;
        item.setAttribute('aria-selected', String(selected));
        item.tabIndex = selected ? 0 : -1;
        item.classList.toggle('is-active', selected);

        var panel = document.getElementById(item.getAttribute('aria-controls'));
        if (!panel) return;

        if (selected) {
          panel.hidden = false;
          // let the browser lay the panel out before the crossfade starts
          nextFrame(function () {
            panel.classList.add('is-active');
          });
        } else {
          panel.classList.remove('is-active');
          panel.hidden = true;
        }
      });

      moveGlider(tab);
      if (focus) tab.focus();
    }

    tabs.forEach(function (tab, index) {
      if (tab.dataset.lmBound) return;
      tab.dataset.lmBound = '1';

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

    var current = tabs.filter(function (tab) {
      return tab.getAttribute('aria-selected') === 'true';
    })[0] || tabs[0];

    moveGlider(current);
    window.addEventListener('resize', function () {
      if (active) moveGlider(current);
    });
  }

  /* ---------------------------------------------------------------------- */
  /* FAQ — animate the close as well as the open                             */
  /* ---------------------------------------------------------------------- */

  function initFaqs() {
    var list = root.querySelector('.lm-faqs');
    if (!list || list.dataset.lmBound) return;

    list.dataset.lmBound = '1';
    list.classList.add('js-faq');

    var items = Array.prototype.slice.call(list.querySelectorAll('.lm-faq'));

    function close(item) {
      item.classList.remove('is-open');
      var body = item.querySelector('.lm-faq-body');
      if (!body || reduceMotion.matches) {
        item.open = false;
        return;
      }
      var done = false;
      function finish() {
        if (done) return;
        done = true;
        body.removeEventListener('transitionend', finish);
        if (!item.classList.contains('is-open')) item.open = false;
      }
      body.addEventListener('transitionend', finish);
      window.setTimeout(finish, 650);
    }

    function open(item) {
      item.open = true;
      nextFrame(function () {
        item.classList.add('is-open');
      });
    }

    items.forEach(function (item) {
      var summary = item.querySelector('summary');
      if (!summary) return;

      summary.addEventListener('click', function (event) {
        event.preventDefault();

        if (item.classList.contains('is-open')) {
          close(item);
          return;
        }

        items.forEach(function (other) {
          if (other !== item && other.classList.contains('is-open')) close(other);
        });
        open(item);
      });
    });
  }

  /* ---------------------------------------------------------------------- */
  /* time-aware greeting                                                     */
  /* ---------------------------------------------------------------------- */

  function initGreeting() {
    var el = document.getElementById('m-greeting');
    if (!el) return;

    var hour = new Date().getHours();
    var greeting = 'Good evening!';
    if (hour < 12) greeting = 'Good morning!';
    else if (hour < 17) greeting = 'Good afternoon!';

    el.textContent = greeting;
  }

  /* ---------------------------------------------------------------------- */
  /* lifecycle                                                               */
  /* ---------------------------------------------------------------------- */

  function build() {
    // Measurement-dependent work must happen while the panel is visible.
    splitWords();
    prepPaths();
    initGreeting();
    initTabs();
    initFaqs();
    built = true;
  }

  function activate() {
    if (active) return;
    root = document.getElementById(PANEL_ID);
    if (!root) return;

    active = true;

    // The panel was `hidden` until now, so wait a frame for layout before
    // measuring path lengths, tab offsets and scroll positions.
    nextFrame(function () {
      if (!active) return;

      if (!built) build();
      else prepPaths();

      initReveals();
      initStaggeredWords();
      initScrollWords();
      initCountUps();
      initDevices();
      initAnatomy();

      // re-seat the tab glider now that the panel has real dimensions
      var activeTab = root.querySelector('.lm-tab.is-active');
      var glider = root.querySelector('.lm-tab-glider');
      if (activeTab && glider) {
        glider.style.width = activeTab.offsetWidth + 'px';
        glider.style.transform = 'translateX(' + activeTab.offsetLeft + 'px)';
      }
    });
  }

  function deactivate() {
    if (!active) return;
    active = false;

    observers.forEach(function (io) {
      io.disconnect();
    });
    observers = [];

    window.removeEventListener('scroll', queueScroll);
    window.removeEventListener('resize', queueScroll);
    document.removeEventListener('visibilitychange', onVisibility);

    if (scrollRaf) {
      window.cancelAnimationFrame(scrollRaf);
      scrollRaf = 0;
    }

    countTimers.forEach(function (id) {
      window.cancelAnimationFrame(id);
    });
    countTimers = [];

    scrollGroups = [];
  }

  function sync(ui) {
    if (ui === 'motion') activate();
    else deactivate();
  }

  function init() {
    if (!document.body.classList.contains('landing')) return;
    if (!document.getElementById(PANEL_ID)) return;

    document.addEventListener('kynvera:landing-ui', function (event) {
      sync(event && event.detail && event.detail.ui);
    });

    // landing-ui.js may have already applied the stored choice before we loaded.
    sync(document.body.getAttribute('data-landing-ui'));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
