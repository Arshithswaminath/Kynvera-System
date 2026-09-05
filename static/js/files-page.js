/**
 * Files module — Finder UI (tree + list + Drive sync)
 */
(function () {
  'use strict';

  var state = {
    folders: [],
    items: [],
    drive: {},
    currentFolderId: null, // null = all
    viewMode: 'folder', // 'folder' | 'templates' | 'unsynced'
    templates: [],
    selected: {},
    selectedTemplates: {},
    query: '',
    modalMode: null, // 'folder' | 'rename-folder' | 'rename-item'
    modalTargetId: null,
    driveSetupInFlight: false,
    connecting: false,
  };

  function authHeaders(json) {
    var h = {};
    if (json) h['Content-Type'] = 'application/json';
    if (typeof getAuthHeaders === 'function') {
      try {
        var g = getAuthHeaders();
        if (g) Object.assign(h, g);
      } catch (e) { /* ignore */ }
    }
    var token = localStorage.getItem('access_token') || localStorage.getItem('token');
    if (token && !h.Authorization) h.Authorization = 'Bearer ' + token;
    return h;
  }

  function api(path, opts) {
    opts = opts || {};
    var headers = authHeaders(!!(opts.body && typeof opts.body === 'string'));
    return fetch(path, {
      method: opts.method || 'GET',
      headers: opts.formData ? authHeaders(false) : headers,
      body: opts.body,
      credentials: 'same-origin',
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok || data.success === false) {
          var err = (data && (data.error || data.message)) || ('HTTP ' + res.status);
          throw new Error(err);
        }
        if (data.data !== undefined) return data.data;
        var out = Object.assign({}, data);
        delete out.success;
        delete out.message;
        return out;
      });
    });
  }

  function toast(msg, opts) {
    opts = opts || {};
    var el = document.getElementById('filesToast');
    var msgEl = document.getElementById('filesToastMsg');
    if (!el) return;
    if (msgEl) {
      if (opts.html) msgEl.innerHTML = msg;
      else msgEl.textContent = msg;
    } else if (opts.html) {
      el.innerHTML = msg;
    } else {
      el.textContent = msg;
    }
    el.classList.toggle('is-loading', !!opts.loading);
    el.classList.toggle('is-error', !!opts.error);
    el.hidden = false;
    clearTimeout(toast._t);
    if (opts.loading) return;
    toast._t = setTimeout(function () {
      el.hidden = true;
      el.classList.remove('is-loading', 'is-error');
    }, opts.duration || 4500);
  }

  function toastLoading(msg) {
    toast(msg, { loading: true });
  }

  function setSyncBusy(busy) {
    var syncNowBtn = document.getElementById('filesSyncNowBtn');
    var syncFolderBtn = document.getElementById('filesSyncFolderBtn');
    if (syncNowBtn) syncNowBtn.disabled = !!busy;
    if (syncFolderBtn) {
      if (busy) syncFolderBtn.disabled = true;
      else updateSyncFolderBtn();
    }
  }

  function formatSyncNowMessage(data) {
    data = data || {};
    var n = (data.synced || []).length;
    var f = (data.failed || []).length;
    var fc = data.folders_created || 0;
    var fr = data.folders_renamed || 0;
    var orphan = data.orphans_removed || 0;
    var parts = ['Synced'];
    if (n) parts.push(n + ' file' + (n === 1 ? '' : 's'));
    if (fc) parts.push(fc + ' folder' + (fc === 1 ? '' : 's') + ' created');
    if (fr) parts.push(fr + ' renamed');
    if (orphan) parts.push(orphan + ' removed from Drive');
    if (f) parts.push(f + ' failed');
    return parts.length === 1 ? 'Synced' : parts.join(' · ');
  }

  function formatSyncFolderMessage(label, data) {
    data = data || {};
    var n = (data.synced || []).length;
    var f = (data.failed || []).length;
    var folders = data.folders_synced || 0;
    var parts = [label ? 'Synced "' + label + '"' : 'Synced'];
    if (folders > 1) parts.push(folders + ' folders');
    if (n) parts.push(n + ' file' + (n === 1 ? '' : 's'));
    if (f) parts.push(f + ' failed');
    return parts.join(' · ');
  }

  function setSidebarToggleState(open) {
    var toggle = document.getElementById('filesSidebarToggle');
    if (!toggle) return;
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggle.setAttribute('aria-label', open ? 'Close Files menu' : 'Open Files menu');
  }

  window.filesToggleSidebar = function () {
    var sb = document.getElementById('filesSidebar');
    var ov = document.getElementById('filesOverlay');
    if (!sb) return;
    var open = !sb.classList.contains('open');
    sb.classList.toggle('open', open);
    if (ov) {
      ov.classList.toggle('active', open);
      ov.setAttribute('aria-hidden', open ? 'false' : 'true');
    }
    setSidebarToggleState(open);
  };

  window.filesCloseSidebar = function () {
    var sb = document.getElementById('filesSidebar');
    var ov = document.getElementById('filesOverlay');
    if (sb) sb.classList.remove('open');
    if (ov) {
      ov.classList.remove('active');
      ov.setAttribute('aria-hidden', 'true');
    }
    setSidebarToggleState(false);
  };

  function folderChildren(parentId) {
    return state.folders.filter(function (f) {
      return (f.parent_id || null) === (parentId || null);
    });
  }

  function itemCountInFolder(folderId) {
    if (folderId == null) return state.items.length;
    var ids = {};
    function collect(id) {
      ids[id] = true;
      folderChildren(id).forEach(function (c) { collect(c.id); });
    }
    collect(folderId);
    return state.items.filter(function (i) { return ids[i.folder_id]; }).length;
  }

  function folderIconSvg(kind) {
    // kind: all | parent | leaf
    if (kind === 'all') {
      return '<svg class="files-folder-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 8.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 016 20.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25A2.25 2.25 0 0113.5 8.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"/></svg>';
    }
    if (kind === 'parent') {
      return '<svg class="files-folder-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z"/></svg>';
    }
    return '<svg class="files-folder-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 9.776c.112-.017.227-.026.344-.026h15.812c.117 0 .232.009.344.026m-16.5 0a2.25 2.25 0 00-1.883 2.542l.857 6a2.25 2.25 0 002.227 1.932H19.05a2.25 2.25 0 002.227-1.932l.857-6a2.25 2.25 0 00-1.883-2.542m-16.5 0V6A2.25 2.25 0 016 3.75h3.879a1.5 1.5 0 011.06.44l2.122 2.12a1.5 1.5 0 001.06.44H18A2.25 2.25 0 0120.25 9v.776"/></svg>';
  }

  function isExpanded(folderId) {
    if (!state.expanded) state.expanded = {};
    if (state.expanded[folderId] === undefined) {
      // Default: expand roots that have children
      state.expanded[folderId] = true;
    }
    return !!state.expanded[folderId];
  }

  function renderTree() {
    var root = document.getElementById('filesFolderTree');
    if (!root) return;
    if (!state.expanded) state.expanded = {};

    var html = '';
    var allCount = state.items.length;
    var allActive = state.viewMode === 'folder' && state.currentFolderId === null;
    html +=
      '<div class="files-folder-row files-folder-row--all' +
      (allActive ? ' is-active' : '') +
      '">' +
      '<span class="files-folder-chevron-spacer" aria-hidden="true"></span>' +
      '<button type="button" class="files-folder-item files-folder-item--all" data-folder-id="">' +
      folderIconSvg('all') +
      '<span class="files-folder-label">All files</span>' +
      '</button>' +
      '<div class="files-folder-trail">' +
      '<span class="files-folder-count">' + allCount + '</span>' +
      '</div></div>';

    function walk(parentId, depth) {
      folderChildren(parentId).forEach(function (f) {
        var kids = folderChildren(f.id);
        var hasKids = kids.length > 0;
        var active = state.viewMode === 'folder' && String(state.currentFolderId) === String(f.id);
        var open = hasKids && isExpanded(f.id);
        var count = itemCountInFolder(f.id);
        var kind = hasKids ? 'parent' : 'leaf';
        var canDeleteFolder = !f.path_key;
        html +=
          '<div class="files-folder-node' + (hasKids ? ' has-children' : '') + (open ? ' is-open' : '') + '" data-node-id="' + f.id + '">' +
          '<div class="files-folder-row' + (active ? ' is-active' : '') + '" style="--depth:' + depth + '">' +
          (hasKids
            ? '<button type="button" class="files-folder-chevron" data-toggle-id="' + f.id + '" aria-label="Toggle ' + escapeHtml(f.name) + '" aria-expanded="' + (open ? 'true' : 'false') + '">' +
              '<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clip-rule="evenodd"/></svg>' +
              '</button>'
            : '<span class="files-folder-chevron-spacer" aria-hidden="true"></span>') +
          '<button type="button" class="files-folder-item' + (hasKids ? ' is-parent' : '') + '" data-folder-id="' + f.id + '">' +
          folderIconSvg(kind) +
          '<span class="files-folder-label">' + escapeHtml(f.name) + '</span>' +
          '</button>' +
          '<div class="files-folder-trail">' +
          '<span class="files-folder-count">' + count + '</span>' +
          '<div class="files-folder-row-actions" role="group" aria-label="Folder actions">' +
          '<button type="button" class="files-folder-ico-btn" data-folder-act="rename" data-folder-id="' + f.id + '" title="Rename" aria-label="Rename folder">' + actionIcon('rename') + '</button>' +
          (canDeleteFolder
            ? '<button type="button" class="files-folder-ico-btn is-danger" data-folder-act="delete" data-folder-id="' + f.id + '" title="Delete" aria-label="Delete folder">' + actionIcon('delete') + '</button>'
            : '') +
          '</div></div></div>';
        if (hasKids && open) {
          html += '<div class="files-folder-children">';
          walk(f.id, depth + 1);
          html += '</div>';
        }
        html += '</div>';
      });
    }
    walk(null, 0);
    root.innerHTML = html;

    root.querySelectorAll('[data-folder-id]').forEach(function (btn) {
      if (btn.getAttribute('data-folder-act')) return;
      btn.addEventListener('click', function () {
        var id = btn.getAttribute('data-folder-id');
        state.viewMode = 'folder';
        state.currentFolderId = id === '' ? null : parseInt(id, 10);
        state.selected = {};
        state.selectedTemplates = {};
        renderLocalNav();
        renderTree();
        renderMain();
        filesCloseSidebar();
      });
    });
    root.querySelectorAll('[data-toggle-id]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var id = parseInt(btn.getAttribute('data-toggle-id'), 10);
        state.expanded[id] = !isExpanded(id);
        renderTree();
      });
    });
    root.querySelectorAll('[data-folder-act]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var act = btn.getAttribute('data-folder-act');
        var id = parseInt(btn.getAttribute('data-folder-id'), 10);
        if (act === 'rename') openRenameFolder(id);
        else if (act === 'delete') deleteFolder(id);
      });
    });
  }

  function escapeHtml(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function titleCaseWords(s) {
    return String(s || '')
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function sourceLabel(item) {
    var m = item.source_module || '';
    var k = item.source_kind || '';
    var names = {
      manpower: 'Manpower',
      leave: 'Leave',
      hiring: 'Hiring',
      hr: 'HR',
      procurement: 'Procurement',
      qhsi: 'QHSE',
      mmr: 'MMR',
      devices: 'Devices',
      technicians: 'Technicians',
      upload: 'Upload',
      branding: 'Branding',
      dochub: 'DocHub',
      ticketing: 'Ticketing',
      bd: 'BD',
    };
    var kinds = {
      template: 'Template',
      export: 'Export',
      upload: 'Upload',
      ui_snapshot: 'Snapshot',
      'brand-asset': 'Brand asset',
      'brand-kit-2.0': 'Brand kit',
      locations: 'Locations',
    };
    var base = names[m] || titleCaseWords(m) || '—';
    if (!k || m === 'upload' || k === 'upload') return base;
    if (k.indexOf('doc:') === 0) return base + ' · Document';
    if (k.indexOf('ticket:') === 0) {
      if (k.indexOf(':report') !== -1) return base + ' · Report';
      if (k.indexOf(':invoice') !== -1) return base + ' · Invoice';
      return base + ' · Ticket';
    }
    var kindLabel = kinds[k] || titleCaseWords(k);
    if (kindLabel && kindLabel !== base) return base + ' · ' + kindLabel;
    return base;
  }

  function matchesQuery(hay) {
    var q = (state.query || '').trim().toLowerCase();
    if (!q) return true;
    return String(hay || '').toLowerCase().indexOf(q) !== -1;
  }

  function visibleItems() {
    var items;
    if (state.viewMode === 'unsynced') {
      items = state.items.filter(function (i) {
        return i.sync_status === 'local' || i.sync_status === 'error';
      });
    } else if (state.currentFolderId == null) {
      items = state.items.slice();
    } else {
      items = state.items.filter(function (i) { return i.folder_id === state.currentFolderId; });
    }
    return items.filter(function (i) {
      return matchesQuery((i.name || '') + ' ' + (i.filename || '') + ' ' + sourceLabel(i));
    });
  }

  function visibleTemplates() {
    return (state.templates || []).filter(function (t) {
      return matchesQuery(
        (t.label || '') + ' ' + (t.filename || '') + ' ' +
        (t.module_label || t.module || '') + ' ' + (t.description || '')
      );
    });
  }

  function folderById(id) {
    return state.folders.find(function (f) { return f.id === id; });
  }

  function folderPath(folderId) {
    var path = [];
    var id = folderId;
    var guard = 0;
    while (id != null && guard++ < 40) {
      var f = folderById(id);
      if (!f) break;
      path.unshift(f);
      id = f.parent_id || null;
    }
    return path;
  }

  function renderCrumb() {
    var el = document.getElementById('filesCrumb');
    if (!el) return;
    if (state.viewMode !== 'folder' || state.currentFolderId == null) {
      el.hidden = true;
      el.innerHTML = '';
      return;
    }
    var path = folderPath(state.currentFolderId);
    if (!path.length) {
      el.hidden = true;
      el.innerHTML = '';
      return;
    }
    el.hidden = false;
    var html = '<button type="button" class="files-crumb-btn" data-crumb="">All files</button>';
    path.forEach(function (f, i) {
      html += '<span class="files-crumb-sep" aria-hidden="true">›</span>';
      if (i === path.length - 1) {
        html += '<span class="files-crumb-current">' + escapeHtml(f.name) + '</span>';
      } else {
        html += '<button type="button" class="files-crumb-btn" data-crumb="' + f.id + '">' + escapeHtml(f.name) + '</button>';
      }
    });
    el.innerHTML = html;
    el.querySelectorAll('[data-crumb]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id = btn.getAttribute('data-crumb');
        state.viewMode = 'folder';
        state.currentFolderId = id === '' ? null : parseInt(id, 10);
        state.selected = {};
        renderLocalNav();
        renderTree();
        renderMain();
      });
    });
  }

  function updateSearchPlaceholder() {
    var search = document.getElementById('filesSearch');
    if (!search) return;
    search.placeholder = state.viewMode === 'templates' ? 'Search templates…' : 'Search files…';
    search.setAttribute('aria-label', search.placeholder);
  }

  function unsyncedCount() {
    return state.items.filter(function (i) {
      return i.sync_status === 'local' || i.sync_status === 'error';
    }).length;
  }

  function renderLocalNav() {
    var tplBtn = document.getElementById('filesNavTemplates');
    var unsyncBtn = document.getElementById('filesNavUnsynced');
    var tplCount = document.getElementById('filesTemplatesCount');
    var unsyncCountEl = document.getElementById('filesUnsyncedCount');
    if (tplCount) tplCount.textContent = String((state.templates || []).length);
    if (unsyncCountEl) unsyncCountEl.textContent = String(unsyncedCount());
    if (tplBtn) tplBtn.classList.toggle('is-active', state.viewMode === 'templates');
    if (unsyncBtn) unsyncBtn.classList.toggle('is-active', state.viewMode === 'unsynced');
  }

  function setToolbarVisibility() {
    var toolbar = document.getElementById('filesToolbar');
    var mode = state.viewMode === 'templates' || state.viewMode === 'unsynced'
      ? state.viewMode
      : 'folder';
    if (toolbar) toolbar.setAttribute('data-mode', mode);
    updateSearchPlaceholder();
    renderCrumb();
    updateTemplateToolbar();
    updateSyncFolderBtn();
  }

  function updateTemplateToolbar() {
    var ids = Object.keys(state.selectedTemplates || {});
    var n = ids.length;
    var visible = visibleTemplates();
    var visibleSelected = visible.filter(function (t) { return state.selectedTemplates[t.id]; }).length;
    var dlSel = document.getElementById('filesTplDownloadSelected');
    var pushBtn = document.getElementById('filesTplPushDrive');
    var selectAll = document.getElementById('filesSelectAll');
    var connected = !!(state.drive && state.drive.connected);
    if (dlSel) dlSel.disabled = n === 0;
    if (pushBtn) {
      pushBtn.disabled = n === 0 || !connected;
      pushBtn.title = connected
        ? 'Save selected templates to Files and sync to Google Drive'
        : 'Connect Google Drive first';
    }
    if (selectAll && state.viewMode === 'templates') {
      selectAll.checked = visible.length > 0 && visibleSelected === visible.length;
      selectAll.indeterminate = visibleSelected > 0 && visibleSelected < visible.length;
    }
  }

  function setTemplateSelected(id, selected) {
    if (!id) return;
    if (selected) state.selectedTemplates[id] = true;
    else delete state.selectedTemplates[id];
    var tr = document.querySelector('#filesTableBody tr[data-template-id="' + id + '"]');
    if (tr) {
      tr.classList.toggle('is-selected', !!selected);
      var cb = tr.querySelector('.files-row-check');
      if (cb) cb.checked = !!selected;
    }
    updateTemplateToolbar();
  }

  function folderTableHeadHtml() {
    return (
      '<tr>' +
      '<th class="files-col-check"><input type="checkbox" id="filesSelectAll" aria-label="Select all"></th>' +
      '<th>Name</th><th>Source</th><th>Size</th><th>Sync</th><th>Updated</th><th></th>' +
      '</tr>'
    );
  }

  function templateTableHeadHtml() {
    return (
      '<tr>' +
      '<th class="files-col-check"><input type="checkbox" id="filesSelectAll" aria-label="Select all"></th>' +
      '<th>Name</th><th>Module</th><th>Description</th><th></th>' +
      '</tr>'
    );
  }

  function renderMain() {
    setToolbarVisibility();
    if (state.viewMode === 'templates') {
      renderTemplatesTable();
    } else {
      renderTable();
    }
    renderLocalNav();
  }

  function bindSelectAll() {
    var selectAll = document.getElementById('filesSelectAll');
    if (!selectAll) return;
    selectAll.onchange = function () {
      if (state.viewMode === 'templates') {
        if (selectAll.checked) {
          visibleTemplates().forEach(function (t) { state.selectedTemplates[t.id] = true; });
        } else {
          state.selectedTemplates = {};
        }
        renderTemplatesTable();
        return;
      }
      var items = visibleItems();
      if (selectAll.checked) {
        items.forEach(function (i) { state.selected[i.id] = true; });
      } else {
        state.selected = {};
      }
      renderTable();
    };
  }

  function renderTemplatesTable() {
    var head = document.getElementById('filesTableHead');
    var body = document.getElementById('filesTableBody');
    var heading = document.getElementById('filesHeading');
    var sub = document.getElementById('filesSub');
    if (heading) heading.textContent = 'Excel templates';
    if (sub) {
      sub.textContent = 'Stay local until you add them to Drive. Download one, selected, or all.';
    }
    if (head) head.innerHTML = templateTableHeadHtml();
    bindSelectAll();
    if (!body) return;
    var templates = visibleTemplates();
    if (!templates.length) {
      var emptyTpl = (state.query || '').trim()
        ? 'No templates match your search.'
        : 'No Excel templates available for your account.';
      body.innerHTML = '<tr><td colspan="5" class="files-empty">' + emptyTpl + '</td></tr>';
      updateTemplateToolbar();
      return;
    }
    body.innerHTML = templates.map(function (t) {
      var selected = !!state.selectedTemplates[t.id];
      var checked = selected ? ' checked' : '';
      return (
        '<tr data-template-id="' + escapeHtml(t.id) + '" class="files-tpl-row' + (selected ? ' is-selected' : '') + '" tabindex="0" role="row" aria-selected="' + (selected ? 'true' : 'false') + '">' +
        '<td class="files-col-check"><label class="files-check-hit"><input type="checkbox" class="files-row-check" data-tpl-id="' + escapeHtml(t.id) + '"' + checked + ' aria-label="Select ' + escapeHtml(t.label) + '"></label></td>' +
        '<td><div class="files-name-cell"><strong>' + escapeHtml(t.label) + '</strong><span class="files-filename">' + escapeHtml(t.filename) + '</span></div></td>' +
        '<td><span class="files-source-pill">' + escapeHtml(t.module_label || t.module) + '</span></td>' +
        '<td class="files-tpl-desc">' + escapeHtml(t.description || '—') + '</td>' +
        '<td class="files-actions-cell"><div class="files-row-actions" role="group" aria-label="Template actions">' +
        '<button type="button" class="files-icon-btn" data-tpl-act="download" data-tpl-id="' + escapeHtml(t.id) + '" data-tooltip="Download" aria-label="Download">' + actionIcon('download') + '</button>' +
        '</div></td></tr>'
      );
    }).join('');

    body.querySelectorAll('tr[data-template-id]').forEach(function (tr) {
      tr.addEventListener('click', function (e) {
        if (e.target.closest('[data-tpl-act="download"]')) return;
        if (e.target.closest('input[type="checkbox"]') || e.target.closest('label.files-check-hit')) return;
        var id = tr.getAttribute('data-template-id');
        setTemplateSelected(id, !state.selectedTemplates[id]);
        tr.setAttribute('aria-selected', state.selectedTemplates[id] ? 'true' : 'false');
      });
      tr.addEventListener('keydown', function (e) {
        if (e.key !== ' ' && e.key !== 'Enter') return;
        if (e.target.closest('[data-tpl-act="download"]')) return;
        e.preventDefault();
        var id = tr.getAttribute('data-template-id');
        setTemplateSelected(id, !state.selectedTemplates[id]);
        tr.setAttribute('aria-selected', state.selectedTemplates[id] ? 'true' : 'false');
      });
    });
    body.querySelectorAll('.files-row-check').forEach(function (cb) {
      cb.addEventListener('click', function (e) {
        e.stopPropagation();
      });
      cb.addEventListener('change', function () {
        var id = cb.getAttribute('data-tpl-id');
        setTemplateSelected(id, cb.checked);
        var tr = cb.closest('tr');
        if (tr) tr.setAttribute('aria-selected', cb.checked ? 'true' : 'false');
      });
    });
    body.querySelectorAll('[data-tpl-act="download"]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        downloadTemplate(btn.getAttribute('data-tpl-id'));
      });
    });
    updateTemplateToolbar();
  }

  function syncBadge(status) {
    var s = status || 'local';
    var cls = 'files-sync files-sync-' + (s === 'synced' ? 'synced' : s === 'error' ? 'error' : 'local');
    var label = s === 'synced' ? 'Synced' : s === 'error' ? 'Error' : 'Local';
    return '<span class="' + cls + '">' + label + '</span>';
  }

  function formatDate(iso) {
    if (!iso) return '—';
    try {
      var d = new Date(iso);
      return d.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (e) {
      return iso;
    }
  }

  function actionIcon(kind) {
    var attrs = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
    if (kind === 'download') {
      return '<svg ' + attrs + '><path d="M12 3v12"/><path d="m8 11 4 4 4-4"/><path d="M5 21h14"/></svg>';
    }
    if (kind === 'rename') {
      return '<svg ' + attrs + '><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
    }
    if (kind === 'delete') {
      return '<svg ' + attrs + '><path d="M4 7h16"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>';
    }
    return '<svg ' + attrs + '><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>';
  }

  function renderTable() {
    var head = document.getElementById('filesTableHead');
    var body = document.getElementById('filesTableBody');
    var heading = document.getElementById('filesHeading');
    var sub = document.getElementById('filesSub');
    var items = visibleItems();
    if (head) head.innerHTML = folderTableHeadHtml();
    bindSelectAll();
    if (heading) {
      if (state.viewMode === 'unsynced') {
        heading.textContent = 'Not synced yet';
      } else if (state.currentFolderId == null) {
        heading.textContent = 'All files';
      } else {
        var f = state.folders.find(function (x) { return x.id === state.currentFolderId; });
        heading.textContent = f ? f.name : 'Folder';
      }
    }
    if (sub) {
      if (state.viewMode === 'unsynced') {
        sub.textContent = 'These files are saved in Files but not yet on Google Drive. Use Sync now to push them.';
      } else {
        sub.textContent = 'Save exports from modules, then sync to Google Drive when ready.';
      }
    }
    if (!body) return;
    if (!items.length) {
      var emptyMsg;
      if ((state.query || '').trim()) {
        emptyMsg = 'No files match your search.';
      } else if (state.viewMode === 'unsynced') {
        emptyMsg = 'Everything here is already synced to Drive — or nothing has been saved yet.';
      } else {
        emptyMsg = 'No files here yet. Upload a file, or save an export from a module.';
      }
      body.innerHTML = '<tr><td colspan="7" class="files-empty">' + emptyMsg + '</td></tr>';
      updateSyncFolderBtn();
      return;
    }
    body.innerHTML = items.map(function (item) {
      var checked = state.selected[item.id] ? ' checked' : '';
      var synced = item.sync_status === 'synced';
      return (
        '<tr data-item-id="' + item.id + '">' +
        '<td class="files-col-check"><input type="checkbox" class="files-row-check" data-id="' + item.id + '"' + checked + ' aria-label="Select"></td>' +
        '<td><div class="files-name-cell"><strong>' + escapeHtml(item.name) + '</strong><span class="files-filename">' + escapeHtml(item.filename) + '</span></div></td>' +
        '<td><span class="files-source-pill">' + escapeHtml(sourceLabel(item)) + '</span></td>' +
        '<td>' + escapeHtml(item.size_label || '—') + '</td>' +
        '<td>' + syncBadge(item.sync_status) + '</td>' +
        '<td class="files-updated">' + escapeHtml(formatDate(item.updated_at)) + '</td>' +
        '<td class="files-actions-cell"><div class="files-row-actions" role="group" aria-label="File actions">' +
        '<button type="button" class="files-icon-btn" data-act="download" data-id="' + item.id + '" data-tooltip="Download" aria-label="Download">' + actionIcon('download') + '</button>' +
        '<button type="button" class="files-icon-btn" data-act="rename" data-id="' + item.id + '" data-tooltip="Rename" aria-label="Rename">' + actionIcon('rename') + '</button>' +
        '<button type="button" class="files-icon-btn' + (synced ? ' is-synced' : '') + '" data-act="sync" data-id="' + item.id + '" data-tooltip="' + (synced ? 'Re-sync to Drive' : 'Sync to Drive') + '" aria-label="' + (synced ? 'Re-sync to Drive' : 'Sync to Drive') + '">' + actionIcon('sync') + '</button>' +
        '<button type="button" class="files-icon-btn is-danger" data-act="delete" data-id="' + item.id + '" data-tooltip="Delete" aria-label="Delete">' + actionIcon('delete') + '</button>' +
        '</div></td></tr>'
      );
    }).join('');

    body.querySelectorAll('.files-row-check').forEach(function (cb) {
      cb.addEventListener('change', function () {
        var id = parseInt(cb.getAttribute('data-id'), 10);
        if (cb.checked) state.selected[id] = true;
        else delete state.selected[id];
        updateBulkToolbar();
      });
    });
    body.querySelectorAll('[data-act]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var act = btn.getAttribute('data-act');
        var id = parseInt(btn.getAttribute('data-id'), 10);
        if (act === 'download') downloadItem(id);
        else if (act === 'rename') openRenameItem(id);
        else if (act === 'sync') syncOne(id);
        else if (act === 'delete') deleteItem(id);
      });
    });
    updateSyncFolderBtn();
  }

  function selectedVisibleIds() {
    return visibleItems()
      .filter(function (i) { return state.selected[i.id]; })
      .map(function (i) { return i.id; });
  }

  function updateBulkToolbar() {
    var ids = selectedVisibleIds();
    var n = ids.length;
    var folderBulk = document.getElementById('filesBulkActions');
    var unsyncBulk = document.getElementById('filesUnsyncedBulk');
    if (folderBulk) folderBulk.hidden = !(state.viewMode === 'folder' && n > 0);
    if (unsyncBulk) unsyncBulk.hidden = !(state.viewMode === 'unsynced' && n > 0);
    var selectAll = document.getElementById('filesSelectAll');
    var items = visibleItems();
    if (selectAll && state.viewMode !== 'templates') {
      selectAll.checked = items.length > 0 && n === items.length;
      selectAll.indeterminate = n > 0 && n < items.length;
    }
  }

  function updateSyncFolderBtn() {
    var btn = document.getElementById('filesSyncFolderBtn');
    var inFolder = state.viewMode === 'folder' && state.currentFolderId != null;
    if (btn) {
      btn.hidden = !inFolder;
      btn.disabled = !inFolder;
    }
    updateBulkToolbar();
  }

  function bulkDownload() {
    var ids = selectedVisibleIds();
    if (!ids.length) return;
    toast('Downloading ' + ids.length + ' file' + (ids.length === 1 ? '' : 's') + '…');
    var i = 0;
    function next() {
      if (i >= ids.length) return;
      downloadItem(ids[i]);
      i += 1;
      if (i < ids.length) setTimeout(next, 400);
    }
    next();
  }

  function bulkSync() {
    startSelectedSync(selectedVisibleIds());
  }

  function bulkDelete() {
    var ids = selectedVisibleIds();
    if (!ids.length) return;
    openConfirm({
      title: ids.length === 1 ? 'Delete file?' : 'Delete ' + ids.length + ' files?',
      message: 'This removes them from Files' + (state.drive && state.drive.connected ? ' and from Google Drive if they were synced' : '') + '.',
      confirmLabel: 'Delete',
      onConfirm: function () {
        toastLoading('Deleting…');
        var chain = Promise.resolve();
        ids.forEach(function (id) {
          chain = chain.then(function () {
            return api('/files/api/items/' + id, { method: 'DELETE' }).catch(function () {});
          });
        });
        chain.then(function () {
          state.selected = {};
          return loadTree().then(function () { toast('Deleted'); });
        });
      },
    });
  }

  function renderDrive() {
    var st = state.drive || {};
    var card = document.getElementById('filesDriveCard');
    var body = document.getElementById('filesDriveStatus');
    var kicker = document.getElementById('filesDriveKicker');
    var pill = document.getElementById('filesDrivePill');
    var connectBtn = document.getElementById('filesDriveConnectBtn');
    var disconnectBtn = document.getElementById('filesDriveDisconnectBtn');
    if (!body) return;

    function setPill(cls, label) {
      if (!pill) return;
      pill.hidden = false;
      pill.className = 'files-drive-pill ' + cls;
      pill.innerHTML = '<span class="files-drive-pill-dot" aria-hidden="true"></span>' + escapeHtml(label);
    }

    if (card) card.setAttribute('data-state', 'idle');

    if (!st.enabled) {
      if (kicker) kicker.textContent = 'Sync unavailable';
      setPill('is-warn', 'Off');
      body.innerHTML = '<p class="files-drive-msg">Enable Drive in env after adding OAuth credentials. Local Files still work.</p>';
      if (connectBtn) connectBtn.hidden = true;
      if (disconnectBtn) disconnectBtn.hidden = true;
      return;
    }
    if (!st.configured) {
      if (kicker) kicker.textContent = 'Needs setup';
      setPill('is-warn', 'Setup');
      body.innerHTML = '<p class="files-drive-msg">Add Google OAuth credentials to connect. Files still work locally.</p>';
      if (connectBtn) connectBtn.hidden = true;
      if (disconnectBtn) disconnectBtn.hidden = true;
      return;
    }
    if (st.connected) {
      if (card) card.setAttribute('data-state', 'connected');
      if (kicker) kicker.textContent = 'Ready to sync';
      setPill('is-on', 'Connected');
      var email = st.connected_email || 'Google account';
      body.innerHTML =
        '<div class="files-drive-account">' +
        '<div class="files-drive-email" title="' + escapeHtml(email) + '">' + escapeHtml(email) + '</div>' +
        '<div class="files-drive-folder">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 9.776c.112-.017.227-.026.344-.026h15.812c.117 0 .232.009.344.026m-16.5 0a2.25 2.25 0 00-1.883 2.542l.857 6a2.25 2.25 0 002.227 1.932H19.05a2.25 2.25 0 002.227-1.932l.857-6a2.25 2.25 0 00-1.883-2.542m-16.5 0V6A2.25 2.25 0 016 3.75h3.879a1.5 1.5 0 011.06.44l2.122 2.12a1.5 1.5 0 001.06.44H18A2.25 2.25 0 0120.25 9v.776"/></svg>' +
        '<span>Syncs into <strong>Kynvera Files</strong></span>' +
        '</div>' +
        '</div>';
      if (connectBtn) connectBtn.hidden = true;
      if (disconnectBtn) disconnectBtn.hidden = false;
    } else {
      if (kicker) kicker.textContent = 'Not linked yet';
      setPill('is-off', 'Offline');
      body.innerHTML = '<p class="files-drive-msg">Connect once to push exports to Google Drive when you sync.</p>';
      if (connectBtn) connectBtn.hidden = false;
      if (disconnectBtn) disconnectBtn.hidden = true;
    }
  }

  function loadTree() {
    return Promise.all([
      api('/files/api/tree'),
      api('/files/api/templates').catch(function (err) {
        console.warn('Files templates catalog failed:', err && err.message ? err.message : err);
        toast((err && err.message) || 'Could not load Excel templates', { error: true });
        return { templates: [], count: 0, unsynced_count: 0 };
      }),
    ]).then(function (results) {
      var data = results[0] || {};
      var tpl = results[1] || {};
      state.folders = data.folders || [];
      state.items = data.items || [];
      state.drive = data.drive || tpl.drive || {};
      state.templates = tpl.templates || [];
      renderTree();
      renderMain();
      renderDrive();
      applyFolderQuery();
      if (state.drive.connected && !state.drive.root_drive_folder_id) {
        setupDriveFolders();
      }
    }).catch(function (e) {
      toast(e.message || 'Failed to load Files');
      var body = document.getElementById('filesTableBody');
      if (body) body.innerHTML = '<tr><td colspan="7" class="files-empty">' + escapeHtml(e.message) + '</td></tr>';
    });
  }

  var folderQueryApplied = false;

  function applyFolderQuery() {
    if (folderQueryApplied) return;
    folderQueryApplied = true;
    var params = new URLSearchParams(window.location.search);
    var folder = params.get('folder');
    if (!folder) return;
    var id = parseInt(folder, 10);
    if (!id) return;
    var found = state.folders.some(function (f) { return f.id === id; });
    if (!found) return;
    state.viewMode = 'folder';
    state.currentFolderId = id;
    state.selected = {};
    renderTree();
    renderMain();
    try {
      var url = new URL(window.location.href);
      url.searchParams.delete('folder');
      window.history.replaceState({}, '', url.pathname + url.search);
    } catch (e) { /* ignore */ }
  }

  function downloadBlobResponse(res, fallbackName) {
    if (!res.ok) throw new Error('Download failed');
    var disp = res.headers.get('Content-Disposition') || '';
    var name = fallbackName || 'download';
    var m = /filename="?([^";]+)"?/i.exec(disp);
    if (m) name = m[1];
    return res.blob().then(function (blob) {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  function downloadItem(id) {
    var url = '/files/api/items/' + id + '/download';
    fetch(url, { headers: authHeaders(false), credentials: 'same-origin' })
      .then(function (res) { return downloadBlobResponse(res, 'download'); })
      .catch(function (e) { toast(e.message); });
  }

  function downloadTemplate(id) {
    if (!id) return;
    toastLoading('Preparing template…');
    fetch('/files/api/templates/' + encodeURIComponent(id) + '/download', {
      headers: authHeaders(false),
      credentials: 'same-origin',
    })
      .then(function (res) {
        return downloadBlobResponse(res, id + '.xlsx').then(function () {
          toast('Downloaded');
        });
      })
      .catch(function (e) { toast(e.message || 'Download failed', { error: true }); });
  }

  function downloadTemplatesZip(ids) {
    toastLoading('Preparing zip…');
    fetch('/files/api/templates/download-zip', {
      method: 'POST',
      headers: authHeaders(true),
      body: JSON.stringify({ ids: ids || [] }),
      credentials: 'same-origin',
    })
      .then(function (res) {
        return downloadBlobResponse(res, 'excel_templates.zip').then(function () {
          toast('Downloaded');
        });
      })
      .catch(function (e) { toast(e.message || 'Download failed', { error: true }); });
  }

  function pushTemplatesToDrive() {
    var ids = Object.keys(state.selectedTemplates || {});
    if (!ids.length) {
      toast('Select at least one template');
      return;
    }
    if (!(state.drive && state.drive.connected)) {
      toast('Connect Google Drive first', { error: true });
      return;
    }
    toastLoading('Adding to Drive…');
    api('/files/api/templates/push-to-drive', {
      method: 'POST',
      body: JSON.stringify({ ids: ids }),
    })
      .then(function (data) {
        state.selectedTemplates = {};
        return loadTree().then(function () {
          var saved = (data && data.saved) || 0;
          var synced = ((data && data.synced) || []).length;
          var failed = ((data && data.failed) || []).length;
          var msg = 'Pushed ' + synced + ' of ' + saved + ' template' + (saved === 1 ? '' : 's') + ' to Drive';
          if (failed) msg += ' · ' + failed + ' failed';
          toast(msg, { error: !!failed && !synced });
        });
      })
      .catch(function (e) { toast(e.message || 'Could not add to Drive', { error: true }); });
  }

  function setViewMode(mode) {
    state.viewMode = mode;
    if (mode !== 'folder') {
      state.currentFolderId = null;
    }
    state.selected = {};
    if (mode !== 'templates') state.selectedTemplates = {};
    renderTree();
    renderMain();
    filesCloseSidebar();
  }

  function notifySyncChip() {
    if (window.FilesSyncStatus && typeof window.FilesSyncStatus.start === 'function') {
      window.FilesSyncStatus.start();
    }
  }

  function startSelectedSync(ids) {
    if (!ids || !ids.length) {
      toast('Select files to sync');
      return;
    }
    if (!(state.drive && state.drive.connected)) {
      toast('Connect Google Drive first', { error: true });
      return;
    }
    setSyncBusy(true);
    api('/files/api/sync-now', { method: 'POST', body: JSON.stringify({ ids: ids }) })
      .then(function () {
        notifySyncChip();
      })
      .catch(function (e) { toast(e.message || 'Sync failed', { error: true }); })
      .finally(function () { setSyncBusy(false); });
  }

  function syncNow() {
    startSelectedSync(selectedVisibleIds());
  }

  function syncOne(id) {
    startSelectedSync([id]);
  }

  function syncFolder() {
    if (state.currentFolderId == null) {
      toast('Select a folder first');
      return;
    }
    if (!(state.drive && state.drive.connected)) {
      toast('Connect Google Drive first', { error: true });
      return;
    }
    setSyncBusy(true);
    api('/files/api/folders/' + state.currentFolderId + '/sync', { method: 'POST', body: '{}' })
      .then(function () {
        notifySyncChip();
      })
      .catch(function (e) { toast(e.message || 'Sync failed', { error: true }); })
      .finally(function () { setSyncBusy(false); });
  }

  var missingState = { folders: [], files: [] };

  function maybePromptMissing(data) {
    if (!data || !data.needs_decision) return;
    var missing = data.missing_on_drive || {};
    var folders = missing.folders || [];
    var files = missing.files || [];
    if (!folders.length && !files.length) return;
    openMissingModal(folders, files);
  }

  function openMissingModal(folders, files) {
    missingState = { folders: folders || [], files: files || [] };
    var backdrop = document.getElementById('filesMissingBackdrop');
    var list = document.getElementById('filesMissingList');
    var note = document.getElementById('filesMissingNote');
    var msg = document.getElementById('filesMissingMsg');
    if (!list) return;

    var total = missingState.folders.length + missingState.files.length;
    if (msg) {
      msg.textContent = total === 1
        ? 'This item was removed in Google Drive. Delete it from Files, or keep it here and restore to Drive?'
        : 'These items were removed in Google Drive. Delete them from Files, or keep them here and restore to Drive?';
    }

    var html = '';
    var hasSystem = false;
    missingState.folders.forEach(function (f) {
      if (f.is_system) hasSystem = true;
      html +=
        '<li>' +
          '<span class="files-missing-kind">Folder</span>' +
          '<span class="files-missing-name" title="' + escapeHtml(f.name || '') + '">' + escapeHtml(f.name || '') + '</span>' +
          (f.is_system ? '<span class="files-missing-system">System</span>' : '') +
        '</li>';
    });
    missingState.files.forEach(function (f) {
      html +=
        '<li>' +
          '<span class="files-missing-kind">File</span>' +
          '<span class="files-missing-name" title="' + escapeHtml(f.name || '') + '">' + escapeHtml(f.name || '') + '</span>' +
        '</li>';
    });
    list.innerHTML = html;
    if (note) note.hidden = !hasSystem;
    if (backdrop) backdrop.hidden = false;
  }

  function closeMissingModal() {
    var backdrop = document.getElementById('filesMissingBackdrop');
    if (backdrop) backdrop.hidden = true;
    missingState = { folders: [], files: [] };
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function resolveMissing(action) {
    var folderIds = (missingState.folders || []).map(function (f) { return f.id; });
    var itemIds = (missingState.files || []).map(function (f) { return f.id; });
    if (!folderIds.length && !itemIds.length) {
      closeMissingModal();
      return;
    }
    toastLoading(action === 'keep' ? 'Restoring to Drive…' : 'Updating Files…');
    api('/files/api/drive/resolve-missing', {
      method: 'POST',
      body: JSON.stringify({
        action: action,
        folder_ids: folderIds,
        item_ids: itemIds,
      }),
    })
      .then(function (data) {
        closeMissingModal();
        return loadTree().then(function () {
          if (action === 'keep') {
            var n = (data.synced || []).length;
            var fc = data.folders_created || 0;
            toast(
              'Kept in Files' +
              (fc ? ' · ' + fc + ' folder' + (fc === 1 ? '' : 's') + ' restored' : '') +
              (n ? ' · ' + n + ' file' + (n === 1 ? '' : 's') + ' restored' : '')
            );
          } else {
            var df = (data.folders_deleted || []).length;
            var di = (data.items_deleted || []).length;
            var sr = (data.system_folders_restored || []).length;
            var parts = [];
            if (di) parts.push(di + ' file' + (di === 1 ? '' : 's') + ' deleted');
            if (df) parts.push(df + ' folder' + (df === 1 ? '' : 's') + ' deleted');
            if (sr) parts.push(sr + ' system folder' + (sr === 1 ? '' : 's') + ' restored to Drive');
            toast(parts.length ? parts.join(' · ') : 'Updated');
          }
        });
      })
      .catch(function (e) { toast(e.message || 'Could not apply choice', { error: true }); });
  }

  function openModal(title, confirmLabel, mode, targetId, initial) {
    state.modalMode = mode;
    state.modalTargetId = targetId;
    var backdrop = document.getElementById('filesModalBackdrop');
    var titleEl = document.getElementById('filesModalTitle');
    var input = document.getElementById('filesModalInput');
    var confirm = document.getElementById('filesModalConfirm');
    if (titleEl) titleEl.textContent = title;
    if (confirm) confirm.textContent = confirmLabel;
    if (input) {
      input.value = initial || '';
      setTimeout(function () { input.focus(); }, 50);
    }
    if (backdrop) backdrop.hidden = false;
  }

  function closeModal() {
    var backdrop = document.getElementById('filesModalBackdrop');
    if (backdrop) backdrop.hidden = true;
    state.modalMode = null;
    state.modalTargetId = null;
  }

  var confirmCallback = null;

  function openConfirm(opts) {
    opts = opts || {};
    var backdrop = document.getElementById('filesConfirmBackdrop');
    var titleEl = document.getElementById('filesConfirmTitle');
    var msgEl = document.getElementById('filesConfirmMsg');
    var okBtn = document.getElementById('filesConfirmOk');
    if (titleEl) titleEl.textContent = opts.title || 'Are you sure?';
    if (msgEl) msgEl.textContent = opts.message || '';
    if (okBtn) {
      okBtn.textContent = opts.confirmLabel || 'Delete';
      okBtn.className = 'files-btn ' + (opts.danger === false ? 'files-btn-primary' : 'files-btn-danger');
    }
    confirmCallback = typeof opts.onConfirm === 'function' ? opts.onConfirm : null;
    if (backdrop) backdrop.hidden = false;
    if (okBtn) setTimeout(function () { okBtn.focus(); }, 30);
  }

  function closeConfirm() {
    var backdrop = document.getElementById('filesConfirmBackdrop');
    if (backdrop) backdrop.hidden = true;
    confirmCallback = null;
  }

  function confirmModal() {
    var input = document.getElementById('filesModalInput');
    var name = (input && input.value || '').trim();
    if (!name) {
      toast('Name is required');
      return;
    }
    var mode = state.modalMode;
    var id = state.modalTargetId;
    var p;
    if (mode === 'folder') {
      var parentId = state.currentFolderId;
      p = api('/files/api/folders', {
        method: 'POST',
        body: JSON.stringify({ name: name, parent_id: parentId }),
      });
    } else if (mode === 'rename-folder') {
      p = api('/files/api/folders/' + id, { method: 'PATCH', body: JSON.stringify({ name: name }) });
    } else if (mode === 'rename-item') {
      p = api('/files/api/items/' + id, { method: 'PATCH', body: JSON.stringify({ name: name }) });
    } else {
      return;
    }
    p.then(function () {
      closeModal();
      toast('Saved');
      return loadTree();
    }).catch(function (e) { toast(e.message); });
  }

  function openRenameItem(id) {
    var item = state.items.find(function (x) { return x.id === id; });
    openModal('Rename file', 'Rename', 'rename-item', id, item ? item.name : '');
  }

  function openRenameFolder(id) {
    var folder = state.folders.find(function (x) { return x.id === id; });
    openModal('Rename folder', 'Rename', 'rename-folder', id, folder ? folder.name : '');
  }

  function deleteItem(id) {
    var item = state.items.find(function (x) { return x.id === id; });
    var label = item ? item.name : 'this file';
    openConfirm({
      title: 'Delete file?',
      message: 'Delete "' + label + '"? This removes it from Files' + (item && item.drive_file_id ? ' and from Google Drive' : '') + '.',
      confirmLabel: 'Delete',
      onConfirm: function () {
        api('/files/api/items/' + id, { method: 'DELETE' })
          .then(function (data) {
            delete state.selected[id];
            if (data && data.had_drive_copy && data.drive_removed === false) {
              toast('Removed from Files, but Google Drive copy could not be deleted');
            } else {
              toast(data && data.had_drive_copy ? 'File deleted from Files and Drive' : 'File deleted');
            }
            return loadTree();
          })
          .catch(function (e) { toast(e.message || 'Delete failed'); });
      },
    });
  }

  function deleteFolder(id) {
    var folder = state.folders.find(function (x) { return x.id === id; });
    if (folder && folder.path_key) {
      toast('System folders cannot be deleted');
      return;
    }
    var label = folder ? folder.name : 'this folder';
    openConfirm({
      title: 'Delete folder?',
      message: 'Delete folder "' + label + '" and everything inside it? Synced copies will also be removed from Google Drive.',
      confirmLabel: 'Delete folder',
      onConfirm: function () {
        api('/files/api/folders/' + id, { method: 'DELETE' })
          .then(function (data) {
            if (state.currentFolderId === id) state.currentFolderId = null;
            if (data && data.had_drive_copies && data.drive_removed === false) {
              toast('Removed from Files, but some Google Drive items could not be deleted');
            } else {
              toast(data && data.had_drive_copies ? 'Folder deleted from Files and Drive' : 'Folder deleted');
            }
            return loadTree();
          })
          .catch(function (e) { toast(e.message || 'Delete failed'); });
      },
    });
  }

  function uploadFiles(fileList) {
    var folderId = state.currentFolderId;
    if (folderId == null) {
      var hr = state.folders.find(function (f) { return f.path_key === 'hr'; });
      folderId = hr ? hr.id : (state.folders[0] && state.folders[0].id);
    }
    if (!folderId) {
      toast('Create or select a folder first');
      return;
    }
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) return;
    var chain = Promise.resolve();
    files.forEach(function (file) {
      chain = chain.then(function () {
        var fd = new FormData();
        fd.append('file', file);
        fd.append('folder_id', String(folderId));
        return fetch('/files/api/upload', {
          method: 'POST',
          headers: authHeaders(false),
          body: fd,
          credentials: 'same-origin',
        }).then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok || data.success === false) throw new Error(data.error || data.message || 'Upload failed');
          });
        });
      });
    });
    chain.then(function () {
      toast('Upload complete');
      return loadTree();
    }).catch(function (e) { toast(e.message); });
  }

  function setupDriveFolders(opts) {
    opts = opts || {};
    if (state.driveSetupInFlight) return Promise.resolve();
    state.driveSetupInFlight = true;
    if (opts.toast) toastLoading('Connected — setting up Drive folders…');
    return api('/files/api/drive/setup', { method: 'POST', body: '{}' })
      .then(function () {
        return loadTree().then(function () {
          if (opts.toast) toast('Google Drive connected');
        });
      })
      .catch(function (e) {
        toast(e.message || 'Drive connected, but folder setup failed. Use Sync now.', { error: true });
      })
      .then(function () {
        state.driveSetupInFlight = false;
      });
  }

  function handleDriveQuery() {
    var params = new URLSearchParams(window.location.search);
    var drive = params.get('drive');
    if (drive === 'connected') setupDriveFolders({ toast: true });
    else if (drive === 'error') toast('Drive connect failed: ' + (params.get('msg') || 'error'), { error: true });
    if (drive) {
      var url = new URL(window.location.href);
      url.searchParams.delete('drive');
      url.searchParams.delete('msg');
      window.history.replaceState({}, '', url.pathname + url.search);
    }
  }

  function bind() {
    var uploadBtn = document.getElementById('filesUploadBtn');
    var uploadInput = document.getElementById('filesUploadInput');
    var newFolderBtn = document.getElementById('filesNewFolderBtn');
    var syncNowBtn = document.getElementById('filesSyncNowBtn');
    var syncFolderBtn = document.getElementById('filesSyncFolderBtn');
    var connectBtn = document.getElementById('filesDriveConnectBtn');
    var disconnectBtn = document.getElementById('filesDriveDisconnectBtn');
    var modalCancel = document.getElementById('filesModalCancel');
    var modalConfirm = document.getElementById('filesModalConfirm');
    var confirmCancel = document.getElementById('filesConfirmCancel');
    var confirmOk = document.getElementById('filesConfirmOk');
    var confirmBackdrop = document.getElementById('filesConfirmBackdrop');
    var missingLater = document.getElementById('filesMissingLater');
    var missingDelete = document.getElementById('filesMissingDelete');
    var missingKeep = document.getElementById('filesMissingKeep');
    var missingBackdrop = document.getElementById('filesMissingBackdrop');
    var navTemplates = document.getElementById('filesNavTemplates');
    var navUnsynced = document.getElementById('filesNavUnsynced');
    var tplDlSelected = document.getElementById('filesTplDownloadSelected');
    var tplDlAll = document.getElementById('filesTplDownloadAll');
    var tplPush = document.getElementById('filesTplPushDrive');
    var unsyncSync = document.getElementById('filesUnsyncedSyncBtn');
    var search = document.getElementById('filesSearch');
    var bulkDownloadBtn = document.getElementById('filesBulkDownload');
    var bulkSyncBtn = document.getElementById('filesBulkSync');
    var bulkDeleteBtn = document.getElementById('filesBulkDelete');
    var unsyncDownload = document.getElementById('filesUnsyncedDownload');
    var unsyncSelectedSync = document.getElementById('filesUnsyncedSync');
    var unsyncDelete = document.getElementById('filesUnsyncedDelete');

    if (navTemplates) {
      navTemplates.addEventListener('click', function () { setViewMode('templates'); });
    }
    if (navUnsynced) {
      navUnsynced.addEventListener('click', function () { setViewMode('unsynced'); });
    }
    if (tplDlSelected) {
      tplDlSelected.addEventListener('click', function () {
        downloadTemplatesZip(Object.keys(state.selectedTemplates || {}));
      });
    }
    if (tplDlAll) {
      tplDlAll.addEventListener('click', function () { downloadTemplatesZip([]); });
    }
    if (tplPush) tplPush.addEventListener('click', pushTemplatesToDrive);
    if (unsyncSync) unsyncSync.addEventListener('click', syncNow);
    if (search) {
      search.addEventListener('input', function () {
        state.query = search.value || '';
        renderMain();
      });
    }
    if (bulkDownloadBtn) bulkDownloadBtn.addEventListener('click', bulkDownload);
    if (bulkSyncBtn) bulkSyncBtn.addEventListener('click', bulkSync);
    if (bulkDeleteBtn) bulkDeleteBtn.addEventListener('click', bulkDelete);
    if (unsyncDownload) unsyncDownload.addEventListener('click', bulkDownload);
    if (unsyncSelectedSync) unsyncSelectedSync.addEventListener('click', bulkSync);
    if (unsyncDelete) unsyncDelete.addEventListener('click', bulkDelete);

    if (uploadBtn && uploadInput) {
      uploadBtn.addEventListener('click', function () { uploadInput.click(); });
      uploadInput.addEventListener('change', function () {
        uploadFiles(uploadInput.files);
        uploadInput.value = '';
      });
    }
    if (newFolderBtn) {
      newFolderBtn.addEventListener('click', function () {
        openModal('New folder', 'Create', 'folder', null, '');
      });
    }
    if (syncNowBtn) syncNowBtn.addEventListener('click', syncNow);
    if (syncFolderBtn) syncFolderBtn.addEventListener('click', syncFolder);
    bindSelectAll();
    if (connectBtn) {
      connectBtn.addEventListener('click', function () {
        if (state.connecting || connectBtn.disabled) return;
        state.connecting = true;
        connectBtn.disabled = true;
        toastLoading('Opening Google…');
        window.location.assign('/files/api/drive/connect');
      });
    }
    if (disconnectBtn) {
      disconnectBtn.addEventListener('click', function () {
        openConfirm({
          title: 'Disconnect Google Drive?',
          message: 'This stops Drive sync for this organization. Local Files stay available.',
          confirmLabel: 'Disconnect',
          onConfirm: function () {
            api('/files/api/drive/disconnect', { method: 'POST', body: '{}' })
              .then(function () {
                toast('Disconnected');
                return loadTree();
              })
              .catch(function (e) { toast(e.message); });
          },
        });
      });
    }
    if (modalCancel) modalCancel.addEventListener('click', closeModal);
    if (modalConfirm) modalConfirm.addEventListener('click', confirmModal);
    if (confirmCancel) confirmCancel.addEventListener('click', closeConfirm);
    if (confirmOk) {
      confirmOk.addEventListener('click', function () {
        var fn = confirmCallback;
        closeConfirm();
        if (fn) fn();
      });
    }
    if (confirmBackdrop) {
      confirmBackdrop.addEventListener('click', function (e) {
        if (e.target === confirmBackdrop) closeConfirm();
      });
    }
    if (missingLater) missingLater.addEventListener('click', closeMissingModal);
    if (missingDelete) {
      missingDelete.addEventListener('click', function () { resolveMissing('delete_local'); });
    }
    if (missingKeep) {
      missingKeep.addEventListener('click', function () { resolveMissing('keep'); });
    }
    if (missingBackdrop) {
      missingBackdrop.addEventListener('click', function (e) {
        if (e.target === missingBackdrop) closeMissingModal();
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    bind();
    handleDriveQuery();
    loadTree();
    window.addEventListener('files-sync-complete', function () {
      loadTree();
    });
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') filesCloseSidebar();
  });
})();
