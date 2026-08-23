/**
 * Automations hub UI
 */
(function () {
  'use strict';

  var jobs = [];
  var runs = [];

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
    return fetch(path, {
      method: opts.method || 'GET',
      headers: authHeaders(!!opts.json),
      body: opts.json ? JSON.stringify(opts.json) : undefined,
      credentials: 'same-origin',
    }).then(function (res) {
      return res.json().then(function (body) {
        body._status = res.status;
        body._ok = res.ok;
        return body;
      });
    });
  }

  function toast(msg) {
    var el = document.getElementById('autoToast');
    var text = document.getElementById('autoToastMsg');
    if (!el || !text) return;
    text.textContent = msg;
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { el.hidden = true; }, 4200);
  }

  function pad(n) {
    return String(n).padStart(2, '0');
  }

  function fmtWhen(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z').toLocaleString('en-GB', {
        timeZone: 'Asia/Dubai',
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      }) + ' GST';
    } catch (e) {
      return iso;
    }
  }

  function statusPill(job) {
    if (!job.implemented) return '<span class="auto-pill is-soon">Coming soon</span>';
    if (!job.enabled) return '<span class="auto-pill is-off">Paused</span>';
    return '<span class="auto-pill">Enabled · ' + pad(job.schedule_hour) + ':' + pad(job.schedule_minute) + ' Dubai</span>';
  }

  function lastLine(job) {
    if (!job.implemented) return 'Not scheduled yet.';
    if (job.last_error) return 'Last issue: ' + job.last_error;
    if (job.last_success_at) return 'Last success: ' + fmtWhen(job.last_success_at);
    return 'No runs yet.';
  }

  function renderJobs() {
    var root = document.getElementById('autoJobs');
    if (!root) return;
    if (!jobs.length) {
      root.innerHTML = '<p class="auto-empty">No jobs configured.</p>';
      return;
    }
    root.innerHTML = jobs.map(function (job) {
      if (!job.implemented) {
        return (
          '<article class="auto-card is-soon">' +
            '<div class="auto-card-top">' +
              '<div>' +
                '<h2 class="auto-card-title">' + esc(job.title) + '</h2>' +
                '<p class="auto-card-desc">' + esc(job.description) + '</p>' +
              '</div>' +
              statusPill(job) +
            '</div>' +
          '</article>'
        );
      }
      return (
        '<article class="auto-card" data-slug="' + esc(job.slug) + '">' +
          '<div class="auto-card-top">' +
            '<div>' +
              '<h2 class="auto-card-title">' + esc(job.title) + '</h2>' +
              '<p class="auto-card-desc">' + esc(job.description) + '</p>' +
            '</div>' +
            statusPill(job) +
          '</div>' +
          '<p class="auto-meta">' + esc(lastLine(job)) + '</p>' +
          '<div class="auto-toggles">' +
            toggleHtml(job, 'enabled', 'Enabled') +
            toggleHtml(job, 'save_to_files', 'Save to Files') +
            toggleHtml(job, 'send_email', 'Email') +
            toggleHtml(job, 'sync_drive', 'Drive sync') +
          '</div>' +
          '<div class="auto-fields">' +
            '<label class="auto-label" for="to-' + esc(job.slug) + '">Email recipients</label>' +
            '<input class="auto-input" id="to-' + esc(job.slug) + '" data-field="to_emails" value="' +
              esc(job.to_emails || '') + '" placeholder="hr@example.com, ops@example.com">' +
          '</div>' +
          '<div class="auto-actions">' +
            '<button type="button" class="files-btn files-btn-ghost" data-action="save">Save recipients</button>' +
            '<button type="button" class="files-btn files-btn-primary" data-action="run">Run now</button>' +
          '</div>' +
        '</article>'
      );
    }).join('');
  }

  function toggleHtml(job, field, label) {
    return (
      '<label class="auto-toggle">' +
        '<input type="checkbox" data-field="' + field + '"' + (job[field] ? ' checked' : '') + '>' +
        label +
      '</label>'
    );
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function runStatusClass(status) {
    if (status === 'ok') return 'is-ok';
    if (status === 'warning') return 'is-warn';
    if (status === 'error') return 'is-err';
    return 'is-off';
  }

  function runMessage(run) {
    var warns = ((run.detail || {}).warnings || []).filter(Boolean);
    if (warns.length) return warns.join('\n');
    return (run.error_message || '').trim();
  }

  var chatCloseTimer = null;

  function friendlyMessage(run) {
    var email = ((run.detail || {}).email) || {};
    if (email.reason === 'no_recipients') {
      return 'The Excel files were saved to Files, but email was skipped because no recipients are set. Add addresses under Email recipients.';
    }
    if (email.reason === 'email_not_configured') {
      return 'The Excel files were saved to Files, but email is not configured on this server yet.';
    }
    if (email.reason === 'no_attachments') {
      return 'Nothing was emailed because no Excel attachments were produced.';
    }
    return runMessage(run);
  }

  function hideMsg() {
    var chat = document.getElementById('autoChat');
    document.querySelectorAll('button.auto-pill[aria-expanded="true"]').forEach(function (el) {
      el.setAttribute('aria-expanded', 'false');
    });
    if (!chat || chat.hidden) return;
    chat.classList.remove('is-open');
    clearTimeout(chatCloseTimer);
    chatCloseTimer = setTimeout(function () {
      chat.hidden = true;
      chat.classList.remove('is-below', 'is-err');
    }, 180);
  }

  function placeChat(chat, btn) {
    var gap = 10;
    var pad = 12;
    var rect = btn.getBoundingClientRect();
    var width = chat.offsetWidth || 336;
    var height = chat.offsetHeight || 110;
    var scrollX = window.pageXOffset || document.documentElement.scrollLeft || 0;
    var scrollY = window.pageYOffset || document.documentElement.scrollTop || 0;
    var left = rect.left + scrollX;
    left = Math.min(Math.max(pad + scrollX, left), scrollX + window.innerWidth - width - pad);
    var below = rect.top - height - gap < pad;
    var top = below
      ? rect.bottom + scrollY + gap
      : rect.top + scrollY - height - gap;
    chat.classList.toggle('is-below', below);
    chat.style.left = Math.round(left) + 'px';
    chat.style.top = Math.round(top) + 'px';
    var nub = Math.max(16, Math.min(width - 30, rect.left + scrollX + rect.width / 2 - left - 7));
    chat.style.setProperty('--nub', nub + 'px');
    chat.style.transformOrigin = nub + 'px ' + (below ? '0%' : '100%');
  }

  function showMsg(btn, run) {
    var chat = document.getElementById('autoChat');
    var title = document.getElementById('autoChatTitle');
    var body = document.getElementById('autoChatBody');
    if (!chat || !title || !body) return;
    var text = friendlyMessage(run);
    if (!text) return;
    var isErr = run.status === 'error';
    title.textContent = isErr ? 'Error' : 'Warning';
    body.textContent = text;
    chat.classList.toggle('is-err', isErr);
    clearTimeout(chatCloseTimer);
    chat.hidden = false;
    chat.classList.remove('is-open');
    if (btn) btn.setAttribute('aria-expanded', 'true');
    placeChat(chat, btn);
    requestAnimationFrame(function () {
      placeChat(chat, btn);
      chat.classList.add('is-open');
    });
  }

  function renderRuns() {
    var body = document.getElementById('autoRunsBody');
    if (!body) return;
    hideMsg();
    if (!runs.length) {
      body.innerHTML = '<tr><td colspan="5" class="files-empty">No runs yet.</td></tr>';
      return;
    }
    body.innerHTML = runs.map(function (run) {
      var files = ((run.detail || {}).files || []).map(function (f) { return f.filename; }).filter(Boolean);
      var warn = ((run.detail || {}).warnings || []).join('; ');
      var detail = files.join(', ') || run.error_message || warn || '—';
      var cls = runStatusClass(run.status);
      var msg = runMessage(run);
      var canOpen = (run.status === 'warning' || run.status === 'error') && !!msg;
      var statusHtml = canOpen
        ? '<button type="button" class="auto-pill ' + cls + '" data-run-id="' + esc(run.id) + '" aria-expanded="false">' + esc(run.status) + '</button>'
        : '<span class="auto-pill ' + cls + '">' + esc(run.status) + '</span>';
      return (
        '<tr>' +
          '<td>' + esc(fmtWhen(run.started_at)) + '</td>' +
          '<td>' + esc(run.slug) + '</td>' +
          '<td>' + esc(run.trigger) + '</td>' +
          '<td>' + statusHtml + '</td>' +
          '<td>' + esc(detail) + '</td>' +
        '</tr>'
      );
    }).join('');
  }

  function load() {
    return api('/automations/api/jobs').then(function (body) {
      if (!body._ok) {
        toast(body.message || body.error || 'Could not load automations');
        return;
      }
      jobs = (body.jobs || body.data && body.data.jobs) || [];
      runs = (body.runs || body.data && body.data.runs) || [];
      if (body.data) {
        jobs = body.data.jobs || jobs;
        runs = body.data.runs || runs;
      }
      renderJobs();
      renderRuns();
    }).catch(function () {
      toast('Could not load automations');
    });
  }

  function patch(slug, payload) {
    return api('/automations/api/jobs/' + encodeURIComponent(slug), {
      method: 'PATCH',
      json: payload,
    }).then(function (body) {
      if (!body._ok) {
        toast(body.message || body.error || 'Could not save');
        return load();
      }
      toast('Saved');
      return load();
    });
  }

  document.addEventListener('change', function (ev) {
    var input = ev.target.closest('[data-field]');
    var card = ev.target.closest('.auto-card[data-slug]');
    if (!input || !card || input.getAttribute('data-field') === 'to_emails') return;
    var field = input.getAttribute('data-field');
    var payload = {};
    payload[field] = !!input.checked;
    patch(card.getAttribute('data-slug'), payload);
  });

  document.addEventListener('click', function (ev) {
    var statusBtn = ev.target.closest('button.auto-pill[data-run-id]');
    if (statusBtn) {
      ev.preventDefault();
      var runId = Number(statusBtn.getAttribute('data-run-id'));
      var run = runs.find(function (row) { return Number(row.id) === runId; });
      if (!run) return;
      if (statusBtn.getAttribute('aria-expanded') === 'true') {
        hideMsg();
        return;
      }
      showMsg(statusBtn, run);
      return;
    }
    if (!ev.target.closest('#autoChat')) hideMsg();

    var btn = ev.target.closest('[data-action]');
    if (btn) {
      var card = btn.closest('.auto-card[data-slug]');
      if (!card) return;
      var slug = card.getAttribute('data-slug');
      var action = btn.getAttribute('data-action');
      if (action === 'save') {
        var field = card.querySelector('[data-field="to_emails"]');
        patch(slug, { to_emails: field ? field.value : '' });
      }
      if (action === 'run') {
        btn.disabled = true;
        api('/automations/api/jobs/' + encodeURIComponent(slug) + '/run', { method: 'POST', json: {} })
          .then(function (body) {
            toast(body.message || body.error || (body._ok ? 'Run finished' : 'Run failed'));
            return load();
          })
          .finally(function () { btn.disabled = false; });
      }
    }
    if (ev.target.id === 'autoRefreshBtn') load();
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') hideMsg();
  });

  window.addEventListener('scroll', function () {
    var open = document.querySelector('button.auto-pill[aria-expanded="true"]');
    var chat = document.getElementById('autoChat');
    if (open && chat && !chat.hidden) placeChat(chat, open);
  }, true);

  window.addEventListener('resize', function () {
    var open = document.querySelector('button.auto-pill[aria-expanded="true"]');
    var chat = document.getElementById('autoChat');
    if (open && chat && !chat.hidden) placeChat(chat, open);
  });

  load();
})();
