/**
 * Viewport-centered notice dialog (replaces window.alert for HR sign-off success).
 * Used by replacement-sign and management-sign pages.
 */
(function () {
  'use strict';

  var KEY_HANDLER_BOUND = false;

  function ensureModal() {
    if (document.getElementById('hrCenterNoticeModal')) {
      return;
    }

    var veil = document.createElement('div');
    veil.id = 'hrCenterNoticeModal';
    veil.className = 'hr-notice-veil';
    veil.setAttribute('aria-hidden', 'true');
    veil.setAttribute('role', 'dialog');
    veil.setAttribute('aria-modal', 'true');
    veil.setAttribute('aria-labelledby', 'hrCenterNoticeKicker');
    veil.setAttribute('aria-describedby', 'hrCenterNoticeBody');
    veil.innerHTML =
      '<div class="hr-notice-panel">' +
      '  <p class="hr-notice-kicker" id="hrCenterNoticeKicker">Injaaz</p>' +
      '  <h2 class="hr-notice-title" id="hrCenterNoticeTitle"></h2>' +
      '  <div class="hr-notice-body" id="hrCenterNoticeBody"></div>' +
      '  <div class="hr-notice-actions">' +
      '    <button type="button" class="hr-notice-btn hr-notice-btn-primary" id="hrCenterNoticeOk">OK</button>' +
      '  </div>' +
      '</div>';

    document.body.appendChild(veil);

    document.getElementById('hrCenterNoticeOk').addEventListener('click', function () {
      var cb = veil._hrNoticeOnOk;
      closeHrCenterNotice();
      if (typeof cb === 'function') {
        cb();
      }
    });

    if (!KEY_HANDLER_BOUND) {
      KEY_HANDLER_BOUND = true;
      document.addEventListener('keydown', function (ev) {
        var v = document.getElementById('hrCenterNoticeModal');
        if (!v || !v.classList.contains('is-open')) {
          return;
        }
        if (ev.key === 'Escape') {
          ev.preventDefault();
          document.getElementById('hrCenterNoticeOk').click();
        }
      });
    }
  }

  function closeHrCenterNotice() {
    var veil = document.getElementById('hrCenterNoticeModal');
    if (!veil) {
      return;
    }
    veil.classList.remove('is-open');
    veil.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    veil._hrNoticeOnOk = null;
  }

  /**
   * @param {{ message: string, title?: string, kicker?: string, okLabel?: string, onOk?: function(): void }} opts
   */
  window.openHrCenterNotice = function (opts) {
    opts = opts || {};
    ensureModal();

    var veil = document.getElementById('hrCenterNoticeModal');
    var kickerEl = document.getElementById('hrCenterNoticeKicker');
    var titleEl = document.getElementById('hrCenterNoticeTitle');
    var bodyEl = document.getElementById('hrCenterNoticeBody');
    var btnOk = document.getElementById('hrCenterNoticeOk');

    kickerEl.textContent = opts.kicker != null ? String(opts.kicker) : 'Injaaz';
    if (opts.title) {
      titleEl.style.display = '';
      titleEl.textContent = opts.title;
      veil.setAttribute('aria-labelledby', 'hrCenterNoticeKicker hrCenterNoticeTitle');
    } else {
      titleEl.style.display = 'none';
      titleEl.textContent = '';
      veil.setAttribute('aria-labelledby', 'hrCenterNoticeKicker');
    }

    bodyEl.innerHTML = '';
    var msg = (opts.message != null ? String(opts.message) : '').trim() || 'Saved.';
    var lines = msg.split(/\n+/);
    lines.forEach(function (line) {
      var t = line.trim();
      if (!t) {
        return;
      }
      var p = document.createElement('p');
      p.textContent = t;
      bodyEl.appendChild(p);
    });
    if (!bodyEl.firstChild) {
      var p0 = document.createElement('p');
      p0.textContent = msg;
      bodyEl.appendChild(p0);
    }

    btnOk.textContent = opts.okLabel || 'OK';
    veil._hrNoticeOnOk = opts.onOk;
    document.body.appendChild(veil);

    veil.classList.add('is-open');
    veil.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    btnOk.focus();
  };
})();
