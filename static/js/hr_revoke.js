/**
 * Shared HR form revoke modal: required comment + optional open-new form.
 * Uses POST /api/workflow/submissions/<id>/revoke (withdraw alias).
 */
(function (global) {
  'use strict';

  var STYLE_ID = 'hr-revoke-modal-styles';
  var OVERLAY_ID = 'hrRevokeModalOverlay';
  var ACCENT = '#ff8e68';
  var ACCENT_DARK = '#e05f36';

  function ensureStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent =
      '#' +
      OVERLAY_ID +
      '{position:fixed;inset:0;z-index:10050;display:none;align-items:center;justify-content:center;' +
      'padding:1.25rem;background:rgba(15,23,42,.48);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);' +
      'opacity:0;transition:opacity .18s ease;}' +
      '#' +
      OVERLAY_ID +
      '.open{display:flex;opacity:1;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal{background:#fff;border-radius:16px;max-width:440px;width:100%;' +
      'box-shadow:0 24px 48px -12px rgba(15,23,42,.35),0 0 0 1px rgba(15,23,42,.04);' +
      'overflow:hidden;transform:translateY(8px) scale(.98);opacity:0;' +
      'transition:transform .2s cubic-bezier(.22,1,.36,1),opacity .2s ease;}' +
      '#' +
      OVERLAY_ID +
      '.open .hr-revoke-modal{transform:translateY(0) scale(1);opacity:1;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal-hd{padding:1.2rem 1.35rem 1.05rem;border-bottom:1px solid #eef2f7;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal-hd h3{margin:0;font-size:1.12rem;letter-spacing:-0.01em;color:' +
      ACCENT_DARK +
      ';font-weight:700;line-height:1.3;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal-hd p{margin:.4rem 0 0;font-size:.875rem;color:#64748b;line-height:1.5;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal-bd{padding:1.15rem 1.35rem;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-field-label{display:block;font-size:.8rem;font-weight:700;color:#334155;margin-bottom:.4rem;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal-bd textarea{width:100%;min-height:104px;border:1.5px solid #f1baa8;border-radius:10px;' +
      'padding:.7rem .8rem;font-size:16px;font-family:inherit;resize:vertical;box-sizing:border-box;' +
      'color:#0f172a;background:#fff;line-height:1.45;transition:border-color .15s,box-shadow .15s;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal-bd textarea::placeholder{color:#94a3b8;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal-bd textarea:focus{outline:none;border-color:' +
      ACCENT +
      ';box-shadow:0 0 0 3px rgba(255, 142, 104,.14);}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal-bd textarea.hr-revoke-invalid{border-color:' +
      ACCENT +
      ';background:#fff8f8;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-meta{display:flex;justify-content:space-between;align-items:center;margin-top:.4rem;gap:.5rem;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-err{display:none;font-size:.8rem;color:' +
      ACCENT_DARK +
      ';font-weight:600;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-count{font-size:.72rem;color:#94a3b8;margin-left:auto;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-check{display:flex;align-items:flex-start;gap:.65rem;margin-top:1rem;padding:.75rem .85rem;' +
      'border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;cursor:pointer;' +
      'font-size:.85rem;color:#334155;line-height:1.4;transition:border-color .15s,background .15s;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-check:hover{border-color:#cbd5e1;background:#f1f5f9;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-check:has(input:checked){border-color:#fecaca;background:#fff8f5;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-check input{margin-top:.12rem;width:18px;height:18px;flex-shrink:0;accent-color:' +
      ACCENT +
      ';cursor:pointer;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-modal-ft{display:flex;flex-wrap:wrap;gap:.55rem;justify-content:flex-end;' +
      'padding:.95rem 1.35rem 1.15rem;border-top:1px solid #eef2f7;background:#fafbfc;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-btn{min-height:44px;padding:.55rem 1.15rem;border-radius:10px;font-weight:600;' +
      'font-size:.9rem;border:1px solid transparent;cursor:pointer;transition:background .15s,border-color .15s,transform .1s;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-btn:active{transform:scale(.98);}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-btn-cancel{background:#fff;border-color:#d1d5db;color:#334155;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-btn-cancel:hover{background:#f8fafc;border-color:#94a3b8;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-btn-confirm{background:' +
      ACCENT +
      ';color:#fff;min-width:6.5rem;}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-btn-confirm:hover:not(:disabled){background:' +
      ACCENT_DARK +
      ';}' +
      '#' +
      OVERLAY_ID +
      ' .hr-revoke-btn-confirm:disabled{opacity:.6;cursor:not-allowed;transform:none;}' +
      '@media (prefers-reduced-motion:reduce){#' +
      OVERLAY_ID +
      ',#' +
      OVERLAY_ID +
      ' .hr-revoke-modal{transition:none;}}';
    document.head.appendChild(style);
  }

  function defaultDescription(actorRole) {
    if (actorRole === 'hr') {
      return 'The form is kept in history as Revoked. The employee who submitted it will be notified.';
    }
    return 'The form is kept in history as Revoked. Your reporting manager will be notified.';
  }

  function ensureOverlay() {
    ensureStyles();
    var existing = document.getElementById(OVERLAY_ID);
    if (existing) return existing;
    var overlay = document.createElement('div');
    overlay.id = OVERLAY_ID;
    overlay.setAttribute('aria-hidden', 'true');
    overlay.innerHTML =
      '<div class="hr-revoke-modal" role="dialog" aria-modal="true" aria-labelledby="hrRevokeModalTitle" aria-describedby="hrRevokeModalDesc">' +
      '<div class="hr-revoke-modal-hd">' +
      '<h3 id="hrRevokeModalTitle">Revoke this HR request?</h3>' +
      '<p id="hrRevokeModalDesc">The form is kept in history as Revoked. Your reporting manager will be notified.</p>' +
      '</div>' +
      '<div class="hr-revoke-modal-bd">' +
      '<label class="hr-revoke-field-label" for="hrRevokeComment">Comment (required)</label>' +
      '<textarea id="hrRevokeComment" maxlength="2000" placeholder="Why are you revoking this request?" rows="4"></textarea>' +
      '<div class="hr-revoke-meta">' +
      '<div class="hr-revoke-err" id="hrRevokeErr" role="alert"></div>' +
      '<div class="hr-revoke-count" id="hrRevokeCount">0 / 2000</div>' +
      '</div>' +
      '<label class="hr-revoke-check">' +
      '<input type="checkbox" id="hrRevokeOpenNew" />' +
      '<span>Open a new blank form of the same type after revoking</span>' +
      '</label>' +
      '</div>' +
      '<div class="hr-revoke-modal-ft">' +
      '<button type="button" class="hr-revoke-btn hr-revoke-btn-cancel" id="hrRevokeCancelBtn">Cancel</button>' +
      '<button type="button" class="hr-revoke-btn hr-revoke-btn-confirm" id="hrRevokeConfirmBtn">Revoke</button>' +
      '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeRevokeModal();
    });
    document.getElementById('hrRevokeCancelBtn').addEventListener('click', closeRevokeModal);

    var ta = document.getElementById('hrRevokeComment');
    if (ta) {
      ta.addEventListener('input', function () {
        updateCount();
        ta.classList.remove('hr-revoke-invalid');
        if ((ta.value || '').trim().length >= 3) showErr('');
      });
    }

    document.addEventListener('keydown', function (e) {
      var ov = document.getElementById(OVERLAY_ID);
      if (!ov || !ov.classList.contains('open')) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        closeRevokeModal();
      }
    });

    return overlay;
  }

  function updateCount() {
    var ta = document.getElementById('hrRevokeComment');
    var el = document.getElementById('hrRevokeCount');
    if (!ta || !el) return;
    el.textContent = String((ta.value || '').length) + ' / 2000';
  }

  function closeRevokeModal() {
    var overlay = document.getElementById(OVERLAY_ID);
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    overlay._hrRevokeOpts = null;
    var confirmBtn = document.getElementById('hrRevokeConfirmBtn');
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Revoke';
    }
  }

  function showErr(msg) {
    var el = document.getElementById('hrRevokeErr');
    var ta = document.getElementById('hrRevokeComment');
    if (!el) return;
    el.textContent = msg || '';
    el.style.display = msg ? 'block' : 'none';
    if (ta) {
      if (msg) ta.classList.add('hr-revoke-invalid');
      else ta.classList.remove('hr-revoke-invalid');
    }
  }

  function authHeaders() {
    var token = localStorage.getItem('access_token') || '';
    var h = { 'Content-Type': 'application/json' };
    if (token) h.Authorization = 'Bearer ' + token;
    return h;
  }

  function openNewForm(moduleType, fromSid) {
    var url =
      typeof global.getHrNewFormUrl === 'function'
        ? global.getHrNewFormUrl(moduleType, fromSid || null)
        : null;
    if (url) {
      global.location.href = url;
    }
  }

  function revokeUrls(sid) {
    var enc = encodeURIComponent(sid);
    return [
      '/hr/api/submissions/' + enc + '/revoke',
      '/api/workflow/submissions/' + enc + '/revoke',
      '/api/workflow/submissions/' + enc + '/withdraw',
    ];
  }

  function revokeErrorMessage(res, payload) {
    var msg =
      (payload && (payload.error || payload.message)) ||
      '';
    if (res && res.status === 404) {
      return (
        msg ||
        'Revoke API not found (HTTP 404). Restart the app server and try again.'
      );
    }
    return msg || 'Could not revoke this form.';
  }

  async function postRevoke(sid, comment) {
    var body = JSON.stringify({ comment: comment });
    var headers = authHeaders();
    var urls = revokeUrls(sid);
    var lastRes = null;
    var lastPayload = {};
    for (var i = 0; i < urls.length; i++) {
      lastRes = await fetch(urls[i], {
        method: 'POST',
        headers: headers,
        body: body,
      });
      lastPayload = await lastRes.json().catch(function () {
        return {};
      });
      if (lastRes.ok) {
        return { ok: true, res: lastRes, payload: lastPayload };
      }
      // Only fall through to the next alias on hard route miss.
      if (lastRes.status !== 404) {
        return { ok: false, res: lastRes, payload: lastPayload };
      }
    }
    return { ok: false, res: lastRes, payload: lastPayload };
  }

  /**
   * @param {{
   *   submissionId: string,
   *   moduleType?: string,
   *   actorRole?: 'hr'|'submitter',
   *   description?: string,
   *   onSuccess?: function,
   *   onError?: function
   * }} opts
   */
  function openHrRevokeModal(opts) {
    opts = opts || {};
    var sid = String(opts.submissionId || '').trim();
    if (!sid) return;
    var overlay = ensureOverlay();
    overlay._hrRevokeOpts = opts;

    var desc = document.getElementById('hrRevokeModalDesc');
    if (desc) {
      desc.textContent =
        opts.description || defaultDescription(opts.actorRole || 'submitter');
    }

    var ta = document.getElementById('hrRevokeComment');
    var cb = document.getElementById('hrRevokeOpenNew');
    var confirmBtn = document.getElementById('hrRevokeConfirmBtn');
    if (ta) ta.value = '';
    if (cb) cb.checked = false;
    showErr('');
    updateCount();
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Revoke';
    }
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    if (ta) setTimeout(function () { ta.focus(); }, 60);

    confirmBtn.onclick = async function () {
      var comment = (ta && ta.value ? ta.value : '').trim();
      if (comment.length < 3) {
        showErr('Please enter a comment (at least 3 characters).');
        if (ta) ta.focus();
        return;
      }
      showErr('');
      confirmBtn.disabled = true;
      confirmBtn.textContent = 'Revoking…';
      try {
        var outcome = await postRevoke(sid, comment);
        var payload = outcome.payload || {};
        if (!outcome.ok) {
          showErr(revokeErrorMessage(outcome.res, payload));
          confirmBtn.disabled = false;
          confirmBtn.textContent = 'Revoke';
          if (typeof opts.onError === 'function') opts.onError(payload);
          return;
        }
        var mod =
          (payload.data && payload.data.module_type) ||
          payload.module_type ||
          opts.moduleType ||
          '';
        var openNew = !!(cb && cb.checked);
        closeRevokeModal();
        if (typeof opts.onSuccess === 'function') {
          opts.onSuccess(payload, { openNew: openNew, moduleType: mod, submissionId: sid });
        }
        if (openNew && mod) {
          openNewForm(mod, sid);
        }
      } catch (e) {
        showErr('Network error — could not revoke. Try again.');
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Revoke';
        if (typeof opts.onError === 'function') opts.onError(e);
      }
    };
  }

  global.openHrRevokeModal = openHrRevokeModal;
  global.closeHrRevokeModal = closeRevokeModal;
})(typeof window !== 'undefined' ? window : globalThis);
