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

    function setFlipped(on) {
      card.classList.toggle('is-flipped', !!on);
      card.setAttribute('aria-pressed', on ? 'true' : 'false');
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
