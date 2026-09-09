/**
 * Who built this? — flip visiting card.
 */
(function () {
  'use strict';

  function $(id) {
    return document.getElementById(id);
  }

  function closeHamburger() {
    var drawer = $('mobileMenuDrawer');
    var overlay = $('mobileOverlay');
    var toggle = $('mobileMenuToggle');
    if (drawer) {
      drawer.classList.remove('active');
      drawer.setAttribute('aria-hidden', 'true');
    }
    if (overlay) overlay.classList.remove('active');
    if (toggle) {
      toggle.classList.remove('active');
      toggle.classList.remove('is-hint-paused');
      toggle.setAttribute('aria-expanded', 'false');
    }
    document.body.classList.remove('mobile-menu-open');
    document.body.style.overflow = '';
  }

  function viewportBox() {
    var vv = window.visualViewport;
    return {
      top: vv ? vv.offsetTop : 0,
      left: vv ? vv.offsetLeft : 0,
      width: Math.round(vv ? vv.width : window.innerWidth),
      height: Math.round(vv ? vv.height : window.innerHeight),
      pageTop: (window.scrollY || window.pageYOffset || 0) + (vv ? vv.offsetTop : 0),
      pageLeft: (window.scrollX || window.pageXOffset || 0) + (vv ? vv.offsetLeft : 0)
    };
  }

  function init() {
    var modal = $('kvBuilderModal');
    var card = $('kvBuilderCard');
    if (!modal || !card) return;
    if (modal.parentElement !== document.body) {
      document.body.appendChild(modal);
    }

    function isOpen() {
      return !modal.hidden;
    }

    function prefersReducedMotion() {
      return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function canTrackPointer() {
      return window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    }

    function resetTilt() {
      card.classList.remove('is-tracking');
      card.classList.add('is-untilting');
      card.style.setProperty('--kv-tilt-x', '0deg');
      card.style.setProperty('--kv-tilt-y', '0deg');
      card.style.setProperty('--kv-scale', '1');
      card.style.setProperty('--kv-shine-x', '50%');
      card.style.setProperty('--kv-shine-y', '50%');
    }

    function trackPointer(e) {
      if (!isOpen() || prefersReducedMotion() || !canTrackPointer()) return;
      var rect = card.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      var px = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      var py = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
      var tiltX = (0.5 - py) * 12;
      var tiltY = (px - 0.5) * 16;
      if (card.classList.contains('is-flipped')) tiltY = -tiltY;
      card.classList.remove('is-untilting');
      card.classList.add('is-tracking');
      card.style.setProperty('--kv-tilt-x', tiltX.toFixed(2) + 'deg');
      card.style.setProperty('--kv-tilt-y', tiltY.toFixed(2) + 'deg');
      card.style.setProperty('--kv-scale', '1.03');
      card.style.setProperty('--kv-shine-x', (px * 100).toFixed(2) + '%');
      card.style.setProperty('--kv-shine-y', (py * 100).toFixed(2) + '%');
    }

    function setFlipped(on) {
      card.classList.toggle('is-flipped', !!on);
      card.setAttribute('aria-pressed', on ? 'true' : 'false');
      resetTilt();
    }

    function clearPin() {
      ['position', 'top', 'left', 'right', 'bottom', 'width', 'height'].forEach(function (prop) {
        modal.style.removeProperty(prop);
      });
    }

    function pinToScreen() {
      if (!isOpen()) return;
      var box = viewportBox();
      modal.style.setProperty('position', 'fixed', 'important');
      modal.style.setProperty('top', box.top + 'px', 'important');
      modal.style.setProperty('left', box.left + 'px', 'important');
      modal.style.setProperty('right', 'auto', 'important');
      modal.style.setProperty('bottom', 'auto', 'important');
      modal.style.setProperty('width', box.width + 'px', 'important');
      modal.style.setProperty('height', box.height + 'px', 'important');

      var rect = modal.getBoundingClientRect();
      if (Math.abs(rect.top - box.top) > 2 || Math.abs(rect.left - box.left) > 2) {
        modal.style.setProperty('position', 'absolute', 'important');
        modal.style.setProperty('top', box.pageTop + 'px', 'important');
        modal.style.setProperty('left', box.pageLeft + 'px', 'important');
      }
    }

    function openCard() {
      closeHamburger();
      setFlipped(false);
      document.documentElement.classList.add('kv-builder-open');
      modal.hidden = false;
      pinToScreen();
      var closeBtn = modal.querySelector('.kv-builder-close');
      if (closeBtn) closeBtn.focus();
    }

    function closeCard() {
      modal.hidden = true;
      setFlipped(false);
      clearPin();
      document.documentElement.classList.remove('kv-builder-open');
    }

    document.querySelectorAll('[data-open-builder-card], #whoBuiltThisBtn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        openCard();
      });
    });

    modal.querySelectorAll('[data-close-builder-card]').forEach(function (el) {
      el.addEventListener('click', closeCard);
    });

    card.addEventListener('pointermove', trackPointer);
    card.addEventListener('pointerleave', resetTilt);

    card.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      setFlipped(!card.classList.contains('is-flipped'));
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) {
        e.stopPropagation();
        closeCard();
      }
    });

    window.addEventListener('resize', pinToScreen);
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', pinToScreen);
      window.visualViewport.addEventListener('scroll', pinToScreen);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
