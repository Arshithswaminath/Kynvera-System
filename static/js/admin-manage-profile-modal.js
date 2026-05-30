/**
 * Shared “Manage profile” admin modal (identity, HR, role, modules, activity).
 * Used from Users & Teams; expects AdminManageProfileModal.configure({...}) first.
 */
(function (w) {
  'use strict';

  const DEFAULT_RESET_DISPLAY_PASSWORD = 'Injaaz@123';
  const ADMIN_PROFILE_LAYOUT_KEY = 'injaaz_admin_profile_layout';

  const CFG = {
    notify: function (msg, type, persist) {
      if (msg) window.alert(msg);
    },
    onUnauthorized: function () {
      return false;
    },
    getUsersDirectory: function () {
      return [];
    },
    reloadDirectory: async function () {},
  };

  let bindingsDone = false;
  let passwordResetConfirmContext = null;

  function fillProfilePasswordField(user) {
    const el = document.getElementById('profilePassword');
    const hint = document.getElementById('profilePasswordHint');
    if (!el) return;
    const stored = user && user.admin_visible_password ? String(user.admin_visible_password) : '';
    el.value = stored;
    el.placeholder = stored ? '' : 'No password on file for admin view';
    el.dataset.storedPassword = stored;
    el.type = 'password';
    const toggle = document.getElementById('profilePasswordToggle');
    if (toggle) toggle.textContent = 'Show';
    if (hint) {
      if (stored) {
        hint.textContent = 'Stored for admin reference. Edit and save to change.';
      } else if (user && user.password_changed) {
        hint.textContent =
          'This account already has a login password, but it was never saved for admin view (e.g. set before this feature or by the user). Use Reset password in Quick actions, or enter a new password here and save — you cannot recover the old one from the database.';
      } else {
        hint.textContent =
          'No password stored for admin view yet. Enter one and save, or use Reset password in Quick actions.';
      }
    }
  }

  function profilePasswordPayload() {
    const el = document.getElementById('profilePassword');
    if (!el) return {};
    const v = el.value.trim();
    const stored = (el.dataset.storedPassword || '').trim();
    if (v && v !== stored) return { password: v };
    return {};
  }

  function patchDirectoryUserPassword(userId, password) {
    const list = directoryUsers();
    const u = list.find(function (x) {
      return Number(x.id) === Number(userId);
    });
    if (u) u.admin_visible_password = password || '';
  }

  w.toggleProfilePasswordVisibility = function toggleProfilePasswordVisibility() {
    const el = document.getElementById('profilePassword');
    const btn = document.getElementById('profilePasswordToggle');
    if (!el || !btn) return;
    const show = el.type === 'password';
    el.type = show ? 'text' : 'password';
    btn.textContent = show ? 'Hide' : 'Show';
    btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
  };

  w.copyProfilePassword = function copyProfilePassword() {
    const el = document.getElementById('profilePassword');
    if (!el || !el.value.trim()) {
      notify('No password to copy', 'error');
      return;
    }
    const v = el.value;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(v).then(function () {
        notify('Password copied', 'success');
      }).catch(function () {
        el.select();
        document.execCommand('copy');
        notify('Password copied', 'success');
      });
    } else {
      el.type = 'text';
      el.select();
      document.execCommand('copy');
      el.type = 'password';
      notify('Password copied', 'success');
    }
  };

  /** @type {FileReader['_result']|''} */
  let profileSignatureDataUrl = '';

  async function refreshAccessToken() {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) return null;
    try {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + refreshToken,
        },
        credentials: 'include',
      });
      if (response.status === 401 || response.status === 422) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        return null;
      }
      const data = await response.json();
      if (data.access_token) {
        localStorage.setItem('access_token', data.access_token);
        return data.access_token;
      }
    } catch (_) { /* ignore */ }
    return null;
  }

  function getInitialAccessToken() {
    let accessToken = localStorage.getItem('access_token');
    if (!accessToken) {
      try {
        accessToken = JSON.parse(localStorage.getItem('user') || '{}').access_token || '';
      } catch (_) {
        accessToken = '';
      }
    }
    return accessToken || '';
  }

  async function profileAuthenticatedFetch(url, options = {}) {
    let accessToken = getInitialAccessToken();
    if (!accessToken) {
      return new Response(null, { status: 401 });
    }

    let response = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        Authorization: 'Bearer ' + accessToken,
      },
    });

    if (response.status !== 401) return response;

    const newToken = await refreshAccessToken();
    if (!newToken) return response;

    return fetch(url, {
      ...options,
      headers: {
        ...options.headers,
        Authorization: 'Bearer ' + newToken,
      },
    });
  }

  function handleUnauthorized(response) {
    if (!(response.status === 401 || response.status === 403)) return false;
    if (typeof CFG.onUnauthorized === 'function' && CFG.onUnauthorized(response)) return true;
    CFG.notify('Access denied. Please log in again.', 'error', true);
    setTimeout(() => {
      w.location.href = '/login';
    }, 900);
    return true;
  }

  function notify(msg, type = 'success', persistent = false) {
    CFG.notify(msg, type, persistent);
  }

  function directoryUsers() {
    const xs = CFG.getUsersDirectory();
    return Array.isArray(xs) ? xs : [];
  }

  function ensurePortalModal(modalEl) {
    if (modalEl && modalEl.parentElement !== document.body) {
      document.body.appendChild(modalEl);
    }
  }

  function activatePortalModal(modalEl) {
    if (!modalEl) return;
    ensurePortalModal(modalEl);
    modalEl.scrollTop = 0;
    modalEl.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _adminSelfUserId() {
    try {
      const raw = localStorage.getItem('user');
      const u = raw ? JSON.parse(raw) : null;
      return u && u.id != null ? Number(u.id) : null;
    } catch (_) {
      return null;
    }
  }

  w.clearProfileSignaturePreview = function clearProfileSignaturePreview() {
    profileSignatureDataUrl = '';
    const f = document.getElementById('profileSignatureFile');
    if (f) f.value = '';
    const img = document.getElementById('profileSignaturePreview');
    if (img) {
      img.src = '';
      img.hidden = true;
    }
  };

  function updateProfileSignaturePreview() {
    const img = document.getElementById('profileSignaturePreview');
    if (!img) return;
    if (profileSignatureDataUrl) {
      img.src = profileSignatureDataUrl;
      img.hidden = false;
    } else {
      img.src = '';
      img.hidden = true;
    }
  }

  /* ── Password reset ──────────────────────────────────────── */

  w.openPasswordResetConfirmModal = function openPasswordResetConfirmModal(userId, username) {
    passwordResetConfirmContext = { userId: userId, username: username };
    const modal = document.getElementById('passwordResetConfirmModal');
    if (!modal) return;
    const intro = document.getElementById('passwordResetConfirmIntro');
    if (intro) {
      intro.textContent = 'Reset the password for "' + (username || 'this user')
        + '"? The standard temporary password will be shown next.';
    }
    ensurePortalModal(modal);
    activatePortalModal(modal);
  };

  w.closePasswordResetConfirmModal = function closePasswordResetConfirmModal() {
    const modal = document.getElementById('passwordResetConfirmModal');
    if (modal) modal.classList.remove('active');
    passwordResetConfirmContext = null;
    const resOpen = document.getElementById('passwordResetResultModal');
    if (!resOpen || !resOpen.classList.contains('active')) {
      document.body.style.overflow = '';
    }
  };

  w.submitPasswordResetConfirm = async function submitPasswordResetConfirm() {
    const ctx = passwordResetConfirmContext;
    if (!ctx) return;
    const uid = ctx.userId;
    const username = ctx.username;
    closePasswordResetConfirmModal();
    await runAdminPasswordReset(uid, username);
  };

  async function runAdminPasswordReset(userId, username) {
    try {
      const response = await profileAuthenticatedFetch('/api/admin/users/' + userId + '/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (handleUnauthorized(response)) return;

      if (!response || typeof response.json !== 'function') {
        notify('Could not complete the request. Reload and try again.', 'error');
        return;
      }

      const data = await response.json();
      if (data.success) {
        const pw = data.temp_password || DEFAULT_RESET_DISPLAY_PASSWORD;
        patchDirectoryUserPassword(userId, pw);
        openPasswordResetResultModal(username, pw);
      } else {
        notify(data.error || 'Failed to reset password', 'error');
      }
    } catch (error) {
      console.error(error);
      notify('Error resetting password', 'error');
    }
  }

  w.openPasswordResetResultModal = function openPasswordResetResultModal(username, password) {
    const modal = document.getElementById('passwordResetResultModal');
    if (!modal) return;
    ensurePortalModal(modal);
    const intro = document.getElementById('passwordResetResultIntro');
    if (intro) {
      intro.textContent = 'The account password for "' + username + '" has been reset. Share the password below securely with the user.';
    }
    const inp = document.getElementById('passwordResetResultValue');
    if (inp) inp.value = password || '';
    activatePortalModal(modal);
  };

  w.closePasswordResetResultModal = function closePasswordResetResultModal() {
    const modal = document.getElementById('passwordResetResultModal');
    if (modal) modal.classList.remove('active');
    document.body.style.overflow = '';
  };

  w.copyPasswordResetResult = function copyPasswordResetResult() {
    const inp = document.getElementById('passwordResetResultValue');
    if (!inp || !inp.value) return;
    const val = inp.value;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(val).then(function () {
        notify('Password copied', 'success');
      }).catch(function () {
        inp.focus();
        inp.select();
      });
    } else {
      inp.focus();
      inp.select();
      try {
        document.execCommand('copy');
        notify('Password copied', 'success');
      } catch (_) { /* ignore */ }
    }
  };

  async function toggleUserActiveRemote(userId, currentStatus) {
    const action = currentStatus ? 'deactivate' : 'activate';
    if (!confirm('Are you sure you want to ' + action + ' this user?')) return;

    try {
      const response = await profileAuthenticatedFetch('/api/admin/users/' + userId + '/toggle-active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (handleUnauthorized(response)) return;
      const data = await response.json();
      if (data.success) {
        notify(data.message || 'Updated', 'success');
        await CFG.reloadDirectory();
      } else {
        notify(data.error || 'Failed', 'error');
      }
    } catch (e) {
      console.error(e);
      notify('Error updating status', 'error');
    }
  }

  w.profileModalResetPassword = function profileModalResetPassword() {
    const uid = parseInt(document.getElementById('profileUserId').value, 10);
    const u = directoryUsers().find(function (x) { return Number(x.id) === uid; });
    closeUserProfileModal();
    if (Number.isFinite(uid)) openPasswordResetConfirmModal(uid, u ? u.username : '');
  };

  w.profileModalViewActivity = function profileModalViewActivity() {
    const uid = parseInt(document.getElementById('profileUserId').value, 10);
    closeUserProfileModal();
    if (Number.isFinite(uid)) openUserActivityModal(uid);
  };

  w.profileModalToggleActive = async function profileModalToggleActive() {
    const uid = parseInt(document.getElementById('profileUserId').value, 10);
    const u = directoryUsers().find(function (x) { return Number(x.id) === uid; });
    if (!u || !Number.isFinite(uid)) return;
    closeUserProfileModal();
    await toggleUserActiveRemote(uid, u.is_active);
  };

  function getAdminProfileLayoutMode() {
    return localStorage.getItem(ADMIN_PROFILE_LAYOUT_KEY) || 'cards';
  }

  function applyAdminProfileLayout() {
    const modal = document.getElementById('accessModal');
    if (!modal) return;
    const isLine = getAdminProfileLayoutMode() === 'line';
    modal.classList.toggle('admin-profile-shell--v2', isLine);
    const btn = document.getElementById('adminProfileLayoutToggle');
    if (btn) {
      btn.textContent = isLine ? 'Cards' : 'Line';
      btn.setAttribute('aria-pressed', isLine ? 'true' : 'false');
    }
  }

  function toggleAdminProfileLayout() {
    const next = getAdminProfileLayoutMode() === 'line' ? 'cards' : 'line';
    localStorage.setItem(ADMIN_PROFILE_LAYOUT_KEY, next);
    applyAdminProfileLayout();
  }

  function fillReportingManagerDropdown(selectEl, excludeUserId) {
    const usersArr = directoryUsers();
    if (!selectEl || !usersArr.length) return;
    const ex = excludeUserId != null && excludeUserId !== ''
      ? parseInt(excludeUserId, 10)
      : null;
    selectEl.innerHTML = '';
    const o0 = document.createElement('option');
    o0.value = '';
    o0.textContent = '— None —';
    selectEl.appendChild(o0);
    usersArr.slice().sort(function (a, b) {
      const na = (a.full_name || a.username || '').toLowerCase();
      const nb = (b.full_name || b.username || '').toLowerCase();
      return na.localeCompare(nb);
    }).forEach(function (u) {
      const id = parseInt(u.id, 10);
      if (ex != null && !Number.isNaN(ex) && id === ex) return;
      const opt = document.createElement('option');
      opt.value = String(u.id);
      opt.textContent = (u.full_name || u.username || '') + ' — ' + (u.email || '');
      selectEl.appendChild(opt);
    });
  }

  w.openUserProfileModal = function openUserProfileModal(userId) {
    const uid = typeof userId === 'number' ? userId : parseInt(String(userId), 10);
    if (!Number.isFinite(uid)) return;
    const user = directoryUsers().find(function (u) {
      return Number(u.id) === Number(uid);
    });
    if (!user) return;

    const modal = document.getElementById('accessModal');
    if (!modal) return;
    ensurePortalModal(modal);
    applyAdminProfileLayout();

    document.getElementById('profileUserId').value = String(uid);
    const sub = document.getElementById('userProfileSubtitle');
    if (sub) sub.textContent = '@' + (user.username || '') + ' · ' + (user.email || '');

    const pill = document.getElementById('userProfileStatusPill');
    if (pill) {
      pill.textContent = user.is_active ? 'Active' : 'Inactive';
      pill.className = 'admin-profile-status-pill' +
        (user.is_active ? ' admin-profile-status-pill--on' : ' admin-profile-status-pill--off');
    }

    document.getElementById('profileFullName').value = user.full_name || '';
    document.getElementById('profileEmail').value = user.email || '';
    document.getElementById('profileUsername').value = user.username || '';
    fillProfilePasswordField(user);
    const jdEl = document.getElementById('profileJobDesignation');
    if (jdEl) jdEl.value = user.job_designation || '';
    const alEl = document.getElementById('profileAnnualLeaveDays');
    if (alEl) {
      alEl.value = user.annual_leave_days != null && user.annual_leave_days !== ''
        ? String(user.annual_leave_days)
        : '';
    }
    const olEl = document.getElementById('profileOtherLeaveDays');
    if (olEl) {
      olEl.value = user.other_leave_days != null && user.other_leave_days !== ''
        ? String(user.other_leave_days)
        : '';
    }

    document.getElementById('profileRole').value = user.role === 'admin' ? 'admin' : 'user';
    document.getElementById('profileDesignation').value = user.designation || '';

    const rmSel = document.getElementById('profileReportingManager');
    if (rmSel) {
      fillReportingManagerDropdown(rmSel, uid);
      rmSel.value = user.reporting_manager_id ? String(user.reporting_manager_id) : '';
    }

    const esdEl = document.getElementById('profileEmploymentStartDate');
    if (esdEl) {
      esdEl.value = user.employment_start_date ? String(user.employment_start_date).slice(0, 10) : '';
    }

    const selfId = _adminSelfUserId();
    const roleEl = document.getElementById('profileRole');
    const roleHint = document.getElementById('profileRoleHint');
    if (Number(uid) === Number(selfId) && user.role === 'admin') {
      roleEl.disabled = true;
      if (roleHint) roleHint.textContent = 'You cannot lower your own administrator role from here.';
    } else {
      roleEl.disabled = false;
      if (roleHint) roleHint.textContent = '';
    }

    const isAdminTarget = user.role === 'admin';
    const modNote = document.getElementById('profileModuleNote');
    const modWrap = document.getElementById('profileModuleAccess');
    if (modNote && modWrap) {
      if (isAdminTarget) {
        modNote.hidden = false;
        modNote.textContent = 'Administrators have full access to all modules by policy.';
        ['accessHvac', 'accessCivil', 'accessCleaning', 'accessHr', 'accessProcurement', 'accessBusinessDev', 'accessDocHub', 'accessReportGen', 'accessSubmittedForms', 'accessTicketing'].forEach(function (id) {
          const cb = document.getElementById(id);
          if (cb) {
            cb.checked = true;
            cb.disabled = true;
          }
        });
      } else {
        modNote.hidden = true;
        modNote.textContent = '';
        document.getElementById('accessHvac').checked = !!user.access_hvac;
        document.getElementById('accessCivil').checked = !!user.access_civil;
        document.getElementById('accessCleaning').checked = !!user.access_cleaning;
        document.getElementById('accessHr').checked = !!user.access_hr;
        document.getElementById('accessProcurement').checked = !!user.access_procurement_module;
        const bd = document.getElementById('accessBusinessDev');
        if (bd) bd.checked = !!user.access_business_development;
        const dh = document.getElementById('accessDocHub');
        if (dh) dh.checked = user.can_access_dochub !== false;
        const rg = document.getElementById('accessReportGen');
        if (rg) rg.checked = !!user.access_report_generation;
        const sf = document.getElementById('accessSubmittedForms');
        if (sf) sf.checked = !!user.access_submitted_forms;
        const tkt = document.getElementById('accessTicketing');
        if (tkt) tkt.checked = !!user.access_ticketing;
        modWrap.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
          cb.disabled = false;
        });
      }
    }

    document.getElementById('profileDefaultComment').value = user.default_comment || '';
    profileSignatureDataUrl = user.default_signature || '';
    const sigFileEl = document.getElementById('profileSignatureFile');
    if (sigFileEl) sigFileEl.value = '';
    updateProfileSignaturePreview();

    const tbtn = document.getElementById('profileQuickToggleBtn');
    if (tbtn) tbtn.textContent = user.is_active ? 'Deactivate account' : 'Activate account';

    activatePortalModal(modal);
  };

  w.openAccessModal = w.openUserProfileModal;

  w.closeUserProfileModal = function closeUserProfileModal() {
    const modal = document.getElementById('accessModal');
    if (modal) modal.classList.remove('active');
    const pr = document.getElementById('passwordResetResultModal');
    const pc = document.getElementById('passwordResetConfirmModal');
    const pu = pr && pr.classList.contains('active');
    const pcc = pc && pc.classList.contains('active');
    if (!pu && !pcc) document.body.style.overflow = '';
  };

  /* ── Activity modal ───────────────────────────────────────── */

  function getFormViewUrl(moduleType, submissionId) {
    if (moduleType === 'hvac_mep') {
      return '/hvac-mep/form?edit=' + encodeURIComponent(submissionId) + '&review=true';
    }
    if (moduleType === 'civil') {
      return '/civil/form?edit=' + encodeURIComponent(submissionId) + '&review=true';
    }
    if (moduleType === 'cleaning') {
      return '/cleaning/form?edit=' + encodeURIComponent(submissionId) + '&review=true';
    }
    return '#';
  }

  w.viewFormFromActivity = function viewFormFromActivity(moduleType, submissionId) {
    const url = getFormViewUrl(moduleType, submissionId);
    if (url !== '#') window.location.href = url;
  };

  function renderUserActivity(data, container, titleEl) {
    const user = data.user;
    const submitted = data.submitted_forms || [];
    const reviewed = data.reviewed_forms || [];

    const initials = user.full_name
      ? user.full_name.split(' ').map(function (n) { return n[0]; }).join('').toUpperCase().slice(0, 2)
      : user.username.slice(0, 2).toUpperCase();

    const designationMap = {
      supervisor: 'Supervisor',
      operations_manager: 'Operations Manager',
      business_development: 'Business Development',
      procurement: 'Procurement',
      general_manager: 'General Manager',
      hr_manager: 'HR Manager',
      employee: 'Employee',
      technician: 'Technician',
      admin: 'Admin',
    };
    const designation = designationMap[user.designation] || user.designation || 'Not assigned';

    titleEl.textContent = 'Activity: ' + (user.full_name || user.username);

    let html =
      '<div class="user-info-card">' +
        '<div class="user-info-avatar">' + initials + '</div>' +
        '<div class="user-info-details">' +
          '<h3>' + escapeHtml(user.full_name || user.username) + '</h3>' +
          '<p>' + escapeHtml(designation) + ' • ' + escapeHtml(user.role) + '</p>' +
        '</div>' +
        '<div class="user-stats">' +
          '<div class="user-stat"><div class="user-stat-value">' + String(data.submitted_count) + '</div><div class="user-stat-label">Submitted</div></div>' +
          '<div class="user-stat"><div class="user-stat-value">' + String(data.reviewed_count) + '</div><div class="user-stat-label">Reviewed</div></div>' +
        '</div>' +
      '</div>';

    html +=
      '<div class="activity-section">' +
      '<div class="activity-section-header"><div class="activity-section-title">📄 Forms Submitted<span class="activity-badge">' + String(submitted.length) + '</span></div></div>';

    if (submitted.length > 0) {
      html += '<table class="activity-table"><thead><tr><th>ID</th><th>Module</th><th>Site Name</th><th>Visit Date</th><th>Status</th><th>Created</th><th>Action</th></tr></thead><tbody>';
      submitted.forEach(function (form) {
        const moduleClass = form.module_type === 'hvac_mep' ? 'hvac' : form.module_type === 'civil' ? 'civil' : 'cleaning';
        const moduleLabel = form.module_type === 'hvac_mep' ? 'HVAC' : form.module_type === 'civil' ? 'Civil' : 'Cleaning';
        const statusClass = form.workflow_status === 'completed' ? 'completed' : form.workflow_status === 'rejected' ? 'rejected' : 'pending';
        const created = form.created_at ? new Date(form.created_at).toLocaleDateString() : '-';
        html +=
          '<tr class="clickable-row" onclick="viewFormFromActivity(\'' + form.module_type + '\',\'' + String(form.submission_id).replace(/'/g, "\\'") + '\')">' +
          '<td><code style="font-size: 0.75rem;">' + escapeHtml(form.submission_id) + '</code></td>' +
          '<td><span class="module-badge-sm ' + moduleClass + '">' + moduleLabel + '</span></td>' +
          '<td>' + escapeHtml(form.site_name) + '</td>' +
          '<td>' + escapeHtml(form.visit_date || '-') + '</td>' +
          '<td><span class="status-badge ' + statusClass + '">' + escapeHtml(form.workflow_status) + '</span></td>' +
          '<td>' + escapeHtml(created) + '</td>' +
          '<td><button class="btn-view-form" type="button" onclick="event.stopPropagation(); viewFormFromActivity(\''
          + form.module_type + '\',\''
          + String(form.submission_id).replace(/'/g, "\\'") + '\')" title="View Form">' +
          '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>' +
          '</button></td></tr>';
      });
      html += '</tbody></table>';
    } else {
      html +=
        '<div class="empty-state"><div class="empty-state-icon">📋</div><p>No forms submitted yet</p></div>';
    }
    html += '</div>';

    html +=
      '<div class="activity-section">' +
      '<div class="activity-section-header"><div class="activity-section-title">✅ Forms Reviewed<span class="activity-badge reviewed">' + String(reviewed.length) + '</span></div></div>';
    if (reviewed.length > 0) {
      html +=
        '<table class="activity-table"><thead><tr><th>ID</th><th>Module</th><th>Site Name</th><th>Submitted By</th><th>Status</th><th>Date</th><th>Action</th></tr></thead><tbody>';
      reviewed.forEach(function (form) {
        const moduleClass = form.module_type === 'hvac_mep' ? 'hvac' : form.module_type === 'civil' ? 'civil' : 'cleaning';
        const moduleLabel = form.module_type === 'hvac_mep' ? 'HVAC' : form.module_type === 'civil' ? 'Civil' : 'Cleaning';
        const statusClass = form.workflow_status === 'completed' ? 'completed' : form.workflow_status === 'rejected' ? 'rejected' : 'pending';
        const created = form.created_at ? new Date(form.created_at).toLocaleDateString() : '-';
        html +=
          '<tr class="clickable-row" onclick="viewFormFromActivity(\''
          + form.module_type + '\',\''
          + String(form.submission_id).replace(/'/g, "\\'") + '\')">' +
          '<td><code style="font-size: 0.75rem;">' + escapeHtml(form.submission_id) + '</code></td>' +
          '<td><span class="module-badge-sm ' + moduleClass + '">' + moduleLabel + '</span></td>' +
          '<td>' + escapeHtml(form.site_name) + '</td>' +
          '<td>' + escapeHtml(form.supervisor || '-') + '</td>' +
          '<td><span class="status-badge ' + statusClass + '">' + escapeHtml(form.workflow_status) + '</span></td>' +
          '<td>' + escapeHtml(created) + '</td>' +
          '<td><button class="btn-view-form" type="button" onclick="event.stopPropagation(); viewFormFromActivity(\''
          + form.module_type + '\',\''
          + String(form.submission_id).replace(/'/g, "\\'") + '\')" title="View Form">' +
          '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>' +
          '</button></td></tr>';
      });
      html += '</tbody></table>';
    } else {
      html +=
        '<div class="empty-state"><div class="empty-state-icon">✓</div><p>No forms reviewed yet</p></div>';
    }
    html += '</div>';

    container.innerHTML = html;
  }

  async function openUserActivityModal(userId) {
    const modal = document.getElementById('userActivityModal');
    const content = document.getElementById('userActivityContent');
    const title = document.getElementById('userActivityTitle');

    content.innerHTML =
      '<div style="text-align: center; padding: 2rem;"><div class="spinner" style="border: 3px solid #f3f3f3; border-top: 3px solid var(--primary); border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto;"></div>'
      + '<p style="margin-top: 1rem; color: #666;">Loading user activity...</p></div>';
    activatePortalModal(modal);

    try {
      const response = await profileAuthenticatedFetch('/api/admin/users/' + userId + '/activity');
      if (handleUnauthorized(response)) return;
      const data = await response.json();
      if (data.success) {
        renderUserActivity(data, content, title);
      } else {
        content.innerHTML = '<div style="text-align: center; padding: 2rem; color: #dc2626;">Failed to load activity</div>';
      }
    } catch (e) {
      console.error(e);
      content.innerHTML = '<div style="text-align: center; padding: 2rem; color: #dc2626;">Error loading activity</div>';
    }
  }

  w.closeUserActivityModal = function closeUserActivityModal() {
    const modal = document.getElementById('userActivityModal');
    if (modal) modal.classList.remove('active');
  };

  function bindOnce() {
    if (bindingsDone) return;
    bindingsDone = true;

    applyAdminProfileLayout();

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      const res = document.getElementById('passwordResetResultModal');
      const conf = document.getElementById('passwordResetConfirmModal');
      const prof = document.getElementById('accessModal');
      const act = document.getElementById('userActivityModal');
      if (res && res.classList.contains('active')) {
        closePasswordResetResultModal();
      } else if (conf && conf.classList.contains('active')) {
        closePasswordResetConfirmModal();
      } else if (prof && prof.classList.contains('active')) {
        closeUserProfileModal();
      } else if (act && act.classList.contains('active')) {
        closeUserActivityModal();
      }
    });

    const userActivityModal = document.getElementById('userActivityModal');
    if (userActivityModal && !userActivityModal.dataset.overlayBound) {
      userActivityModal.dataset.overlayBound = '1';
      userActivityModal.addEventListener('click', function (e) {
        if (e.target.id === 'userActivityModal') closeUserActivityModal();
      });
    }

    const accessModal = document.getElementById('accessModal');
    if (accessModal && !accessModal.dataset.overlayDupBound) {
      accessModal.dataset.overlayDupBound = '1';
      accessModal.addEventListener('click', function (e) {
        if (e.target.id === 'accessModal') closeUserProfileModal();
      });
    }

    const formEl = document.getElementById('userProfileForm');
    if (formEl && !formEl.dataset.bound) {
      formEl.dataset.bound = '1';
      formEl.addEventListener('submit', async function (ev) {
        ev.preventDefault();
        const userId = document.getElementById('profileUserId').value;
        if (!userId) return;

        const des = document.getElementById('profileDesignation').value;
        /** @type {Record<string, unknown>} */
        const payload = {
          full_name: document.getElementById('profileFullName').value.trim(),
          email: document.getElementById('profileEmail').value.trim(),
          username: document.getElementById('profileUsername').value.trim(),
          role: document.getElementById('profileRole').value,
          designation: des || null,
          default_comment: document.getElementById('profileDefaultComment').value.trim() || null,
          default_signature: profileSignatureDataUrl || null,
          employment_start_date:
            document.getElementById('profileEmploymentStartDate') &&
            document.getElementById('profileEmploymentStartDate').value.trim()
              ? document.getElementById('profileEmploymentStartDate').value.trim()
              : '',
          job_designation:
            document.getElementById('profileJobDesignation')
              ? document.getElementById('profileJobDesignation').value.trim()
              : '',
          annual_leave_days:
            document.getElementById('profileAnnualLeaveDays')
              ? document.getElementById('profileAnnualLeaveDays').value.trim()
              : '',
          other_leave_days:
            document.getElementById('profileOtherLeaveDays')
              ? document.getElementById('profileOtherLeaveDays').value.trim()
              : '',
        };
        Object.assign(payload, profilePasswordPayload());
        const prm = document.getElementById('profileReportingManager');
        if (prm) {
          if (!prm.value) payload.reporting_manager_id = null;
          else {
            const mid = parseInt(prm.value, 10);
            payload.reporting_manager_id = Number.isNaN(mid) ? null : mid;
          }
        }

        const u = directoryUsers().find(function (x) {
          return String(x.id) === String(userId);
        });
        if (u && u.role !== 'admin') {
          payload.access_hvac = document.getElementById('accessHvac').checked;
          payload.access_civil = document.getElementById('accessCivil').checked;
          payload.access_cleaning = document.getElementById('accessCleaning').checked;
          payload.access_hr = document.getElementById('accessHr').checked;
          payload.access_procurement_module = document.getElementById('accessProcurement').checked;
          payload.access_business_development = document.getElementById('accessBusinessDev').checked;
          payload.access_report_generation = document.getElementById('accessReportGen').checked;
          payload.access_submitted_forms = document.getElementById('accessSubmittedForms').checked;
          const tgx = document.getElementById('accessTicketing');
          payload.access_ticketing = !!(tgx && tgx.checked);
        }

        try {
          const response = await profileAuthenticatedFetch('/api/admin/users/' + userId, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (handleUnauthorized(response)) return;
          const data = await response.json();
          const roleIsAdmin = document.getElementById('profileRole').value === 'admin';
          const okPut = response.ok && data.success;
          if (okPut) {
            if (data.user && data.user.admin_visible_password != null) {
              patchDirectoryUserPassword(userId, data.user.admin_visible_password);
            } else if (payload.password) {
              patchDirectoryUserPassword(userId, payload.password);
            }
            if (!roleIsAdmin) {
              const dhub = document.getElementById('accessDocHub');
              const dhRes = await profileAuthenticatedFetch('/api/admin/dochub/access-users/' + userId, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ can_access: dhub ? dhub.checked : true }),
              });
              if (handleUnauthorized(dhRes)) return;
              const dhData = await dhRes.json().catch(function () { return {}; });
              if (!dhRes.ok || !dhData.success) {
                notify(
                  (dhData && dhData.message) || (dhData && dhData.error)
                    ? String(dhData.message || dhData.error)
                    : 'Saved profile, but Document hub access could not be updated',
                  'error',
                  true,
                );
                closeUserProfileModal();
                await CFG.reloadDirectory();
                return;
              }
            }
            notify(data.message || 'Profile saved successfully', 'success');
            closeUserProfileModal();
            await CFG.reloadDirectory();
          } else {
            notify((data && (data.error || data.message)) || 'Failed to save profile', 'error');
          }
        } catch (err) {
          console.error(err);
          notify('Error saving profile', 'error');
        }
      });
    }

    try {
      const pwToggle = document.getElementById('profilePasswordToggle');
      if (pwToggle && !pwToggle.dataset.bound) {
        pwToggle.dataset.bound = '1';
        pwToggle.addEventListener('click', w.toggleProfilePasswordVisibility);
      }
      const pwCopy = document.getElementById('profilePasswordCopy');
      if (pwCopy && !pwCopy.dataset.bound) {
        pwCopy.dataset.bound = '1';
        pwCopy.addEventListener('click', w.copyProfilePassword);
      }
    } catch (_) { /* ignore */ }

    try {
      const lt = document.getElementById('adminProfileLayoutToggle');
      if (lt && !lt.dataset.layoutBound) {
        lt.dataset.layoutBound = '1';
        lt.addEventListener('click', toggleAdminProfileLayout);
      }
    } catch (_) { /* ignore */ }

    try {
      const sigFile = document.getElementById('profileSignatureFile');
      if (sigFile && !sigFile.dataset.bound) {
        sigFile.dataset.bound = '1';
        sigFile.addEventListener('change', function () {
          const f = sigFile.files && sigFile.files[0];
          if (!f) return;
          if (f.size > 400 * 1024) {
            notify('Signature image must be under 400KB.', 'error');
            sigFile.value = '';
            return;
          }
          const reader = new FileReader();
          reader.onload = function () {
            profileSignatureDataUrl = reader.result || '';
            updateProfileSignaturePreview();
          };
          reader.readAsDataURL(f);
        });
      }
    } catch (_) { /* ignore */ }

    try {
      ensurePortalModal(document.getElementById('passwordResetConfirmModal'));
      ensurePortalModal(document.getElementById('passwordResetResultModal'));
      ensurePortalModal(document.getElementById('accessModal'));
    } catch (_) { /* ignore */ }
  }

  w.openUserActivityModal = openUserActivityModal;

  w.AdminManageProfileModal = {
    configure: function (opts) {
      if (!opts || typeof opts !== 'object') return;
      if (opts.notify) CFG.notify = opts.notify;
      if (opts.onUnauthorized) CFG.onUnauthorized = opts.onUnauthorized;
      if (opts.getUsersDirectory) CFG.getUsersDirectory = opts.getUsersDirectory;
      if (opts.reloadDirectory) CFG.reloadDirectory = opts.reloadDirectory;
      bindOnce();
    },
    init: bindOnce,
  };
})(typeof window !== 'undefined' ? window : globalThis);
