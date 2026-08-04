/**
 * Shared login shell behaviour for /login and the landing modal.
 *
 * Usage:
 *   initLoginShell({ redirect: true })           // full page → dashboard / ?next=
 *   initLoginShell({ onSuccess: function(user) { ... } })  // modal, no redirect
 */
(function (global) {
  'use strict';

  var eyeOpen =
    '<path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>';
  var eyeOff =
    '<path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-7 0-11-7-11-7a21.77 21.77 0 0 1 5.06-5.94M9.9 4.24A10.94 10.94 0 0 1 12 5c7 0 11 7 11 7a21.8 21.8 0 0 1-2.16 3.19M1 1l22 22"/><path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/>';

  function initLoginShell(options) {
    options = options || {};
    var onSuccess = typeof options.onSuccess === 'function' ? options.onSuccess : null;

    var pwInput = document.getElementById('password');
    var pwToggle = document.getElementById('pw-toggle');
    var pwIcon = document.getElementById('pw-toggle-icon');
    if (pwToggle && pwInput && pwIcon) {
      pwToggle.addEventListener('click', function () {
        var isHidden = pwInput.type === 'password';
        pwInput.type = isHidden ? 'text' : 'password';
        pwIcon.innerHTML = isHidden ? eyeOff : eyeOpen;
        pwToggle.setAttribute(
          'aria-label',
          isHidden ? 'Hide password' : 'Show password'
        );
      });
    }

    var loginForm = document.getElementById('login-form');
    var loginBtn = document.getElementById('login-btn');
    var loading = document.getElementById('loading');
    var errorMessage = document.getElementById('error-message');
    var successMessage = document.getElementById('success-message');

    if (!loginForm || !loginBtn || !errorMessage || !successMessage) {
      return null;
    }

    function showError(msg) {
      successMessage.classList.remove('show-success');
      successMessage.style.display = 'none';
      errorMessage.textContent = msg || '';
      errorMessage.classList.toggle('show-error', !!msg);
      errorMessage.style.display = msg ? 'block' : 'none';
    }

    function showSuccess(msg) {
      errorMessage.classList.remove('show-error');
      errorMessage.style.display = 'none';
      successMessage.textContent = msg || '';
      successMessage.classList.toggle('show-success', !!msg);
      successMessage.style.display = msg ? 'block' : 'none';
    }

    function resetUi() {
      showError('');
      showSuccess('');
      if (loginBtn) loginBtn.disabled = false;
      if (loading) loading.classList.remove('show');
      if (loginForm) loginForm.hidden = false;
      var forgotPanel = document.getElementById('forgot-panel');
      if (forgotPanel) forgotPanel.hidden = true;
      if (pwInput) {
        pwInput.type = 'password';
        pwInput.value = '';
      }
      if (pwIcon) pwIcon.innerHTML = eyeOpen;
      if (pwToggle) pwToggle.setAttribute('aria-label', 'Show password');
    }

    loginForm.addEventListener('submit', async function (e) {
      e.preventDefault();
      showError('');
      showSuccess('');

      var usernameEl = document.getElementById('username');
      var username = usernameEl ? usernameEl.value.trim() : '';
      var password = pwInput ? pwInput.value : '';

      // Step through empty fields instead of a generic required error.
      if (!username) {
        if (usernameEl) usernameEl.focus();
        return;
      }
      if (!password) {
        if (pwInput) pwInput.focus();
        return;
      }

      loginBtn.disabled = true;
      if (loading) loading.classList.add('show');

      try {
        var response = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: username, password: password }),
        });

        var contentType = response.headers.get('content-type');
        if (!contentType || contentType.indexOf('application/json') === -1) {
          showError('Server error: Expected JSON response.');
          loginBtn.disabled = false;
          if (loading) loading.classList.remove('show');
          return;
        }

        var data = await response.json();

        if (response.ok) {
          localStorage.setItem('access_token', data.access_token);
          localStorage.setItem('refresh_token', data.refresh_token);
          var userPayload = Object.assign({}, data.user || {}, {
            requires_password_change: !!data.requires_password_change,
            password_expiry_warning: !!data.password_expiry_warning,
            password_days_remaining: data.password_days_remaining,
            temp_password_reminder: !!data.temp_password_reminder,
          });
          localStorage.setItem('user', JSON.stringify(userPayload));

          if (onSuccess) {
            showSuccess('Signed in');
            if (loading) loading.classList.remove('show');
            onSuccess(userPayload, data);
            return;
          }

          showSuccess('Login successful! Redirecting...');
          setTimeout(function () {
            var next = '/dashboard';
            try {
              var params = new URLSearchParams(window.location.search);
              var raw = (params.get('next') || '').trim();
              if (
                raw.startsWith('/') &&
                !raw.startsWith('//') &&
                raw.indexOf('://') === -1
              ) {
                next = raw;
              }
            } catch (err) {}
            window.location.href = next;
          }, 1000);
        } else {
          var code = data.error_code || data.code || '';
          if (
            code === 'PASSWORD_EXPIRED_LOCKED' ||
            (data.error || '').toLowerCase().indexOf('password expired') !== -1
          ) {
            showError(
              data.error ||
                'Account locked because the password expired. Please contact an administrator to unlock.'
            );
          } else {
            showError(data.error || 'Login failed');
          }
          loginBtn.disabled = false;
          if (loading) loading.classList.remove('show');
        }
      } catch (error) {
        showError('Network error. Please try again.');
        loginBtn.disabled = false;
        if (loading) loading.classList.remove('show');
      }
    });

    // Forgot-password flow
    (function () {
      var loginFormEl = document.getElementById('login-form');
      var forgotPanel = document.getElementById('forgot-panel');
      var openBtn = document.getElementById('forgot-open-btn');
      var backBtnFp = document.getElementById('forgot-back-btn');
      var fpLoading = document.getElementById('fp-loading');
      var stepIdentify = document.getElementById('fp-step-identify');
      var stepOtp = document.getElementById('fp-step-otp');
      var stepPassword = document.getElementById('fp-step-password');
      var labels = [
        document.getElementById('fp-step-label-1'),
        document.getElementById('fp-step-label-2'),
        document.getElementById('fp-step-label-3'),
      ];
      var fpIdentifier = '';
      var fpResetToken = null;

      function setFpBusy(busy) {
        if (fpLoading) fpLoading.classList.toggle('show', !!busy);
        [
          'fp-send-otp-btn',
          'fp-verify-otp-btn',
          'fp-reset-btn',
          'fp-resend-btn',
        ].forEach(function (id) {
          var el = document.getElementById(id);
          if (el) el.disabled = !!busy;
        });
      }

      function setFpStep(step) {
        if (stepIdentify) stepIdentify.hidden = step !== 1;
        if (stepOtp) stepOtp.hidden = step !== 2;
        if (stepPassword) stepPassword.hidden = step !== 3;
        labels.forEach(function (el, i) {
          if (el) el.classList.toggle('is-active', i + 1 === step);
        });
      }

      function openForgot() {
        showError('');
        showSuccess('');
        var usernameEl = document.getElementById('username');
        fpIdentifier = (usernameEl && usernameEl.value) || '';
        fpIdentifier = fpIdentifier.trim();
        var idEl = document.getElementById('fp-identifier');
        if (idEl) idEl.value = fpIdentifier;
        var otpEl = document.getElementById('fp-otp');
        if (otpEl) otpEl.value = '';
        var np = document.getElementById('fp-new-password');
        if (np) np.value = '';
        var cp = document.getElementById('fp-confirm-password');
        if (cp) cp.value = '';
        fpResetToken = null;
        setFpStep(1);
        if (loginFormEl) loginFormEl.hidden = true;
        if (forgotPanel) forgotPanel.hidden = false;
        setTimeout(function () {
          if (idEl) idEl.focus();
        }, 40);
      }

      function closeForgot() {
        showError('');
        showSuccess('');
        fpResetToken = null;
        if (forgotPanel) forgotPanel.hidden = true;
        if (loginFormEl) loginFormEl.hidden = false;
      }

      async function fpJson(url, body) {
        var response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body || {}),
        });
        var data = {};
        try {
          data = await response.json();
        } catch (_) {}
        return { ok: response.ok, status: response.status, data: data };
      }

      async function sendOtp() {
        showError('');
        showSuccess('');
        var idEl = document.getElementById('fp-identifier');
        fpIdentifier = ((idEl && idEl.value) || '').trim();
        if (!fpIdentifier) {
          showError('Enter your username or email.');
          return;
        }
        setFpBusy(true);
        try {
          var res = await fpJson('/api/auth/forgot-password/request-otp', {
            identifier: fpIdentifier,
          });
          if (!res.ok) {
            showError(res.data.error || 'Could not send verification code.');
            return;
          }
          var masked = res.data.masked_email || '';
          var hint = document.getElementById('fp-otp-hint');
          if (hint) {
            hint.textContent = masked
              ? 'We sent a 6-digit code to ' + masked + '. Enter it below.'
              : 'If an account matches, a code was sent. Enter it below.';
          }
          setFpStep(2);
          showSuccess(res.data.message || 'Check your email for a code.');
          setTimeout(function () {
            var otp = document.getElementById('fp-otp');
            if (otp) otp.focus();
          }, 40);
        } catch (err) {
          showError('Network error. Please try again.');
        } finally {
          setFpBusy(false);
        }
      }

      async function verifyOtp() {
        showError('');
        showSuccess('');
        var otpEl = document.getElementById('fp-otp');
        var code = ((otpEl && otpEl.value) || '').trim();
        if (!/^\d{6}$/.test(code)) {
          showError('Enter the 6-digit code from your email.');
          return;
        }
        setFpBusy(true);
        try {
          var res = await fpJson('/api/auth/forgot-password/verify-otp', {
            identifier: fpIdentifier,
            code: code,
          });
          if (!res.ok) {
            showError(res.data.error || 'Incorrect or expired code.');
            return;
          }
          fpResetToken =
            res.data.reset_token ||
            (res.data.data && res.data.data.reset_token) ||
            null;
          if (!fpResetToken) {
            showError('Verification succeeded but reset token was missing.');
            return;
          }
          setFpStep(3);
          showSuccess('Code verified. Choose a new password.');
          setTimeout(function () {
            var np = document.getElementById('fp-new-password');
            if (np) np.focus();
          }, 40);
        } catch (err) {
          showError('Network error. Please try again.');
        } finally {
          setFpBusy(false);
        }
      }

      async function resetPassword() {
        showError('');
        showSuccess('');
        var pw =
          (document.getElementById('fp-new-password') &&
            document.getElementById('fp-new-password').value) ||
          '';
        var confirm =
          (document.getElementById('fp-confirm-password') &&
            document.getElementById('fp-confirm-password').value) ||
          '';
        if (pw !== confirm) {
          showError('Password confirmation does not match.');
          return;
        }
        if (!fpResetToken) {
          showError('Reset session expired. Start again.');
          setFpStep(1);
          return;
        }
        setFpBusy(true);
        try {
          var res = await fpJson('/api/auth/forgot-password/reset', {
            reset_token: fpResetToken,
            new_password: pw,
            confirm_password: confirm,
          });
          if (!res.ok) {
            showError(res.data.error || 'Failed to update password.');
            return;
          }
          var uname = res.data.username || fpIdentifier;
          closeForgot();
          var userEl = document.getElementById('username');
          if (userEl && uname) userEl.value = uname;
          if (pwInput) pwInput.value = '';
          showSuccess('Password updated. Sign in with your new password.');
        } catch (err) {
          showError('Network error. Please try again.');
        } finally {
          setFpBusy(false);
        }
      }

      if (openBtn) openBtn.addEventListener('click', openForgot);
      if (backBtnFp) backBtnFp.addEventListener('click', closeForgot);
      var sendBtn = document.getElementById('fp-send-otp-btn');
      if (sendBtn) sendBtn.addEventListener('click', sendOtp);
      var resendBtn = document.getElementById('fp-resend-btn');
      if (resendBtn) resendBtn.addEventListener('click', sendOtp);
      var verifyBtn = document.getElementById('fp-verify-otp-btn');
      if (verifyBtn) verifyBtn.addEventListener('click', verifyOtp);
      var resetBtn = document.getElementById('fp-reset-btn');
      if (resetBtn) resetBtn.addEventListener('click', resetPassword);

      var otpEl = document.getElementById('fp-otp');
      if (otpEl) {
        otpEl.addEventListener('input', function () {
          otpEl.value = otpEl.value.replace(/\D/g, '').slice(0, 6);
        });
        otpEl.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') {
            e.preventDefault();
            verifyOtp();
          }
        });
      }
      var idEl = document.getElementById('fp-identifier');
      if (idEl) {
        idEl.addEventListener('keydown', function (e) {
          if (e.key === 'Enter') {
            e.preventDefault();
            sendOtp();
          }
        });
      }
      ['fp-new-password', 'fp-confirm-password'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) {
          el.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
              e.preventDefault();
              resetPassword();
            }
          });
        }
      });
    })();

    return {
      showError: showError,
      showSuccess: showSuccess,
      resetUi: resetUi,
      focusUsername: function () {
        var el = document.getElementById('username');
        if (el) el.focus();
      },
    };
  }

  global.initLoginShell = initLoginShell;
})(typeof window !== 'undefined' ? window : this);
