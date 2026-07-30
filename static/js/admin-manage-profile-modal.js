/**
 * Shared “Manage profile” admin modal (identity, HR, role, modules, activity).
 * Used from Users & Teams; expects AdminManageProfileModal.configure({...}) first.
 */
(function (w) {
  'use strict';

  const DEFAULT_RESET_DISPLAY_PASSWORD = 'Injaaz@123';
  const PROTECT_UNLOCK_STORAGE_KEY = 'adminProtectUnlock';
  const PROTECT_UNLOCK_HEADER = 'X-Admin-Protect-Unlock';
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

  /** Session unlock token for editing protected admin accounts (30 min). */
  const AdminProtectUnlock = {
    STORAGE_KEY: PROTECT_UNLOCK_STORAGE_KEY,
    HEADER: PROTECT_UNLOCK_HEADER,
    get: function () {
      try {
        const raw = sessionStorage.getItem(PROTECT_UNLOCK_STORAGE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || !parsed.token || !parsed.expiresAt) return null;
        if (Date.now() >= Number(parsed.expiresAt)) {
          sessionStorage.removeItem(PROTECT_UNLOCK_STORAGE_KEY);
          return null;
        }
        return parsed;
      } catch (_) {
        return null;
      }
    },
    isValid: function () {
      return !!AdminProtectUnlock.get();
    },
    save: function (token, expiresInSeconds) {
      const exp = Date.now() + Math.max(0, Number(expiresInSeconds) || 0) * 1000;
      sessionStorage.setItem(
        PROTECT_UNLOCK_STORAGE_KEY,
        JSON.stringify({ token: String(token), expiresAt: exp }),
      );
    },
    clear: function () {
      try {
        sessionStorage.removeItem(PROTECT_UNLOCK_STORAGE_KEY);
      } catch (_) { /* ignore */ }
    },
    headerValue: function () {
      const u = AdminProtectUnlock.get();
      return u ? u.token : '';
    },
  };
  w.AdminProtectUnlock = AdminProtectUnlock;

  function relockAdminProtect() {
    AdminProtectUnlock.clear();
    // Refresh staff badges immediately (Cancel / Save / Esc / backdrop).
    if (typeof CFG.onProtectRelock === 'function') {
      try {
        CFG.onProtectRelock();
      } catch (_) { /* ignore */ }
    }
  }
  w.relockAdminProtect = relockAdminProtect;

  let bindingsDone = false;
  let passwordResetConfirmContext = null;
  let accountActionConfirmContext = null;

  function setProfileQuickToggleButton(tbtn, isActive) {
    if (!tbtn) return;
    const label = tbtn.querySelector('.admin-quick-action-label');
    const text = isActive ? 'Deactivate account' : 'Activate account';
    if (label) label.textContent = text;
    else tbtn.textContent = text;
    tbtn.classList.toggle('is-deactivate', !!isActive);
    tbtn.classList.toggle('is-activate', !isActive);
  }

  function paintProfilePasswordField(user, stored) {
    const el = document.getElementById('profilePassword');
    const hint = document.getElementById('profilePasswordHint');
    if (!el) return;
    stored = stored ? String(stored) : '';
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

  // The bulk /users directory list no longer ships every user's admin-visible
  // password. Reveal the single user's stored password on demand from the
  // admin single-user endpoint when the modal opens. Falls back gracefully to
  // any value already cached on the directory object (e.g. just after a reset).
  async function fillProfilePasswordField(user) {
    const cached = user && user.admin_visible_password ? String(user.admin_visible_password) : '';
    paintProfilePasswordField(user, cached);
    if (cached || !user || user.id == null) return;
    try {
      const resp = await profileAuthenticatedFetch('/api/admin/users/' + user.id);
      if (!resp || !resp.ok) return;
      const data = await resp.json();
      const fresh = data && data.user ? data.user.admin_visible_password : '';
      if (fresh) {
        patchDirectoryUserPassword(user.id, fresh);
        // Only repaint if the admin hasn't started typing a new password.
        const el = document.getElementById('profilePassword');
        if (el && !el.value) paintProfilePasswordField(user, fresh);
      }
    } catch (e) {
      /* leave the "no password on file" state; admin can still reset */
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

  function withAuthHeaders(options, accessToken) {
    const headers = Object.assign({}, options.headers || {}, {
      Authorization: 'Bearer ' + accessToken,
    });
    const unlock = AdminProtectUnlock.headerValue();
    if (unlock) headers[PROTECT_UNLOCK_HEADER] = unlock;
    return Object.assign({}, options, { headers: headers });
  }

  async function profileAuthenticatedFetch(url, options = {}) {
    let accessToken = getInitialAccessToken();
    if (!accessToken) {
      return new Response(null, { status: 401 });
    }

    let response = await fetch(url, withAuthHeaders(options, accessToken));

    if (response.status !== 401) return response;

    const newToken = await refreshAccessToken();
    if (!newToken) return response;

    return fetch(url, withAuthHeaders(options, newToken));
  }

  function handleUnauthorized(response) {
    // Only force re-login on auth failure; business 403s (e.g. PROTECTED_ACCOUNT) are handled by callers.
    if (response.status !== 401) return false;
    if (typeof CFG.onUnauthorized === 'function' && CFG.onUnauthorized(response)) return true;
    CFG.notify('Access denied. Please log in again.', 'error', true);
    setTimeout(() => {
      w.location.href = '/login';
    }, 900);
    return true;
  }

  function notifyProtectedAccountError(data) {
    if (data && data.error_code === 'PROTECTED_ACCOUNT') {
      relockAdminProtect();
      notify(
        (data && (data.error || data.message)) ||
          'Admin protect unlock expired. Enter your PIN again.',
        'error',
        true,
      );
      return true;
    }
    return false;
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

  w.closePasswordResetConfirmModal = function closePasswordResetConfirmModal(opts) {
    opts = opts || {};
    const modal = document.getElementById('passwordResetConfirmModal');
    if (modal) modal.classList.remove('active');
    passwordResetConfirmContext = null;
    const resOpen = document.getElementById('passwordResetResultModal');
    if (!resOpen || !resOpen.classList.contains('active')) {
      document.body.style.overflow = '';
    }
    if (!opts.keepUnlock) relockAdminProtect();
  };

  w.submitPasswordResetConfirm = async function submitPasswordResetConfirm() {
    const ctx = passwordResetConfirmContext;
    if (!ctx) return;
    const uid = ctx.userId;
    const username = ctx.username;
    closePasswordResetConfirmModal({ keepUnlock: true });
    await runAdminPasswordReset(uid, username);
    const res = document.getElementById('passwordResetResultModal');
    if (!res || !res.classList.contains('active')) relockAdminProtect();
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
      } else if (!notifyProtectedAccountError(data)) {
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
    relockAdminProtect();
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

  w.openAccountActionConfirmModal = function openAccountActionConfirmModal(opts) {
    opts = opts || {};
    accountActionConfirmContext = {
      action: opts.action,
      userId: opts.userId,
      username: opts.username || '',
      fullName: opts.fullName || '',
      currentStatus: opts.currentStatus,
    };
    const modal = document.getElementById('accountActionConfirmModal');
    if (!modal) return;
    const title = document.getElementById('accountActionConfirmTitle');
    const intro = document.getElementById('accountActionConfirmIntro');
    const note = document.getElementById('accountActionConfirmNote');
    const btn = document.getElementById('accountActionConfirmBtn');
    const label = opts.fullName || opts.username || 'this user';
    const userIdLabel = opts.username || String(opts.userId || '');
    const action = opts.action;

    if (note) {
      note.hidden = true;
      note.textContent = '';
    }

    if (action === 'delete') {
      if (title) title.textContent = 'Delete account?';
      if (intro) {
        intro.textContent =
          'Permanently delete ' + label + (userIdLabel ? ' (' + userIdLabel + ')' : '') + '?';
      }
      if (note) {
        note.hidden = false;
        note.textContent = 'This cannot be undone.';
      }
      if (btn) {
        btn.textContent = 'Delete account';
        btn.className = 'btn btn-account-danger';
      }
    } else if (action === 'deactivate') {
      if (title) title.textContent = 'Deactivate account?';
      if (intro) {
        intro.textContent = 'Deactivate ' + label + '? They will not be able to sign in until reactivated.';
      }
      if (btn) {
        btn.textContent = 'Deactivate';
        btn.className = 'btn btn-account-danger';
      }
    } else if (action === 'unlock') {
      if (title) title.textContent = 'Unlock password?';
      if (intro) {
        intro.textContent = 'Unlock ' + label + ' and issue a new temporary password?';
      }
      if (btn) {
        btn.textContent = 'Unlock password';
        btn.className = 'btn btn-reset';
      }
    } else {
      if (title) title.textContent = 'Activate account?';
      if (intro) {
        intro.textContent = 'Activate ' + label + ' so they can sign in again?';
      }
      if (btn) {
        btn.textContent = 'Activate';
        btn.className = 'btn btn-account-activate';
      }
    }
    ensurePortalModal(modal);
    activatePortalModal(modal);
  };

  w.closeAccountActionConfirmModal = function closeAccountActionConfirmModal(opts) {
    opts = opts || {};
    const modal = document.getElementById('accountActionConfirmModal');
    if (modal) modal.classList.remove('active');
    accountActionConfirmContext = null;
    const otherOpen =
      (document.getElementById('passwordResetResultModal') || {}).classList &&
      document.getElementById('passwordResetResultModal').classList.contains('active');
    if (!otherOpen) document.body.style.overflow = '';
    if (!opts.keepUnlock) relockAdminProtect();
  };

  async function runToggleUserActive(userId) {
    try {
      const response = await profileAuthenticatedFetch('/api/admin/users/' + userId + '/toggle-active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (handleUnauthorized(response)) {
        relockAdminProtect();
        return;
      }
      const data = await response.json();
      if (data.success) {
        notify(data.message || 'Updated', 'success');
        await CFG.reloadDirectory();
      } else if (!notifyProtectedAccountError(data)) {
        notify(data.error || 'Failed', 'error');
      }
    } catch (e) {
      console.error(e);
      notify('Error updating status', 'error');
    } finally {
      relockAdminProtect();
    }
  }

  async function runDeleteUser(userId, username) {
    try {
      let currentUserId = null;
      try {
        const raw = localStorage.getItem('user');
        if (raw) currentUserId = JSON.parse(raw).id;
      } catch (_) { /* ignore */ }
      if (Number(userId) === Number(currentUserId)) {
        notify('You cannot delete your own account', 'error');
        relockAdminProtect();
        return;
      }
      const response = await profileAuthenticatedFetch('/api/admin/users/' + userId, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
      });
      if (handleUnauthorized(response)) {
        relockAdminProtect();
        return;
      }
      const data = await response.json();
      if (data.success) {
        notify(data.message || ('User ' + (username || '') + ' deleted'), 'success');
        await CFG.reloadDirectory();
      } else if (!notifyProtectedAccountError(data)) {
        notify(data.error || data.message || 'Failed to delete user', 'error');
      }
    } catch (e) {
      console.error(e);
      notify('Error deleting user', 'error');
    } finally {
      relockAdminProtect();
    }
  }

  async function runUnlockPassword(userId, username, fullName) {
    try {
      const response = await profileAuthenticatedFetch('/api/admin/users/' + userId + '/unlock-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (handleUnauthorized(response)) {
        relockAdminProtect();
        return;
      }
      const data = await response.json();
      if (data.success) {
        const pw = data.temp_password || DEFAULT_RESET_DISPLAY_PASSWORD;
        patchDirectoryUserPassword(userId, pw);
        const u = directoryUsers().find(function (x) { return Number(x.id) === Number(userId); });
        if (u) u.password_locked = false;
        openPasswordResetResultModal(username || '', pw);
        const intro = document.getElementById('passwordResetResultIntro');
        if (intro) {
          intro.textContent =
            'Password unlocked for "' + (fullName || username || 'user') +
            '". Share the temporary password below securely with the user.';
        }
        await CFG.reloadDirectory();
      } else if (!notifyProtectedAccountError(data)) {
        notify(data.error || data.message || 'Failed to unlock password', 'error');
      }
    } catch (e) {
      console.error(e);
      notify('Error unlocking password', 'error');
    } finally {
      const res = document.getElementById('passwordResetResultModal');
      if (!res || !res.classList.contains('active')) relockAdminProtect();
    }
  }

  w.submitAccountActionConfirm = async function submitAccountActionConfirm() {
    const ctx = accountActionConfirmContext;
    if (!ctx) return;
    const action = ctx.action;
    const uid = ctx.userId;
    const username = ctx.username;
    const fullName = ctx.fullName;
    closeAccountActionConfirmModal({ keepUnlock: true });
    if (action === 'delete') {
      await runDeleteUser(uid, username);
    } else if (action === 'unlock') {
      await runUnlockPassword(uid, username, fullName);
    } else {
      await runToggleUserActive(uid);
    }
  };

  w.profileModalResetPassword = function profileModalResetPassword() {
    const uid = parseInt(document.getElementById('profileUserId').value, 10);
    const u = directoryUsers().find(function (x) { return Number(x.id) === uid; });
    closeUserProfileModal({ keepUnlock: true });
    if (Number.isFinite(uid)) openPasswordResetConfirmModal(uid, u ? u.username : '');
    else relockAdminProtect();
  };

  w.profileModalUnlockPassword = function profileModalUnlockPassword() {
    const uid = parseInt(document.getElementById('profileUserId').value, 10);
    const u = directoryUsers().find(function (x) { return Number(x.id) === uid; });
    if (!Number.isFinite(uid)) return;
    closeUserProfileModal({ keepUnlock: true });
    openAccountActionConfirmModal({
      action: 'unlock',
      userId: uid,
      username: u ? u.username : '',
      fullName: u ? u.full_name : '',
    });
  };

  w.profileModalViewActivity = function profileModalViewActivity() {
    const uid = parseInt(document.getElementById('profileUserId').value, 10);
    closeUserProfileModal({ keepUnlock: true });
    if (Number.isFinite(uid)) openUserActivityModal(uid);
    else relockAdminProtect();
  };

  w.profileModalToggleActive = function profileModalToggleActive() {
    const uid = parseInt(document.getElementById('profileUserId').value, 10);
    const u = directoryUsers().find(function (x) { return Number(x.id) === uid; });
    if (!u || !Number.isFinite(uid)) return;
    closeUserProfileModal({ keepUnlock: true });
    openAccountActionConfirmModal({
      action: u.is_active ? 'deactivate' : 'activate',
      userId: uid,
      username: u.username,
      fullName: u.full_name,
      currentStatus: u.is_active,
    });
  };

  w.profileModalDeleteAccount = function profileModalDeleteAccount() {
    const uid = parseInt(document.getElementById('profileUserId').value, 10);
    const u = directoryUsers().find(function (x) { return Number(x.id) === uid; });
    if (!u || !Number.isFinite(uid)) return;
    closeUserProfileModal({ keepUnlock: true });
    openAccountActionConfirmModal({
      action: 'delete',
      userId: uid,
      username: u.username,
      fullName: u.full_name,
    });
  };

  function applyAdminProfileLayout() {
    const modal = document.getElementById('accessModal');
    if (modal) modal.classList.remove('admin-profile-shell--v2');
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

    if (
      String(user.role || '').toLowerCase() === 'admin' &&
      !AdminProtectUnlock.isValid()
    ) {
      notify(
        'System administrator accounts are protected. Click Protected and enter your PIN to edit.',
        'error',
        true,
      );
      return;
    }

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
    const slEl = document.getElementById('profileSickLeaveDays');
    if (slEl) {
      slEl.value = user.sick_leave_days != null && user.sick_leave_days !== ''
        ? String(user.sick_leave_days)
        : '';
    }
    const olEl = document.getElementById('profileOtherLeaveDays');
    if (olEl) {
      olEl.value = user.other_leave_days != null && user.other_leave_days !== ''
        ? String(user.other_leave_days)
        : '';
    }
    const insEl = document.getElementById('profileInsuranceDetails');
    if (insEl) {
      insEl.value = user.insurance_details || '';
    }

    document.getElementById('profileRole').value = user.role === 'admin' ? 'admin' : 'user';
    // Legacy business_development rows map to Sales in the dropdown
    const desig = user.designation === 'business_development' ? 'sales' : (user.designation || '');
    document.getElementById('profileDesignation').value = desig;

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
        ['accessFireApp', 'accessMunicipalityApp', 'accessFireInspection', 'accessHr', 'accessProcurement', 'accessBusinessDev', 'accessSalesManager', 'accessQuotations', 'accessDocHub', 'accessReportGen', 'accessSubmittedForms', 'accessTicketing', 'accessOperations', 'accessOpsOvertime', 'accessOpsTimesheet', 'accessOpsInvoices', 'accessOpsClients', 'accessOpsCheques', 'accessFinance'].forEach(function (id) {
          const cb = document.getElementById(id);
          if (cb) {
            cb.checked = true;
            cb.disabled = true;
          }
        });
      } else {
        modNote.hidden = true;
        modNote.textContent = '';
        const fireAppEl = document.getElementById('accessFireApp');
        if (fireAppEl) fireAppEl.checked = !!user.access_fire_app;
        const muniAppEl = document.getElementById('accessMunicipalityApp');
        if (muniAppEl) muniAppEl.checked = !!user.access_municipality_app;
        const fireEl = document.getElementById('accessFireInspection');
        if (fireEl) {
          fireEl.checked = !!user.access_hvac;
        }
        document.getElementById('accessHr').checked = !!user.access_hr;
        document.getElementById('accessProcurement').checked = !!user.access_procurement_module;
        const bd = document.getElementById('accessBusinessDev');
        if (bd) bd.checked = !!user.access_business_development || !!user.access_sales_manager;
        const sm = document.getElementById('accessSalesManager');
        if (sm) sm.checked = !!user.access_sales_manager;
        const aq = document.getElementById('accessQuotations');
        if (aq) aq.checked = !!user.access_quotations;
        const dh = document.getElementById('accessDocHub');
        if (dh) dh.checked = user.can_access_dochub !== false;
        const rg = document.getElementById('accessReportGen');
        if (rg) rg.checked = !!user.access_report_generation;
        const sf = document.getElementById('accessSubmittedForms');
        if (sf) sf.checked = !!user.access_submitted_forms;
        const tkt = document.getElementById('accessTicketing');
        if (tkt) tkt.checked = !!user.access_ticketing;
        const ops = document.getElementById('accessOperations');
        const opsSubs = [
          document.getElementById('accessOpsOvertime'),
          document.getElementById('accessOpsTimesheet'),
          document.getElementById('accessOpsAttendance'),
          document.getElementById('accessOpsInvoices'),
          document.getElementById('accessOpsClients'),
          document.getElementById('accessOpsCheques'),
        ];
        const opsSubVals = [
          !!user.access_operations_overtime,
          !!user.access_operations_timesheet,
          !!user.access_operations_attendance,
          !!user.access_operations_invoices,
          !!user.access_operations_clients,
          !!user.access_operations_cheques,
        ];
        const anySub = opsSubVals.some(Boolean);
        // Legacy hub-only users: treat as all subs on
        const legacyAll = !!user.access_operations && !anySub;
        opsSubs.forEach(function (el, i) {
          if (el) el.checked = legacyAll ? true : opsSubVals[i];
        });
        if (ops) ops.checked = !!user.access_operations || anySub || legacyAll;
        const fin = document.getElementById('accessFinance');
        if (fin) fin.checked = !!user.access_finance;
        modWrap.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
          cb.disabled = false;
        });
        function anyOpsSubChecked() {
          return opsSubs.some(function (el) { return el && el.checked; });
        }
        function setAllOpsSubs(on) {
          opsSubs.forEach(function (el) { if (el) el.checked = !!on; });
        }
        function syncOpsFromParent() {
          if (!ops) return;
          if (ops.checked) {
            if (!anyOpsSubChecked()) setAllOpsSubs(true);
          } else {
            setAllOpsSubs(false);
          }
        }
        function syncOpsFromSubs() {
          if (!ops) return;
          ops.checked = anyOpsSubChecked();
        }
        if (ops && !ops.dataset.opsManageBound) {
          ops.dataset.opsManageBound = '1';
          ops.addEventListener('change', syncOpsFromParent);
        }
        opsSubs.forEach(function (el) {
          if (el && !el.dataset.opsSubBound) {
            el.dataset.opsSubBound = '1';
            el.addEventListener('change', syncOpsFromSubs);
          }
        });
        if (sm && !sm.dataset.salesMgrBound) {
          sm.dataset.salesMgrBound = '1';
          sm.addEventListener('change', function () {
            if (sm.checked && bd) bd.checked = true;
          });
        }
      }
    }

    document.getElementById('profileDefaultComment').value = user.default_comment || '';
    profileSignatureDataUrl = user.default_signature || '';
    const sigFileEl = document.getElementById('profileSignatureFile');
    if (sigFileEl) sigFileEl.value = '';
    updateProfileSignaturePreview();

    const tbtn = document.getElementById('profileQuickToggleBtn');
    setProfileQuickToggleButton(tbtn, user.is_active);

    const unlockBtn = document.getElementById('profileUnlockPasswordBtn');
    if (unlockBtn) {
      unlockBtn.style.display = user.password_locked ? '' : 'none';
    }

    activatePortalModal(modal);
  };

  w.openAccessModal = w.openUserProfileModal;

  w.closeUserProfileModal = function closeUserProfileModal(opts) {
    opts = opts || {};
    const modal = document.getElementById('accessModal');
    if (modal) modal.classList.remove('active');
    const pr = document.getElementById('passwordResetResultModal');
    const pc = document.getElementById('passwordResetConfirmModal');
    const pu = pr && pr.classList.contains('active');
    const pcc = pc && pc.classList.contains('active');
    if (!pu && !pcc) document.body.style.overflow = '';
    // Relock as soon as the manage-profile popup is dismissed (Cancel / backdrop / Esc).
    if (!opts.keepUnlock) relockAdminProtect();
  };

  /* ── Activity modal ───────────────────────────────────────── */

  function getFormViewUrl(moduleType, submissionId) {
    if (moduleType === 'hvac_mep') {
      return '/hvac-mep/form?edit=' + encodeURIComponent(submissionId) + '&review=true';
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
      sales: 'Sales',
      business_development: 'Sales',
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
        const moduleClass = 'hvac';
        const moduleLabel = 'Fire Systems';
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
        const moduleClass = 'hvac';
        const moduleLabel = 'Fire Systems';
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
    relockAdminProtect();
  };

  function bindOnce() {
    if (bindingsDone) return;
    bindingsDone = true;

    applyAdminProfileLayout();

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      const res = document.getElementById('passwordResetResultModal');
      const conf = document.getElementById('passwordResetConfirmModal');
      const acct = document.getElementById('accountActionConfirmModal');
      const prof = document.getElementById('accessModal');
      const act = document.getElementById('userActivityModal');
      if (res && res.classList.contains('active')) {
        closePasswordResetResultModal();
      } else if (acct && acct.classList.contains('active')) {
        closeAccountActionConfirmModal();
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
          sick_leave_days:
            document.getElementById('profileSickLeaveDays')
              ? document.getElementById('profileSickLeaveDays').value.trim()
              : '',
          other_leave_days:
            document.getElementById('profileOtherLeaveDays')
              ? document.getElementById('profileOtherLeaveDays').value.trim()
              : '',
          insurance_details:
            document.getElementById('profileInsuranceDetails')
              ? document.getElementById('profileInsuranceDetails').value.trim()
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
          const fireOn = !!(document.getElementById('accessFireInspection') && document.getElementById('accessFireInspection').checked);
          // Fire system inspection is the only inspection product; keep legacy flags in sync.
          payload.access_hvac = fireOn;
          payload.access_fire_app = !!(document.getElementById('accessFireApp') && document.getElementById('accessFireApp').checked);
          payload.access_municipality_app = !!(document.getElementById('accessMunicipalityApp') && document.getElementById('accessMunicipalityApp').checked);
          payload.access_civil = false;
          payload.access_cleaning = false;
          payload.access_hr = document.getElementById('accessHr').checked;
          payload.access_procurement_module = document.getElementById('accessProcurement').checked;
          const salesMgrOn = !!(document.getElementById('accessSalesManager') && document.getElementById('accessSalesManager').checked);
          payload.access_sales_manager = salesMgrOn;
          payload.access_quotations = !!(document.getElementById('accessQuotations') && document.getElementById('accessQuotations').checked);
          // Sales Manager implies Sales module access
          payload.access_business_development = !!(document.getElementById('accessBusinessDev') && document.getElementById('accessBusinessDev').checked) || salesMgrOn;
          payload.access_report_generation = document.getElementById('accessReportGen').checked;
          payload.access_submitted_forms = document.getElementById('accessSubmittedForms').checked;
          const tgx = document.getElementById('accessTicketing');
          payload.access_ticketing = !!(tgx && tgx.checked);
          const opOt = document.getElementById('accessOpsOvertime');
          const opTs = document.getElementById('accessOpsTimesheet');
          const opAtt = document.getElementById('accessOpsAttendance');
          const opInv = document.getElementById('accessOpsInvoices');
          const opCli = document.getElementById('accessOpsClients');
          const opChq = document.getElementById('accessOpsCheques');
          payload.access_operations_overtime = !!(opOt && opOt.checked);
          payload.access_operations_timesheet = !!(opTs && opTs.checked);
          payload.access_operations_attendance = !!(opAtt && opAtt.checked);
          payload.access_operations_invoices = !!(opInv && opInv.checked);
          payload.access_operations_clients = !!(opCli && opCli.checked);
          payload.access_operations_cheques = !!(opChq && opChq.checked);
          const opx = document.getElementById('accessOperations');
          payload.access_operations = !!(opx && opx.checked) || payload.access_operations_overtime
            || payload.access_operations_timesheet || payload.access_operations_attendance
            || payload.access_operations_invoices || payload.access_operations_clients
            || payload.access_operations_cheques;
          // View/Full level UI removed — Operations access always includes manage.
          payload.access_operations_manage = !!payload.access_operations;
          const finx = document.getElementById('accessFinance');
          payload.access_finance = !!(finx && finx.checked);
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
          } else if (!notifyProtectedAccountError(data)) {
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
      ensurePortalModal(document.getElementById('accountActionConfirmModal'));
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
      if (typeof opts.onProtectRelock === 'function') {
        CFG.onProtectRelock = opts.onProtectRelock;
      }
      bindOnce();
    },
    init: bindOnce,
  };
})(typeof window !== 'undefined' ? window : globalThis);
