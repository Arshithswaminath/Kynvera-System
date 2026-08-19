(function () {
  const cfg = window.BD_EMAIL || {};
  const gmEmails = cfg.gmEmails || [];
  const bdEmails = cfg.bdEmails || [];
  const poEmails = cfg.poEmails || [];
  const omEmails = cfg.omEmails || [];
  const supervisorEmails = cfg.supervisorEmails || [];

  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  function authHeaders(json) {
    const headers = {};
    const token = localStorage.getItem('access_token');
    if (token) headers.Authorization = 'Bearer ' + token;
    if (json !== false) headers['Content-Type'] = 'application/json';
    return headers;
  }

  async function api(path, options) {
    const opts = options || {};
    const response = await fetch(path, {
      method: opts.method || 'GET',
      headers: opts.headers || authHeaders(opts.json !== false),
      body: opts.body,
    });
    let data = {};
    try {
      data = await response.json();
    } catch (err) {
      data = {};
    }
    if (!response.ok) {
      const error = new Error(data.error || data.message || 'Request failed');
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  function showAlert(box, message, kind) {
    if (!box) return;
    box.innerHTML = `<div class="alert ${kind || 'success'}">${escapeHtml(message)}</div>`;
  }

  function parseEmails(value) {
    return String(value || '').split(/[;,]/).map((p) => p.trim()).filter(Boolean);
  }

  function uniqueEmails(list) {
    const seen = new Set();
    const out = [];
    list.forEach((email) => {
      const key = email.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      out.push(email);
    });
    return out;
  }

  function pad2(n) {
    return String(n).padStart(2, '0');
  }

  function formatStamp(iso) {
    if (!iso) return 'Never';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString();
  }

  function formatStampCompact(iso) {
    if (!iso) return 'Never';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  }

  let currentTab = 'personal';
  let automations = [];
  let groups = [];
  let selectedId = null;
  let draftSlots = [];
  let cloudCatalog = { items: [], folders: [] };
  let pickerMode = 'once';
  let pickerKind = 'file';
  let selectedOnceIds = [];
  let selectedCloudOnce = [];

  function currentScope() {
    return currentTab === 'public' ? 'public' : 'personal';
  }

  function selectedAutomation() {
    return automations.find((a) => String(a.id) === String(selectedId)) || null;
  }

  function openSidebar() {
    const sidebar = $('bdeSidebar');
    const overlay = $('bdeSidebarOverlay');
    if (sidebar) sidebar.classList.add('open');
    if (overlay) {
      overlay.classList.add('active');
      overlay.setAttribute('aria-hidden', 'false');
    }
  }

  function closeSidebar() {
    const sidebar = $('bdeSidebar');
    const overlay = $('bdeSidebarOverlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) {
      overlay.classList.remove('active');
      overlay.setAttribute('aria-hidden', 'true');
    }
  }

  function toggleSidebar() {
    const sidebar = $('bdeSidebar');
    if (!sidebar) return;
    if (sidebar.classList.contains('open')) closeSidebar();
    else openSidebar();
  }

  async function loadUser() {
    try {
      const response = await fetch('/api/auth/me', { headers: authHeaders(false) });
      if (!response.ok) return;
      const data = await response.json();
      const user = data.user;
      if (!user) return;
      const name = user.full_name || user.username || 'User';
      const role = user.role === 'admin' ? 'Admin' : (user.designation ? String(user.designation).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : 'BD');
      const initials = name.split(' ').map((n) => n[0]).filter(Boolean).join('').toUpperCase().slice(0, 2) || 'U';
      const av = $('bdeUserAv');
      const nm = $('bdeUserName');
      const rl = $('bdeUserRole');
      if (av) av.textContent = initials;
      if (nm) nm.textContent = name;
      if (rl) rl.textContent = role;
    } catch (err) {
      /* ignore */
    }
  }

  function scheduleTimestamp(auto) {
    return auto.last_success_at || auto.last_run_at || null;
  }

  async function loadKpis() {
    try {
      const [personalData, publicData] = await Promise.all([
        api('/bd/email-module/automations?scope=personal'),
        api('/bd/email-module/automations?scope=public'),
      ]);
      const personal = personalData.items || [];
      const pub = publicData.items || [];
      const combined = personal.concat(pub);
      const scheduledCount = combined.filter((a) => a.enabled !== false && a.schedule_enabled && !a.schedule_paused).length;
      const lastRun = combined
        .map(scheduleTimestamp)
        .filter(Boolean)
        .sort((a, b) => new Date(b) - new Date(a))[0];

      const mineEl = $('bdeKpiMineValue');
      const pubEl = $('bdeKpiPublicValue');
      const schedEl = $('bdeKpiScheduledValue');
      const lastRunEl = $('bdeKpiLastRunValue');
      if (mineEl) mineEl.textContent = String(personal.length);
      if (pubEl) pubEl.textContent = String(pub.length);
      if (schedEl) schedEl.textContent = String(scheduledCount);
      if (lastRunEl) lastRunEl.textContent = lastRun ? formatStampCompact(lastRun) : 'Never';

      const countPersonal = $('bdeCountPersonal');
      const countPublic = $('bdeCountPublic');
      if (countPersonal) countPersonal.textContent = String(personal.length);
      if (countPublic) countPublic.textContent = String(pub.length);
    } catch (err) {
      /* KPI tiles are best-effort; ignore failures */
    }
  }

  function setTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.sb-nav-item[data-tab]').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    const autoView = $('automationView');
    const onceView = $('sendOnceView');
    const listSub = $('autoListSub');
    if (tab === 'once') {
      autoView.classList.add('hidden-view');
      onceView.classList.remove('hidden-view');
    } else {
      onceView.classList.add('hidden-view');
      autoView.classList.remove('hidden-view');
      if (listSub) listSub.textContent = tab === 'public' ? 'Public' : 'Personal';
      loadAutomations();
      loadGroups();
    }
    closeSidebar();
  }

  function renderGroupButtons(scopeFilter) {
    const visible = groups.filter((g) => !scopeFilter || g.scope === scopeFilter || g.scope === 'public');
    ['autoToGroupButtons', 'autoCcGroupButtons', 'toGroupButtons', 'ccGroupButtons'].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.innerHTML = visible.map((g) => `
        <span class="group-button-wrap">
          <button type="button" class="btn btn-secondary group-add-btn" data-group-id="${g.id}">${escapeHtml(g.name)}</button>
          ${g.can_edit ? `<span class="group-actions">
            <button type="button" class="group-edit-btn" data-group-id="${g.id}" title="Edit">✎</button>
            <button type="button" class="group-remove-btn" data-group-id="${g.id}" title="Remove">×</button>
          </span>` : ''}
        </span>
      `).join('');
    });
  }

  function addEmailsToField(field, emails) {
    if (!field) return;
    field.value = uniqueEmails(parseEmails(field.value).concat(emails)).join(', ');
    field.dispatchEvent(new Event('input'));
  }

  function renderChips(listEl, field) {
    if (!listEl || !field) return;
    const emails = parseEmails(field.value);
    listEl.innerHTML = emails.map((email) => `
      <span class="recipient-chip">${escapeHtml(email)}
        <button type="button" data-email="${escapeHtml(email)}" aria-label="Remove">×</button>
      </span>
    `).join('');
  }

  function bindRecipientField(field, listEl) {
    if (!field || !listEl) return;
    field.addEventListener('input', () => renderChips(listEl, field));
    listEl.addEventListener('click', (ev) => {
      const btn = ev.target.closest('button[data-email]');
      if (!btn) return;
      const remove = btn.dataset.email;
      field.value = parseEmails(field.value).filter((e) => e !== remove).join(', ');
      renderChips(listEl, field);
    });
    renderChips(listEl, field);
  }

  async function loadGroups() {
    const data = await api('/bd/email-module/groups');
    groups = data.items || [];
    renderGroupButtons(currentScope());
  }

  async function loadAutomations() {
    const data = await api(`/bd/email-module/automations?scope=${encodeURIComponent(currentScope())}`);
    automations = data.items || [];
    if (selectedId && !automations.some((a) => a.id === selectedId)) selectedId = null;
    renderAutomationList();
    if (selectedId) {
      fillBuilder(selectedAutomation());
    } else if (!selectedId) {
      resetBuilder();
    }
    loadKpis();
  }

  function initialsFrom(name) {
    const parts = String(name || 'A').trim().split(/\s+/).filter(Boolean);
    const letters = parts.map((p) => p[0]).join('').toUpperCase().slice(0, 2);
    return letters || 'A';
  }

  function avatarTone(name) {
    const s = String(name || '');
    let n = 0;
    for (let i = 0; i < s.length; i += 1) n += s.charCodeAt(i);
    return (n % 4) + 1;
  }

  function listTimeLabel(auto) {
    if (auto.schedule_enabled) {
      return `${pad2(auto.schedule_hour)}:${pad2(auto.schedule_minute)}`;
    }
    const stamp = auto.last_run_at || auto.updated_at;
    if (!stamp) return 'Manual';
    const d = new Date(stamp);
    if (Number.isNaN(d.getTime())) return 'Manual';
    const today = new Date();
    if (d.toDateString() === today.toDateString()) {
      return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
    }
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function renderAutomationList() {
    const wrap = $('autoList');
    const countEl = $('autoListCount');
    const n = automations.length;
    if (countEl) countEl.textContent = n === 1 ? '1 automation' : `${n} automations`;
    if (!wrap) return;
    if (!n) {
      wrap.innerHTML = '<p class="helper">No saved automations yet. Tap New to create one.</p>';
      return;
    }
    wrap.innerHTML = automations.map((auto) => {
      const files = auto.attachment_count || 0;
      const preview = auto.to_emails
        ? `To ${auto.to_emails}`
        : (auto.schedule_enabled ? 'Scheduled send' : 'No recipients yet');
      const clip = files
        ? `<svg class="auto-card__clip" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 8.25l-10.94 10.939a1.5 1.5 0 01-2.121-2.121L14.87 8.3"/></svg>`
        : '';
      return `
        <button type="button" class="auto-card ${String(auto.id) === String(selectedId) ? 'active' : ''}" data-id="${auto.id}">
          <span class="auto-card__av auto-card__av--${avatarTone(auto.name)}">${escapeHtml(initialsFrom(auto.name))}</span>
          <span class="auto-card__body">
            <strong>${escapeHtml(auto.name || 'Untitled')}</strong>
            <span class="auto-card__sub">${escapeHtml(auto.subject || 'No subject')}</span>
            <span class="auto-card__preview">${escapeHtml(preview)}</span>
          </span>
          <span class="auto-card__meta">
            <span class="auto-card__time">${escapeHtml(listTimeLabel(auto))}</span>
            ${clip}
          </span>
        </button>
      `;
    }).join('');
  }

  function slotLabel(slot) {
    if (slot.kind === 'folder_latest') return `Latest in ${slot.folder_name || 'folder'}`;
    if (slot.kind === 'submission_reports') return `Reviewed form ${slot.submission_id}`;
    return slot.file_name || 'Cloud file';
  }

  function renderSlots() {
    const box = $('autoSlots');
    if (!box) return;
    if (!draftSlots.length) {
      box.innerHTML = '<p class="helper">No files yet. Pick from Files, upload a new file, or use the latest file in a folder.</p>';
      return;
    }
    box.innerHTML = draftSlots.map((slot, idx) => `
      <div class="slot-card" data-idx="${idx}">
        <div class="slot-card-top">
          <div>
            <strong>${escapeHtml(slotLabel(slot))}</strong>
            <div class="helper">${escapeHtml(slot.kind === 'linked_file' ? (slot.sync_status || 'local') : slot.kind.replace('_', ' '))}</div>
          </div>
          <button type="button" class="btn btn-secondary slot-remove" data-idx="${idx}">Remove</button>
        </div>
        ${slot.kind !== 'submission_reports' ? `
          <label class="slot-require">
            <input type="checkbox" class="slot-require-new" data-idx="${idx}" ${slot.require_new ? 'checked' : ''}>
            Require a new file before each send
          </label>
        ` : ''}
      </div>
    `).join('');
  }

  function fillBuilder(auto) {
    $('autoName').value = auto && auto.name ? auto.name : '';
    const scope = (auto && auto.scope) || currentScope();
    $('scopePersonalBtn').classList.toggle('active', scope !== 'public');
    $('scopePublicBtn').classList.toggle('active', scope === 'public');
    $('autoTo').value = auto && auto.to_emails ? auto.to_emails : '';
    $('autoCc').value = auto && auto.cc_emails ? auto.cc_emails : '';
    $('autoSubject').value = auto && auto.subject ? auto.subject : '';
    $('autoMessage').value = auto && auto.body ? auto.body : '';
    $('autoEnabled').checked = auto ? auto.enabled !== false : true;
    $('autoScheduleEnabled').checked = !!(auto && auto.schedule_enabled);
    $('autoSchedulePaused').checked = !!(auto && auto.schedule_paused);
    const hour = auto && auto.schedule_hour != null ? auto.schedule_hour : 10;
    const minute = auto && auto.schedule_minute != null ? auto.schedule_minute : 0;
    $('autoScheduleTime').value = `${pad2(hour)}:${pad2(minute)}`;
    draftSlots = auto && auto.attachments ? auto.attachments.map((s) => ({ ...s })) : [];
    renderSlots();
    renderChips($('autoToList'), $('autoTo'));
    renderChips($('autoCcList'), $('autoCc'));
    $('deleteAutoBtn').style.display = auto && auto.id && auto.can_edit !== false ? '' : 'none';
    $('runAutoBtn').style.display = auto && auto.id ? '' : 'none';
    $('uploadAutoFile').disabled = !(auto && auto.id && auto.can_edit !== false);
    const title = $('builderTitle');
    if (title) title.textContent = auto && auto.id ? (auto.name || 'Untitled') : 'New automation';
    loadHistory(auto && auto.id);
  }

  function resetBuilder() {
    selectedId = null;
    fillBuilder({
      name: '',
      scope: currentScope(),
      to_emails: '',
      cc_emails: '',
      subject: '',
      body: '',
      enabled: true,
      schedule_enabled: false,
      schedule_paused: false,
      schedule_hour: 10,
      schedule_minute: 0,
      attachments: [],
      can_edit: true,
    });
    renderAutomationList();
  }

  function builderPayload() {
    const time = ($('autoScheduleTime').value || '10:00').split(':');
    return {
      name: $('autoName').value.trim(),
      scope: $('scopePublicBtn').classList.contains('active') ? 'public' : 'personal',
      to_emails: $('autoTo').value,
      cc_emails: $('autoCc').value,
      subject: $('autoSubject').value,
      body: $('autoMessage').value,
      enabled: $('autoEnabled').checked,
      schedule_enabled: $('autoScheduleEnabled').checked,
      schedule_paused: $('autoSchedulePaused').checked,
      schedule_hour: Number(time[0] || 10),
      schedule_minute: Number(time[1] || 0),
      attachments: draftSlots.map((slot) => ({
        kind: slot.kind,
        files_item_id: slot.files_item_id || null,
        folder_id: slot.folder_id || null,
        submission_id: slot.submission_id || null,
        require_new: !!slot.require_new,
      })),
    };
  }

  async function saveAutomation() {
    const payload = builderPayload();
    if (!payload.name) throw new Error('Name is required');
    let data;
    if (selectedId) {
      data = await api(`/bd/email-module/automations/${selectedId}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      });
    } else {
      data = await api('/bd/email-module/automations', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    }
    selectedId = data.item && data.item.id;
    showAlert($('autoAlert'), 'Automation saved.', 'success');
    await loadAutomations();
    return data.item;
  }

  async function loadHistory(id) {
    const box = $('autoHistory');
    if (!box) return;
    if (!id) {
      box.innerHTML = '<p class="helper">Save and run an automation to see send history here.</p>';
      return;
    }
    try {
      const data = await api(`/bd/email-module/automations/${id}/history`);
      const items = data.items || [];
      if (!items.length) {
        box.innerHTML = '<p class="helper">No runs yet.</p>';
        return;
      }
      box.innerHTML = items.map((row) => `
        <div class="history-item">
          <strong>${escapeHtml(row.status)}</strong>
          · ${escapeHtml(formatStamp(row.created_at))}
          <div class="helper">${escapeHtml(row.subject || '')} · ${row.attachment_count || 0} attachment(s)${row.error_message ? ' · ' + row.error_message : ''}</div>
        </div>
      `).join('');
    } catch (err) {
      box.innerHTML = `<p class="helper">${escapeHtml(err.message)}</p>`;
    }
  }

  async function loadCloudCatalog() {
    const data = await api('/bd/email-module/cloud-files');
    cloudCatalog = { items: data.items || [], folders: data.folders || [] };
  }

  function renderFilesPicker() {
    const list = $('filesPickerList');
    const foldersEl = $('filesPickerFolders');
    const q = (($('filesPickerSearch') && $('filesPickerSearch').value) || '').toLowerCase();
    if (foldersEl) {
      foldersEl.innerHTML = (cloudCatalog.folders || []).slice(0, 24).map((folder) => `
        <button type="button" class="btn btn-secondary files-folder-chip" data-folder-id="${folder.id}">${escapeHtml(folder.folder_path || folder.name)}</button>
      `).join('');
    }
    if (pickerKind === 'folder') {
      const folders = (cloudCatalog.folders || []).filter((f) => {
        const hay = `${f.name || ''} ${f.folder_path || ''}`.toLowerCase();
        return !q || hay.includes(q);
      });
      if (!folders.length) {
        list.innerHTML = '<div class="files-picker-empty">No matching folders.</div>';
        return;
      }
      list.innerHTML = folders.map((folder) => `
        <label class="files-picker-row">
          <input type="checkbox" data-folder-id="${folder.id}">
          <div>
            <strong>${escapeHtml(folder.name)}</strong>
            <div class="helper">${escapeHtml(folder.folder_path || '')}</div>
          </div>
          <span class="cloud-file-meta">folder</span>
        </label>
      `).join('');
      return;
    }
    const items = (cloudCatalog.items || []).filter((item) => {
      const hay = `${item.name || ''} ${item.filename || ''} ${item.folder_path || ''}`.toLowerCase();
      return !q || hay.includes(q);
    });
    if (!items.length) {
      list.innerHTML = '<div class="files-picker-empty">No matching files found.</div>';
      return;
    }
    list.innerHTML = items.map((item) => `
      <label class="files-picker-row">
        <input type="checkbox" data-item-id="${item.id}">
        <div>
          <strong>${escapeHtml(item.name)}</strong>
          <div class="helper">${escapeHtml(item.folder_path || '')} · ${escapeHtml(item.size_label || '')}</div>
        </div>
        <span class="cloud-file-meta">${escapeHtml(item.sync_status || 'local')}</span>
      </label>
    `).join('');
  }

  async function openFilesPicker(mode, kind) {
    pickerMode = mode;
    pickerKind = kind || 'file';
    $('filesPickerTitle').textContent = kind === 'folder' ? 'Use latest file in a folder' : 'Attach from Files';
    $('filesPickerModal').classList.add('active');
    $('filesPickerSearch').value = '';
    $('filesPickerList').innerHTML = '<div class="files-picker-empty">Loading files…</div>';
    try {
      await loadCloudCatalog();
      renderFilesPicker();
    } catch (err) {
      $('filesPickerList').innerHTML = `<div class="files-picker-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  function closeFilesPicker() {
    $('filesPickerModal').classList.remove('active');
  }

  function confirmFilesPicker() {
    if (pickerKind === 'folder') {
      const ids = Array.from(document.querySelectorAll('#filesPickerList input[data-folder-id]:checked'))
        .map((el) => Number(el.dataset.folderId));
      ids.forEach((folderId) => {
        const folder = (cloudCatalog.folders || []).find((f) => f.id === folderId);
        if (!folder) return;
        if (pickerMode === 'auto') {
          draftSlots.push({
            kind: 'folder_latest',
            folder_id: folder.id,
            folder_name: folder.name,
            require_new: true,
          });
        }
      });
      if (pickerMode === 'auto') renderSlots();
      closeFilesPicker();
      return;
    }
    const ids = Array.from(document.querySelectorAll('#filesPickerList input[data-item-id]:checked'))
      .map((el) => Number(el.dataset.itemId));
    const picked = (cloudCatalog.items || []).filter((item) => ids.includes(item.id));
    if (pickerMode === 'auto') {
      picked.forEach((item) => {
        if (draftSlots.some((s) => s.kind === 'linked_file' && s.files_item_id === item.id)) return;
        draftSlots.push({
          kind: 'linked_file',
          files_item_id: item.id,
          file_name: item.name,
          sync_status: item.sync_status,
          require_new: false,
        });
      });
      renderSlots();
    } else {
      picked.forEach((item) => {
        if (selectedCloudOnce.some((s) => s.id === item.id)) return;
        selectedCloudOnce.push(item);
      });
      renderOnceAttachments();
    }
    closeFilesPicker();
  }

  function renderOnceAttachments() {
    const box = $('attachmentsBox');
    if (!box) return;
    const formRows = selectedOnceIds.length
      ? selectedOnceIds.map((id) => `<div class="attachment-row"><strong>${escapeHtml(id)}</strong></div>`).join('')
      : '';
    const chips = selectedCloudOnce.map((item) => `
      <span class="cloud-file-chip">${escapeHtml(item.name)}
        <span class="cloud-file-meta">${escapeHtml(item.sync_status || 'local')}</span>
        <button type="button" data-remove-cloud="${item.id}">×</button>
      </span>
    `).join('');
    if (!formRows && !chips) {
      box.innerHTML = '<div class="helper">Select reviewed forms or attach files from the Files module.</div>';
      return;
    }
    box.innerHTML = `<div class="attachments-list">${formRows}<div>${chips}</div></div>`;
  }

  async function refreshOnceAttachmentPreview() {
    if (!selectedOnceIds.length) {
      renderOnceAttachments();
      return;
    }
    try {
      const data = await api(`/bd/email-module/attachments?ids=${encodeURIComponent(selectedOnceIds.join(','))}`);
      const items = data.items || [];
      const box = $('attachmentsBox');
      const rows = items.map((item) => {
        const links = [];
        if (item.pdf_url) links.push(`<a class="attachment-link" href="${escapeHtml(item.pdf_url)}" target="_blank" rel="noopener">PDF</a>`);
        if (item.excel_url) links.push(`<a class="attachment-link" href="${escapeHtml(item.excel_url)}" target="_blank" rel="noopener">Excel</a>`);
        return `<div class="attachment-row"><strong>${escapeHtml(item.submission_id)}</strong>${links.join(' ')}</div>`;
      }).join('');
      const chips = selectedCloudOnce.map((item) => `
        <span class="cloud-file-chip">${escapeHtml(item.name)}
          <span class="cloud-file-meta">${escapeHtml(item.sync_status || 'local')}</span>
          <button type="button" data-remove-cloud="${item.id}">×</button>
        </span>
      `).join('');
      box.innerHTML = `<div class="attachments-list">${rows || ''}<div>${chips}</div></div>`;
    } catch (err) {
      renderOnceAttachments();
    }
  }

  function openGroupModal(group) {
    $('groupModal').classList.add('active');
    $('groupModalTitle').textContent = group ? 'Edit Group' : 'Add Group';
    $('groupNameInput').value = group ? group.name : '';
    $('groupEmailsInput').value = group ? group.emails : '';
    $('groupScopeInput').value = group ? group.scope : currentScope();
    $('groupSaveBtn').dataset.groupId = group ? String(group.id) : '';
  }

  function closeGroupModal() {
    $('groupModal').classList.remove('active');
  }

  function filterOnceRows() {
    const q = (($('searchInput') && $('searchInput').value) || '').toLowerCase();
    const module = ($('moduleFilter') && $('moduleFilter').value) || '';
    const status = ($('statusFilter') && $('statusFilter').value) || '';
    document.querySelectorAll('#submissionTableBody .submission-row').forEach((row) => {
      const hay = `${row.dataset.site || ''} ${row.dataset.id || ''} ${row.dataset.module || ''} ${row.dataset.status || ''}`.toLowerCase();
      const matchQ = !q || hay.includes(q);
      const matchModule = !module || row.dataset.module === module;
      const matchStatus = !status || row.dataset.status === status;
      row.style.display = matchQ && matchModule && matchStatus ? '' : 'none';
    });
  }

  function bindOnceTable() {
    const tbody = $('submissionTableBody');
    if (!tbody) return;
    tbody.addEventListener('change', (ev) => {
      if (!ev.target.classList.contains('row-check')) return;
      const row = ev.target.closest('.submission-row');
      row.classList.toggle('row-selected', ev.target.checked);
    });
    $('selectAllRows') && $('selectAllRows').addEventListener('change', (ev) => {
      document.querySelectorAll('#submissionTableBody .submission-row').forEach((row) => {
        if (row.style.display === 'none') return;
        const check = row.querySelector('.row-check');
        if (!check) return;
        check.checked = ev.target.checked;
        row.classList.toggle('row-selected', ev.target.checked);
      });
    });
    $('addSelectedBtn') && $('addSelectedBtn').addEventListener('click', () => {
      const ids = Array.from(document.querySelectorAll('#submissionTableBody .row-check:checked'))
        .map((el) => el.closest('.submission-row').dataset.id)
        .filter(Boolean);
      selectedOnceIds = uniqueEmails(selectedOnceIds.concat(ids));
      $('selectedSubmissionIds').value = selectedOnceIds.join(',');
      if (ids.length && !$('onceSubject').value) {
        $('onceSubject').value = `Approval Update - ${ids[0]}`;
      }
      refreshOnceAttachmentPreview();
    });
    $('clearSelectedBtn') && $('clearSelectedBtn').addEventListener('click', () => {
      selectedOnceIds = [];
      $('selectedSubmissionIds').value = '';
      document.querySelectorAll('#submissionTableBody .row-check').forEach((el) => {
        el.checked = false;
        el.closest('.submission-row').classList.remove('row-selected');
      });
      refreshOnceAttachmentPreview();
    });
    ['searchInput', 'moduleFilter', 'statusFilter'].forEach((id) => {
      const el = $(id);
      if (el) el.addEventListener('input', filterOnceRows);
      if (el) el.addEventListener('change', filterOnceRows);
    });
  }

  function bindQuickAdds() {
    const map = [
      ['addAllGmBtn', 'onceTo', gmEmails],
      ['addAllBdBtn', 'onceTo', bdEmails],
      ['addAllPoBtn', 'onceTo', poEmails],
      ['addAllOmBtn', 'onceTo', omEmails],
      ['addAllSupervisorBtn', 'onceTo', supervisorEmails],
      ['addCcGmBtn', 'onceCc', gmEmails],
      ['addCcBdBtn', 'onceCc', bdEmails],
      ['addCcPoBtn', 'onceCc', poEmails],
      ['addCcOmBtn', 'onceCc', omEmails],
      ['addCcSupervisorBtn', 'onceCc', supervisorEmails],
      ['autoAddGmBtn', 'autoTo', gmEmails],
      ['autoAddBdBtn', 'autoTo', bdEmails],
      ['autoAddPoBtn', 'autoTo', poEmails],
      ['autoAddOmBtn', 'autoTo', omEmails],
      ['autoAddSupervisorBtn', 'autoTo', supervisorEmails],
      ['autoCcGmBtn', 'autoCc', gmEmails],
      ['autoCcBdBtn', 'autoCc', bdEmails],
      ['autoCcPoBtn', 'autoCc', poEmails],
      ['autoCcOmBtn', 'autoCc', omEmails],
      ['autoCcSupervisorBtn', 'autoCc', supervisorEmails],
    ];
    map.forEach(([btnId, fieldId, emails]) => {
      const btn = $(btnId);
      if (!btn) return;
      btn.addEventListener('click', () => addEmailsToField($(fieldId), emails));
    });
  }

  document.querySelectorAll('.sb-nav-item[data-tab]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      setTab(btn.dataset.tab);
    });
  });

  $('newAutoBtn') && $('newAutoBtn').addEventListener('click', () => {
    resetBuilder();
    closeSidebar();
  });
  $('autoList') && $('autoList').addEventListener('click', (ev) => {
    const card = ev.target.closest('.auto-card');
    if (!card) return;
    selectedId = Number(card.dataset.id);
    const auto = selectedAutomation();
    renderAutomationList();
    if (auto) fillBuilder(auto);
    closeSidebar();
  });

  $('scopePersonalBtn').addEventListener('click', () => {
    $('scopePersonalBtn').classList.add('active');
    $('scopePublicBtn').classList.remove('active');
  });
  $('scopePublicBtn').addEventListener('click', () => {
    $('scopePublicBtn').classList.add('active');
    $('scopePersonalBtn').classList.remove('active');
  });

  bindRecipientField($('autoTo'), $('autoToList'));
  bindRecipientField($('autoCc'), $('autoCcList'));
  bindRecipientField($('onceTo'), $('onceToList'));
  bindRecipientField($('onceCc'), $('onceCcList'));
  bindQuickAdds();
  bindOnceTable();

  $('autoSlots') && $('autoSlots').addEventListener('click', (ev) => {
    const btn = ev.target.closest('.slot-remove');
    if (!btn) return;
    draftSlots.splice(Number(btn.dataset.idx), 1);
    renderSlots();
  });
  $('autoSlots') && $('autoSlots').addEventListener('change', (ev) => {
    if (!ev.target.classList.contains('slot-require-new')) return;
    const idx = Number(ev.target.dataset.idx);
    if (draftSlots[idx]) draftSlots[idx].require_new = ev.target.checked;
  });

  $('attachAutoFilesBtn') && $('attachAutoFilesBtn').addEventListener('click', () => openFilesPicker('auto', 'file'));
  $('attachAutoFolderBtn') && $('attachAutoFolderBtn').addEventListener('click', () => openFilesPicker('auto', 'folder'));
  $('attachCloudFilesBtn') && $('attachCloudFilesBtn').addEventListener('click', () => openFilesPicker('once', 'file'));
  $('filesPickerCancelBtn').addEventListener('click', closeFilesPicker);
  $('filesPickerConfirmBtn').addEventListener('click', confirmFilesPicker);
  $('filesPickerSearch') && $('filesPickerSearch').addEventListener('input', renderFilesPicker);
  $('filesPickerFolders') && $('filesPickerFolders').addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-folder-id]');
    if (!btn) return;
    $('filesPickerSearch').value = (cloudCatalog.folders || []).find((f) => String(f.id) === String(btn.dataset.folderId))?.name || '';
    renderFilesPicker();
  });

  $('uploadAutoFile') && $('uploadAutoFile').addEventListener('change', async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    ev.target.value = '';
    if (!file) return;
    try {
      if (!selectedId) await saveAutomation();
      const body = new FormData();
      body.append('file', file);
      const data = await api(`/bd/email-module/automations/${selectedId}/attachments/upload`, {
        method: 'POST',
        headers: authHeaders(false),
        json: false,
        body,
      });
      selectedId = data.item.id;
      showAlert($('autoAlert'), 'File uploaded to Files and attached.', 'success');
      await loadAutomations();
    } catch (err) {
      showAlert($('autoAlert'), err.message, 'error');
    }
  });

  $('saveAutoBtn').addEventListener('click', async () => {
    try {
      await saveAutomation();
    } catch (err) {
      showAlert($('autoAlert'), err.message, 'error');
    }
  });

  $('runAutoBtn').addEventListener('click', async () => {
    try {
      if (!selectedId) await saveAutomation();
      else await saveAutomation();
      const data = await api(`/bd/email-module/automations/${selectedId}/run`, { method: 'POST', body: '{}' });
      showAlert($('autoAlert'), data.message || 'Ran automation.', data.skipped ? 'success' : 'success');
      await loadAutomations();
    } catch (err) {
      showAlert($('autoAlert'), err.message, 'error');
    }
  });

  $('deleteAutoBtn').addEventListener('click', async () => {
    if (!selectedId) return;
    if (!window.confirm('Delete this automation?')) return;
    try {
      await api(`/bd/email-module/automations/${selectedId}`, { method: 'DELETE' });
      selectedId = null;
      showAlert($('autoAlert'), 'Automation deleted.', 'success');
      await loadAutomations();
      resetBuilder();
    } catch (err) {
      showAlert($('autoAlert'), err.message, 'error');
    }
  });

  document.body.addEventListener('click', (ev) => {
    const addBtn = ev.target.closest('.group-add-btn');
    if (addBtn) {
      const group = groups.find((g) => String(g.id) === String(addBtn.dataset.groupId));
      if (!group) return;
      const field = addBtn.closest('.field').querySelector('input[type="text"], input:not([type])') || addBtn.closest('.field').querySelector('input');
      if (field) addEmailsToField(field, parseEmails(group.emails));
    }
    const editBtn = ev.target.closest('.group-edit-btn');
    if (editBtn) {
      const group = groups.find((g) => String(g.id) === String(editBtn.dataset.groupId));
      if (group) openGroupModal(group);
    }
    const removeBtn = ev.target.closest('.group-remove-btn');
    if (removeBtn) {
      const group = groups.find((g) => String(g.id) === String(removeBtn.dataset.groupId));
      if (!group) return;
      api(`/bd/email-module/groups/${group.id}`, { method: 'DELETE' })
        .then(loadGroups)
        .catch((err) => showAlert($('autoAlert'), err.message, 'error'));
    }
    const cloudRemove = ev.target.closest('[data-remove-cloud]');
    if (cloudRemove) {
      selectedCloudOnce = selectedCloudOnce.filter((item) => String(item.id) !== String(cloudRemove.dataset.removeCloud));
      refreshOnceAttachmentPreview();
    }
  });

  $('addToGroupBtn') && $('addToGroupBtn').addEventListener('click', () => openGroupModal(null));
  $('addCcGroupBtn') && $('addCcGroupBtn').addEventListener('click', () => openGroupModal(null));
  $('autoAddGroupBtn') && $('autoAddGroupBtn').addEventListener('click', () => openGroupModal(null));
  $('autoCcGroupBtn') && $('autoCcGroupBtn').addEventListener('click', () => openGroupModal(null));
  $('groupCancelBtn').addEventListener('click', closeGroupModal);
  $('groupSaveBtn').addEventListener('click', async () => {
    const payload = {
      name: $('groupNameInput').value.trim(),
      emails: $('groupEmailsInput').value,
      scope: $('groupScopeInput').value || currentScope(),
    };
    const id = $('groupSaveBtn').dataset.groupId;
    try {
      if (id) {
        await api(`/bd/email-module/groups/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
      } else {
        await api('/bd/email-module/groups', { method: 'POST', body: JSON.stringify(payload) });
      }
      closeGroupModal();
      await loadGroups();
    } catch (err) {
      showAlert($('autoAlert'), err.message, 'error');
    }
  });

  $('attachmentsBox') && $('attachmentsBox').addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-remove-cloud]');
    if (!btn) return;
    selectedCloudOnce = selectedCloudOnce.filter((item) => String(item.id) !== String(btn.dataset.removeCloud));
    refreshOnceAttachmentPreview();
  });

  $('emailForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      const data = await api('/bd/email-module/send', {
        method: 'POST',
        body: JSON.stringify({
          to: $('onceTo').value,
          cc: $('onceCc').value,
          subject: $('onceSubject').value,
          message: $('onceMessage').value,
          submission_ids: selectedOnceIds,
          file_item_ids: selectedCloudOnce.map((item) => item.id),
        }),
      });
      showAlert($('onceAlert'), data.message || 'Email sent successfully', 'success');
    } catch (err) {
      showAlert($('onceAlert'), err.message, 'error');
    }
  });

  $('clearOnceBtn') && $('clearOnceBtn').addEventListener('click', () => {
    $('emailForm').reset();
    selectedOnceIds = [];
    selectedCloudOnce = [];
    $('selectedSubmissionIds').value = '';
    renderChips($('onceToList'), $('onceTo'));
    renderChips($('onceCcList'), $('onceCc'));
    refreshOnceAttachmentPreview();
    $('onceAlert').innerHTML = '';
  });

  $('bdeSidebarToggle') && $('bdeSidebarToggle').addEventListener('click', toggleSidebar);
  $('bdeSidebarOverlay') && $('bdeSidebarOverlay').addEventListener('click', closeSidebar);

  resetBuilder();
  loadUser();
  loadGroups().catch(() => {});
  loadAutomations().catch((err) => showAlert($('autoAlert'), err.message, 'error'));
})();
