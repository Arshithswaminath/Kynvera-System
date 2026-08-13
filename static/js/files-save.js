/**
 * Save to Files — shared modal for modules with export/template/download.
 *
 * Set on each page:
 *   window.FILES_SAVE_MODULE = 'hiring' | 'leave' | 'manpower' | 'procurement' | 'dochub' | ...
 * Optional:
 *   window.FILES_SAVE_MODULE_LABEL = 'Hiring Documents'  (overrides catalog label)
 *
 * Adds "Save to Files" to the module menu (left sidebar card, or hamburger
 * drawer on pages without that card). Never injects into the global top nav.
 * Also binds #filesSaveToFilesBtn and .files-save-menu-link (e.g. DocHub topbar).
 */
(function () {
  'use strict';

  function authHeaders() {
    var h = { 'Content-Type': 'application/json' };
    if (typeof getAuthHeaders === 'function') {
      try {
        Object.assign(h, getAuthHeaders());
      } catch (e) { /* ignore */ }
    }
    var token = localStorage.getItem('access_token') || localStorage.getItem('token');
    if (token && !h.Authorization) h.Authorization = 'Bearer ' + token;
    return h;
  }

  function moduleKey() {
    return String(window.FILES_SAVE_MODULE || '').trim().toLowerCase();
  }

  function currentTicketStatus() {
    return String(window.FILES_SAVE_TICKET_STATUS || '').trim().toLowerCase();
  }

  function isCurrentTicketUnclosed() {
    var st = currentTicketStatus();
    return !!st && st !== 'closed';
  }

  function ticketingHintText() {
    if (isCurrentTicketUnclosed()) {
      return 'This work order isn\'t closed yet. The invoice and service report can be saved after it\'s closed.';
    }
    return 'Tick service reports and invoices from closed work orders. Sync to Google Drive later from Files.';
  }

  function ticketingEmptyHtml() {
    if (isCurrentTicketUnclosed()) {
      return '<p style="color:#64748b;font-size:.875rem">This ticket isn\'t closed yet. Close the work order first to save the invoice and service report.</p>';
    }
    return '<p style="color:#64748b;font-size:.875rem">No closed work orders to save yet.</p>';
  }

  function ensureStyles() {
    if (document.getElementById('filesSaveModalStyles')) return;
    var style = document.createElement('style');
    style.id = 'filesSaveModalStyles';
    style.textContent =
      '#filesSaveModal{position:fixed;inset:0;z-index:1400;display:flex;align-items:center;justify-content:center;padding:1rem}' +
      '#filesSaveModal[hidden]{display:none!important}' +
      '#filesSaveModal .files-save-backdrop{position:absolute;inset:0;background:rgba(15,23,42,.45)}' +
      '#filesSaveModal .files-save-dialog{position:relative;background:#fff;border-radius:14px;padding:1.25rem 1.35rem 1.2rem;width:min(480px,100%);max-height:min(88vh,720px);display:flex;flex-direction:column;box-shadow:0 20px 50px rgba(0,0,0,.18);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif}' +
      '#filesSaveModal .files-save-module-badge{display:inline-flex;align-items:center;gap:.35rem;margin:0 0 .55rem;padding:.28rem .65rem;border-radius:999px;border:none;background:#fff4ef;color:#e05f36;font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase}' +
      '#filesSaveModal .files-save-dialog h2{margin:0 0 .35rem;padding:0;font-size:1.15rem;font-weight:700;line-height:1.25;color:#0f172a}' +
      '#filesSaveModal .files-save-hint{margin:0 0 .95rem;font-size:.875rem;color:#64748b;line-height:1.4}' +
      '#filesSaveModal .files-save-options{display:flex;flex-direction:column;gap:1.05rem;flex:1 1 auto;min-height:0;max-height:min(420px,52vh);overflow-y:auto;padding:0 4px 2px 0}' +
      '#filesSaveModal .files-save-options::-webkit-scrollbar{width:8px}' +
      '#filesSaveModal .files-save-options::-webkit-scrollbar-track{background:transparent}' +
      '#filesSaveModal .files-save-options::-webkit-scrollbar-thumb{background:#d4d4d8;border-radius:8px}' +
      '#filesSaveModal .files-save-section{display:flex;flex-direction:column;gap:.5rem;margin:0;padding:0}' +
      '#filesSaveModal .files-save-group{display:flex;align-items:center;justify-content:space-between;gap:.75rem;margin:0;padding:.15rem .1rem .05rem;min-height:1.25rem;flex:0 0 auto;position:sticky;top:0;z-index:1;background:#fff}' +
      '#filesSaveModal .files-save-group-label{font-size:.68rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#94a3b8;line-height:1}' +
      '#filesSaveModal .files-save-select-all{background:none;border:none;padding:0;margin:0;cursor:pointer;font-size:.72rem;font-weight:700;letter-spacing:.01em;text-transform:none;color:#e05f36;line-height:1}' +
      '#filesSaveModal .files-save-list{display:flex;flex-direction:column;gap:.55rem}' +
      '#filesSaveModal .files-save-option{display:flex;gap:.75rem;align-items:flex-start;margin:0;padding:.8rem .9rem;border:1px solid #e2e8f0;border-radius:12px;cursor:pointer;min-height:44px;background:#fff;color:#0f172a;text-transform:none;letter-spacing:normal;font-weight:inherit}' +
      '#filesSaveModal .files-save-option:hover{border-color:#ffcdb8;background:#fff4ef}' +
      '#filesSaveModal .files-save-option.is-selected{border-color:#ff8e68;background:#fff4ef}' +
      '#filesSaveModal .files-save-option input{flex:0 0 auto;margin:.2rem 0 0;accent-color:#ff8e68}' +
      '#filesSaveModal .files-save-option-copy{min-width:0;flex:1 1 auto}' +
      '#filesSaveModal .files-save-option-title{display:block;font-size:.9rem;font-weight:700;color:#0f172a;line-height:1.3;text-transform:none}' +
      '#filesSaveModal .files-save-option-meta{display:block;margin-top:.15rem;font-size:.78rem;font-weight:400;color:#64748b;line-height:1.35}' +
      '#filesSaveModal .files-save-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1.15rem;flex:0 0 auto}' +
      '#filesSaveModal .files-save-btn{box-sizing:border-box;min-height:44px;padding:.5rem 1rem;border-radius:10px;font-weight:600;font-size:.8125rem;border:1px solid transparent;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}' +
      '#filesSaveModal .files-save-btn.ghost{background:#fff;border:1px solid #e2e8f0;color:#334155}' +
      '#filesSaveModal .files-save-btn.primary{background:#ff8e68;border:1px solid #ff8e68;color:#fff;box-shadow:0 2px 8px rgba(255,142,104,.28)}' +
      '#filesSaveModal .files-save-btn.primary:disabled{opacity:.45;cursor:not-allowed}' +
      '#filesSaveModal .files-save-status{margin:.85rem 0 0;font-size:.85rem;color:#e05f36}' +
      '#filesSaveModal .files-save-status a{color:#e05f36;font-weight:700}' +
      /* Compact menu-footer CTA — keep styles outside modal-only path */
      '.files-menu-footer{flex:0 0 auto;margin:0 .85rem calc(.85rem + env(safe-area-inset-bottom,0px));padding:.7rem .75rem;border-radius:12px;border:1px solid rgba(255,142,104,.28);background:#fff;box-shadow:none}' +
      '.files-menu-footer-top{display:flex;align-items:flex-start;gap:.65rem;margin:0 0 .65rem}' +
      '.files-menu-footer-icon{flex:0 0 auto;width:32px;height:32px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;background:#ff8e68;color:#fff}' +
      '.files-menu-footer-icon svg{width:16px;height:16px;display:block}' +
      '.files-menu-footer-copy{min-width:0;flex:1 1 auto}' +
      '.files-menu-footer-title{margin:0;font-size:.8125rem;font-weight:700;color:#1f2937;line-height:1.2}' +
      '.files-menu-footer-hint{margin:.2rem 0 0;font-size:.72rem;line-height:1.35;color:#7c5a4e}' +
      '.files-menu-footer-mod{font-weight:700;color:#e05f36}' +
      '.files-menu-footer-actions{display:flex;align-items:center;gap:.5rem}' +
      '.files-save-menu-link{flex:1 1 auto;display:inline-flex;align-items:center;justify-content:center;min-height:36px;padding:.4rem .7rem;border:none;border-radius:9px;background:#ff8e68;color:#fff!important;font-size:.78rem;font-weight:700;cursor:pointer;text-decoration:none;box-shadow:none}' +
      '.files-save-menu-link:hover{background:#f97e54}' +
      '.files-menu-footer-open{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;min-height:36px;padding:.35rem .65rem;border-radius:9px;border:1px solid rgba(224,95,54,.28);background:#fff;color:#e05f36!important;font-size:.75rem;font-weight:600;text-decoration:none}' +
      '.files-menu-footer-open:hover{background:#fff8f5;text-decoration:none}';
    document.head.appendChild(style);
  }

  function ensureModal() {
    ensureStyles();
    var existing = document.getElementById('filesSaveModal');
    if (existing) return existing;

    var wrap = document.createElement('div');
    wrap.id = 'filesSaveModal';
    wrap.hidden = true;
    wrap.innerHTML =
      '<div class="files-save-backdrop" data-files-save-close></div>' +
      '<div class="files-save-dialog" role="dialog" aria-modal="true" aria-labelledby="filesSaveTitle">' +
      '  <p class="files-save-module-badge" id="filesSaveModuleBadge"></p>' +
      '  <h2 id="filesSaveTitle">Save to Files</h2>' +
      '  <p class="files-save-hint" id="filesSaveHint">Choose which file to save from this module. Sync to Google Drive later from Files.</p>' +
      '  <div class="files-save-options" id="filesSaveOptions"></div>' +
      '  <div class="files-save-actions">' +
      '    <button type="button" class="files-save-btn ghost" data-files-save-close>Cancel</button>' +
      '    <button type="button" class="files-save-btn primary" id="filesSaveConfirm" disabled>Save</button>' +
      '  </div>' +
      '  <p class="files-save-status" id="filesSaveStatus" hidden></p>' +
      '</div>';
    document.body.appendChild(wrap);

    wrap.addEventListener('click', function (e) {
      if (e.target && e.target.hasAttribute('data-files-save-close')) closeModal();
    });
    var confirm = document.getElementById('filesSaveConfirm');
    if (confirm) confirm.addEventListener('click', submitSave);
    return wrap;
  }

  var selectedKinds = [];
  var cachedModuleLabel = '';

  function closeModal() {
    var modal = document.getElementById('filesSaveModal');
    if (modal) modal.hidden = true;
    selectedKinds = [];
  }

  function isLiveKind(kind) {
    var k = String(kind || '');
    return k.indexOf('doc:') === 0 || k.indexOf('ticket:') === 0;
  }

  function livePrefix(kind) {
    var k = String(kind || '');
    if (k.indexOf('ticket:') === 0) return 'ticket:';
    if (k.indexOf('doc:') === 0) return 'doc:';
    return '';
  }

  function liveSelector(prefix) {
    return '.files-save-option[data-kind^="' + (prefix || 'doc:') + '"] input';
  }

  function syncSelectedKinds() {
    selectedKinds = [];
    var optsEl = document.getElementById('filesSaveOptions');
    if (!optsEl) return;
    optsEl.querySelectorAll('.files-save-option').forEach(function (lab) {
      var input = lab.querySelector('input');
      var kind = lab.getAttribute('data-kind');
      var on = !!(input && input.checked);
      lab.classList.toggle('is-selected', on);
      if (on && kind) selectedKinds.push(kind);
    });
    var confirm = document.getElementById('filesSaveConfirm');
    if (confirm) {
      confirm.disabled = selectedKinds.length === 0;
      if (selectedKinds.length > 1) confirm.textContent = 'Save ' + selectedKinds.length;
      else confirm.textContent = 'Save';
    }
    var selAll = document.getElementById('filesSaveSelectDocs');
    if (selAll) {
      var prefix = selAll.getAttribute('data-live-prefix') || 'doc:';
      var docs = optsEl.querySelectorAll(liveSelector(prefix));
      var checked = 0;
      docs.forEach(function (inp) { if (inp.checked) checked += 1; });
      selAll.textContent = (docs.length && checked === docs.length) ? 'Clear all' : 'Select all';
    }
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function openModal() {
    var module = moduleKey();
    if (!module) {
      alert('Save to Files is not available on this page.');
      return;
    }
    var modal = ensureModal();
    var optsEl = document.getElementById('filesSaveOptions');
    var status = document.getElementById('filesSaveStatus');
    var confirm = document.getElementById('filesSaveConfirm');
    var badge = document.getElementById('filesSaveModuleBadge');
    var hint = document.getElementById('filesSaveHint');
    if (status) {
      status.hidden = true;
      status.innerHTML = '';
      status.style.color = '';
    }
    if (confirm) {
      confirm.disabled = true;
      confirm.textContent = 'Save';
    }
    selectedKinds = [];
    optsEl.innerHTML = '<p style="color:#64748b;font-size:.875rem">Loading options…</p>';
    if (badge) badge.textContent = 'Module: …';
    modal.hidden = false;

    fetch('/files/api/catalog?module=' + encodeURIComponent(module), {
      headers: authHeaders(),
      credentials: 'same-origin',
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || data.success === false) throw new Error(data.error || data.message || 'Could not load options');
          if (data.data !== undefined) return data.data;
          var out = Object.assign({}, data);
          delete out.success;
          delete out.message;
          return out;
        });
      })
      .then(function (cat) {
        var label = window.FILES_SAVE_MODULE_LABEL || cat.label || module;
        cachedModuleLabel = label;
        if (badge) badge.textContent = 'From module · ' + label;
        var options = cat.options || [];
        var hasDocs = options.some(function (o) { return String(o.kind || '').indexOf('doc:') === 0; });
        var hasTickets = options.some(function (o) { return String(o.kind || '').indexOf('ticket:') === 0; });
        if (hint) {
          if (hasTickets || module === 'ticketing') {
            hint.textContent = ticketingHintText();
          } else if (hasDocs) {
            hint.textContent = 'Tick one or more DocHub documents to copy into Files, or include the library index Excel. Sync to Google Drive later from Files.';
          } else {
            hint.textContent = 'These files come from ' + label + '. Tick one or more items to save into Files, then sync to Google Drive when ready.';
          }
        }
        if (!options.length) {
          optsEl.innerHTML = module === 'ticketing'
            ? ticketingEmptyHtml()
            : '<p style="color:#b91c1c">No save options for this module.</p>';
          return;
        }
        function optionRow(o) {
          return (
            '<label class="files-save-option" data-kind="' + escapeHtml(o.kind) + '">' +
            '<input type="checkbox" name="filesSaveKind" value="' + escapeHtml(o.kind) + '">' +
            '<div class="files-save-option-copy">' +
            '<span class="files-save-option-title">' + escapeHtml(o.label || o.kind) + '</span>' +
            (o.description ? '<span class="files-save-option-meta">' + escapeHtml(o.description) + '</span>' : '') +
            '</div></label>'
          );
        }
        function sectionBlock(title, rowsHtml, extra) {
          return (
            '<section class="files-save-section">' +
            '<div class="files-save-group">' +
            '<span class="files-save-group-label">' + escapeHtml(title) + '</span>' +
            (extra || '') +
            '</div>' +
            '<div class="files-save-list">' + rowsHtml + '</div>' +
            '</section>'
          );
        }
        var html = '';
        var live = options.filter(function (o) { return isLiveKind(o.kind); });
        var exports = options.filter(function (o) { return !isLiveKind(o.kind); });
        var prefix = live.length ? livePrefix(live[0].kind) : '';
        if (live.length) {
          if (exports.length) {
            html += sectionBlock('Library', exports.map(optionRow).join(''));
          }
          html += sectionBlock(
            prefix === 'ticket:' ? 'Closed tickets' : 'Documents',
            live.map(optionRow).join(''),
            '<button type="button" class="files-save-select-all" id="filesSaveSelectDocs" data-live-prefix="' + escapeHtml(prefix) + '">Select all</button>'
          );
        } else {
          html = '<div class="files-save-list">' + options.map(optionRow).join('') + '</div>';
        }
        optsEl.innerHTML = html;
        optsEl.querySelectorAll('.files-save-option input').forEach(function (inp) {
          inp.addEventListener('change', syncSelectedKinds);
        });
        var selAll = document.getElementById('filesSaveSelectDocs');
        if (selAll) {
          selAll.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            var boxes = optsEl.querySelectorAll(liveSelector(selAll.getAttribute('data-live-prefix') || prefix || 'doc:'));
            var allOn = true;
            boxes.forEach(function (inp) { if (!inp.checked) allOn = false; });
            boxes.forEach(function (inp) { inp.checked = !allOn; });
            syncSelectedKinds();
          });
        }
        syncSelectedKinds();
      })
      .catch(function (e) {
        if (badge) badge.textContent = 'From module · ' + (window.FILES_SAVE_MODULE_LABEL || module);
        if (module === 'ticketing') {
          if (hint) hint.textContent = ticketingHintText();
          optsEl.innerHTML = ticketingEmptyHtml();
          return;
        }
        optsEl.innerHTML = '<p style="color:#b91c1c">' + escapeHtml(e.message || 'Failed to load') + '</p>';
      });
  }

  function submitSave() {
    var module = moduleKey();
    if (!module || !selectedKinds.length) return;
    var confirm = document.getElementById('filesSaveConfirm');
    var status = document.getElementById('filesSaveStatus');
    var kinds = selectedKinds.slice();
    if (confirm) {
      confirm.disabled = true;
      confirm.textContent = 'Saving…';
    }
    fetch('/files/api/save-from-module', {
      method: 'POST',
      headers: authHeaders(),
      credentials: 'same-origin',
      body: JSON.stringify({ module: module, kinds: kinds }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || data.success === false) throw new Error(data.error || data.message || 'Save failed');
          if (data.data !== undefined) return data.data;
          var out = Object.assign({}, data);
          delete out.success;
          return out;
        });
      })
      .then(function (data) {
        var label = data.folder_label || 'Files';
        var saved = Number(data.saved != null ? data.saved : (data.items ? data.items.length : kinds.length)) || 0;
        var failed = (data.failed || []).length;
        var noun = saved === 1 ? 'file' : 'files';
        var msg = 'Saved ' + saved + ' ' + noun + ' → Files → ' + label + '. Open Files to sync to Google Drive.';
        if (failed) {
          var first = data.failed[0] || {};
          msg += ' ' + failed + ' could not be saved' + (first.error ? ': ' + first.error : '.');
        }
        if (status) {
          status.hidden = false;
          status.style.color = failed ? '#b91c1c' : '#e05f36';
          status.innerHTML = escapeHtml(msg) + ' <a href="/files/">Open Files</a>';
        }
        if (confirm) {
          confirm.textContent = saved ? 'Saved' : 'Save';
          confirm.disabled = !saved;
        }
        if (saved && !failed) setTimeout(closeModal, 2800);
        else if (saved) syncSelectedKinds();
      })
      .catch(function (e) {
        if (status) {
          status.hidden = false;
          status.style.color = '#b91c1c';
          status.textContent = e.message || 'Save failed';
        }
        if (confirm) {
          confirm.disabled = selectedKinds.length === 0;
          confirm.textContent = selectedKinds.length > 1 ? 'Save ' + selectedKinds.length : 'Save';
        }
      });
  }

  function injectMenuFooter() {
    if (!moduleKey()) return;
    // Module already has its own left sidebar Files card — don't duplicate in the hamburger menu.
    if (document.getElementById('filesSaveSidebarCard')) return;
    ensureStyles();
    if (document.getElementById('filesSaveDrawerCard')) return;
    var drawer = document.getElementById('mobileMenuDrawer');
    if (!drawer) return;

    var label = window.FILES_SAVE_MODULE_LABEL || 'this module';
    var card = document.createElement('div');
    card.id = 'filesSaveDrawerCard';
    card.className = 'files-menu-footer';
    card.setAttribute('role', 'region');
    card.setAttribute('aria-label', 'Kynvera Files');
    card.innerHTML =
      '<div class="files-menu-footer-top">' +
        '<span class="files-menu-footer-icon" aria-hidden="true">' +
          '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.9" stroke="currentColor" width="16" height="16">' +
            '<path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z"/>' +
          '</svg>' +
        '</span>' +
        '<div class="files-menu-footer-copy">' +
          '<p class="files-menu-footer-title">Kynvera Files</p>' +
          '<p class="files-menu-footer-hint">Keep <span class="files-menu-footer-mod"></span> exports here, then sync to Drive.</p>' +
        '</div>' +
      '</div>' +
      '<div class="files-menu-footer-actions">' +
        '<button type="button" class="files-save-menu-link">Save to Files</button>' +
        '<a class="files-menu-footer-open" href="/files/">Open</a>' +
      '</div>';
    var modEl = card.querySelector('.files-menu-footer-mod');
    if (modEl) modEl.textContent = label;

    drawer.appendChild(card);
  }

  function closeMobileMenuIfOpen() {
    var toggle = document.getElementById('mobileMenuToggle');
    var drawer = document.getElementById('mobileMenuDrawer');
    var overlay = document.getElementById('mobileOverlay');
    if (toggle) {
      toggle.classList.remove('active', 'is-hint-paused');
      toggle.setAttribute('aria-expanded', 'false');
    }
    if (drawer) {
      drawer.classList.remove('active', 'open');
      drawer.setAttribute('aria-hidden', 'true');
    }
    if (overlay) overlay.classList.remove('active', 'open');
    document.body.classList.remove('mobile-menu-open');
    document.body.style.overflow = '';
  }

  function bindSaveTriggers() {
    document.addEventListener('click', function (e) {
      var trigger = e.target.closest('#filesSaveToFilesBtn, #dhSaveToFilesBtn, .files-save-menu-link');
      if (!trigger) return;
      e.preventDefault();
      closeMobileMenuIfOpen();
      openModal();
    });
  }

  window.openFilesSaveModal = openModal;

  document.addEventListener('DOMContentLoaded', function () {
    bindSaveTriggers();
    injectMenuFooter();
  });
})();
