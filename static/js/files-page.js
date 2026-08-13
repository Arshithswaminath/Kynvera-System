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
    selected: {},
    modalMode: null, // 'folder' | 'rename-folder' | 'rename-item'
    modalTargetId: null,
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

  window.filesToggleSidebar = function () {
    var sb = document.getElementById('filesSidebar');
    var ov = document.getElementById('filesOverlay');
    if (!sb) return;
    var open = !sb.classList.contains('open');
    sb.classList.toggle('open', open);
    if (ov) {
      ov.classList.toggle('open', open);
      ov.setAttribute('aria-hidden', open ? 'false' : 'true');
    }
  };

  window.filesCloseSidebar = function () {
    var sb = document.getElementById('filesSidebar');
    var ov = document.getElementById('filesOverlay');
    if (sb) sb.classList.remove('open');
    if (ov) {
      ov.classList.remove('open');
      ov.setAttribute('aria-hidden', 'true');
    }
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
    html +=
      '<div class="files-folder-row files-folder-row--all' +
      (state.currentFolderId === null ? ' is-active' : '') +
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
        var active = String(state.currentFolderId) === String(f.id);
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
        state.currentFolderId = id === '' ? null : parseInt(id, 10);
        state.selected = {};
        renderTree();
        renderTable();
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

  function visibleItems() {
    if (state.currentFolderId == null) return state.items.slice();
    return state.items.filter(function (i) { return i.folder_id === state.currentFolderId; });
  }

  function syncBadge(status) {
    var s = status || 'local';
    var cls = 'files-sync files-sync-' + (s === 'synced' ? 'synced' : s === 'error' ? 'error' : 'local');
    var label = s === 'synced' ? 'Synced' : s === 'error' ? 'Error' : 'Local';
    return '<span class="' + cls + '">' + label + '</span>';
  }

  function sourceLabel(item) {
    var m = item.source_module || '';
    var k = item.source_kind || '';
    var names = {
      manpower: 'Manpower',
      leave: 'Leave',
      hiring: 'Hiring',
      procurement: 'Procurement',
      qhsi: 'QHSE',
      mmr: 'MMR',
      devices: 'Devices',
      technicians: 'Technicians',
      upload: 'Upload',
    };
    var base = names[m] || m || '—';
    if (m === 'upload') return base;
    return base + ' · ' + (k || '—');
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
    if (kind === 'download') {
      return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"/></svg>';
    }
    if (kind === 'rename') {
      return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10"/></svg>';
    }
    if (kind === 'delete') {
      return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673A2.25 2.25 0 0115.916 21H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>';
    }
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z"/></svg>';
  }

  function renderTable() {
    var body = document.getElementById('filesTableBody');
    var heading = document.getElementById('filesHeading');
    var items = visibleItems();
    if (heading) {
      if (state.currentFolderId == null) heading.textContent = 'All files';
      else {
        var f = state.folders.find(function (x) { return x.id === state.currentFolderId; });
        heading.textContent = f ? f.name : 'Folder';
      }
    }
    if (!body) return;
    if (!items.length) {
      body.innerHTML = '<tr><td colspan="7" class="files-empty">No files here yet. Use Save to Files from Leave or Manpower, or upload.</td></tr>';
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
        updateSyncFolderBtn();
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

  function updateSyncFolderBtn() {
    var btn = document.getElementById('filesSyncFolderBtn');
    if (!btn) return;
    btn.disabled = state.currentFolderId == null;
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
    return api('/files/api/tree').then(function (data) {
      state.folders = data.folders || [];
      state.items = data.items || [];
      state.drive = data.drive || {};
      renderTree();
      renderTable();
      renderDrive();
    }).catch(function (e) {
      toast(e.message || 'Failed to load Files');
      var body = document.getElementById('filesTableBody');
      if (body) body.innerHTML = '<tr><td colspan="7" class="files-empty">' + escapeHtml(e.message) + '</td></tr>';
    });
  }

  function downloadItem(id) {
    var token = localStorage.getItem('access_token') || localStorage.getItem('token');
    var url = '/files/api/items/' + id + '/download';
    fetch(url, { headers: authHeaders(false), credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) throw new Error('Download failed');
        var disp = res.headers.get('Content-Disposition') || '';
        var name = 'download';
        var m = /filename="?([^";]+)"?/i.exec(disp);
        if (m) name = m[1];
        return res.blob().then(function (blob) {
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = name;
          a.click();
          URL.revokeObjectURL(a.href);
        });
      })
      .catch(function (e) { toast(e.message); });
  }

  function syncOne(id) {
    toastLoading('Syncing…');
    api('/files/api/items/' + id + '/sync', { method: 'POST', body: '{}' })
      .then(function () {
        return loadTree().then(function () {
          toast('Synced');
        });
      })
      .catch(function (e) { toast(e.message || 'Sync failed', { error: true }); });
  }

  function syncFolder() {
    if (state.currentFolderId == null) {
      toast('Select a folder first');
      return;
    }
    var folder = state.folders.find(function (x) { return x.id === state.currentFolderId; });
    var label = folder ? folder.name : 'folder';
    setSyncBusy(true);
    toastLoading('Syncing "' + label + '"…');
    api('/files/api/folders/' + state.currentFolderId + '/sync', { method: 'POST', body: '{}' })
      .then(function (data) {
        return loadTree().then(function () {
          toast(formatSyncFolderMessage(label, data));
          maybePromptMissing(data);
        });
      })
      .catch(function (e) { toast(e.message || 'Sync failed', { error: true }); })
      .finally(function () { setSyncBusy(false); });
  }

  function syncNow() {
    setSyncBusy(true);
    toastLoading('Syncing…');
    api('/files/api/sync-now', { method: 'POST', body: '{}' })
      .then(function (data) {
        return loadTree().then(function () {
          toast(formatSyncNowMessage(data));
          maybePromptMissing(data);
        });
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

  function handleDriveQuery() {
    var params = new URLSearchParams(window.location.search);
    var drive = params.get('drive');
    if (drive === 'connected') toast('Google Drive connected');
    else if (drive === 'error') toast('Drive connect failed: ' + (params.get('msg') || 'error'));
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
    var selectAll = document.getElementById('filesSelectAll');
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
    if (selectAll) {
      selectAll.addEventListener('change', function () {
        var items = visibleItems();
        if (selectAll.checked) {
          items.forEach(function (i) { state.selected[i.id] = true; });
        } else {
          state.selected = {};
        }
        renderTable();
      });
    }
    if (connectBtn) {
      connectBtn.addEventListener('click', function () {
        api('/files/api/drive/connect?redirect=0').then(function (data) {
          if (data.auth_url) window.location.href = data.auth_url;
          else toast('Could not start Google Drive connect');
        }).catch(function (e) { toast(e.message || 'Connect failed'); });
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
  });
})();
