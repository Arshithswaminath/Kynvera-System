/**
 * Landing/applications auth: open login modal, paint user pill, sign out.
 * Depends on login.js (initLoginShell).
 */
(function () {
  'use strict';

  var loginApi = null;
  var lastFocus = null;

  function getStoredUser() {
    try {
      var raw = localStorage.getItem('user');
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function hasSession() {
    return !!(localStorage.getItem('access_token') && getStoredUser());
  }

  function initialsFor(user) {
    if (!user) return 'U';
    if (user.full_name) {
      return user.full_name
        .split(/\s+/)
        .filter(Boolean)
        .map(function (n) {
          return n[0];
        })
        .join('')
        .toUpperCase()
        .slice(0, 2);
    }
    if (user.username) return user.username.slice(0, 2).toUpperCase();
    return 'U';
  }

  function roleLabel(user) {
    if (!user) return '';
    var role = (user.designation || user.job_designation || user.role || '').toString();
    return role.replace(/_/g, ' ');
  }

  function setUserMenuOpen(open) {
    var pill = document.getElementById('l-user-pill');
    var trigger = document.getElementById('l-user-trigger');
    var menu = document.getElementById('l-user-menu');
    if (!pill || !trigger || !menu) return;
    pill.classList.toggle('is-open', open);
    trigger.setAttribute('aria-expanded', String(open));
    menu.hidden = !open;
  }

  function paintAuthed(user) {
    var nav = document.getElementById('l-nav');
    var pill = document.getElementById('l-user-pill');
    var avatar = document.getElementById('l-user-avatar');
    var nameEl = document.getElementById('l-user-name');
    var roleEl = document.getElementById('l-user-role');
    if (!nav || !pill) return;

    nav.classList.add('is-authed');
    pill.hidden = false;
    if (avatar) avatar.textContent = initialsFor(user);
    if (nameEl) nameEl.textContent = user.full_name || user.username || 'Account';
    if (roleEl) {
      var role = roleLabel(user);
      roleEl.textContent = role;
      roleEl.hidden = !role;
    }
    setUserMenuOpen(false);
  }

  function paintGuest() {
    var nav = document.getElementById('l-nav');
    var pill = document.getElementById('l-user-pill');
    if (nav) nav.classList.remove('is-authed');
    if (pill) pill.hidden = true;
    setUserMenuOpen(false);
  }

  function openModal() {
    var modal = document.getElementById('l-login-modal');
    if (!modal) return;
    lastFocus = document.activeElement;
    modal.hidden = false;
    document.body.classList.add('l-login-open');
    if (loginApi) {
      loginApi.resetUi();
      setTimeout(function () {
        loginApi.focusUsername();
      }, 40);
    } else {
      var userEl = document.getElementById('username');
      if (userEl) {
        setTimeout(function () {
          userEl.focus();
        }, 40);
      }
    }
  }

  function closeModal() {
    var modal = document.getElementById('l-login-modal');
    if (!modal || modal.hidden) return;
    modal.hidden = true;
    document.body.classList.remove('l-login-open');
    if (loginApi) loginApi.resetUi();
    if (lastFocus && typeof lastFocus.focus === 'function') {
      try {
        lastFocus.focus();
      } catch (e) {}
    }
  }

  async function signOut() {
    var token = localStorage.getItem('access_token');
    try {
      if (token) {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: 'Bearer ' + token,
          },
        });
      }
    } catch (e) {
      /* best effort */
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    paintGuest();
    setUserMenuOpen(false);
  }

  function init() {
    var modal = document.getElementById('l-login-modal');
    if (!modal) return;

    if (typeof window.initLoginShell === 'function') {
      loginApi = window.initLoginShell({
        onSuccess: function (user) {
          paintAuthed(user);
          closeModal();
        },
      });
    }

    document.querySelectorAll('[data-login-open]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var nav = document.getElementById('l-nav');
        if (nav) nav.classList.remove('is-open');
        var toggle = document.getElementById('l-nav-toggle');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
        openModal();
      });
    });

    modal.querySelectorAll('[data-login-modal-close]').forEach(function (el) {
      el.addEventListener('click', closeModal);
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        if (!modal.hidden) {
          closeModal();
          return;
        }
        setUserMenuOpen(false);
      }
    });

    var trigger = document.getElementById('l-user-trigger');
    var menu = document.getElementById('l-user-menu');
    if (trigger && menu) {
      trigger.addEventListener('click', function (e) {
        e.stopPropagation();
        setUserMenuOpen(menu.hidden);
      });
      document.addEventListener('click', function (e) {
        var pill = document.getElementById('l-user-pill');
        if (!pill || pill.hidden) return;
        if (!pill.contains(e.target)) setUserMenuOpen(false);
      });
    }

    var signout = document.getElementById('l-user-signout');
    if (signout) {
      signout.addEventListener('click', function () {
        signOut();
      });
    }

    if (hasSession()) {
      paintAuthed(getStoredUser());
    } else {
      paintGuest();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
