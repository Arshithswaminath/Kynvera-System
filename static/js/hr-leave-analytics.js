/**
 * Leave Tracker analytics pages — Repeat Sick + Sick Trends.
 */
(function () {
  'use strict';

  function $(id) {
    return document.getElementById(id);
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function authHeaders() {
    var h = { Accept: 'application/json' };
    var token = null;
    try {
      token = localStorage.getItem('access_token');
    } catch (_) {}
    if (token) h.Authorization = 'Bearer ' + token;
    return h;
  }

  function unwrap(body) {
    if (!body) return {};
    if (body.data && typeof body.data === 'object') return body.data;
    return body;
  }

  function apiGet(url) {
    return fetch(url, {
      headers: authHeaders(),
      credentials: 'same-origin',
    }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok) {
          var msg = (body && (body.error || body.message)) || r.statusText || 'Request failed';
          throw new Error(msg);
        }
        return unwrap(body);
      });
    });
  }

  function logsLink(empId) {
    return '/hr/leave-tracker?tab=logs&amp;employee_id=' + encodeURIComponent(empId);
  }

  function filterQuery() {
    var params = [];
    var company = ($('ltAnCompany') && $('ltAnCompany').value) || 'all';
    if (company && company !== 'all') {
      params.push('company=' + encodeURIComponent(company));
    }
    var month = $('ltAnMonth') && $('ltAnMonth').value;
    if (month) {
      params.push('month=' + encodeURIComponent(month));
    }
    var from = $('ltAnDateFrom') && $('ltAnDateFrom').value;
    if (from) {
      params.push('date_from=' + encodeURIComponent(from));
    }
    var to = $('ltAnDateTo') && $('ltAnDateTo').value;
    if (to) {
      params.push('date_to=' + encodeURIComponent(to));
    }
    return params.length ? '?' + params.join('&') : '';
  }

  function renderRepeat(data) {
    var rows = data.rows || [];
    $('ltAnCount').textContent = data.count != null ? data.count : '—';
    $('ltAnRows').textContent = rows.length;
    var body = $('ltAnBody');
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="8" class="lt-empty">No staff with 2+ sick applications in the same month for this filter.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map(function (r) {
        return (
          '<tr>' +
          '<td>' +
          esc(r.emp_id) +
          '</td>' +
          '<td>' +
          esc(r.full_name) +
          '</td>' +
          '<td>' +
          esc(r.company) +
          '</td>' +
          '<td>' +
          esc(r.designation) +
          '</td>' +
          '<td>' +
          esc(r.month_label) +
          ' ' +
          esc(r.year) +
          '</td>' +
          '<td class="lt-num">' +
          esc(r.applications) +
          '</td>' +
          '<td class="lt-num">' +
          esc(r.days) +
          '</td>' +
          '<td><a class="lt-link" href="' +
          logsLink(r.employee_id) +
          '">View logs</a></td>' +
          '</tr>'
        );
      })
      .join('');
  }

  function fmtDay(v) {
    if (v == null || v === 0) return '—';
    return String(v);
  }

  function renderTrends(data) {
    var rows = data.rows || [];
    $('ltAnCount').textContent = data.count != null ? data.count : '—';
    if ($('ltAnRising')) {
      $('ltAnRising').textContent = data.rising_count != null ? data.rising_count : '—';
    }
    if ($('ltAnRisingLabel') && data.current_month_label) {
      $('ltAnRisingLabel').textContent = 'Rising · ' + data.current_month_label;
    }
    var body = $('ltAnBody');
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="12" class="lt-empty">No sick leave matches this filter.</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map(function (r, i) {
        var m = r.months || {};
        var trend =
          r.trend === 'rising'
            ? '<span class="lt-trend lt-trend-rising">Rising</span>'
            : '<span class="lt-trend">Active</span>';
        return (
          '<tr>' +
          '<td class="lt-num">' +
          (i + 1) +
          '</td>' +
          '<td>' +
          esc(r.emp_id) +
          '</td>' +
          '<td>' +
          esc(r.full_name) +
          '</td>' +
          '<td>' +
          esc(r.company) +
          '</td>' +
          '<td class="lt-num">' +
          esc(r.applications) +
          '</td>' +
          '<td class="lt-num">' +
          esc(r.days) +
          '</td>' +
          '<td class="lt-num">' +
          esc(fmtDay(m['8'])) +
          '</td>' +
          '<td class="lt-num">' +
          esc(fmtDay(m['9'])) +
          '</td>' +
          '<td class="lt-num">' +
          esc(fmtDay(m['10'])) +
          '</td>' +
          '<td class="lt-num">' +
          esc(fmtDay(m['11'])) +
          '</td>' +
          '<td class="lt-num">' +
          esc(fmtDay(m['12'])) +
          '</td>' +
          '<td>' +
          trend +
          '</td>' +
          '</tr>'
        );
      })
      .join('');
  }

  function load() {
    var root = $('ltAnalyticsRoot');
    if (!root) return;
    var mode = root.getAttribute('data-analytics');
    var qs = filterQuery();
    var url =
      mode === 'sick-trends'
        ? '/hr/api/leave-tracker/analytics/sick-trends' + qs
        : '/hr/api/leave-tracker/analytics/repeat-sick' + qs;

    apiGet(url)
      .then(function (data) {
        if (mode === 'sick-trends') renderTrends(data);
        else renderRepeat(data);
      })
      .catch(function (err) {
        var body = $('ltAnBody');
        if (body) {
          body.innerHTML =
            '<tr><td colspan="12" class="lt-empty">Failed to load: ' +
            esc(err.message || err) +
            '</td></tr>';
        }
      });
  }

  function bindFilters() {
    ['ltAnCompany', 'ltAnMonth', 'ltAnDateFrom', 'ltAnDateTo'].forEach(function (id) {
      var el = $(id);
      if (!el) return;
      el.addEventListener('change', load);
    });
  }

  function init() {
    if (!$('ltAnalyticsRoot')) return;
    bindFilters();
    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
