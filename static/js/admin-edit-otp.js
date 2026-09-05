/**
 * Step-up email OTP to unlock administrator Manage profile edits.
 * Loaded on Users & Teams and Administration.
 */
(function (w) {
  'use strict';

  const CFG = {
    fetch: null,
    notify: function (msg) { if (msg) w.alert(msg); },
    syncOverlay: function () {},
  };

  let currentUser = null;
  let locked = false;
  let grantExpiresAt = null;
  let codeExpiresAt = null;
  let resendAvailableAt = null;
  let sendFailed = false;
  let tickTimer = null;

  function notify(msg, type) {
    if (typeof CFG.notify === 'function') CFG.notify(msg, type || 'success');
  }

  async function apiFetch(url, options) {
    const fn = CFG.fetch;
    if (typeof fn === 'function') return fn(url, options || {});
    const token = localStorage.getItem('access_token') || '';
    return fetch(url, {
      ...(options || {}),
      headers: {
        ...((options && options.headers) || {}),
        Authorization: 'Bearer ' + token,
      },
    });
  }

  function ensurePortal(el) {
    if (el) (document.documentElement || document.body).appendChild(el);
  }

  function remainingFromIso(iso) {
    if (!iso) return { text: '0:00', seconds: 0, done: true };
    const ms = new Date(iso).getTime() - Date.now();
    if (!Number.isFinite(ms) || ms <= 0) return { text: '0:00', seconds: 0, done: true };
    const total = Math.ceil(ms / 1000);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return { text: m + ':' + String(s).padStart(2, '0'), seconds: total, done: false };
  }

  function stopTicks() {
    if (tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
  }

  function startTicks() {
    stopTicks();
    tick();
    tickTimer = setInterval(tick, 1000);
  }

  function identitySubtitle(user) {
    if (!user) return '';
    const handle = user.username ? '@' + user.username : '';
    const email = user.email || '';
    if (handle && email) return handle + ' · ' + email;
    return handle || email;
  }

  function restoreSubtitle() {
    const sub = document.getElementById('userProfileSubtitle');
    if (sub) sub.textContent = identitySubtitle(currentUser);
  }

  function applyTimingFromData(data) {
    if (!data) return;
    if (data.grant_expires_at) grantExpiresAt = data.grant_expires_at;
    if (Object.prototype.hasOwnProperty.call(data, 'code_expires_at')) {
      codeExpiresAt = data.code_expires_at || null;
    }
    if (data.resend_available_at) {
      resendAvailableAt = data.resend_available_at;
    } else if (typeof data.resend_after_seconds === 'number') {
      resendAvailableAt = new Date(Date.now() + Math.max(0, data.resend_after_seconds) * 1000).toISOString();
    }
  }

  function setResendUi() {
    const sendBtn = document.getElementById('profileAdminOtpSendBtn');
    const resendBtn = document.getElementById('profileAdminOtpResendBtn');
    const resendMeta = document.getElementById('profileAdminOtpResendMeta');
    const hintMeta = document.getElementById('profileAdminOtpHintResendMeta');
    const wait = remainingFromIso(resendAvailableAt);
    const cooling = !wait.done && wait.seconds > 0;
    if (sendBtn && currentUser && (currentUser.email || '').trim() && !sendFailed) {
      sendBtn.disabled = cooling;
      sendBtn.textContent = cooling ? ('Resend in ' + wait.text) : 'Send verification code';
    }
    if (resendBtn) {
      resendBtn.disabled = cooling;
      resendBtn.textContent = cooling ? ('Resend in ' + wait.text) : 'Resend code';
    }
    if (resendMeta) {
      resendMeta.textContent = cooling ? ('You can resend in ' + wait.text) : '';
    }
    if (hintMeta) {
      hintMeta.hidden = !cooling;
      hintMeta.textContent = cooling ? ('You can resend in ' + wait.text) : '';
    }
  }

  function setCodeTimerUi() {
    const el = document.getElementById('profileAdminOtpCodeTimer');
    if (!el) return;
    if (!codeExpiresAt) {
      el.hidden = true;
      return;
    }
    const wait = remainingFromIso(codeExpiresAt);
    el.hidden = false;
    el.textContent = wait.done ? 'Code expired. Send a new one.' : ('Code expires in ' + wait.text);
  }

  function setGrantChipUi() {
    const unlockedEl = document.getElementById('profileAdminOtpUnlocked');
    if (!unlockedEl || unlockedEl.hidden) return;
    const wait = remainingFromIso(grantExpiresAt);
    unlockedEl.textContent = wait.done ? 'Unlocked · 0:00' : ('Unlocked · ' + wait.text);
  }

  function tick() {
    setGrantChipUi();
    setCodeTimerUi();
    setResendUi();
    if (grantExpiresAt && remainingFromIso(grantExpiresAt).done && !locked) {
      grantExpiresAt = null;
      if (currentUser) applyForUser(currentUser);
    }
  }

  function setHint(opts) {
    const hint = document.getElementById('profileAdminOtpHint');
    const prefix = document.getElementById('profileAdminOtpHintPrefix');
    const emailVal = document.getElementById('profileAdminOtpEmailValue');
    const sendBtn = document.getElementById('profileAdminOtpSendBtn');
    const pwdWrap = document.getElementById('profileAdminOtpHintPasswordWrap');
    const pwdLead = document.getElementById('profileAdminOtpHintPasswordLead');
    if (!hint) return;
    if (!opts || !opts.show) {
      hint.hidden = true;
      hint.classList.remove('is-password-needed');
      return;
    }
    hint.hidden = false;
    const noEmail = opts.hasEmail === false;
    const needPwd = noEmail || !!opts.sendFailed;
    hint.classList.toggle('is-password-needed', needPwd);
    if (pwdWrap) pwdWrap.hidden = false;
    if (pwdLead) {
      pwdLead.textContent = noEmail
        ? 'This account has no email. Unlock with your admin login password.'
        : (opts.sendFailed
          ? 'The verification email could not be sent. Unlock with your admin login password.'
          : 'If a code cannot be sent, unlock with your admin login password.');
    }
    if (noEmail) {
      if (prefix) prefix.textContent = 'This account needs an email before a code can be sent.';
      if (emailVal) {
        emailVal.textContent = '';
        emailVal.hidden = true;
      }
      if (sendBtn) sendBtn.disabled = true;
      return;
    }
    if (prefix) prefix.textContent = 'A verification code will be sent to ';
    if (emailVal) {
      emailVal.hidden = false;
      emailVal.textContent = opts.emailMasked || 'the account email';
    }
    if (sendBtn) sendBtn.disabled = false;
    setResendUi();
  }

  function setBanner(opts) {
    const banner = document.getElementById('profileAdminOtpBanner');
    const modal = document.getElementById('accessModal');
    const titleEl = document.getElementById('profileAdminOtpBannerTitle');
    const intro = document.getElementById('profileAdminOtpIntro');
    const emailLine = document.getElementById('profileAdminOtpEmailLine');
    const unlockedEl = document.getElementById('profileAdminOtpUnlocked');
    if (modal) {
      modal.classList.remove('admin-otp-is-locked', 'admin-otp-is-unlocked');
    }
    restoreSubtitle();
    if (!banner) {
      setHint({ show: false });
      return;
    }
    if (!opts || !opts.show) {
      banner.hidden = true;
      banner.classList.remove('is-unlocked');
      if (unlockedEl) unlockedEl.hidden = true;
      setHint({ show: false });
      stopTicks();
      return;
    }
    banner.classList.toggle('is-unlocked', !!opts.unlocked);
    if (modal) {
      modal.classList.add(opts.unlocked ? 'admin-otp-is-unlocked' : 'admin-otp-is-locked');
    }
    if (opts.unlocked) {
      banner.hidden = false;
      if (titleEl) titleEl.textContent = 'Editing unlocked';
      if (intro) intro.hidden = true;
      if (emailLine) emailLine.hidden = true;
      if (unlockedEl) {
        unlockedEl.hidden = false;
        grantExpiresAt = opts.grantExpiresAt || grantExpiresAt;
        setGrantChipUi();
      }
      setHint({ show: false });
      startTicks();
    } else {
      banner.hidden = true;
      if (titleEl) titleEl.textContent = 'Verify to edit';
      if (intro) {
        intro.hidden = false;
        intro.textContent = 'This administrator account is locked to prevent unconfirmed profile, password, or access changes.';
      }
      if (unlockedEl) unlockedEl.hidden = true;
      if (emailLine) {
        emailLine.hidden = false;
        emailLine.textContent = opts.hasEmail === false
          ? 'This account needs an email before a code can be sent.'
          : ('A verification code will be sent to ' + (opts.emailMasked || 'the account email'));
      }
      setHint({
        show: true,
        hasEmail: opts.hasEmail,
        emailMasked: opts.emailMasked,
        sendFailed: opts.sendFailed || sendFailed,
      });
      startTicks();
    }
  }

  function applyFieldLock(isLocked, user) {
    locked = !!isLocked;
    const form = document.getElementById('userProfileForm');
    if (!form) return;
    const keepEnabled = {
      profileUserId: true,
      profilePasswordToggle: true,
      profilePasswordCopy: true,
      profileAdminOtpSendBtn: true,
      profileAdminOtpCode: true,
      profileAdminOtpVerifyBtn: true,
      profileAdminOtpResendBtn: true,
      profileAdminOtpPassword: true,
      profileAdminOtpPasswordUnlockBtn: true,
      profileAdminOtpHintPassword: true,
      profileAdminOtpHintPasswordUnlockBtn: true,
    };
    form.querySelectorAll('input, select, textarea').forEach(function (el) {
      if (keepEnabled[el.id]) return;
      if (el.closest('#profileAdminOtpBanner')) return;
      el.disabled = isLocked;
    });
    const emailCreds = document.getElementById('profileEmailCredentialsBtn');
    if (emailCreds) emailCreds.disabled = isLocked;
    const sigClear = document.getElementById('profileSignatureClear');
    if (sigClear) sigClear.disabled = isLocked;
    const resetBtn = form.querySelector('.admin-quick-action.btn-reset');
    if (resetBtn) resetBtn.disabled = isLocked;
    const toggleBtn = document.getElementById('profileQuickToggleBtn');
    if (toggleBtn) toggleBtn.disabled = isLocked;
    const delBtn = document.getElementById('profileDeleteUserBtn');
    if (delBtn) delBtn.disabled = isLocked;
    const activityBtn = form.querySelector('.admin-quick-action.btn-activity');
    if (activityBtn) activityBtn.disabled = false;

    if (!isLocked && user && user.role === 'admin') {
      const selfId = (function () {
        try {
          const raw = localStorage.getItem('user');
          const u = raw ? JSON.parse(raw) : null;
          return u && u.id != null ? Number(u.id) : null;
        } catch (_) {
          return null;
        }
      })();
      const roleEl = document.getElementById('profileRole');
      if (roleEl && Number(user.id) === Number(selfId)) roleEl.disabled = true;
      const modWrap = document.getElementById('profileModuleAccess');
      if (modWrap) {
        modWrap.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
          cb.disabled = true;
        });
      }
    }

    const saveBtn = document.getElementById('profileSaveChangesBtn');
    if (saveBtn) {
      saveBtn.hidden = isLocked;
      saveBtn.style.display = isLocked ? 'none' : '';
    }
  }

  function showUnlocked(grantIso) {
    grantExpiresAt = grantIso || grantExpiresAt;
    sendFailed = false;
    applyFieldLock(false, currentUser);
    setBanner({
      show: true,
      unlocked: true,
      grantExpiresAt: grantExpiresAt,
      hasEmail: true,
    });
  }

  async function applyForUser(user) {
    currentUser = user || null;
    sendFailed = false;
    grantExpiresAt = null;
    codeExpiresAt = null;
    resendAvailableAt = null;
    if (!user || user.role !== 'admin') {
      setBanner({ show: false });
      applyFieldLock(false, user);
      return;
    }
    applyFieldLock(true, user);
    setBanner({
      show: true,
      unlocked: false,
      emailMasked: user.email ? String(user.email).replace(/^.(.*)@/, function (_, rest) {
        return String(user.email).charAt(0) + '***@';
      }) : 'the account email',
      hasEmail: !!(user.email || '').trim(),
    });
    try {
      const response = await apiFetch('/api/admin/users/' + user.id + '/edit-otp/status', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response || response.status === 401) return;
      const data = await response.json().catch(function () { return {}; });
      if (!data || !data.otp_required) {
        setBanner({ show: false });
        applyFieldLock(false, user);
        return;
      }
      applyTimingFromData(data);
      if (data.unlocked) {
        showUnlocked(data.grant_expires_at);
      } else {
        applyFieldLock(true, user);
        setBanner({
          show: true,
          unlocked: false,
          emailMasked: data.email_masked,
          hasEmail: data.has_email,
        });
      }
    } catch (err) {
      console.error(err);
    }
  }

  w.requestAdminProfileOtp = async function requestAdminProfileOtp() {
    const uid = currentUser && currentUser.id;
    if (!uid) return;
    const sendBtn = document.getElementById('profileAdminOtpSendBtn');
    const resendBtn = document.getElementById('profileAdminOtpResendBtn');
    if (sendBtn) sendBtn.disabled = true;
    if (resendBtn) resendBtn.disabled = true;
    try {
      const response = await apiFetch('/api/admin/users/' + uid + '/edit-otp/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const data = await response.json().catch(function () { return {}; });
      applyTimingFromData(data);
      if (response.status === 429) {
        notify(data.error || 'Wait before sending another code.', 'error');
        startTicks();
        return;
      }
      if (!response.ok) {
        sendFailed = true;
        notify(data.error || 'Could not send the verification code. Check mail settings and try again.', 'error');
        setHint({
          show: true,
          hasEmail: !!(currentUser.email || '').trim(),
          emailMasked: data.sent_to,
          sendFailed: true,
        });
        startTicks();
        return;
      }
      sendFailed = false;
      notify(data.message || 'Verification code sent.', 'success');
      const intro = document.getElementById('profileAdminOtpModalIntro');
      if (intro) {
        intro.textContent = 'Enter the 6-digit code sent to '
          + (data.sent_to || 'the administrator email') + '.';
      }
      const input = document.getElementById('profileAdminOtpCode');
      if (input) input.value = '';
      const modal = document.getElementById('profileAdminOtpModal');
      if (modal) {
        ensurePortal(modal);
        modal.classList.add('active');
        CFG.syncOverlay();
        if (input) setTimeout(function () { input.focus(); }, 50);
      }
      startTicks();
    } catch (err) {
      console.error(err);
      sendFailed = true;
      notify('Could not send the verification code.', 'error');
    } finally {
      setResendUi();
    }
  };

  w.closeAdminProfileOtpModal = function closeAdminProfileOtpModal() {
    const modal = document.getElementById('profileAdminOtpModal');
    if (modal) modal.classList.remove('active');
    CFG.syncOverlay();
  };

  w.submitAdminProfileOtp = async function submitAdminProfileOtp() {
    const uid = currentUser && currentUser.id;
    if (!uid) return;
    const input = document.getElementById('profileAdminOtpCode');
    const code = input ? String(input.value || '').replace(/\D/g, '') : '';
    if (code.length !== 6) {
      notify('Enter the 6-digit code from the email.', 'error');
      return;
    }
    try {
      const response = await apiFetch('/api/admin/users/' + uid + '/edit-otp/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code }),
      });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        notify(data.error || 'That code did not match. Check the email and try again.', 'error');
        return;
      }
      w.closeAdminProfileOtpModal();
      notify(data.message || 'Editing unlocked.', 'success');
      showUnlocked(data.grant_expires_at);
    } catch (err) {
      console.error(err);
      notify('Could not verify that code.', 'error');
    }
  };

  w.unlockAdminProfileWithPassword = async function unlockAdminProfileWithPassword(source) {
    const uid = currentUser && currentUser.id;
    if (!uid) return;
    const inputId = source === 'modal' ? 'profileAdminOtpPassword' : 'profileAdminOtpHintPassword';
    const input = document.getElementById(inputId);
    const password = input ? String(input.value || '') : '';
    if (!password.trim()) {
      notify('Enter your admin password.', 'error');
      return;
    }
    try {
      const response = await apiFetch('/api/admin/users/' + uid + '/edit-otp/unlock-with-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: password }),
      });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        notify(data.error || 'That password did not match.', 'error');
        return;
      }
      if (input) input.value = '';
      w.closeAdminProfileOtpModal();
      notify(data.message || 'Editing unlocked.', 'success');
      showUnlocked(data.grant_expires_at);
    } catch (err) {
      console.error(err);
      notify('Could not unlock with that password.', 'error');
    }
  };

  w.lockAdminProfileNow = async function lockAdminProfileNow() {
    const uid = currentUser && currentUser.id;
    if (!uid) return;
    try {
      const response = await apiFetch('/api/admin/users/' + uid + '/edit-otp/lock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        notify(data.error || 'Could not lock this profile.', 'error');
        return;
      }
      grantExpiresAt = null;
      codeExpiresAt = null;
      resendAvailableAt = null;
      notify('Profile locked.', 'success');
      applyFieldLock(true, currentUser);
      setBanner({
        show: true,
        unlocked: false,
        emailMasked: data.email_masked,
        hasEmail: data.has_email,
      });
    } catch (err) {
      console.error(err);
      notify('Could not lock this profile.', 'error');
    }
  };

  w.AdminEditOtp = {
    configure: function (opts) {
      if (!opts || typeof opts !== 'object') return;
      if (opts.fetch) CFG.fetch = opts.fetch;
      if (opts.notify) CFG.notify = opts.notify;
      if (opts.syncOverlay) CFG.syncOverlay = opts.syncOverlay;
      const input = document.getElementById('profileAdminOtpCode');
      if (input && !input.dataset.otpBound) {
        input.dataset.otpBound = '1';
        input.addEventListener('input', function () {
          input.value = String(input.value || '').replace(/\D/g, '').slice(0, 6);
        });
        input.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') {
            e.preventDefault();
            w.submitAdminProfileOtp();
          }
        });
      }
      ['profileAdminOtpHintPassword', 'profileAdminOtpPassword'].forEach(function (id) {
        const el = document.getElementById(id);
        if (!el || el.dataset.otpBound) return;
        el.dataset.otpBound = '1';
        el.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') {
            e.preventDefault();
            w.unlockAdminProfileWithPassword(id === 'profileAdminOtpPassword' ? 'modal' : 'hint');
          }
        });
      });
    },
    apply: applyForUser,
    isLocked: function () { return locked; },
    relock: function () {
      if (currentUser) return applyForUser(currentUser);
    },
  };
})(typeof window !== 'undefined' ? window : globalThis);
