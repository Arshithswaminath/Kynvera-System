/**
 * Save to Files — shared modal for modules with export/template/download.
 *
 * Set on each page:
 *   window.FILES_SAVE_MODULE = 'hiring' | 'leave' | 'manpower' | 'procurement' | ...
 * Optional:
 *   window.FILES_SAVE_MODULE_LABEL = 'Hiring Documents'  (overrides catalog label)
 *
 * Injects a navbar "Save to Files" control when FILES_SAVE_MODULE is set
 * (for pages without a module sidebar). Also binds #filesSaveToFilesBtn.
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

  function ensureModal() {
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

    if (!document.getElementById('filesSaveModalStyles')) {
      var style = document.createElement('style');
      style.id = 'filesSaveModalStyles';
      style.textContent =
        '#filesSaveModal{position:fixed;inset:0;z-index:1400;display:flex;align-items:center;justify-content:center;padding:1rem}' +
        '#filesSaveModal[hidden]{display:none!important}' +
        '.files-save-backdrop{position:absolute;inset:0;background:rgba(15,23,42,.45)}' +
        '.files-save-dialog{position:relative;background:#fff;border-radius:14px;padding:1.25rem 1.35rem;width:min(460px,100%);box-shadow:0 20px 50px rgba(0,0,0,.18);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif}' +
        '.files-save-module-badge{display:inline-flex;align-items:center;gap:.35rem;margin:0 0 .55rem;padding:.28rem .65rem;border-radius:999px;background:#fff4ef;color:#e05f36;font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase}' +
        '.files-save-dialog h2{margin:0 0 .35rem;font-size:1.15rem;color:#0f172a}' +
        '.files-save-hint{margin:0 0 1rem;font-size:.875rem;color:#64748b;line-height:1.4}' +
        '.files-save-options{display:flex;flex-direction:column;gap:.5rem}' +
        '.files-save-option{display:flex;gap:.75rem;align-items:flex-start;padding:.85rem .9rem;border:1px solid #e2e8f0;border-radius:12px;cursor:pointer;min-height:44px}' +
        '.files-save-option:hover{border-color:#ffcdb8;background:#fff4ef}' +
        '.files-save-option.is-selected{border-color:#ff8e68;background:#fff4ef}' +
        '.files-save-option input{margin-top:.2rem}' +
        '.files-save-option strong{display:block;font-size:.9rem;color:#0f172a}' +
        '.files-save-option span{display:block;font-size:.78rem;color:#64748b;margin-top:.15rem}' +
        '.files-save-actions{display:flex;justify-content:flex-end;gap:.5rem;margin-top:1.1rem}' +
        '.files-save-btn{min-height:44px;padding:.5rem 1rem;border-radius:10px;font-weight:600;font-size:.8125rem;border:1px solid transparent;cursor:pointer}' +
        '.files-save-btn.ghost{background:#fff;border-color:#e2e8f0;color:#334155}' +
        '.files-save-btn.primary{background:#ff8e68;color:#fff;box-shadow:0 2px 8px rgba(255,142,104,.28)}' +
        '.files-save-btn.primary:disabled{opacity:.45;cursor:not-allowed}' +
        '.files-save-status{margin:.85rem 0 0;font-size:.85rem;color:#e05f36}' +
        '.files-save-status a{color:#e05f36;font-weight:700}' +
        '.nav-save-files-btn{display:inline-flex;align-items:center;gap:.4rem;min-height:40px;padding:.4rem .75rem;border-radius:10px;border:1px solid #ffcdb8;background:#fff4ef;color:#e05f36;font-size:.78rem;font-weight:600;cursor:pointer;margin-right:.35rem}' +
        '.nav-save-files-btn:hover{background:#ffe6db}' +
        '.nav-save-files-btn .nav-save-files-mod{font-weight:500;opacity:.85;max-width:9rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
        '@media (max-width:720px){.nav-save-files-btn .nav-save-files-mod{display:none}}' +
        '.mobile-menu-drawer-list .files-save-drawer-item button{width:100%;text-align:left;background:transparent;border:none;font:inherit;color:inherit;padding:.75rem 1rem;min-height:44px;cursor:pointer}';
      document.head.appendChild(style);
    }

    wrap.addEventListener('click', function (e) {
      if (e.target && e.target.hasAttribute('data-files-save-close')) closeModal();
    });
    var confirm = document.getElementById('filesSaveConfirm');
    if (confirm) confirm.addEventListener('click', submitSave);
    return wrap;
  }

  var selectedKind = null;
  var cachedModuleLabel = '';

  function closeModal() {
    var modal = document.getElementById('filesSaveModal');
    if (modal) modal.hidden = true;
    selectedKind = null;
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
    selectedKind = null;
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
        if (hint) {
          hint.textContent = 'These files come from ' + label + '. Choose what to save into Files, then sync to Google Drive when ready.';
        }
        var options = cat.options || [];
        if (!options.length) {
          optsEl.innerHTML = '<p style="color:#b91c1c">No save options for this module.</p>';
          return;
        }
        optsEl.innerHTML = options.map(function (o) {
          return (
            '<label class="files-save-option" data-kind="' + o.kind + '">' +
            '<input type="radio" name="filesSaveKind" value="' + o.kind + '">' +
            '<div><strong>' + (o.label || o.kind) + '</strong><span>' + (o.description || '') + '</span></div>' +
            '</label>'
          );
        }).join('');
        optsEl.querySelectorAll('.files-save-option').forEach(function (lab) {
          lab.addEventListener('click', function () {
            optsEl.querySelectorAll('.files-save-option').forEach(function (x) { x.classList.remove('is-selected'); });
            lab.classList.add('is-selected');
            var radio = lab.querySelector('input');
            if (radio) radio.checked = true;
            selectedKind = lab.getAttribute('data-kind');
            if (confirm) confirm.disabled = !selectedKind;
          });
        });
        var prefer = optsEl.querySelector('[data-kind="export"]') || optsEl.querySelector('.files-save-option');
        if (prefer) prefer.click();
      })
      .catch(function (e) {
        optsEl.innerHTML = '<p style="color:#b91c1c">' + (e.message || 'Failed to load') + '</p>';
        if (badge) badge.textContent = 'From module · ' + (window.FILES_SAVE_MODULE_LABEL || module);
      });
  }

  function submitSave() {
    var module = moduleKey();
    if (!module || !selectedKind) return;
    var confirm = document.getElementById('filesSaveConfirm');
    var status = document.getElementById('filesSaveStatus');
    if (confirm) {
      confirm.disabled = true;
      confirm.textContent = 'Saving…';
    }
    fetch('/files/api/save-from-module', {
      method: 'POST',
      headers: authHeaders(),
      credentials: 'same-origin',
      body: JSON.stringify({ module: module, kind: selectedKind }),
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
        var modLabel = data.module_label || cachedModuleLabel || module;
        var msg = 'Saved from ' + modLabel + ' → Files → ' + label + '. Open Files to sync to Google Drive.';
        if (status) {
          status.hidden = false;
          status.style.color = '#e05f36';
          status.innerHTML = msg + ' <a href="/files/">Open Files</a>';
        }
        if (confirm) {
          confirm.textContent = 'Saved';
          confirm.disabled = true;
        }
        setTimeout(closeModal, 2800);
      })
      .catch(function (e) {
        if (status) {
          status.hidden = false;
          status.style.color = '#b91c1c';
          status.textContent = e.message || 'Save failed';
        }
        if (confirm) {
          confirm.disabled = false;
          confirm.textContent = 'Save';
        }
      });
  }

  function injectNavbarButton() {
    if (!moduleKey()) return;
    if (document.getElementById('filesNavSaveBtn')) return;
    var navRight = document.querySelector('.nav-right');
    if (!navRight) return;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'filesNavSaveBtn';
    btn.className = 'nav-save-files-btn';
    btn.title = 'Save export/template from this module to Files';
    btn.innerHTML =
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" width="16" height="16" aria-hidden="true">' +
      '<path stroke-linecap="round" stroke-linejoin="round" d="M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.233-2.33 3 3 0 0 1 3.758 3.848A3.752 3.752 0 0 1 18 19.5H6.75Z"/></svg>' +
      '<span>Save to Files</span>' +
      '<span class="nav-save-files-mod" id="filesNavSaveModLabel"></span>';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      openModal();
    });

    var logout = document.getElementById('logoutBtn');
    if (logout && logout.parentNode === navRight) {
      navRight.insertBefore(btn, logout);
    } else {
      navRight.insertBefore(btn, navRight.firstChild);
    }

    // Prefer explicit label; else fetch catalog label
    var modEl = document.getElementById('filesNavSaveModLabel');
    if (window.FILES_SAVE_MODULE_LABEL && modEl) {
      modEl.textContent = '· ' + window.FILES_SAVE_MODULE_LABEL;
      return;
    }
    fetch('/files/api/catalog?module=' + encodeURIComponent(moduleKey()), {
      headers: authHeaders(),
      credentials: 'same-origin',
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var label = (data && data.label) || '';
        if (modEl && label) modEl.textContent = '· ' + label;
      })
      .catch(function () { /* ignore */ });
  }

  function injectDrawerItem() {
    if (!moduleKey()) return;
    var list = document.getElementById('mobileMenuDrawerList');
    if (!list || document.getElementById('filesSaveDrawerItem')) return;
    var li = document.createElement('li');
    li.id = 'filesSaveDrawerItem';
    li.className = 'files-save-drawer-item';
    li.innerHTML = '<button type="button">Save to Files</button>';
    li.querySelector('button').addEventListener('click', function () {
      openModal();
      var drawer = document.getElementById('mobileMenuDrawer');
      var overlay = document.getElementById('mobileOverlay');
      if (drawer) {
        drawer.classList.remove('open');
        drawer.setAttribute('aria-hidden', 'true');
      }
      if (overlay) overlay.classList.remove('open');
    });
    list.appendChild(li);
  }

  function bindSidebarTrigger() {
    var btn = document.getElementById('filesSaveToFilesBtn');
    if (!btn) return;
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      openModal();
    });
  }

  window.openFilesSaveModal = openModal;

  document.addEventListener('DOMContentLoaded', function () {
    bindSidebarTrigger();
    if (moduleKey()) {
      injectNavbarButton();
      // Drawer list is often populated async — retry a few times
      injectDrawerItem();
      setTimeout(injectDrawerItem, 400);
      setTimeout(injectDrawerItem, 1200);
    }
  });
})();
