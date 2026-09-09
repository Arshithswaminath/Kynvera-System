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

    function setFlipped(on) {
      card.classList.toggle('is-flipped', !!on);
      card.setAttribute('aria-pressed', on ? 'true' : 'false');
    }

    function openCard() {
      closeHamburger();
      setFlipped(false);
      modal.hidden = false;
      document.body.style.overflow = 'hidden';
      var closeBtn = modal.querySelector('.kv-builder-close');
      if (closeBtn) closeBtn.focus();
    }

    function closeCard() {
      modal.hidden = true;
      setFlipped(false);
      if (!document.body.classList.contains('mobile-menu-open')) {
        document.body.style.overflow = '';
      }
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
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
