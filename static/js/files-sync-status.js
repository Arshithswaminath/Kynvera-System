/**
 * Navbar Files sync chip — polls /files/api/sync-status so progress
 * survives leaving the Files page.
 */
(function () {
  'use strict';

  var POLL_MS = 2000;
  var DISMISS_KEY = 'filesSyncDismissedJobId';
  var timer = null;
  var lastJobId = null;
  var watching = false;

  function authHeaders() {
    var h = {};
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

  function dismissedId() {
    try { return sessionStorage.getItem(DISMISS_KEY) || ''; } catch (e) { return ''; }
  }

  function setDismissed(id) {
    try { sessionStorage.setItem(DISMISS_KEY, id || ''); } catch (e) { /* ignore */ }
  }

  function els() {
    return {
      chip: document.getElementById('filesSyncChip'),
      label: document.getElementById('filesSyncChipLabel'),
      fill: document.getElementById('filesSyncChipBarFill'),
      link: document.getElementById('filesSyncChipLink'),
      close: document.getElementById('filesSyncChipClose'),
    };
  }

  function hideChip() {
    var chip = els().chip;
    if (chip) {
      chip.hidden = true;
      chip.setAttribute('data-state', 'idle');
    }
  }

  function folderHref(job) {
    var id = job && job.folder_id;
    if (id) return '/files/?folder=' + encodeURIComponent(id);
    return '/files/';
  }

  function render(job) {
    var ui = els();
    if (!ui.chip) return;
    if (!job || !job.job_id) {
      hideChip();
      return;
    }
    if (dismissedId() === String(job.job_id)) {
      hideChip();
      return;
    }

    lastJobId = job.job_id;
    var status = job.status || 'running';
    ui.chip.hidden = false;
    ui.chip.setAttribute('data-state', status === 'running' ? 'running' : (status === 'error' ? 'error' : 'done'));

    var total = job.total || 0;
    var done = job.done || 0;
    var pct = Math.max(0, Math.min(100, parseInt(job.progress, 10) || 0));
    if (ui.fill) ui.fill.style.width = pct + '%';

    if (status === 'running') {
      if (!total) {
        ui.label.textContent = job.message || 'Syncing…';
      } else if (!done) {
        ui.label.textContent = total === 1 ? 'Syncing 1 file' : ('Syncing ' + total + ' files');
      } else {
        ui.label.textContent = 'Syncing ' + done + ' of ' + total;
      }
      if (ui.link) ui.link.hidden = true;
    } else if (status === 'error') {
      ui.label.textContent = job.message || 'Sync failed';
      if (ui.link) {
        ui.link.hidden = false;
        ui.link.href = folderHref(job);
        ui.link.textContent = 'Check folder';
      }
    } else {
      ui.label.textContent = 'Sync completed';
      if (ui.link) {
        ui.link.hidden = false;
        ui.link.href = folderHref(job);
        ui.link.textContent = 'Check folder';
      }
    }
  }

  function stopPoll() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function fetchStatus() {
    return fetch('/files/api/sync-status', {
      headers: authHeaders(),
      credentials: 'same-origin',
    }).then(function (res) {
      if (res.status === 401 || res.status === 403 || res.status === 404) {
        hideChip();
        stopPoll();
        return null;
      }
      return res.json().then(function (data) {
        if (!data || data.success === false) return null;
        return data.job || null;
      });
    }).catch(function () { return null; });
  }

  function tick() {
    fetchStatus().then(function (job) {
      render(job);
      if (job && job.status === 'running') {
        timer = setTimeout(tick, POLL_MS);
        return;
      }
      if (watching && job && (job.status === 'done' || job.status === 'error')) {
        watching = false;
        try {
          window.dispatchEvent(new CustomEvent('files-sync-complete', { detail: job }));
        } catch (e) { /* ignore */ }
      }
      stopPoll();
    });
  }

  function start(opts) {
    opts = opts || {};
    watching = !!opts.watch;
    stopPoll();
    tick();
  }

  window.FilesSyncStatus = {
    start: function () { start({ watch: true }); },
    refresh: function () { start({}); },
  };

  document.addEventListener('DOMContentLoaded', function () {
    var ui = els();
    if (ui.close) {
      ui.close.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (lastJobId) setDismissed(String(lastJobId));
        hideChip();
        stopPoll();
      });
    }
    start({});
  });
})();
