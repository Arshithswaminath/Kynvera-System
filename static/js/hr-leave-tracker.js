/**
 * Leave Tracker — Sick / Annual staff master + Leave Logs (source of truth)
 */
(function () {
  'use strict';

  var MONTHS = [8, 9, 10, 11, 12];
  var MONTH_LABELS = { 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec' };
  var YEAR = 2026;
  var WINDOW_START = new Date(2026, 7, 1);
  var WINDOW_END = new Date(2026, 11, 31);

  var state = {
    employees: [],
    directory: [], // full unfiltered staff for typeahead
    plans: [],
    logs: [],
    tab: 'sick',
    alertLevel: '', // '' | approaching | exhausted
    selectedLogEmp: null,
    selectedPlanEmp: null,
    personEmp: null,
    colFilters: {
      emp_id: '',
      full_name: '',
      designation: '',
      company: '',
    },
    logColFilters: {
      log_leave_from: '',
      log_leave_to: '',
      log_emp_id: '',
      log_full_name: '',
      log_leave_type: '',
      log_days: '',
      log_notes: '',
      log_created: '',
      log_edited: '',
    },
    colFilterKey: null,
    colFilterSelected: null, // Set of exact values when using checklist
  };

  function $(id) {
    return document.getElementById(id);
  }

  function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /** In-app confirm (replaces window.confirm). Resolves true/false. */
  function confirmDialog(opts) {
    var options = opts || {};
    var title = options.title || 'Confirm';
    var message = options.message || 'Are you sure?';
    var confirmLabel = options.confirmLabel || 'Confirm';
    var cancelLabel = options.cancelLabel || 'Cancel';
    var danger = options.danger !== false;

    return new Promise(function (resolve) {
      var backdrop = document.getElementById('ltConfirmModal');
      if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.id = 'ltConfirmModal';
        backdrop.className = 'hh-modal-backdrop lt-confirm-backdrop';
        backdrop.setAttribute('role', 'dialog');
        backdrop.setAttribute('aria-modal', 'true');
        backdrop.innerHTML =
          '<div class="hh-modal hh-confirm-modal">' +
          '<h2 id="ltConfirmTitle"></h2>' +
          '<p class="hh-modal-sub" id="ltConfirmMessage"></p>' +
          '<div class="hh-modal-actions">' +
          '<button type="button" class="hh-btn hh-btn-ghost" data-lt-confirm-cancel></button>' +
          '<button type="button" class="hh-btn" data-lt-confirm-ok></button>' +
          '</div>' +
          '</div>';
        document.body.appendChild(backdrop);
      }

      var titleEl = backdrop.querySelector('#ltConfirmTitle');
      var msgEl = backdrop.querySelector('#ltConfirmMessage');
      var cancelBtn = backdrop.querySelector('[data-lt-confirm-cancel]');
      var okBtn = backdrop.querySelector('[data-lt-confirm-ok]');

      titleEl.textContent = title;
      msgEl.textContent = message;
      msgEl.style.whiteSpace = 'pre-line';
      cancelBtn.textContent = cancelLabel;
      okBtn.textContent = confirmLabel;
      okBtn.className = 'hh-btn ' + (danger ? 'hh-btn-danger' : 'hh-btn-primary');
      backdrop.setAttribute('aria-labelledby', 'ltConfirmTitle');

      function cleanup(result) {
        backdrop.classList.remove('open');
        backdrop.removeEventListener('click', onBackdrop);
        cancelBtn.removeEventListener('click', onCancel);
        okBtn.removeEventListener('click', onOk);
        document.removeEventListener('keydown', onKey);
        resolve(result);
      }

      function onCancel() {
        cleanup(false);
      }
      function onOk() {
        cleanup(true);
      }
      function onBackdrop(e) {
        if (e.target === backdrop) cleanup(false);
      }
      function onKey(e) {
        if (e.key === 'Escape') cleanup(false);
      }

      cancelBtn.addEventListener('click', onCancel);
      okBtn.addEventListener('click', onOk);
      backdrop.addEventListener('click', onBackdrop);
      document.addEventListener('keydown', onKey);

      backdrop.classList.add('open');
      okBtn.focus();
    });
  }

  function alertLabel(level) {
    if (level === 'warning') return 'Approaching limit';
    if (level === 'critical') return 'Nearly exhausted';
    if (level === 'exhausted') return 'Exhausted';
    return '';
  }

  function fmtDays(v) {
    if (v == null || v === '') return '—';
    var n = Number(v);
    if (Number.isNaN(n)) return '—';
    return n % 1 === 0 ? String(n) : String(Math.round(n * 10) / 10);
  }

  function showImportResult(msg, isError) {
    var el = $('ltImportResult');
    if (!el) return;
    el.hidden = false;
    el.textContent = msg;
    el.classList.toggle('has-errors', !!isError);
    setTimeout(function () {
      el.hidden = true;
    }, 8000);
  }

  function queryParams() {
    var q = ($('ltSearch') && $('ltSearch').value) || '';
    var company = ($('ltCompany') && $('ltCompany').value) || 'all';
    var month = ($('ltMonth') && $('ltMonth').value) || '';
    var alerts = $('ltAlertsOnly') && $('ltAlertsOnly').checked;
    var params = new URLSearchParams();
    if (q.trim()) params.set('q', q.trim());
    if (company && company !== 'all') params.set('company', company);
    if (month) params.set('month', month);
    if (state.alertLevel) params.set('alert_level', state.alertLevel);
    else if (alerts) params.set('alerts_only', '1');
    return params.toString();
  }

  function logsQueryParams() {
    var params = new URLSearchParams();
    var q =
      (($('ltLogsSearch') && $('ltLogsSearch').value) ||
        ($('ltSearch') && $('ltSearch').value) ||
        '').trim();
    var company = ($('ltCompany') && $('ltCompany').value) || 'all';
    var lt = ($('ltLogTypeFilter') && $('ltLogTypeFilter').value) || 'all';
    if ($('ltLogCompanyFilter')) company = $('ltLogCompanyFilter').value || 'all';
    var month = ($('ltMonth') && $('ltMonth').value) || '';
    var leaveFrom = ($('ltLogLeaveFrom') && $('ltLogLeaveFrom').value) || '';
    var leaveTo = ($('ltLogLeaveTo') && $('ltLogLeaveTo').value) || '';
    if (q) params.set('q', q);
    if (company && company !== 'all') params.set('company', company);
    if (lt && lt !== 'all') params.set('leave_type', lt);
    if (month) params.set('month', month);
    if (leaveFrom) params.set('leave_from', leaveFrom);
    if (leaveTo) params.set('leave_to', leaveTo);
    if (state.alertLevel) params.set('alert_level', state.alertLevel);
    else if ($('ltAlertsOnly') && $('ltAlertsOnly').checked) params.set('alerts_only', '1');
    return params.toString();
  }

  function authHeaders() {
    var h = {};
    try {
      if (typeof getAuthHeaders === 'function') return getAuthHeaders();
    } catch (e) { /* ignore */ }
    var token = localStorage.getItem('access_token') || localStorage.getItem('token');
    if (token) h['Authorization'] = 'Bearer ' + token;
    return h;
  }

  function unwrap(body) {
    if (!body) return {};
    if (body.data != null && typeof body.data === 'object' && !Array.isArray(body.data)) {
      return Object.assign({}, body, body.data);
    }
    return body;
  }

  function apiGet(url) {
    return fetch(url, {
      credentials: 'same-origin',
      headers: Object.assign({ Accept: 'application/json' }, authHeaders()),
    }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok || body.success === false) {
          throw new Error((body && (body.error || body.message)) || 'Request failed');
        }
        return unwrap(body);
      });
    });
  }

  function apiJson(url, method, payload) {
    var opts = {
      method: method,
      credentials: 'same-origin',
      headers: Object.assign(
        { Accept: 'application/json', 'Content-Type': 'application/json' },
        authHeaders()
      ),
    };
    if (method !== 'DELETE') {
      opts.body = JSON.stringify(payload || {});
    }
    return fetch(url, opts).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok || body.success === false) {
          throw new Error((body && (body.error || body.message)) || 'Request failed');
        }
        return unwrap(body);
      });
    });
  }

  function renderSummary(summary) {
    if (!summary) return;
    $('ltStatTotal').textContent = summary.total_staff != null ? summary.total_staff : '—';
    if ($('ltStatOnLeave')) {
      $('ltStatOnLeave').textContent =
        summary.on_leave_this_month != null ? summary.on_leave_this_month : '—';
    }
    if ($('ltStatOnLeaveLabel')) {
      var mLabel = summary.current_month_label || '';
      $('ltStatOnLeaveLabel').textContent = mLabel
        ? 'On leave · ' + mLabel
        : 'On leave this month';
    }
    if ($('ltStatLeaveDays')) {
      var sick = summary.sick_days_total != null ? summary.sick_days_total : 0;
      var annual = summary.annual_days_total != null ? summary.annual_days_total : 0;
      $('ltStatLeaveDays').textContent = sick + ' / ' + annual;
    }
    if ($('ltStatLow')) {
      $('ltStatLow').textContent = summary.low_remaining != null ? summary.low_remaining : '—';
    }
    if ($('ltStatRepeatSick')) {
      $('ltStatRepeatSick').textContent =
        summary.repeat_sick_month != null ? summary.repeat_sick_month : '—';
    }
    document.querySelectorAll('[data-card-filter]').forEach(function (btn) {
      var f = btn.getAttribute('data-card-filter');
      var on =
        (f === 'all' && !state.alertLevel && !($('ltAlertsOnly') && $('ltAlertsOnly').checked)) ||
        (f === 'on_leave_month' && state.alertLevel === 'on_leave_month') ||
        (f === 'low_remaining' && state.alertLevel === 'low_remaining') ||
        (f === 'repeat_sick_month' && state.alertLevel === 'repeat_sick_month') ||
        (f === 'approaching' && state.alertLevel === 'approaching') ||
        (f === 'exhausted' && state.alertLevel === 'exhausted');
      btn.classList.toggle('is-active', on);
    });
  }

  function monthCell(value) {
    return '<td class="lt-num lt-month-ro">' + esc(fmtDays(value)) + '</td>';
  }

  var COL_LABELS = {
    emp_id: 'Emp ID',
    full_name: 'Name',
    designation: 'Designation',
    company: 'Company',
    log_leave_from: 'From',
    log_leave_to: 'To',
    log_emp_id: 'Emp ID',
    log_full_name: 'Name',
    log_leave_type: 'Type',
    log_days: 'Days',
    log_notes: 'Notes',
    log_created: 'Created',
    log_edited: 'Edited',
  };

  var LOG_CHECKLIST_COLS = {
    log_leave_type: true,
    log_leave_from: true,
    log_leave_to: true,
    log_days: true,
    log_created: true,
    log_edited: true,
  };

  function isLogColFilter(key) {
    return key && String(key).indexOf('log_') === 0;
  }

  function empField(e, key) {
    if (key === 'emp_id') return String(e.emp_id || '');
    if (key === 'full_name') return String(e.full_name || '');
    if (key === 'designation') return String(e.designation || '');
    if (key === 'company') return String(e.company || '');
    return '';
  }

  function logField(p, key) {
    if (key === 'log_emp_id') return String(p.emp_id || '');
    if (key === 'log_full_name') return String(p.full_name || '');
    if (key === 'log_leave_type') return String(p.leave_type || '');
    if (key === 'log_notes') return String(p.notes || '');
    if (key === 'log_days') return fmtDays(p.days);
    if (key === 'log_leave_from') return fmtDateDMY(p.leave_date);
    if (key === 'log_leave_to') return fmtDateDMY(p.end_date || p.leave_date);
    if (key === 'log_created') return fmtDateDMY(p.created_at);
    if (key === 'log_edited') return fmtDateDMY(p.updated_at || p.created_at);
    return '';
  }

  function inYmdRange(iso, fromYmd, toYmd) {
    if (!fromYmd && !toYmd) return true;
    var key = toYmdKey(iso);
    if (!key) return false;
    if (fromYmd && key < fromYmd) return false;
    if (toYmd && key > toYmd) return false;
    return true;
  }

  function filteredEmployees() {
    var rows = state.employees || [];
    var filters = state.colFilters || {};
    return rows.filter(function (e) {
      return Object.keys(filters).every(function (key) {
        var q = String(filters[key] || '').trim().toLowerCase();
        if (!q) return true;
        return empField(e, key).toLowerCase().indexOf(q) !== -1;
      });
    });
  }

  function filteredLogs() {
    var rows = state.logs || [];
    var filters = state.logColFilters || {};
    var leaveFrom = ($('ltLogLeaveFrom') && $('ltLogLeaveFrom').value) || '';
    var leaveTo = ($('ltLogLeaveTo') && $('ltLogLeaveTo').value) || '';
    var createdFrom = ($('ltLogCreatedFrom') && $('ltLogCreatedFrom').value) || '';
    var createdTo = ($('ltLogCreatedTo') && $('ltLogCreatedTo').value) || '';
    return rows.filter(function (p) {
      var colsOk = Object.keys(filters).every(function (key) {
        var q = String(filters[key] || '').trim().toLowerCase();
        if (!q) return true;
        return logField(p, key).toLowerCase().indexOf(q) !== -1;
      });
      if (!colsOk) return false;
      var end = p.end_date || p.leave_date;
      if (leaveFrom && toYmdKey(end) < leaveFrom) return false;
      if (leaveTo && toYmdKey(p.leave_date) > leaveTo) return false;
      if (!inYmdRange(p.created_at, createdFrom, createdTo)) return false;
      return true;
    });
  }

  function hasActiveLogFilters() {
    var filters = state.logColFilters || {};
    var hasCol = Object.keys(filters).some(function (k) {
      return String(filters[k] || '').trim();
    });
    var q = ($('ltLogsSearch') && $('ltLogsSearch').value) || '';
    var lt = ($('ltLogTypeFilter') && $('ltLogTypeFilter').value) || 'all';
    var company = ($('ltLogCompanyFilter') && $('ltLogCompanyFilter').value) || 'all';
    var leaveFrom = ($('ltLogLeaveFrom') && $('ltLogLeaveFrom').value) || '';
    var leaveTo = ($('ltLogLeaveTo') && $('ltLogLeaveTo').value) || '';
    var createdFrom = ($('ltLogCreatedFrom') && $('ltLogCreatedFrom').value) || '';
    var createdTo = ($('ltLogCreatedTo') && $('ltLogCreatedTo').value) || '';
    return (
      hasCol ||
      !!q.trim() ||
      (lt && lt !== 'all') ||
      (company && company !== 'all') ||
      !!leaveFrom ||
      !!leaveTo ||
      !!createdFrom ||
      !!createdTo
    );
  }

  function syncLogsClearBtn() {
    var btn = $('ltLogsClearFilters');
    if (!btn) return;
    btn.hidden = !hasActiveLogFilters();
  }

  function syncColFilterButtons() {
    document.querySelectorAll('.lt-col-filter-btn').forEach(function (btn) {
      var key = btn.getAttribute('data-col-filter');
      var active = false;
      if (isLogColFilter(key)) {
        active = !!(state.logColFilters[key] && String(state.logColFilters[key]).trim());
      } else {
        active = !!(state.colFilters[key] && String(state.colFilters[key]).trim());
      }
      btn.classList.toggle('is-active', active);
    });
    syncLogsClearBtn();
  }

  function uniqueValuesForCol(key) {
    var seen = {};
    var out = [];
    if (isLogColFilter(key)) {
      if (key === 'log_leave_type') {
        return ['sick', 'annual'];
      }
      (state.logs || []).forEach(function (p) {
        var v = logField(p, key).trim();
        if (!v || v === '—') return;
        var k = v.toLowerCase();
        if (seen[k]) return;
        seen[k] = true;
        out.push(v);
      });
    } else {
      (state.employees || []).forEach(function (e) {
        var v = empField(e, key).trim();
        if (!v) return;
        var k = v.toLowerCase();
        if (seen[k]) return;
        seen[k] = true;
        out.push(v);
      });
    }
    out.sort(function (a, b) {
      return a.localeCompare(b, undefined, { sensitivity: 'base', numeric: true });
    });
    return out;
  }

  function closeColMenu() {
    var menu = $('ltColMenu');
    if (menu) menu.hidden = true;
    state.colFilterKey = null;
    document.querySelectorAll('.lt-col-filter-btn.is-open').forEach(function (b) {
      b.classList.remove('is-open');
    });
  }

  function openColMenu(btn) {
    var key = btn.getAttribute('data-col-filter');
    var menu = $('ltColMenu');
    var input = $('ltColMenuInput');
    var list = $('ltColMenuList');
    var label = $('ltColMenuLabel');
    if (!menu || !input || !key) return;

    document.querySelectorAll('.lt-col-filter-btn.is-open').forEach(function (b) {
      b.classList.remove('is-open');
    });
    btn.classList.add('is-open');
    state.colFilterKey = key;
    if (label) label.textContent = 'Filter ' + (COL_LABELS[key] || key);
    var store = isLogColFilter(key) ? state.logColFilters : state.colFilters;
    input.value = store[key] || '';

    if (list && (key === 'designation' || key === 'company' || LOG_CHECKLIST_COLS[key])) {
      var vals = uniqueValuesForCol(key);
      var current = String(store[key] || '').trim().toLowerCase();
      list.hidden = false;
      list.innerHTML = vals
        .slice(0, 80)
        .map(function (v) {
          var checked = current && v.toLowerCase() === current ? ' checked' : '';
          return (
            '<label class="lt-col-menu-opt">' +
            '<input type="radio" name="ltColPick" value="' +
            esc(v) +
            '"' +
            checked +
            '>' +
            '<span>' +
            esc(v) +
            '</span></label>'
          );
        })
        .join('');
      input.placeholder = 'Or type to filter…';
    } else if (list) {
      list.hidden = true;
      list.innerHTML = '';
      input.placeholder = 'Contains…';
    }

    menu.hidden = false;
    var rect = btn.getBoundingClientRect();
    var top = rect.bottom + 6;
    var left = Math.min(rect.left, window.innerWidth - 240);
    if (left < 8) left = 8;
    menu.style.top = top + 'px';
    menu.style.left = left + 'px';
    input.focus();
    input.select();
  }

  function applyColMenu() {
    var key = state.colFilterKey;
    if (!key) return;
    var input = $('ltColMenuInput');
    var picked = document.querySelector('#ltColMenuList input[name="ltColPick"]:checked');
    var val = '';
    if (input && input.value.trim()) val = input.value.trim();
    else if (picked) val = picked.value;
    if (isLogColFilter(key)) {
      state.logColFilters[key] = val;
    } else {
      state.colFilters[key] = val;
    }
    closeColMenu();
    syncColFilterButtons();
    if (isLogColFilter(key)) renderLogs();
    else {
      renderSick();
      renderAnnual();
    }
  }

  function clearColMenu() {
    var key = state.colFilterKey;
    if (!key) return;
    if (isLogColFilter(key)) {
      state.logColFilters[key] = '';
    } else {
      state.colFilters[key] = '';
    }
    if ($('ltColMenuInput')) $('ltColMenuInput').value = '';
    document.querySelectorAll('#ltColMenuList input[name="ltColPick"]').forEach(function (r) {
      r.checked = false;
    });
    closeColMenu();
    syncColFilterButtons();
    if (isLogColFilter(key)) renderLogs();
    else {
      renderSick();
      renderAnnual();
    }
  }

  function renderSick() {
    var tbody = $('ltSickBody');
    if (!tbody) return;
    var rows = filteredEmployees();
    if (!rows.length) {
      tbody.innerHTML = state.employees.length
        ? '<tr><td colspan="12" class="lt-empty">No staff match these column filters.</td></tr>'
        : '<tr><td colspan="12" class="lt-empty">No staff yet. Click <strong>Seed Staff</strong>, then use <strong>Log leave</strong> to record days.</td></tr>';
      syncColFilterButtons();
      return;
    }
    tbody.innerHTML = rows
      .map(function (e) {
        var sick = e.sick || {};
        var months = sick.months || {};
        var alert = sick.alert || '';
        var cells = MONTHS.map(function (m) {
          return monthCell(months[m] != null ? months[m] : months[String(m)]);
        }).join('');
        var badge = alert
          ? '<span class="lt-badge ' + alert + '">' + esc(alertLabel(alert)) + '</span>'
          : '';
        return (
          '<tr class="lt-row lt-row-clickable ' +
          esc(alert) +
          '" data-id="' +
          e.id +
          '" data-person-id="' +
          e.id +
          '" tabindex="0" role="button" aria-label="View leave for ' +
          esc(e.full_name) +
          '">' +
          '<td>' +
          esc(e.emp_id) +
          '</td>' +
          '<td class="name-cell">' +
          esc(e.full_name) +
          '</td>' +
          '<td>' +
          esc(e.designation) +
          '</td>' +
          '<td>' +
          esc(e.company) +
          '</td>' +
          cells +
          '<td class="lt-num">' +
          esc(fmtDays(sick.used)) +
          '</td>' +
          '<td class="lt-num">' +
          esc(fmtDays(sick.remaining)) +
          '</td>' +
          '<td>' +
          badge +
          '</td>' +
          '</tr>'
        );
      })
      .join('');
    syncColFilterButtons();
  }

  function renderAnnual() {
    var tbody = $('ltAnnualBody');
    if (!tbody) return;
    var rows = filteredEmployees();
    if (!rows.length) {
      tbody.innerHTML = state.employees.length
        ? '<tr><td colspan="12" class="lt-empty">No staff match these column filters.</td></tr>'
        : '<tr><td colspan="12" class="lt-empty">No staff yet. Click <strong>Seed Staff</strong>.</td></tr>';
      syncColFilterButtons();
      return;
    }
    tbody.innerHTML = rows
      .map(function (e) {
        var an = e.annual || {};
        var months = an.months || {};
        var cells = MONTHS.map(function (m) {
          return monthCell(months[m] != null ? months[m] : months[String(m)]);
        }).join('');
        var rem = an.remaining == null ? '—' : fmtDays(an.remaining);
        return (
          '<tr class="lt-row-clickable" data-id="' +
          e.id +
          '" data-person-id="' +
          e.id +
          '" tabindex="0" role="button" aria-label="View leave for ' +
          esc(e.full_name) +
          '">' +
          '<td>' +
          esc(e.emp_id) +
          '</td>' +
          '<td class="name-cell">' +
          esc(e.full_name) +
          '</td>' +
          '<td>' +
          esc(e.designation) +
          '</td>' +
          '<td>' +
          esc(e.company) +
          '</td>' +
          '<td><input class="lt-cell lt-ent" type="number" min="0" step="1" ' +
          'data-emp="' +
          e.id +
          '" data-field="annual_entitlement" value="' +
          esc(e.annual_entitlement != null ? e.annual_entitlement : '') +
          '" placeholder="—" aria-label="Annual entitlement"></td>' +
          cells +
          '<td class="lt-num">' +
          esc(fmtDays(an.used)) +
          '</td>' +
          '<td class="lt-num">' +
          esc(rem) +
          '</td>' +
          '</tr>'
        );
      })
      .join('');
    syncColFilterButtons();
  }

  function toYmdKey(iso) {
    if (!iso) return '';
    var str = String(iso).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(str)) return str;
    var d = null;
    try {
      if (window.InjaazDateTimeUAE && InjaazDateTimeUAE.parseInstant) {
        d = InjaazDateTimeUAE.parseInstant(str);
      }
    } catch (e) { /* ignore */ }
    if (!d) {
      d = new Date(str);
      if (Number.isNaN(d.getTime())) return '';
    }
    var tz = (window.InjaazDateTimeUAE && InjaazDateTimeUAE.TZ) || 'Asia/Dubai';
    var parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(d);
    var map = {};
    parts.forEach(function (p) {
      if (p.type !== 'literal') map[p.type] = p.value;
    });
    if (!map.year || !map.month || !map.day) return '';
    return map.year + '-' + map.month + '-' + map.day;
  }

  function fmtDateDMY(iso) {
    if (!iso) return '—';
    try {
      if (window.InjaazDateTimeUAE && InjaazDateTimeUAE.formatDateDMY) {
        var formatted = InjaazDateTimeUAE.formatDateDMY(iso);
        if (formatted) return formatted;
      }
    } catch (e) { /* ignore */ }
    var key = toYmdKey(iso);
    if (!key) return String(iso);
    var bits = key.split('-');
    return bits[2] + '/' + bits[1] + '/' + bits[0];
  }

  function renderLogs() {
    var tbody = $('ltLogsBody');
    if (!tbody) return;
    var all = state.logs || [];
    var logs = filteredLogs();
    syncColFilterButtons();
    if (!all.length) {
      tbody.innerHTML =
        '<tr><td colspan="10" class="lt-empty">No leave logs yet. Click <strong>Log leave</strong> to add an entry — it rolls into the staff master.</td></tr>';
      return;
    }
    if (!logs.length) {
      tbody.innerHTML =
        '<tr><td colspan="10" class="lt-empty">No leave logs match these filters.</td></tr>';
      return;
    }
    tbody.innerHTML = logs
      .map(function (p) {
        var end = p.end_date || p.leave_date;
        return (
          '<tr class="lt-row-clickable" data-log="' +
          p.id +
          '" data-person-id="' +
          p.employee_id +
          '">' +
          '<td>' +
          esc(fmtDateDMY(p.leave_date)) +
          '</td>' +
          '<td>' +
          esc(fmtDateDMY(end)) +
          '</td>' +
          '<td>' +
          esc(p.emp_id) +
          '</td>' +
          '<td class="name-cell">' +
          esc(p.full_name) +
          '</td>' +
          '<td><span class="lt-type lt-type-' +
          esc(p.leave_type) +
          '">' +
          esc(p.leave_type) +
          '</span></td>' +
          '<td class="lt-num">' +
          esc(fmtDays(p.days)) +
          '</td>' +
          '<td>' +
          esc(p.notes) +
          '</td>' +
          '<td class="lt-ts">' +
          esc(fmtDateDMY(p.created_at)) +
          '</td>' +
          '<td class="lt-ts">' +
          esc(fmtDateDMY(p.updated_at || p.created_at)) +
          '</td>' +
          '<td class="lt-actions">' +
          '<button type="button" data-edit-log="' +
          p.id +
          '">Edit</button>' +
          '<button type="button" data-del-log="' +
          p.id +
          '">Delete</button>' +
          '</td>' +
          '</tr>'
        );
      })
      .join('');
  }

  function dayOffset(d) {
    var t = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
    var s = Date.UTC(WINDOW_START.getFullYear(), WINDOW_START.getMonth(), WINDOW_START.getDate());
    return Math.round((t - s) / 86400000);
  }

  var WINDOW_DAYS = dayOffset(WINDOW_END) + 1;

  function timelineMonthSegments() {
    var segs = [];
    var cursor = 0;
    MONTHS.forEach(function (m) {
      var daysInMonth = new Date(YEAR, m, 0).getDate();
      var widthPct = (daysInMonth / WINDOW_DAYS) * 100;
      var leftPct = (cursor / WINDOW_DAYS) * 100;
      segs.push({
        month: m,
        label: MONTH_LABELS[m] || String(m),
        days: daysInMonth,
        leftPct: leftPct,
        widthPct: widthPct,
      });
      cursor += daysInMonth;
    });
    return segs;
  }

  function timelineScaleHtml() {
    var segs = timelineMonthSegments();
    return (
      '<div class="lt-tl-scale" aria-hidden="true">' +
      segs
        .map(function (s) {
          return (
            '<div class="lt-tl-scale-cell" style="left:' +
            s.leftPct +
            '%;width:' +
            s.widthPct +
            '%">' +
            '<span class="lt-tl-scale-label">' +
            esc(s.label) +
            '</span>' +
            '</div>'
          );
        })
        .join('') +
      '</div>'
    );
  }

  function timelineMonthMarksHtml() {
    var segs = timelineMonthSegments();
    return segs
      .slice(1)
      .map(function (s) {
        return (
          '<span class="lt-tl-mark" style="left:' + s.leftPct + '%"></span>'
        );
      })
      .join('');
  }

  function renderPlans() {
    var tbody = $('ltPlansBody');
    var timeline = $('ltTimeline');
    if (!tbody) return;
    var plans = state.plans || [];
    if (!plans.length) {
      tbody.innerHTML =
        '<tr><td colspan="8" class="lt-empty">No planned leave yet. Add a date range to plan annual leave.</td></tr>';
    } else {
      tbody.innerHTML = plans
        .map(function (p) {
          return (
            '<tr class="lt-row-clickable" data-plan="' +
            p.id +
            '" data-person-id="' +
            p.employee_id +
            '">' +
            '<td>' +
            esc(p.emp_id) +
            '</td>' +
            '<td class="name-cell">' +
            esc(p.full_name) +
            '</td>' +
            '<td>' +
            esc(p.company) +
            '</td>' +
            '<td>' +
            esc(fmtDateDMY(p.start_date)) +
            '</td>' +
            '<td>' +
            esc(fmtDateDMY(p.end_date)) +
            '</td>' +
            '<td class="lt-num">' +
            esc(p.days) +
            '</td>' +
            '<td>' +
            esc(p.notes) +
            '</td>' +
            '<td class="lt-actions">' +
            '<button type="button" data-apply="' +
            p.id +
            '" title="Create leave logs from this plan">Apply to logs</button>' +
            '<button type="button" data-del="' +
            p.id +
            '">Delete</button>' +
            '</td>' +
            '</tr>'
          );
        })
        .join('');
    }

    if (timeline) {
      if (!plans.length) {
        timeline.innerHTML = '<p class="lt-empty">No overlapping leave in this window.</p>';
      } else {
        var marks = timelineMonthMarksHtml();
        timeline.innerHTML =
          timelineScaleHtml() +
          plans
            .map(function (p) {
              var start = new Date(p.start_date + 'T00:00:00');
              var end = new Date(p.end_date + 'T00:00:00');
              var left = Math.max(0, dayOffset(start));
              var right = Math.min(WINDOW_DAYS - 1, dayOffset(end));
              var width = Math.max(1, right - left + 1);
              var leftPct = (left / WINDOW_DAYS) * 100;
              var widthPct = (width / WINDOW_DAYS) * 100;
              return (
                '<div class="lt-tl-item">' +
                '<div class="lt-tl-name">' +
                esc(p.full_name) +
                ' <span class="lt-tl-meta">(' +
                esc(p.emp_id) +
                ')</span></div>' +
                '<div class="lt-tl-meta">' +
                esc(fmtDateDMY(p.start_date)) +
                ' → ' +
                esc(fmtDateDMY(p.end_date)) +
                ' · ' +
                esc(p.days) +
                'd</div>' +
                '<div class="lt-tl-bar" aria-hidden="true">' +
                marks +
                '<div class="lt-tl-fill" style="left:' +
                leftPct +
                '%;width:' +
                widthPct +
                '%"></div>' +
                '</div></div>'
              );
            })
            .join('');
      }
    }
  }

  function setTab(tab) {
    state.tab = tab;
    document.querySelectorAll('.lt-tab').forEach(function (btn) {
      var on = btn.getAttribute('data-tab') === tab;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    $('ltPanelSick').hidden = tab !== 'sick';
    $('ltPanelAnnual').hidden = tab !== 'annual';
    if ($('ltPanelLogs')) $('ltPanelLogs').hidden = tab !== 'logs';
    $('ltPanelPlanner').hidden = tab !== 'planner';
    if (tab === 'planner') loadPlans();
    if (tab === 'logs') loadLogs();
  }

  function loadEmployees() {
    var qs = queryParams();
    var url = '/hr/api/leave-tracker/employees' + (qs ? '?' + qs : '');
    return apiGet(url)
      .then(function (data) {
        state.employees = data.employees || [];
        renderSummary(data.summary);
        renderSick();
        renderAnnual();
        if (!state.directory.length) {
          state.directory = data.employees || [];
        }
      })
      .catch(function (err) {
        $('ltSickBody').innerHTML =
          '<tr><td colspan="12" class="lt-empty">' + esc(err.message) + '</td></tr>';
        $('ltAnnualBody').innerHTML =
          '<tr><td colspan="12" class="lt-empty">' + esc(err.message) + '</td></tr>';
      });
  }

  function loadLogs() {
    var qs = logsQueryParams();
    var url = '/hr/api/leave-tracker/logs' + (qs ? '?' + qs : '');
    return apiGet(url)
      .then(function (data) {
        state.logs = data.logs || [];
        renderLogs();
      })
      .catch(function (err) {
        if ($('ltLogsBody')) {
          $('ltLogsBody').innerHTML =
            '<tr><td colspan="10" class="lt-empty">' + esc(err.message) + '</td></tr>';
        }
      });
  }

  function loadPlans() {
    var company = ($('ltCompany') && $('ltCompany').value) || 'all';
    var q = ($('ltSearch') && $('ltSearch').value) || '';
    var params = new URLSearchParams();
    if (company && company !== 'all') params.set('company', company);
    if (q.trim()) params.set('q', q.trim());
    var url = '/hr/api/leave-tracker/plans' + (params.toString() ? '?' + params : '');
    return apiGet(url)
      .then(function (data) {
        state.plans = data.plans || [];
        renderPlans();
      })
      .catch(function (err) {
        $('ltPlansBody').innerHTML =
          '<tr><td colspan="8" class="lt-empty">' + esc(err.message) + '</td></tr>';
      });
  }

  function loadDirectory() {
    return apiGet('/hr/api/leave-tracker/employees').then(function (data) {
      state.directory = data.employees || [];
      return state.directory;
    });
  }

  function findInDirectory(id) {
    id = Number(id);
    return (state.directory || []).find(function (e) {
      return e.id === id;
    }) || (state.employees || []).find(function (e) {
      return e.id === id;
    }) || null;
  }

  function matchEmployees(query, limit) {
    limit = limit || 12;
    var q = (query || '').trim().toLowerCase();
    if (!q) return [];
    var list = state.directory && state.directory.length ? state.directory : state.employees;
    var scored = [];
    for (var i = 0; i < list.length; i++) {
      var e = list[i];
      var empId = String(e.emp_id || '').toLowerCase();
      var name = String(e.full_name || '').toLowerCase();
      var desig = String(e.designation || '').toLowerCase();
      var score = 0;
      if (empId === q) score = 100;
      else if (empId.indexOf(q) === 0) score = 80;
      else if (empId.indexOf(q) >= 0) score = 60;
      else if (name.indexOf(q) === 0) score = 50;
      else if (name.indexOf(q) >= 0) score = 40;
      else if (desig.indexOf(q) >= 0) score = 20;
      if (score) scored.push({ e: e, score: score });
    }
    scored.sort(function (a, b) {
      return b.score - a.score;
    });
    return scored.slice(0, limit).map(function (x) {
      return x.e;
    });
  }

  function renderAcResults(listEl, matches, activeIdx, query) {
    if (!listEl) return;
    var q = (query || '').trim();
    if (!q) {
      listEl.innerHTML = '';
      listEl.hidden = true;
      return;
    }
    if (!matches.length) {
      listEl.innerHTML = '<li class="lt-ac-empty">No matching staff</li>';
      listEl.hidden = false;
      return;
    }
    listEl.innerHTML = matches
      .map(function (e, i) {
        return (
          '<li role="option">' +
          '<button type="button" class="lt-ac-item' +
          (i === activeIdx ? ' is-active' : '') +
          '" data-emp-pick="' +
          e.id +
          '">' +
          '<div class="lt-ac-item-main">' +
          esc(e.emp_id) +
          ' — ' +
          esc(e.full_name) +
          '</div>' +
          '<div class="lt-ac-item-sub">' +
          esc(e.designation || '—') +
          ' · ' +
          esc(e.company || '') +
          '</div>' +
          '</button></li>'
        );
      })
      .join('');
    listEl.hidden = false;
  }

  function showEmpCard(prefix, emp) {
    var card = $(prefix + 'EmployeeCard');
    if (!card) return;
    if (!emp) {
      card.hidden = true;
      return;
    }
    $(prefix + 'EmpName').textContent = emp.full_name || '—';
    $(prefix + 'EmpId').textContent = emp.emp_id || '—';
    $(prefix + 'EmpDesig').textContent = emp.designation || '—';
    $(prefix + 'EmpCompany').textContent = emp.company || '—';
    card.hidden = false;
  }

  function selectLogEmployee(emp) {
    state.selectedLogEmp = emp || null;
    $('ltLogEmployeeId').value = emp ? String(emp.id) : '';
    var search = $('ltLogEmployeeSearch');
    if (search && emp) {
      search.value = emp.emp_id + ' — ' + emp.full_name;
      search.classList.remove('is-invalid');
      search.dataset.locked = '1';
    }
    if (!emp && search) {
      search.classList.remove('is-invalid');
      search.dataset.locked = '0';
    }
    var results = $('ltLogEmployeeResults');
    if (results) results.hidden = true;
    showEmpCard('ltLog', emp);
  }

  function selectPlanEmployee(emp) {
    state.selectedPlanEmp = emp || null;
    $('ltPlanEmployeeId').value = emp ? String(emp.id) : '';
    var search = $('ltPlanEmployeeSearch');
    if (search && emp) {
      search.value = emp.emp_id + ' — ' + emp.full_name;
      search.classList.remove('is-invalid');
      search.dataset.locked = '1';
    }
    if (!emp && search) {
      search.classList.remove('is-invalid');
      search.dataset.locked = '0';
    }
    var results = $('ltPlanEmployeeResults');
    if (results) results.hidden = true;
    showEmpCard('ltPlan', emp);
  }

  function wireAutocomplete(searchId, resultsId, onPick) {
    var input = $(searchId);
    var list = $(resultsId);
    if (!input || !list) return;
    var activeIdx = -1;
    var currentMatches = [];

    function refresh() {
      var q = input.value;
      // If a full selection is already shown, don't flood the list until user edits
      if (input.dataset.locked === '1' && !q) {
        list.hidden = true;
        return;
      }
      currentMatches = matchEmployees(q, 12);
      activeIdx = currentMatches.length ? 0 : -1;
      renderAcResults(list, currentMatches, activeIdx, q);
    }

    input.addEventListener('input', function () {
      input.dataset.locked = '0';
      onPick(null);
      refresh();
    });
    input.addEventListener('focus', function () {
      // Only open suggestions after the user has typed something
      if ((input.value || '').trim() && input.dataset.locked !== '1') {
        refresh();
      } else {
        list.hidden = true;
      }
    });
    input.addEventListener('keydown', function (e) {
      if (list.hidden) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (!currentMatches.length) return;
        activeIdx = (activeIdx + 1) % currentMatches.length;
        renderAcResults(list, currentMatches, activeIdx, input.value);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (!currentMatches.length) return;
        activeIdx = (activeIdx - 1 + currentMatches.length) % currentMatches.length;
        renderAcResults(list, currentMatches, activeIdx, input.value);
      } else if (e.key === 'Enter') {
        if (activeIdx >= 0 && currentMatches[activeIdx]) {
          e.preventDefault();
          input.dataset.locked = '1';
          onPick(currentMatches[activeIdx]);
        }
      } else if (e.key === 'Escape') {
        list.hidden = true;
      }
    });
    list.addEventListener('mousedown', function (e) {
      var btn = e.target.closest('[data-emp-pick]');
      if (!btn) return;
      e.preventDefault();
      var emp = findInDirectory(btn.getAttribute('data-emp-pick'));
      if (emp) {
        input.dataset.locked = '1';
        onPick(emp);
      }
    });
    document.addEventListener('click', function (e) {
      if (!input.contains(e.target) && !list.contains(e.target)) {
        list.hidden = true;
      }
    });
  }

  function calcLogDays() {
    var startEl = $('ltLogDate');
    var endEl = $('ltLogEndDate');
    var daysEl = $('ltLogDays');
    if (!startEl || !endEl || !daysEl) return 1;
    var start = startEl.value;
    var end = endEl.value || start;
    if (!start) {
      daysEl.value = '1';
      return 1;
    }
    if (!endEl.value) endEl.value = start;
    if (end < start) {
      endEl.value = start;
      end = start;
    }
    var s = new Date(start + 'T00:00:00');
    var e = new Date(end + 'T00:00:00');
    var days = Math.round((e - s) / 86400000) + 1;
    if (days < 1) days = 1;
    daysEl.value = String(days);
    return days;
  }

  function openLogModal(log, prefillEmp) {
    var ensure = state.directory.length ? Promise.resolve() : loadDirectory();
    ensure.then(function () {
      $('ltLogId').value = log && log.id ? log.id : '';
      $('ltLogModalTitle').textContent = log && log.id ? 'Edit leave log' : 'Log leave';
      if (log) {
        var emp = findInDirectory(log.employee_id) || {
          id: log.employee_id,
          emp_id: log.emp_id,
          full_name: log.full_name,
          designation: log.designation || '',
          company: log.company || '',
        };
        selectLogEmployee(emp);
        $('ltLogType').value = log.leave_type || 'sick';
        $('ltLogDate').value = log.leave_date || '';
        $('ltLogEndDate').value = log.end_date || log.leave_date || '';
        $('ltLogNotes').value = log.notes || '';
        calcLogDays();
      } else {
        selectLogEmployee(prefillEmp || null);
        if (!prefillEmp && $('ltLogEmployeeSearch')) {
          $('ltLogEmployeeSearch').value = '';
          $('ltLogEmployeeSearch').dataset.locked = '0';
        }
        if ($('ltLogEmployeeResults')) $('ltLogEmployeeResults').hidden = true;
        $('ltLogType').value = 'sick';
        $('ltLogNotes').value = '';
        var today = new Date();
        var iso;
        if (today >= WINDOW_START && today <= WINDOW_END) {
          iso = today.toISOString().slice(0, 10);
        } else {
          iso = '2026-08-01';
        }
        $('ltLogDate').value = iso;
        $('ltLogEndDate').value = iso;
        calcLogDays();
      }
      $('ltLogModal').hidden = false;
      setTimeout(function () {
        var el = $('ltLogEmployeeSearch');
        if (el) {
          el.focus();
          el.select && el.select();
        }
      }, 80);
    });
  }

  function closeLogModal() {
    $('ltLogModal').hidden = true;
    selectLogEmployee(null);
    $('ltLogId').value = '';
    if ($('ltLogEmployeeSearch')) $('ltLogEmployeeSearch').value = '';
    if ($('ltLogEmployeeResults')) $('ltLogEmployeeResults').hidden = true;
  }

  function initialsFromName(name) {
    var parts = String(name || '')
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!parts.length) return '?';
    var a = parts[0].charAt(0);
    var b = parts.length > 1 ? parts[parts.length - 1].charAt(0) : '';
    return (a + b).toUpperCase();
  }

  function formatLeaveRange(log) {
    if (!log || !log.leave_date) return '—';
    var start = fmtDateDMY(log.leave_date);
    var end = fmtDateDMY(log.end_date || log.leave_date);
    if (end === start) return start;
    return start + ' → ' + end;
  }

  function renderPersonLatest(log) {
    var el = $('ltPersonLatest');
    if (!el) return;
    if (!log) {
      el.innerHTML = '<p class="lt-person-empty">No leave logged in Aug–Dec 2026 yet.</p>';
      return;
    }
    el.innerHTML =
      '<div class="lt-person-latest-card">' +
      '<div class="lt-person-latest-top">' +
      '<span class="lt-type lt-type-' +
      esc(log.leave_type) +
      '">' +
      esc(log.leave_type) +
      '</span>' +
      '<span class="lt-person-days">' +
      esc(fmtDays(log.days)) +
      ' day' +
      (Number(log.days) === 1 ? '' : 's') +
      '</span>' +
      '</div>' +
      '<div class="lt-person-latest-dates">' +
      esc(formatLeaveRange(log)) +
      '</div>' +
      (log.notes
        ? '<p class="lt-person-notes">' + esc(log.notes) + '</p>'
        : '<p class="lt-person-notes lt-person-notes-muted">No notes</p>') +
      '</div>';
  }

  function renderPersonApps(apps, monthLabel) {
    var title = $('ltPersonAppsTitle');
    if (title) {
      title.textContent = monthLabel
        ? 'Applications · ' + monthLabel
        : 'Recent applications';
    }
    var el = $('ltPersonApps');
    if (!el) return;
    if (!apps || !apps.length) {
      el.innerHTML =
        '<p class="lt-person-empty">' +
        (monthLabel
          ? 'No applications in ' + esc(monthLabel) + '.'
          : 'No applications in the tracker window.') +
        '</p>';
      return;
    }
    el.innerHTML = apps
      .map(function (log) {
        return (
          '<div class="lt-person-app-row">' +
          '<span class="lt-type lt-type-' +
          esc(log.leave_type) +
          '">' +
          esc(log.leave_type) +
          '</span>' +
          '<span class="lt-person-app-dates">' +
          esc(formatLeaveRange(log)) +
          '</span>' +
          '<span class="lt-person-app-days">' +
          esc(fmtDays(log.days)) +
          'd</span>' +
          '</div>'
        );
      })
      .join('');
  }

  function openPersonModal(empId) {
    if (!empId || !$('ltPersonModal')) return;
    var month = ($('ltMonth') && $('ltMonth').value) || '';
    var qs = month ? '?month=' + encodeURIComponent(month) : '';
    $('ltPersonLatest').innerHTML = '<p class="lt-person-empty">Loading…</p>';
    $('ltPersonApps').innerHTML = '';
    $('ltPersonModal').hidden = false;
    apiGet('/hr/api/leave-tracker/employees/' + empId + '/leave-profile' + qs)
      .then(function (data) {
        var emp = data.employee || {};
        state.personEmp = emp;
        $('ltPersonAvatar').textContent = initialsFromName(emp.full_name);
        $('ltPersonName').textContent = emp.full_name || '—';
        var meta = [emp.emp_id, emp.designation, emp.company].filter(Boolean).join(' · ');
        $('ltPersonMeta').textContent = meta || '—';
        var sick = emp.sick || {};
        var annual = emp.annual || {};
        $('ltPersonBalances').innerHTML =
          '<div class="lt-person-chip">' +
          '<span class="lt-person-chip-label">Sick</span>' +
          '<span class="lt-person-chip-val">' +
          esc(fmtDays(sick.used)) +
          ' used · ' +
          esc(fmtDays(sick.remaining)) +
          ' left</span>' +
          '</div>' +
          '<div class="lt-person-chip">' +
          '<span class="lt-person-chip-label">Annual</span>' +
          '<span class="lt-person-chip-val">' +
          esc(fmtDays(annual.used)) +
          ' used · ' +
          (annual.remaining == null ? '—' : esc(fmtDays(annual.remaining))) +
          ' left</span>' +
          '</div>';
        renderPersonLatest(data.latest);
        renderPersonApps(data.applications, data.month_label || '');
      })
      .catch(function (err) {
        $('ltPersonLatest').innerHTML =
          '<p class="lt-person-empty">Failed to load: ' + esc(err.message || err) + '</p>';
      });
  }

  function closePersonModal() {
    if ($('ltPersonModal')) $('ltPersonModal').hidden = true;
    state.personEmp = null;
  }

  function openPlanModal() {
    var ensure = state.directory.length ? Promise.resolve() : loadDirectory();
    ensure.then(function () {
      selectPlanEmployee(null);
      if ($('ltPlanEmployeeSearch')) $('ltPlanEmployeeSearch').value = '';
      $('ltPlanModal').hidden = false;
      setTimeout(function () {
        $('ltPlanEmployeeSearch') && $('ltPlanEmployeeSearch').focus();
      }, 50);
    });
  }

  function closePlanModal() {
    $('ltPlanModal').hidden = true;
    selectPlanEmployee(null);
    if ($('ltPlanEmployeeSearch')) $('ltPlanEmployeeSearch').value = '';
    if ($('ltPlanEmployeeResults')) $('ltPlanEmployeeResults').hidden = true;
    $('ltPlanForm').reset();
  }

  function saveEntitlement(empId, value) {
    return apiJson('/hr/api/leave-tracker/employees/' + empId, 'PATCH', {
      annual_entitlement: value === '' || value == null ? null : Number(value),
    }).then(function (data) {
      if (data.employee) {
        var idx = state.employees.findIndex(function (e) {
          return e.id === data.employee.id;
        });
        if (idx >= 0) state.employees[idx] = data.employee;
        renderAnnual();
      }
    });
  }

  function onCellBlur(e) {
    var input = e.target;
    if (!input.classList || !input.classList.contains('lt-cell')) return;
    if (input.dataset.field === 'annual_entitlement') {
      saveEntitlement(input.dataset.emp, input.value).catch(function (err) {
        showImportResult(err.message, true);
      });
    }
  }

  function onCellKey(e) {
    if (e.key === 'Enter' && e.target.classList && e.target.classList.contains('lt-cell')) {
      e.target.blur();
    }
  }

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments;
      var self = this;
      clearTimeout(t);
      t = setTimeout(function () {
        fn.apply(self, args);
      }, ms);
    };
  }

  function refreshAll() {
    return loadEmployees().then(function () {
      if (state.tab === 'logs') return loadLogs();
      if (state.tab === 'planner') return loadPlans();
    });
  }

  function downloadExport() {
    fetch('/hr/api/leave-tracker/export', {
      credentials: 'same-origin',
      headers: authHeaders(),
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Export failed');
        return r.blob();
      })
      .then(function (blob) {
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'leave_tracker_2026_aug_dec.xlsx';
        document.body.appendChild(a);
        a.click();
        a.remove();
      })
      .catch(function (err) {
        showImportResult(err.message, true);
      });
  }

  function downloadTemplate() {
    fetch('/hr/api/leave-tracker/template', {
      credentials: 'same-origin',
      headers: authHeaders(),
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Template download failed');
        return r.blob();
      })
      .then(function (blob) {
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'leave_log_template_2026_aug_dec.xlsx';
        document.body.appendChild(a);
        a.click();
        a.remove();
      })
      .catch(function (err) {
        showImportResult(err.message, true);
      });
  }

  function uploadImport(file) {
    var fd = new FormData();
    fd.append('file', file);
    fetch('/hr/api/leave-tracker/import', {
      method: 'POST',
      credentials: 'same-origin',
      headers: authHeaders(),
      body: fd,
    })
      .then(function (r) {
        return r.json().then(function (body) {
          if (!r.ok || body.success === false) {
            throw new Error((body && (body.error || body.message)) || 'Import failed');
          }
          return unwrap(body);
        });
      })
      .then(function (data) {
        showImportResult(
          'Imported — staff +' +
            (data.created || 0) +
            ', logs +' +
            (data.logs_created || 0) +
            ', monthly adj ' +
            (data.usage_updates || 0) +
            (data.errors && data.errors.length ? '; issues: ' + data.errors.slice(0, 3).join('; ') : '')
        );
        refreshAll();
      })
      .catch(function (err) {
        showImportResult(err.message, true);
      });
  }

  function seedStaff(file) {
    var fd = new FormData();
    if (file) fd.append('file', file);
    fetch('/hr/api/leave-tracker/seed-staff', {
      method: 'POST',
      credentials: 'same-origin',
      headers: authHeaders(),
      body: fd,
    })
      .then(function (r) {
        return r.json().then(function (body) {
          if (!r.ok || body.success === false) {
            throw new Error((body && (body.error || body.message)) || 'Seed failed');
          }
          return unwrap(body);
        });
      })
      .then(function (data) {
        showImportResult(
          'Seeded ' +
            (data.created || 0) +
            ' staff (skipped ' +
            (data.skipped || 0) +
            ' of ' +
            (data.total_parsed || 0) +
            ')'
        );
        loadEmployees();
      })
      .catch(function (err) {
        showImportResult(err.message, true);
      });
  }

  function applyCardFilter(filter) {
    if (filter === 'all') {
      state.alertLevel = '';
      if ($('ltAlertsOnly')) $('ltAlertsOnly').checked = false;
    } else if (
      filter === 'on_leave_month' ||
      filter === 'low_remaining' ||
      filter === 'repeat_sick_month' ||
      filter === 'approaching' ||
      filter === 'exhausted'
    ) {
      state.alertLevel = filter;
      if ($('ltAlertsOnly')) $('ltAlertsOnly').checked = false;
      setTab('sick');
    }
    loadEmployees();
    if (state.tab === 'logs') loadLogs();
  }

  function emptyLogColFilters() {
    return {
      log_leave_from: '',
      log_leave_to: '',
      log_emp_id: '',
      log_full_name: '',
      log_leave_type: '',
      log_days: '',
      log_notes: '',
      log_created: '',
      log_edited: '',
    };
  }

  function syncSearchClear(inputId, btnId) {
    var input = $(inputId);
    var btn = $(btnId);
    if (!btn) return;
    btn.hidden = !(input && String(input.value || '').length);
  }

  function wireSearchClear(inputId, btnId) {
    var input = $(inputId);
    var btn = $(btnId);
    if (!input || !btn) return;
    function sync() {
      syncSearchClear(inputId, btnId);
    }
    input.addEventListener('input', sync);
    input.addEventListener('search', sync);
    btn.addEventListener('click', function () {
      input.value = '';
      sync();
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
    });
    sync();
  }

  function init() {
    var reload = debounce(function () {
      state.alertLevel = '';
      loadEmployees();
      if (state.tab === 'logs') loadLogs();
      if (state.tab === 'planner') loadPlans();
    }, 250);

    $('ltSearch') && $('ltSearch').addEventListener('input', reload);
    $('ltCompany') && $('ltCompany').addEventListener('change', reload);
    $('ltMonth') && $('ltMonth').addEventListener('change', reload);
    wireSearchClear('ltSearch', 'ltSearchClear');
    wireSearchClear('ltLogsSearch', 'ltLogsSearchClear');
    $('ltLogsSearch') &&
      $('ltLogsSearch').addEventListener(
        'input',
        debounce(function () {
          loadLogs();
          syncLogsClearBtn();
        }, 250)
      );
    $('ltLogsClearFilters') &&
      $('ltLogsClearFilters').addEventListener('click', function () {
        state.logColFilters = emptyLogColFilters();
        if ($('ltLogsSearch')) $('ltLogsSearch').value = '';
        if ($('ltLogTypeFilter')) $('ltLogTypeFilter').value = 'all';
        if ($('ltLogCompanyFilter')) $('ltLogCompanyFilter').value = 'all';
        ['ltLogLeaveFrom', 'ltLogLeaveTo', 'ltLogCreatedFrom', 'ltLogCreatedTo'].forEach(
          function (id) {
            if ($(id)) $(id).value = '';
          }
        );
        syncSearchClear('ltLogsSearch', 'ltLogsSearchClear');
        syncColFilterButtons();
        loadLogs();
      });
    $('ltAlertsOnly') &&
      $('ltAlertsOnly').addEventListener('change', function () {
        state.alertLevel = '';
        loadEmployees();
        if (state.tab === 'logs') loadLogs();
      });

    document.addEventListener('click', function (e) {
      if (e.target.closest('input, button, a, select, textarea, .lt-actions, .lt-col-filter-btn')) {
        return;
      }
      var row = e.target.closest('tr.lt-row-clickable[data-person-id]');
      if (!row) return;
      e.preventDefault();
      row.classList.add('is-pressed');
      setTimeout(function () {
        row.classList.remove('is-pressed');
      }, 180);
      openPersonModal(Number(row.getAttribute('data-person-id')));
    });

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var row = e.target.closest && e.target.closest('tr.lt-row-clickable[data-person-id]');
      if (!row || e.target !== row) return;
      e.preventDefault();
      openPersonModal(Number(row.getAttribute('data-person-id')));
    });

    document.querySelectorAll('[data-close-person-modal]').forEach(function (el) {
      el.addEventListener('click', closePersonModal);
    });
    $('ltPersonLogBtn') &&
      $('ltPersonLogBtn').addEventListener('click', function () {
        var emp = state.personEmp;
        closePersonModal();
        if (emp) openLogModal(null, emp);
        else openLogModal(null);
      });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && $('ltPersonModal') && !$('ltPersonModal').hidden) {
        closePersonModal();
      }
    });

    document.querySelectorAll('.lt-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        setTab(btn.getAttribute('data-tab'));
      });
    });

    document.querySelectorAll('[data-card-filter]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        /* Anchors (e.g. Repeat Sick) navigate to their section page */
        if (btn.tagName === 'A' && btn.getAttribute('href')) return;
        e.preventDefault();
        applyCardFilter(btn.getAttribute('data-card-filter'));
      });
    });

    document.addEventListener('click', function (e) {
      var filterBtn = e.target.closest('[data-col-filter]');
      if (filterBtn) {
        e.preventDefault();
        e.stopPropagation();
        if (state.colFilterKey === filterBtn.getAttribute('data-col-filter') && !$('ltColMenu').hidden) {
          closeColMenu();
        } else {
          openColMenu(filterBtn);
        }
        return;
      }
      if ($('ltColMenu') && !$('ltColMenu').hidden && !e.target.closest('#ltColMenu')) {
        closeColMenu();
      }
    });

    $('ltColMenuApply') && $('ltColMenuApply').addEventListener('click', applyColMenu);
    $('ltColMenuClear') && $('ltColMenuClear').addEventListener('click', clearColMenu);
    $('ltColMenuInput') &&
      $('ltColMenuInput').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          applyColMenu();
        } else if (e.key === 'Escape') {
          closeColMenu();
        }
      });
    $('ltColMenuList') &&
      $('ltColMenuList').addEventListener('change', function (e) {
        if (e.target && e.target.name === 'ltColPick') {
          if ($('ltColMenuInput')) $('ltColMenuInput').value = e.target.value;
        }
      });
    $('ltColMenuList') &&
      $('ltColMenuList').addEventListener('dblclick', function (e) {
        var opt = e.target.closest('.lt-col-menu-opt');
        if (!opt) return;
        var radio = opt.querySelector('input[name="ltColPick"]');
        if (radio) {
          radio.checked = true;
          if ($('ltColMenuInput')) $('ltColMenuInput').value = radio.value;
          applyColMenu();
        }
      });

    document.addEventListener('focusout', onCellBlur);
    document.addEventListener('keydown', onCellKey);

    $('ltExportBtn') && $('ltExportBtn').addEventListener('click', downloadExport);
    $('ltTemplateBtn') && $('ltTemplateBtn').addEventListener('click', downloadTemplate);
    $('ltImportBtn') &&
      $('ltImportBtn').addEventListener('click', function () {
        $('ltImportFile').click();
      });
    $('ltImportFile') &&
      $('ltImportFile').addEventListener('change', function () {
        if (this.files && this.files[0]) uploadImport(this.files[0]);
        this.value = '';
      });

    $('ltSeedBtn') &&
      $('ltSeedBtn').addEventListener('click', function (e) {
        if (e.shiftKey) {
          $('ltSeedFile').click();
          return;
        }
        confirmDialog({
          title: 'Seed staff',
          message:
            'Load staff from the bundled July 2026 staff list?\n\nExisting Emp IDs are skipped.\n\nTip: Shift+click to upload a different staff Excel instead.',
          confirmLabel: 'Load staff',
          danger: false,
        }).then(function (ok) {
          if (ok) seedStaff(null);
        });
      });
    $('ltSeedFile') &&
      $('ltSeedFile').addEventListener('change', function () {
        if (this.files && this.files[0]) seedStaff(this.files[0]);
        this.value = '';
      });

    function openLog() {
      openLogModal(null);
    }
    $('ltLogLeaveBtn') && $('ltLogLeaveBtn').addEventListener('click', openLog);

    document.querySelectorAll('[data-close-log-modal]').forEach(function (el) {
      el.addEventListener('click', closeLogModal);
    });

    $('ltLogTypeFilter') &&
      $('ltLogTypeFilter').addEventListener('change', function () {
        loadLogs();
        syncLogsClearBtn();
      });
    $('ltLogCompanyFilter') &&
      $('ltLogCompanyFilter').addEventListener('change', function () {
        loadLogs();
        syncLogsClearBtn();
      });
    ['ltLogLeaveFrom', 'ltLogLeaveTo', 'ltLogCreatedFrom', 'ltLogCreatedTo'].forEach(
      function (id) {
        $(id) &&
          $(id).addEventListener('change', function () {
            syncLogsClearBtn();
            if (id === 'ltLogLeaveFrom' || id === 'ltLogLeaveTo') loadLogs();
            else renderLogs();
          });
      }
    );

    $('ltLogForm') &&
      $('ltLogForm').addEventListener('submit', function (e) {
        e.preventDefault();
        var empId = Number($('ltLogEmployeeId').value);
        if (!empId) {
          $('ltLogEmployeeSearch').classList.add('is-invalid');
          $('ltLogEmployeeSearch').focus();
          showImportResult('Select an employee from the list (type Emp ID or name)', true);
          return;
        }
        var id = $('ltLogId').value;
        var payload = {
          employee_id: empId,
          leave_type: $('ltLogType').value,
          leave_date: $('ltLogDate').value,
          end_date: $('ltLogEndDate').value || $('ltLogDate').value,
          days: calcLogDays(),
          notes: $('ltLogNotes').value,
        };
        var req = id
          ? apiJson('/hr/api/leave-tracker/logs/' + id, 'PATCH', payload)
          : apiJson('/hr/api/leave-tracker/logs', 'POST', payload);
        req
          .then(function () {
            closeLogModal();
            showImportResult(id ? 'Log updated — staff master refreshed' : 'Leave logged — staff master updated');
            refreshAll();
          })
          .catch(function (err) {
            showImportResult(err.message, true);
          });
      });

    $('ltLogsBody') &&
      $('ltLogsBody').addEventListener('click', function (e) {
        var edit = e.target.closest('[data-edit-log]');
        var del = e.target.closest('[data-del-log]');
        if (edit) {
          var eid = Number(edit.getAttribute('data-edit-log'));
          var log = state.logs.find(function (x) {
            return x.id === eid;
          });
          if (log) openLogModal(log);
        }
        if (del) {
          var did = del.getAttribute('data-del-log');
          confirmDialog({
            title: 'Delete leave log',
            message: 'Delete this leave log? Staff master totals will update.',
            confirmLabel: 'Delete',
            danger: true,
          }).then(function (ok) {
            if (!ok) return;
            apiJson('/hr/api/leave-tracker/logs/' + did, 'DELETE', {})
              .then(function () {
                showImportResult('Log deleted — staff master refreshed');
                refreshAll();
              })
              .catch(function (err) {
                showImportResult(err.message, true);
              });
          });
        }
      });

    $('ltAddPlanBtn') && $('ltAddPlanBtn').addEventListener('click', openPlanModal);
    document.querySelectorAll('[data-close-modal]').forEach(function (el) {
      el.addEventListener('click', closePlanModal);
    });

    $('ltPlanForm') &&
      $('ltPlanForm').addEventListener('submit', function (e) {
        e.preventDefault();
        var empId = Number($('ltPlanEmployeeId').value);
        if (!empId) {
          $('ltPlanEmployeeSearch').classList.add('is-invalid');
          $('ltPlanEmployeeSearch').focus();
          showImportResult('Select an employee from the list (type Emp ID or name)', true);
          return;
        }
        var payload = {
          employee_id: empId,
          start_date: $('ltPlanStart').value,
          end_date: $('ltPlanEnd').value,
          notes: $('ltPlanNotes').value,
        };
        apiJson('/hr/api/leave-tracker/plans', 'POST', payload)
          .then(function () {
            closePlanModal();
            loadPlans();
            showImportResult('Plan saved');
          })
          .catch(function (err) {
            showImportResult(err.message, true);
          });
      });

    $('ltPlansBody') &&
      $('ltPlansBody').addEventListener('click', function (e) {
        var del = e.target.closest('[data-del]');
        var apply = e.target.closest('[data-apply]');
        if (del) {
          var id = del.getAttribute('data-del');
          confirmDialog({
            title: 'Delete leave plan',
            message: 'Delete this leave plan?',
            confirmLabel: 'Delete',
            danger: true,
          }).then(function (ok) {
            if (!ok) return;
            apiJson('/hr/api/leave-tracker/plans/' + id, 'DELETE', {})
              .then(function () {
                loadPlans();
              })
              .catch(function (err) {
                showImportResult(err.message, true);
              });
          });
        }
        if (apply) {
          var pid = apply.getAttribute('data-apply');
          confirmDialog({
            title: 'Apply leave plan',
            message:
              'Create leave logs from this plan (days split by month) and update the staff master?',
            confirmLabel: 'Apply',
            danger: false,
          }).then(function (ok) {
            if (!ok) return;
            apiJson('/hr/api/leave-tracker/plans/' + pid + '/apply-monthly', 'POST', {})
              .then(function () {
                showImportResult('Plan applied as leave logs — staff master updated');
                refreshAll();
              })
              .catch(function (err) {
                showImportResult(err.message, true);
              });
          });
        }
      });

    wireAutocomplete('ltLogEmployeeSearch', 'ltLogEmployeeResults', selectLogEmployee);
    wireAutocomplete('ltPlanEmployeeSearch', 'ltPlanEmployeeResults', selectPlanEmployee);

    $('ltLogDate') && $('ltLogDate').addEventListener('change', calcLogDays);
    $('ltLogEndDate') && $('ltLogEndDate').addEventListener('change', calcLogDays);
    $('ltLogDate') && $('ltLogDate').addEventListener('input', calcLogDays);
    $('ltLogEndDate') && $('ltLogEndDate').addEventListener('input', calcLogDays);

    loadDirectory();
    loadEmployees();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
