/**
 * Automations hub UI
 */
(function () {
  'use strict';

  var jobs = [];
  var runs = [];
  var runningBySlug = {};

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

  function isRunning(slug) {
    return !!runningBySlug[slug];
  }

  function spinnerHtml() {
    return '<span class="auto-spinner" aria-hidden="true"></span>';
  }

  function statusPill(job) {
    if (isRunning(job.slug)) {
      return '<span class="auto-pill is-running">' + spinnerHtml() + 'Running</span>';
    }
    if (job.linked) return '<span class="auto-pill is-linked">Report Generation</span>';
    if (!job.implemented) return '<span class="auto-pill is-soon">Coming soon</span>';
    if (!job.enabled) return '<span class="auto-pill is-off">Paused</span>';
    return '<span class="auto-pill">Enabled · ' + pad(job.schedule_hour) + ':' + pad(job.schedule_minute) + ' Dubai</span>';
  }

  function statusStrip(job) {
    if (isRunning(job.slug)) {
      return (
        '<div class="auto-status is-running">' +
          spinnerHtml() +
          '<div>' +
            '<p class="auto-status-label">In progress</p>' +
            '<p class="auto-status-value">Exporting Excel and sending email…</p>' +
          '</div>' +
        '</div>'
      );
    }
    var next = nextRunParts(job.schedule_hour, job.schedule_minute, !!job.enabled);
    var nextCol =
      '<div class="auto-status-col auto-status-next">' +
        '<p class="auto-status-label">Next run</p>' +
        '<p class="auto-status-value" data-next-run>' + esc(next.value) + '</p>' +
      '</div>';
    var blocks = [];
    if (job.last_success_at) {
      blocks.push(
        '<div class="auto-status is-ok">' +
          '<span class="auto-status-mark" aria-hidden="true"></span>' +
          '<div class="auto-status-col">' +
            '<p class="auto-status-label">Last success</p>' +
            '<p class="auto-status-value">' + esc(fmtWhen(job.last_success_at)) + '</p>' +
          '</div>' +
          nextCol +
        '</div>'
      );
    } else {
      blocks.push(
        '<div class="auto-status is-idle">' +
          '<span class="auto-status-mark" aria-hidden="true"></span>' +
          '<div class="auto-status-col">' +
            '<p class="auto-status-label">No runs yet</p>' +
            '<p class="auto-status-value">Run now, or wait for the daily schedule.</p>' +
          '</div>' +
          nextCol +
        '</div>'
      );
    }
    if (job.last_error) {
      blocks.push(
        '<div class="auto-status is-warn">' +
          '<span class="auto-status-mark" aria-hidden="true"></span>' +
          '<div>' +
            '<p class="auto-status-label">Note from last run</p>' +
            '<p class="auto-status-value">' + esc(job.last_error) + '</p>' +
          '</div>' +
        '</div>'
      );
    }
    return '<div class="auto-status-stack">' + blocks.join('') + '</div>';
  }

  function linkedStatusHtml(job) {
    var last = job.linked_last_send || null;
    var href = esc(job.linked_url || '/admin/mmr/');
    var body;
    if (!last || !last.sent_at) {
      body =
        '<div class="auto-status is-idle">' +
          '<span class="auto-status-mark" aria-hidden="true"></span>' +
          '<div class="auto-status-col">' +
            '<p class="auto-status-label">No report email yet</p>' +
            '<p class="auto-status-value">When Report Generation sends, the time and file show here.</p>' +
          '</div>' +
        '</div>';
    } else {
      var file = last.filename || 'Workbook attached';
      body =
        '<div class="auto-status is-ok">' +
          '<span class="auto-status-mark" aria-hidden="true"></span>' +
          '<div class="auto-status-col">' +
            '<p class="auto-status-label">Last email</p>' +
            '<p class="auto-status-value">' + esc(fmtWhen(last.sent_at)) + '</p>' +
          '</div>' +
          '<div class="auto-status-col">' +
            '<p class="auto-status-label">File</p>' +
            '<p class="auto-status-value auto-linked-file">' + esc(file) + '</p>' +
          '</div>' +
        '</div>';
    }
    return (
      '<div class="auto-status-stack">' + body + '</div>' +
      '<div class="auto-linked-actions">' +
        '<a class="files-btn files-btn-ghost" href="' + href + '">Open Report Generation</a>' +
      '</div>'
    );
  }

  function emailHint(job) {
    var recips = job.resolved_recipients || [];
    if (!job.send_email) return 'Off — files still save';
    if (recips.length === 1) return recips[0];
    if (recips.length > 1) return recips[0] + ' +' + (recips.length - 1);
    return 'Add at least one address';
  }

  function selectedModuleIds(job) {
    var ids = job.export_modules || [];
    if (!Array.isArray(ids)) ids = String(ids || '').split(',');
    return ids.map(function (id) { return String(id || '').trim(); }).filter(Boolean);
  }

  function filesHint(job) {
    var choices = job.module_choices || [];
    if (choices.length < 2) return job.files_hint || 'Excel into Files';
    var selected = selectedModuleIds(job);
    var labels = choices.filter(function (m) { return selected.indexOf(m.id) !== -1; })
      .map(function (m) { return m.label; });
    return labels.length ? labels.join(', ') : (job.files_hint || 'Excel into Files');
  }

  function modulePickerHtml(job) {
    var choices = job.module_choices || [];
    if (choices.length < 2) return '';
    var selected = selectedModuleIds(job);
    var running = isRunning(job.slug);
    var chips = choices.map(function (m) {
      var on = selected.indexOf(m.id) !== -1;
      return (
        '<label class="auto-mod' + (on ? ' is-on' : '') + (running ? ' is-disabled' : '') + '">' +
          '<input type="checkbox" data-module="' + esc(m.id) + '"' +
            (on ? ' checked' : '') + (running ? ' disabled' : '') + '>' +
          '<span>' + esc(m.label) + '</span>' +
        '</label>'
      );
    }).join('');
    return (
      '<div class="auto-modules">' +
        '<p class="auto-label">Modules</p>' +
        '<div class="auto-mod-row" role="group" aria-label="Modules to include">' + chips + '</div>' +
        '<p class="auto-field-hint">Excel backups only include the modules you pick.</p>' +
      '</div>'
    );
  }

  function nextRunParts(hour, minute, enabled) {
    var hh = pad(hour);
    var mm = pad(minute);
    if (!enabled) return { label: 'Next run', value: 'Paused' };
    try {
      var parts = new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Asia/Dubai',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      }).formatToParts(new Date());
      var nowH = parseInt((parts.find(function (p) { return p.type === 'hour'; }) || {}).value, 10);
      var nowM = parseInt((parts.find(function (p) { return p.type === 'minute'; }) || {}).value, 10);
      var dueToday = (nowH < hour) || (nowH === hour && nowM < minute);
      return {
        label: 'Next run',
        value: (dueToday ? 'Today' : 'Tomorrow') + ' at ' + hh + ':' + mm + ' GST'
      };
    } catch (e) {
      return { label: 'Next run', value: 'Daily at ' + hh + ':' + mm + ' Dubai' };
    }
  }

  function nextRunHint(hour, minute, enabled) {
    if (!enabled) return 'Paused — turn on to run daily';
    var next = nextRunParts(hour, minute, enabled);
    return 'Next run ' + next.value.replace(/^Today/, 'today').replace(/^Tomorrow/, 'tomorrow');
  }

  var TIME_PRESETS = [
    { time: '08:00', name: 'Morning' },
    { time: '12:00', name: 'Midday' },
    { time: '18:00', name: 'Evening' },
    { time: '20:00', name: 'Night' }
  ];

  var CLOCK_ICON =
    '<svg class="auto-clock-icon" xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.75" aria-hidden="true">' +
      '<circle cx="12" cy="12" r="8.25"/>' +
      '<path stroke-linecap="round" stroke-linejoin="round" d="M12 7.75V12l2.75 1.75"/>' +
    '</svg>';

  function parseTimeValue(value) {
    var raw = String(value == null ? '' : value).trim();
    if (!raw) return null;
    var bits = raw.split(/[:.]/);
    var hour;
    var minute;
    if (bits.length >= 2) {
      hour = parseInt(bits[0], 10);
      minute = parseInt(bits[1], 10);
    } else {
      var digits = raw.replace(/\D/g, '');
      if (digits.length === 3) {
        hour = parseInt(digits.slice(0, 1), 10);
        minute = parseInt(digits.slice(1), 10);
      } else if (digits.length >= 4) {
        hour = parseInt(digits.slice(0, 2), 10);
        minute = parseInt(digits.slice(2, 4), 10);
      } else {
        hour = parseInt(digits, 10);
        minute = 0;
      }
    }
    if (isNaN(hour) || hour < 0 || hour > 23) return null;
    if (isNaN(minute) || minute < 0 || minute > 59) return null;
    return { hour: hour, minute: minute };
  }

  function findJob(slug) {
    return jobs.find(function (item) { return item.slug === slug; });
  }

  function refreshScheduleChrome(slug) {
    var job = findJob(slug);
    var card = document.querySelector('.auto-card[data-slug="' + slug + '"]');
    if (!job || !card) return;
    var time = pad(job.schedule_hour) + ':' + pad(job.schedule_minute);
    var hint = card.querySelector('.auto-schedule .auto-opt-hint');
    if (hint) hint.textContent = nextRunHint(job.schedule_hour, job.schedule_minute, !!job.enabled);
    card.querySelectorAll('.auto-time-chip').forEach(function (chip) {
      chip.classList.toggle('is-on', chip.getAttribute('data-time') === time);
    });
    var active = document.activeElement;
    var hourEl = card.querySelector('[data-time-part="hour"]');
    var minEl = card.querySelector('[data-time-part="minute"]');
    if (hourEl && hourEl !== active) hourEl.value = pad(job.schedule_hour);
    if (minEl && minEl !== active) minEl.value = pad(job.schedule_minute);
    var pill = card.querySelector('.auto-card-top .auto-pill');
    if (pill && job.enabled && !isRunning(job.slug) && job.implemented) {
      pill.textContent = 'Enabled · ' + time + ' Dubai';
    }
    var nextEl = card.querySelector('[data-next-run]');
    if (nextEl) {
      nextEl.textContent = nextRunParts(job.schedule_hour, job.schedule_minute, !!job.enabled).value;
    }
  }

  function scheduleHtml(job) {
    var running = isRunning(job.slug);
    var on = !!job.enabled;
    var hour = parseInt(job.schedule_hour, 10);
    var minute = parseInt(job.schedule_minute, 10);
    if (isNaN(hour)) hour = 20;
    if (isNaN(minute)) minute = 0;
    var time = pad(hour) + ':' + pad(minute);
    var slug = esc(job.slug);
    var chips = TIME_PRESETS.map(function (preset) {
      return (
        '<button type="button" class="auto-time-chip' + (preset.time === time ? ' is-on' : '') +
          '" data-action="set-time" data-time="' + preset.time + '"' +
          (running ? ' disabled' : '') + '>' +
          '<span class="auto-time-chip-time">' + preset.time + '</span>' +
          '<span class="auto-time-chip-name">' + preset.name + '</span>' +
        '</button>'
      );
    }).join('');
    var lock = running ? ' disabled' : '';
    return (
      '<div class="auto-schedule' + (on ? ' is-on' : '') + (running ? ' is-disabled' : '') + '">' +
        '<label class="auto-opt auto-opt--bare' + (on ? ' is-on' : '') + (running ? ' is-disabled' : '') + '">' +
          '<input class="auto-opt-input" type="checkbox" data-field="enabled"' +
            (on ? ' checked' : '') + (running ? ' disabled' : '') + '>' +
          '<span class="auto-opt-copy">' +
            '<span class="auto-opt-title">Schedule</span>' +
            '<span class="auto-opt-hint">' + esc(nextRunHint(job.schedule_hour, job.schedule_minute, on)) + '</span>' +
          '</span>' +
          '<span class="auto-switch" aria-hidden="true"></span>' +
        '</label>' +
        '<div class="auto-schedule-editor">' +
          '<div class="auto-clock auto-time-pick" role="group" aria-labelledby="time-label-' + slug + '">' +
            CLOCK_ICON +
            '<div class="auto-clock-face">' +
              '<div class="auto-clock-head">' +
                '<p class="auto-clock-caption" id="time-label-' + slug + '">Daily time · Dubai</p>' +
                '<span class="auto-clock-tz">GST</span>' +
              '</div>' +
              '<div class="auto-clock-digits">' +
                '<label class="auto-clock-cell">' +
                  '<input class="auto-time-select" type="text" inputmode="numeric" maxlength="2"' +
                    ' data-time-part="hour" aria-label="Hour" autocomplete="off" spellcheck="false"' +
                    ' placeholder="HH" value="' + pad(hour) + '"' + lock + '>' +
                  '<span>Hour</span>' +
                '</label>' +
                '<span class="auto-time-colon" aria-hidden="true">:</span>' +
                '<label class="auto-clock-cell">' +
                  '<input class="auto-time-select" type="text" inputmode="numeric" maxlength="2"' +
                    ' data-time-part="minute" aria-label="Minute" autocomplete="off" spellcheck="false"' +
                    ' placeholder="MM" value="' + pad(minute) + '"' + lock + '>' +
                  '<span>Min</span>' +
                '</label>' +
              '</div>' +
            '</div>' +
            '<div class="auto-time-presets">' +
              '<p class="auto-time-presets-label">Quick pick</p>' +
              '<div class="auto-time-chips" role="group" aria-label="Suggested times">' + chips + '</div>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function optionHtml(job, field, title, hint) {
    var running = isRunning(job.slug);
    var on = !!job[field];
    return (
      '<label class="auto-opt' + (on ? ' is-on' : '') + (running ? ' is-disabled' : '') + '">' +
        '<input class="auto-opt-input" type="checkbox" data-field="' + field + '"' +
          (on ? ' checked' : '') + (running ? ' disabled' : '') + '>' +
        '<span class="auto-opt-copy">' +
          '<span class="auto-opt-title">' + esc(title) + '</span>' +
          '<span class="auto-opt-hint">' + esc(hint) + '</span>' +
        '</span>' +
        '<span class="auto-switch" aria-hidden="true"></span>' +
      '</label>'
    );
  }

  function renderJobs() {
    var root = document.getElementById('autoJobs');
    if (!root) return;
    if (!jobs.length) {
      root.innerHTML = '<p class="auto-empty">No jobs configured.</p>';
      return;
    }
    root.innerHTML = jobs.map(function (job) {
      if (job.linked) {
        return (
          '<article class="auto-card is-linked" data-slug="' + esc(job.slug) + '">' +
            '<div class="auto-card-top">' +
              '<div>' +
                '<h2 class="auto-card-title">' + esc(job.title) + '</h2>' +
                '<p class="auto-card-desc">' + esc(job.description) + '</p>' +
              '</div>' +
              statusPill(job) +
            '</div>' +
            linkedStatusHtml(job) +
          '</article>'
        );
      }
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
      var running = isRunning(job.slug);
      return (
        '<article class="auto-card' + (running ? ' is-running' : '') + '" data-slug="' + esc(job.slug) + '"' +
          (running ? ' aria-busy="true"' : '') + '>' +
          '<div class="auto-card-top">' +
            '<div>' +
              '<h2 class="auto-card-title">' + esc(job.title) + '</h2>' +
              '<p class="auto-card-desc">' + esc(job.description) + '</p>' +
            '</div>' +
            statusPill(job) +
          '</div>' +
          statusStrip(job) +
          '<p class="auto-section-label">Delivery</p>' +
          '<div class="auto-opts">' +
            scheduleHtml(job) +
            optionHtml(job, 'save_to_files', 'Save to Files', filesHint(job)) +
            optionHtml(job, 'send_email', 'Email', emailHint(job)) +
            optionHtml(job, 'sync_drive', 'Drive sync', 'When Google Drive is connected') +
          '</div>' +
          modulePickerHtml(job) +
          '<div class="auto-recipients' + (job.send_email ? '' : ' is-dim') + '">' +
            '<label class="auto-label" for="to-' + esc(job.slug) + '">Email recipients</label>' +
            '<div class="auto-recipients-row">' +
              '<input class="auto-input" id="to-' + esc(job.slug) + '" data-field="to_emails" value="' +
                esc(job.to_emails || '') + '" placeholder="name@injaaz.ae, ops@injaaz.ae"' +
                (running ? ' disabled' : '') + '>' +
              '<button type="button" class="files-btn files-btn-ghost" data-action="save"' +
                (running ? ' disabled' : '') + '>Save</button>' +
            '</div>' +
            '<p class="auto-field-hint">Comma-separated. Saved for the next run.</p>' +
          '</div>' +
          '<div class="auto-actions">' +
            '<button type="button" class="files-btn files-btn-primary' + (running ? ' is-running' : '') +
              '" data-action="run"' + (running ? ' disabled aria-busy="true"' : '') + '>' +
              (running ? spinnerHtml() + 'Running…' : 'Run now') +
            '</button>' +
          '</div>' +
        '</article>'
      );
    }).join('');
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function runStatusClass(status) {
    if (status === 'running') return 'is-running';
    if (status === 'ok') return 'is-ok';
    if (status === 'warning') return 'is-warn';
    if (status === 'error') return 'is-err';
    return 'is-off';
  }

  function pendingRuns() {
    return Object.keys(runningBySlug).map(function (slug) {
      var info = runningBySlug[slug] || {};
      return {
        id: 'pending:' + slug,
        pending: true,
        status: 'running',
        trigger: 'manual',
        started_at: info.startedAt,
        slug: slug,
        view: {
          job_title: info.title || slug,
          files: [],
          email: { line: '', outcome: '' },
          warnings: []
        }
      };
    });
  }

  function fallbackEmailLine(email) {
    var recips = email.recipients || [];
    if (email.sent || email.outcome === 'sent') {
      if (!recips.length) return 'Sent';
      if (recips.length === 1) return 'Sent to ' + recips[0];
      return 'Sent to ' + recips[0] + ' +' + (recips.length - 1);
    }
    if (email.reason === 'send_email_off') return 'Email off';
    if (email.reason === 'no_recipients') return 'Not sent — no recipients';
    if (email.reason === 'email_not_configured') return 'Not sent — email not configured';
    if (email.reason === 'no_attachments') return 'Not sent — no attachments';
    if (email.skipped === false || email.outcome === 'failed') return 'Email send failed';
    return 'Email not sent';
  }

  function runView(run) {
    if (run && run.view && run.view.email) return run.view;
    var detail = (run && run.detail) || {};
    var email = detail.email || {};
    var files = detail.files || [];
    var outcome = email.outcome || (email.sent ? 'sent' : (email.skipped === false ? 'failed' : 'skipped'));
    return {
      job_title: (run && run.slug) || 'Automation',
      files: files,
      email: {
        outcome: outcome,
        reason: email.reason || '',
        recipients: email.recipients || [],
        subject: email.subject || '',
        attachment_names: email.attachment_names || [],
        line: fallbackEmailLine(email),
        note: '',
        reason_label: ''
      },
      warnings: detail.warnings || []
    };
  }

  function fmtSize(n) {
    n = Number(n) || 0;
    if (!n) return '';
    if (n < 1024) return n + ' B';
    if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
    return (n / 1048576).toFixed(1) + ' MB';
  }

  function emailOutcomeClass(outcome) {
    if (outcome === 'sent') return 'is-ok';
    if (outcome === 'failed') return 'is-err';
    return 'is-warn';
  }

  function emailOutcomeLabel(outcome) {
    if (outcome === 'sent') return 'Sent';
    if (outcome === 'failed') return 'Failed';
    return 'Not sent';
  }

  function triggerLabel(trigger) {
    if (trigger === 'scheduler') return 'Scheduled';
    if (trigger === 'catchup') return 'Catch-up';
    if (trigger === 'manual') return 'Manual';
    return trigger || '—';
  }

  var modalLastFocus = null;
  var openRunId = null;

  function runModalEl() {
    return document.getElementById('autoRunModal');
  }

  function closeRunModal() {
    var modal = runModalEl();
    if (!modal || !modal.open) return;
    if (typeof modal.close === 'function') modal.close();
  }

  function onRunModalClosed() {
    document.documentElement.style.overflow = '';
    document.body.style.overflow = '';
    openRunId = null;
    if (modalLastFocus && typeof modalLastFocus.focus === 'function') {
      try { modalLastFocus.focus(); } catch (e) { /* ignore */ }
    }
    modalLastFocus = null;
  }

  function fillRunModal(run) {
    var view = runView(run);
    var email = view.email || {};
    var title = document.getElementById('autoRunTitle');
    var outcomeEl = document.getElementById('autoRunOutcome');
    var meta = document.getElementById('autoRunMeta');
    var recEl = document.getElementById('autoRunRecipients');
    var filesEl = document.getElementById('autoRunFiles');
    var emailEl = document.getElementById('autoRunEmail');
    var notesEl = document.getElementById('autoRunNotes');
    var notesSec = document.getElementById('autoRunNotesSection');
    if (title) title.textContent = view.job_title || run.slug || 'Run';
    if (outcomeEl) {
      outcomeEl.className = 'auto-outcome ' + emailOutcomeClass(email.outcome);
      outcomeEl.innerHTML =
        '<p class="auto-outcome-label">Email</p>' +
        '<p class="auto-outcome-line">' + esc(email.line || emailOutcomeLabel(email.outcome)) + '</p>' +
        '<p class="auto-outcome-note">' + esc(email.note || email.reason_label || '') + '</p>';
    }
    if (meta) {
      meta.innerHTML =
        '<dt>When</dt><dd>' + esc(fmtWhen(run.started_at)) + '</dd>' +
        '<dt>Finished</dt><dd>' + esc(fmtWhen(run.finished_at)) + '</dd>' +
        '<dt>Job</dt><dd>' + esc((view.job_title || run.slug || '—') + (run.slug ? ' · ' + run.slug : '')) + '</dd>' +
        '<dt>Trigger</dt><dd>' + esc(triggerLabel(run.trigger)) + '</dd>' +
        '<dt>Status</dt><dd><span class="auto-pill ' + runStatusClass(run.status) + '">' + esc(run.status || '—') + '</span></dd>';
    }
    if (recEl) {
      var recips = email.recipients || [];
      if (recips.length) {
        recEl.innerHTML = '<div class="auto-chips">' + recips.map(function (addr) {
          return '<span class="auto-chip">' + esc(addr) + '</span>';
        }).join('') + '</div>';
      } else {
        recEl.innerHTML = '<p class="auto-muted">' +
          esc(email.reason_label || 'Recipients were not recorded on this run.') + '</p>';
      }
    }
    if (filesEl) {
      var files = view.files || [];
      if (!files.length) {
        filesEl.innerHTML = '<li class="auto-muted">No files were saved on this run.</li>';
      } else {
        filesEl.innerHTML = files.map(function (file) {
          var bits = [file.folder, fmtSize(file.size_bytes)].filter(Boolean).join(' · ');
          var dl = file.item_id
            ? '<button type="button" class="files-btn files-btn-ghost" data-download-item="' +
              esc(file.item_id) + '">Download</button>'
            : '';
          return (
            '<li class="auto-file-row">' +
              '<div>' +
                '<p class="auto-file-name">' + esc(file.filename || file.label || 'File') + '</p>' +
                (bits ? '<p class="auto-file-meta">' + esc(bits) + '</p>' : '') +
              '</div>' + dl +
            '</li>'
          );
        }).join('');
      }
    }
    if (emailEl) {
      var attach = (email.attachment_names || []).filter(Boolean);
      emailEl.innerHTML =
        '<div class="auto-email-kv">' +
          '<p><strong>Outcome.</strong> ' + esc(emailOutcomeLabel(email.outcome)) + '</p>' +
          '<p><strong>Subject.</strong> ' + esc(email.subject || '—') + '</p>' +
          '<p><strong>Attachments on the message.</strong> ' +
            esc(attach.length ? attach.join(', ') : 'None') + '</p>' +
        '</div>';
    }
    var notes = (view.warnings || []).filter(Boolean);
    if (run.error_message && notes.indexOf(run.error_message) === -1 && run.status === 'error') {
      notes = [run.error_message].concat(notes);
    }
    if (notesSec && notesEl) {
      if (!notes.length) {
        notesSec.hidden = true;
        notesEl.innerHTML = '';
      } else {
        notesSec.hidden = false;
        notesEl.innerHTML = notes.map(function (n) {
          return '<li>' + esc(n) + '</li>';
        }).join('');
      }
    }
  }

  function runIdKey(id) {
    return String(id == null ? '' : id);
  }

  function isExternalRun(run) {
    if (!run) return false;
    if (run.external) return true;
    return runIdKey(run.id).indexOf('mmr-cycle-') === 0;
  }

  function findRunById(id) {
    var key = runIdKey(id);
    return runs.find(function (item) { return runIdKey(item.id) === key; });
  }

  function openRunModal(run) {
    var modal = runModalEl();
    if (!modal || !run) return;
    modalLastFocus = document.activeElement;
    openRunId = runIdKey(run.id);
    fillRunModal(run);
    if (!modal.open && typeof modal.showModal === 'function') {
      modal.showModal();
    }
    document.documentElement.style.overflow = 'hidden';
    document.body.style.overflow = 'hidden';
    var closeBtn = document.getElementById('autoRunClose');
    if (closeBtn) closeBtn.focus();
    if (isExternalRun(run)) return;
    api('/automations/api/runs/' + encodeURIComponent(run.id)).then(function (body) {
      if (!body._ok || runIdKey(openRunId) !== runIdKey(run.id)) return;
      var fresh = body.run || (body.data && body.data.run);
      if (!fresh) return;
      var idx = runs.findIndex(function (row) { return runIdKey(row.id) === runIdKey(fresh.id); });
      if (idx >= 0) runs[idx] = fresh;
      fillRunModal(fresh);
    }).catch(function () { /* list payload is enough */ });
  }

  function downloadItem(id) {
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
      .catch(function (e) { toast(e.message || 'Download failed'); });
  }

  function renderRuns() {
    var body = document.getElementById('autoRunsBody');
    var wrap = document.querySelector('.auto-runs');
    if (!body) return;
    var rows = pendingRuns().concat(runs);
    var busy = Object.keys(runningBySlug).length > 0;
    if (wrap) wrap.setAttribute('aria-busy', busy ? 'true' : 'false');
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="5" class="files-empty">No runs yet.</td></tr>';
      return;
    }
    body.innerHTML = rows.map(function (run) {
      if (run.pending) {
        var title = (run.view && run.view.job_title) || run.slug || 'Automation';
        return (
          '<tr class="auto-run-row is-running" aria-busy="true">' +
            '<td>' + esc(fmtWhen(run.started_at)) + '</td>' +
            '<td>' + esc(title) + '</td>' +
            '<td>manual</td>' +
            '<td><span class="auto-pill is-running">' + spinnerHtml() + 'Running</span></td>' +
            '<td><span class="auto-detail-main">Preparing Excel files…</span>' +
              '<span class="auto-detail-sub">Email will send when the export finishes.</span></td>' +
          '</tr>'
        );
      }
      var view = runView(run);
      var files = (view.files || []).map(function (f) { return f.filename; }).filter(Boolean);
      var warn = (view.warnings || []).join('; ');
      var detail = files.join(', ') || run.error_message || warn || '—';
      var line = (view.email && view.email.line) || '';
      var cls = runStatusClass(run.status);
      return (
        '<tr class="auto-run-row" tabindex="0" data-run-id="' + esc(run.id) + '">' +
          '<td>' + esc(fmtWhen(run.started_at)) + '</td>' +
          '<td>' + esc(view.job_title || run.slug) + '</td>' +
          '<td>' + esc(triggerLabel(run.trigger)) + '</td>' +
          '<td><span class="auto-pill ' + cls + '">' + esc(run.status) + '</span></td>' +
          '<td><span class="auto-detail-main">' + esc(detail) + '</span>' +
            (line ? '<span class="auto-detail-sub">' + esc(line) + '</span>' : '') +
          '</td>' +
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

  function patch(slug, payload, opts) {
    opts = opts || {};
    return api('/automations/api/jobs/' + encodeURIComponent(slug), {
      method: 'PATCH',
      json: payload,
    }).then(function (body) {
      if (!body._ok) {
        toast(body.message || body.error || 'Could not save');
        return load();
      }
      toast('Saved');
      var saved = body.job || (body.data && body.data.job);
      var current = findJob(slug);
      if (opts.keepEditor && saved && current) {
        if (opts.expected && (
          Number(current.schedule_hour) !== opts.expected.hour ||
          Number(current.schedule_minute) !== opts.expected.minute
        )) {
          return;
        }
        Object.assign(current, saved);
        refreshScheduleChrome(slug);
        return;
      }
      return load();
    });
  }

  function saveScheduleTime(slug, value) {
    var parsed = parseTimeValue(value);
    if (!parsed) return;
    var job = findJob(slug);
    if (job && Number(job.schedule_hour) === parsed.hour && Number(job.schedule_minute) === parsed.minute) {
      return;
    }
    if (job) {
      job.schedule_hour = parsed.hour;
      job.schedule_minute = parsed.minute;
      refreshScheduleChrome(slug);
    }
    return patch(slug, {
      schedule_hour: parsed.hour,
      schedule_minute: parsed.minute
    }, { keepEditor: true, expected: parsed });
  }

  function timeParts(card) {
    return {
      hourEl: card.querySelector('[data-time-part="hour"]'),
      minEl: card.querySelector('[data-time-part="minute"]')
    };
  }

  function timeFromCard(card) {
    var parts = timeParts(card);
    if (!parts.hourEl || !parts.minEl) return '';
    return parts.hourEl.value + ':' + parts.minEl.value;
  }

  function fillTimeParts(card, parsed) {
    var parts = timeParts(card);
    if (!parts.hourEl || !parts.minEl || !parsed) return;
    parts.hourEl.value = pad(parsed.hour);
    parts.minEl.value = pad(parsed.minute);
  }

  function revertTimeParts(card) {
    var job = findJob(card.getAttribute('data-slug'));
    if (!job) return;
    fillTimeParts(card, { hour: job.schedule_hour, minute: job.schedule_minute });
  }

  function commitTimeFromCard(card) {
    var parsed = parseTimeValue(timeFromCard(card));
    if (!parsed) {
      revertTimeParts(card);
      return;
    }
    fillTimeParts(card, parsed);
    saveScheduleTime(card.getAttribute('data-slug'), pad(parsed.hour) + ':' + pad(parsed.minute));
  }

  document.addEventListener('focusin', function (ev) {
    var part = ev.target.closest('.auto-time-select[data-time-part]');
    if (part && typeof part.select === 'function') part.select();
  });

  document.addEventListener('input', function (ev) {
    var part = ev.target.closest('[data-time-part]');
    if (!part) return;
    var pick = part.closest('.auto-time-pick');
    var digits = part.value.replace(/\D/g, '').slice(0, 2);
    part.value = digits;
    if (part.getAttribute('data-time-part') === 'hour' && digits.length === 2 && pick) {
      var minEl = pick.querySelector('[data-time-part="minute"]');
      if (minEl) minEl.focus();
    }
  });

  document.addEventListener('paste', function (ev) {
    var part = ev.target.closest('[data-time-part]');
    if (!part) return;
    var text = '';
    try { text = (ev.clipboardData || window.clipboardData).getData('text') || ''; } catch (e) { return; }
    var parsed = parseTimeValue(text);
    if (!parsed) return;
    ev.preventDefault();
    var card = part.closest('.auto-card[data-slug]');
    if (!card) return;
    fillTimeParts(card, parsed);
    saveScheduleTime(card.getAttribute('data-slug'), pad(parsed.hour) + ':' + pad(parsed.minute));
  });

  document.addEventListener('keydown', function (ev) {
    var part = ev.target.closest('[data-time-part]');
    if (!part) return;
    var pick = part.closest('.auto-time-pick');
    var card = part.closest('.auto-card[data-slug]');
    if (ev.key === 'Enter') {
      ev.preventDefault();
      if (card) commitTimeFromCard(card);
      part.blur();
      return;
    }
    if ((ev.key === ':' || ev.key === '.') && part.getAttribute('data-time-part') === 'hour' && pick) {
      ev.preventDefault();
      var minEl = pick.querySelector('[data-time-part="minute"]');
      if (minEl) minEl.focus();
    }
  });

  document.addEventListener('focusout', function (ev) {
    var pick = ev.target.closest('.auto-time-pick');
    if (!pick) return;
    var next = ev.relatedTarget;
    if (next && pick.contains(next)) return;
    var card = pick.closest('.auto-card[data-slug]');
    if (card) commitTimeFromCard(card);
  });

  document.addEventListener('change', function (ev) {
    var card = ev.target.closest('.auto-card[data-slug]');
    if (card && card.classList.contains('is-linked')) return;
    if (ev.target.closest('[data-time-part]')) return;
    var moduleInput = ev.target.closest('[data-module]');
    if (moduleInput && card) {
      var picked = [];
      card.querySelectorAll('[data-module]').forEach(function (el) {
        if (el.checked) picked.push(el.getAttribute('data-module'));
      });
      if (!picked.length) {
        moduleInput.checked = true;
        var wrap = moduleInput.closest('.auto-mod');
        if (wrap) wrap.classList.add('is-on');
        toast('Keep at least one module');
        return;
      }
      patch(card.getAttribute('data-slug'), { export_modules: picked });
      return;
    }
    var input = ev.target.closest('[data-field]');
    if (!input || !card || input.getAttribute('data-field') === 'to_emails') return;
    var field = input.getAttribute('data-field');
    var payload = {};
    payload[field] = !!input.checked;
    patch(card.getAttribute('data-slug'), payload);
  });

  document.addEventListener('click', function (ev) {
    var downloadBtn = ev.target.closest('[data-download-item]');
    if (downloadBtn) {
      ev.preventDefault();
      ev.stopPropagation();
      downloadItem(downloadBtn.getAttribute('data-download-item'));
      return;
    }
    if (ev.target.id === 'autoRunClose' || ev.target.closest('#autoRunClose')) {
      ev.preventDefault();
      closeRunModal();
      return;
    }
    var row = ev.target.closest('tr.auto-run-row[data-run-id]');
    if (row) {
      var run = findRunById(row.getAttribute('data-run-id'));
      if (run) openRunModal(run);
      return;
    }

    var btn = ev.target.closest('[data-action]');
    if (btn) {
      var card = btn.closest('.auto-card[data-slug]');
      if (!card || card.classList.contains('is-linked')) return;
      var slug = card.getAttribute('data-slug');
      var action = btn.getAttribute('data-action');
      if (action === 'set-time') {
        saveScheduleTime(slug, btn.getAttribute('data-time'));
        return;
      }
      if (action === 'save') {
        var field = card.querySelector('[data-field="to_emails"]');
        patch(slug, { to_emails: field ? field.value : '' });
      }
      if (action === 'run') {
        if (runningBySlug[slug]) return;
        var job = jobs.find(function (item) { return item.slug === slug; }) || {};
        runningBySlug[slug] = {
          title: job.title || slug,
          startedAt: new Date().toISOString()
        };
        renderJobs();
        renderRuns();
        toast('Backup started…');
        api('/automations/api/jobs/' + encodeURIComponent(slug) + '/run', { method: 'POST', json: {} })
          .then(function (body) {
            toast(body.message || body.error || (body._ok ? 'Run finished' : 'Run failed'));
          })
          .catch(function () {
            toast('Run failed');
          })
          .finally(function () {
            delete runningBySlug[slug];
            return load();
          });
      }
    }
    if (ev.target.id === 'autoRefreshBtn') load();
  });

  document.addEventListener('keydown', function (ev) {
    if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.closest('tr.auto-run-row[data-run-id]')) {
      ev.preventDefault();
      var keyed = ev.target.closest('tr.auto-run-row[data-run-id]');
      var keyedRun = findRunById(keyed.getAttribute('data-run-id'));
      if (keyedRun) openRunModal(keyedRun);
    }
  });

  var runModal = runModalEl();
  if (runModal) {
    runModal.addEventListener('close', onRunModalClosed);
    runModal.addEventListener('click', function (ev) {
      if (ev.target === runModal) closeRunModal();
    });
  }

  load();
})();
