/**
 * Leave Tracker — month cards with shared roster; Leave Logs are the source of truth
 */
(function () {
  'use strict';

  var MONTH_LABELS = {
    1: 'Jan',
    2: 'Feb',
    3: 'Mar',
    4: 'Apr',
    5: 'May',
    6: 'Jun',
    7: 'Jul',
    8: 'Aug',
    9: 'Sep',
    10: 'Oct',
    11: 'Nov',
    12: 'Dec',
  };
  var MONTH_FULL = {
    1: 'January',
    2: 'February',
    3: 'March',
    4: 'April',
    5: 'May',
    6: 'June',
    7: 'July',
    8: 'August',
    9: 'September',
    10: 'October',
    11: 'November',
    12: 'December',
  };
  var BASE_YEAR = 2026;
  var PERIODS_KEY = 'ltMonthPeriods';
  var DEFAULT_PERIODS = { '2026': [7, 8, 9, 10, 11, 12] };
  var SICK_ENTITLEMENT = 15;
  var VALID_TABS = ['logs', 'sick', 'annual', 'planner'];

  function clonePeriods(src) {
    var out = {};
    Object.keys(src || {}).forEach(function (y) {
      out[y] = (src[y] || []).slice();
    });
    return out;
  }

  function defaultPeriods() {
    return clonePeriods(DEFAULT_PERIODS);
  }

  function normalizePeriods(raw) {
    var out = defaultPeriods();
    if (!raw || typeof raw !== 'object') return out;
    Object.keys(raw).forEach(function (key) {
      var year = parseInt(key, 10);
      if (year < 2026 || year > 2035) return;
      var months = [];
      (raw[key] || []).forEach(function (item) {
        var m = parseInt(item, 10);
        if (m >= 1 && m <= 12 && months.indexOf(m) < 0) months.push(m);
      });
      if (year === 2026) {
        DEFAULT_PERIODS['2026'].forEach(function (m) {
          if (months.indexOf(m) < 0) months.push(m);
        });
      }
      months.sort(function (a, b) {
        return a - b;
      });
      if (months.length) out[String(year)] = months;
    });
    return out;
  }

  function readLocalPeriods() {
    try {
      var raw = localStorage.getItem(PERIODS_KEY);
      if (raw) return normalizePeriods(JSON.parse(raw));
    } catch (e) { /* ignore */ }
    return defaultPeriods();
  }

  function activePeriods() {
    return (state && state.periods) || readLocalPeriods();
  }

  function periodYears(periods) {
    return Object.keys(periods || activePeriods())
      .map(function (y) {
        return parseInt(y, 10);
      })
      .filter(function (y) {
        return y;
      })
      .sort(function (a, b) {
        return a - b;
      });
  }

  function monthsForYear(year) {
    var list = activePeriods()[String(year)] || [];
    return list.slice();
  }

  function hasPeriod(year, month) {
    return monthsForYear(year).indexOf(Number(month)) >= 0;
  }

  function openMonths() {
    return monthsForYear(state.openYear);
  }

  function allPeriodSlots() {
    var slots = [];
    periodYears().forEach(function (y) {
      monthsForYear(y).forEach(function (m) {
        slots.push({ year: y, month: m });
      });
    });
    return slots;
  }

  function adjacentPeriod(delta) {
    var slots = allPeriodSlots();
    var i = -1;
    slots.forEach(function (s, idx) {
      if (s.year === Number(state.openYear) && s.month === Number(state.openMonth)) i = idx;
    });
    if (i < 0) return null;
    return slots[i + delta] || null;
  }

  function syncMonthNav() {
    var prev = adjacentPeriod(-1);
    var next = adjacentPeriod(1);
    var prevBtn = $('ltPrevMonth');
    var nextBtn = $('ltNextMonth');
    if (prevBtn) {
      prevBtn.disabled = !prev;
      prevBtn.textContent = prev
        ? '← ' + (MONTH_FULL[prev.month] || '')
        : '← Previous';
      prevBtn.setAttribute(
        'aria-label',
        prev ? 'Previous month, ' + MONTH_FULL[prev.month] + ' ' + prev.year : 'No previous month'
      );
    }
    if (nextBtn) {
      nextBtn.disabled = !next;
      nextBtn.textContent = next
        ? (MONTH_FULL[next.month] || '') + ' →'
        : 'Next →';
      nextBtn.setAttribute(
        'aria-label',
        next ? 'Next month, ' + MONTH_FULL[next.month] + ' ' + next.year : 'No next month'
      );
    }
  }

  function shiftOpenMonth(delta) {
    var next = adjacentPeriod(delta);
    if (!next) return;
    setOpenMonth(next.month, { year: next.year, skipTabReset: true });
  }

  function writeMonthUrl() {
    if (!(window.history && window.history.replaceState)) return;
    try {
      var url = new URL(window.location.href);
      if (state.view === 'month' && state.openMonth) {
        url.searchParams.set('year', String(state.openYear));
        url.searchParams.set('month', String(state.openMonth));
        if (state.tab && state.tab !== 'logs') url.searchParams.set('tab', state.tab);
        else url.searchParams.delete('tab');
      } else {
        url.searchParams.delete('month');
        url.searchParams.delete('year');
        url.searchParams.delete('tab');
      }
      var qs = url.searchParams.toString();
      window.history.replaceState({}, '', url.pathname + (qs ? '?' + qs : '') + url.hash);
    } catch (e) { /* ignore */ }
  }

  function currentTrackerPeriod() {
    var now = new Date();
    var y = now.getFullYear();
    var m = now.getMonth() + 1;
    if (hasPeriod(y, m)) return { year: y, month: m };
    var years = periodYears();
    if (!years.length) return { year: BASE_YEAR, month: 7 };
    if (y < years[0]) {
      var first = monthsForYear(years[0]);
      return { year: years[0], month: first[0] };
    }
    var lastYear = years[years.length - 1];
    var lastMonths = monthsForYear(lastYear);
    return { year: lastYear, month: lastMonths[lastMonths.length - 1] };
  }

  var _nowPeriod = currentTrackerPeriod();
  var state = {
    employees: [],
    directory: [], // full unfiltered staff for typeahead
    plans: [],
    logs: [],
    tab: 'logs',
    view: 'grid',
    periods: readLocalPeriods(),
    openYear: _nowPeriod.year,
    openMonth: _nowPeriod.month,
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
    logSort: { key: null, dir: 'desc' },
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
    var month = state.openMonth;
    var alerts = $('ltAlertsOnly') && $('ltAlertsOnly').checked;
    var params = new URLSearchParams();
    if (q.trim()) params.set('q', q.trim());
    if (company && company !== 'all') params.set('company', company);
    if (state.openYear) params.set('year', String(state.openYear));
    if (month) params.set('month', String(month));
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
    var leaveFrom = ($('ltLogLeaveFrom') && $('ltLogLeaveFrom').value) || '';
    var leaveTo = ($('ltLogLeaveTo') && $('ltLogLeaveTo').value) || '';
    if (q) params.set('q', q);
    if (company && company !== 'all') params.set('company', company);
    if (lt && lt !== 'all') params.set('leave_type', lt);
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
      var sick = summary.sick_staff_month != null ? summary.sick_staff_month : 0;
      var annual = summary.annual_staff_month != null ? summary.annual_staff_month : 0;
      $('ltStatLeaveDays').innerHTML =
        '<span class="lt-stat-val-pair">' +
        '<span>' + sick + '<small>sick</small></span>' +
        '<span>' + annual + '<small>annual</small></span>' +
        '</span>';
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

  function pad2(n) {
    return n < 10 ? '0' + n : String(n);
  }

  function ymdFromParts(y, m, d) {
    return y + '-' + pad2(m) + '-' + pad2(d);
  }

  function monthStartYmd(month, year) {
    year = year == null ? state.openYear : year;
    return ymdFromParts(year, month, 1);
  }

  function daysInMonth(month, year) {
    year = year == null ? state.openYear : year;
    return new Date(year, month, 0).getDate();
  }

  function monthEndYmd(month, year) {
    year = year == null ? state.openYear : year;
    return ymdFromParts(year, month, daysInMonth(month, year));
  }

  function defaultDateInOpenMonth() {
    var m = state.openMonth;
    var start = monthStartYmd(m);
    var end = monthEndYmd(m);
    var today = new Date();
    var iso = ymdFromParts(today.getFullYear(), today.getMonth() + 1, today.getDate());
    if (iso >= start && iso <= end) return iso;
    return start;
  }

  function monthValue(map, month) {
    if (!map) return null;
    if (map[month] != null) return map[month];
    if (map[String(month)] != null) return map[String(month)];
    return null;
  }

  function sumMonths(map, months) {
    var total = 0;
    var any = false;
    (months || []).forEach(function (mo) {
      var v = monthValue(map, mo);
      if (v != null && v !== '') {
        var n = Number(v);
        if (!Number.isNaN(n)) {
          total += n;
          any = true;
        }
      }
    });
    return any ? total : 0;
  }

  function monthsThrough(month, year) {
    year = year == null ? state.openYear : year;
    if (year === BASE_YEAR) {
      var all = [];
      for (var m = 1; m <= month; m++) all.push(m);
      return all;
    }
    return monthsForYear(year).filter(function (mo) {
      return mo <= month;
    });
  }

  function monthsBefore(month, year) {
    year = year == null ? state.openYear : year;
    if (year === BASE_YEAR) {
      var prior = [];
      for (var m = 1; m < month; m++) prior.push(m);
      return prior;
    }
    return monthsForYear(year).filter(function (mo) {
      return mo < month;
    });
  }

  function asOfSick(e, month) {
    var sick = (e && e.sick) || {};
    var months = sick.months || {};
    var thisMonth = monthValue(months, month);
    var ytd = sumMonths(months, monthsThrough(month));
    var remaining = SICK_ENTITLEMENT - ytd;
    var alert = '';
    if (ytd >= SICK_ENTITLEMENT) alert = 'exhausted';
    else if (ytd >= 13) alert = 'critical';
    else if (ytd >= 10) alert = 'warning';
    return {
      thisMonth: thisMonth,
      ytd: ytd,
      remaining: remaining,
      alert: alert,
    };
  }

  function asOfAnnual(e, month) {
    var an = (e && e.annual) || {};
    var months = an.months || {};
    var entitlement = e && e.annual_entitlement != null ? Number(e.annual_entitlement) : null;
    var thisMonth = monthValue(months, month);
    var usedBefore = sumMonths(months, monthsBefore(month));
    var usedYtd = sumMonths(months, monthsThrough(month));
    var bf = entitlement == null ? null : entitlement - usedBefore;
    var remaining = entitlement == null ? null : entitlement - usedYtd;
    return {
      thisMonth: thisMonth,
      broughtForward: bf,
      remaining: remaining,
      entitlement: entitlement,
    };
  }

  function rangeOverlapsMonth(startYmd, endYmd, month, year) {
    year = year == null ? state.openYear : year;
    var start = toYmdKey(startYmd);
    var end = toYmdKey(endYmd || startYmd) || start;
    if (!start) return false;
    var ms = monthStartYmd(month, year);
    var me = monthEndYmd(month, year);
    return start <= me && end >= ms;
  }

  function continuesHtml(startYmd, endYmd, month, year) {
    year = year == null ? state.openYear : year;
    var start = toYmdKey(startYmd);
    var end = toYmdKey(endYmd || startYmd) || start;
    if (!start) return '';
    var startKey = start.slice(0, 7);
    var endKey = end.slice(0, 7);
    var openKey = ymdFromParts(year, month, 1).slice(0, 7);
    if (startKey === endKey) return '';
    var bits = [];
    if (startKey < openKey) {
      bits.push('from ' + (MONTH_LABELS[Number(start.slice(5, 7))] || start.slice(5, 7)));
    }
    if (endKey > openKey) {
      bits.push('into ' + (MONTH_LABELS[Number(end.slice(5, 7))] || end.slice(5, 7)));
    }
    if (!bits.length) return '';
    return '<span class="lt-continues">' + esc(bits.join(' · ')) + '</span>';
  }

  var ROSTER_BANNER_DISMISS_KEY = 'ltRosterBannerDismissed';

  function showRosterBanner(detail) {
    var banner = $('ltRosterBanner');
    var text = $('ltRosterBannerText');
    if (!banner) return;
    if (text && detail) text.textContent = detail;
    banner.hidden = false;
    try {
      sessionStorage.removeItem(ROSTER_BANNER_DISMISS_KEY);
    } catch (e) { /* ignore */ }
  }

  function hideRosterBanner() {
    var banner = $('ltRosterBanner');
    if (banner) banner.hidden = true;
    try {
      sessionStorage.setItem(ROSTER_BANNER_DISMISS_KEY, '1');
    } catch (e) { /* ignore */ }
  }

  function periodFromUrl() {
    try {
      var params = new URLSearchParams(window.location.search);
      var year = parseInt(params.get('year'), 10);
      var month = parseInt(params.get('month'), 10);
      var tab = String(params.get('tab') || '').toLowerCase();
      if (!year) year = BASE_YEAR;
      if (!hasPeriod(year, month)) return null;
      return {
        year: year,
        month: month,
        tab: VALID_TABS.indexOf(tab) >= 0 ? tab : null,
      };
    } catch (e) { /* ignore */ }
    return null;
  }

  function monthCardHtml(year, month) {
    return (
      '<article class="lt-month-card" data-year="' +
      year +
      '" data-month="' +
      month +
      '" id="ltMonthCard-' +
      year +
      '-' +
      month +
      '">' +
      '<h2 class="lt-mc-title">' +
      esc(MONTH_FULL[month] || '') +
      '</h2>' +
      '<div class="lt-mc-tags" data-month-chips="' +
      year +
      '-' +
      month +
      '"></div>' +
      '<div class="lt-mc-foot">' +
      '<div class="lt-mc-metric" data-month-metric="' +
      year +
      '-' +
      month +
      '">—</div>' +
      '<button type="button" class="lt-mc-open" data-open-year="' +
      year +
      '" data-open-month="' +
      month +
      '" aria-label="Open ' +
      esc(MONTH_FULL[month] || '') +
      ' ' +
      year +
      '">Open</button>' +
      '</div>' +
      '</article>'
    );
  }

  function addCardHtml() {
    return (
      '<button type="button" class="lt-month-card lt-add-card" id="ltAddMonthCard" aria-label="Add month card">' +
      '<span class="lt-add-card-plus" aria-hidden="true">+</span>' +
      '<p class="lt-add-card-title">Add card</p>' +
      '<p class="lt-add-card-sub">New year sits on a row below</p>' +
      '</button>'
    );
  }

  function renderMonthBoard() {
    var board = $('ltMonthBoard');
    if (!board) return;
    var years = periodYears();
    var lastYear = years.length ? years[years.length - 1] : BASE_YEAR;
    board.innerHTML = years
      .map(function (year) {
        var months = monthsForYear(year);
        var cards = months.map(function (m) {
          return monthCardHtml(year, m);
        });
        if (year === lastYear) cards.push(addCardHtml());
        return (
          '<section class="lt-year-block" data-year-block="' +
          year +
          '">' +
          '<h2 class="lt-year-heading">' +
          year +
          '</h2>' +
          '<div class="lt-month-cards">' +
          cards.join('') +
          '</div>' +
          '</section>'
        );
      })
      .join('');
    updateMonthChips();
  }

  function persistPeriods(next) {
    state.periods = normalizePeriods(next);
    try {
      localStorage.setItem(PERIODS_KEY, JSON.stringify(state.periods));
    } catch (e) { /* ignore */ }
    renderMonthBoard();
    return apiJson('/hr/api/leave-tracker/periods', 'PUT', { periods: state.periods })
      .then(function (data) {
        if (data && data.periods) state.periods = normalizePeriods(data.periods);
        renderMonthBoard();
        return state.periods;
      })
      .catch(function () {
        return state.periods;
      });
  }

  function nextYearToAdd() {
    var years = periodYears();
    var last = years.length ? years[years.length - 1] : BASE_YEAR;
    return Math.min(2035, last + 1);
  }

  function fillAddCardMonthSelect(year) {
    var sel = $('ltAddCardMonth');
    if (!sel) return;
    var used = monthsForYear(year);
    var html = '';
    for (var m = 1; m <= 12; m++) {
      if (used.indexOf(m) >= 0) continue;
      html += '<option value="' + m + '">' + esc(MONTH_FULL[m]) + '</option>';
    }
    sel.innerHTML = html || '<option value="">All months already added</option>';
    sel.disabled = !html;
  }

  function syncAddCardNote() {
    var year = parseInt(($('ltAddCardYear') && $('ltAddCardYear').value) || '', 10);
    var mode = ($('ltAddCardMode') && $('ltAddCardMode').value) || 'year';
    var note = $('ltAddCardNote');
    var wrap = $('ltAddCardMonthWrap');
    if (wrap) wrap.hidden = mode !== 'month';
    if (year) fillAddCardMonthSelect(year);
    if (!note) return;
    var years = periodYears();
    if (year && years.indexOf(year) < 0) {
      note.textContent = year + ' will appear as a new row below ' + (years[years.length - 1] || BASE_YEAR) + '.';
    } else if (mode === 'year') {
      note.textContent = 'Missing months in ' + (year || 'this year') + ' will be added to that year’s row.';
    } else {
      note.textContent = 'This month is added to the ' + (year || '') + ' row.';
    }
  }

  function openAddCardModal() {
    var modal = $('ltAddCardModal');
    if (!modal) return;
    if ($('ltAddCardYear')) $('ltAddCardYear').value = String(nextYearToAdd());
    if ($('ltAddCardMode')) $('ltAddCardMode').value = 'year';
    syncAddCardNote();
    modal.hidden = false;
    setTimeout(function () {
      if ($('ltAddCardYear')) $('ltAddCardYear').focus();
    }, 50);
  }

  function closeAddCardModal() {
    if ($('ltAddCardModal')) $('ltAddCardModal').hidden = true;
  }

  function submitAddCard() {
    var year = parseInt(($('ltAddCardYear') && $('ltAddCardYear').value) || '', 10);
    var mode = ($('ltAddCardMode') && $('ltAddCardMode').value) || 'year';
    if (!year || year < 2026 || year > 2035) {
      throw new Error('Year must be between 2026 and 2035');
    }
    var next = clonePeriods(state.periods);
    var existing = next[String(year)] ? next[String(year)].slice() : [];
    var add = [];
    if (mode === 'year') {
      for (var m = 1; m <= 12; m++) add.push(m);
    } else {
      var month = parseInt(($('ltAddCardMonth') && $('ltAddCardMonth').value) || '', 10);
      if (!month) throw new Error('Choose a month that is not already on the board');
      add.push(month);
    }
    add.forEach(function (m) {
      if (existing.indexOf(m) < 0) existing.push(m);
    });
    existing.sort(function (a, b) {
      return a - b;
    });
    next[String(year)] = existing;
    closeAddCardModal();
    persistPeriods(next).then(function () {
      showMonthGrid();
    });
  }

  function showMonthGrid() {
    state.view = 'grid';
    if ($('ltMonthBoard')) $('ltMonthBoard').hidden = false;
    if ($('ltMonthDetail')) $('ltMonthDetail').hidden = true;
    document.querySelectorAll('.lt-month-card').forEach(function (card) {
      card.classList.remove('is-open');
      card.removeAttribute('aria-current');
      var openBtn = card.querySelector('.lt-mc-open');
      if (openBtn) openBtn.textContent = 'Open';
    });
    updateMonthChips();
    if (window.history && window.history.replaceState) {
      try {
        var url = new URL(window.location.href);
        url.searchParams.delete('month');
        url.searchParams.delete('year');
        url.searchParams.delete('tab');
        window.history.replaceState({}, '', url.pathname + (url.search || '') + url.hash);
      } catch (e) { /* ignore */ }
    }
  }

  function placeMonthWorkspace() {
    var detail = $('ltMonthDetail');
    var workspace = $('ltMonthWorkspace');
    if (!detail || !workspace) return;
    if (workspace.parentNode !== detail) detail.appendChild(workspace);
    detail.hidden = false;
  }

  function setOpenMonth(month, opts) {
    opts = opts || {};
    month = Number(month);
    var year = Number(opts.year != null ? opts.year : state.openYear);
    if (!hasPeriod(year, month)) return;
    var changed = state.openMonth !== month || state.openYear !== year || state.view !== 'month';
    state.openMonth = month;
    state.openYear = year;
    state.view = 'month';
    if ($('ltMonthBoard')) $('ltMonthBoard').hidden = true;
    placeMonthWorkspace();
    var heading = $('ltMonthDetailTitle');
    if (heading) heading.textContent = (MONTH_FULL[month] || '') + ' ' + year;
    syncMonthNav();
    if (!opts.skipTabReset && changed) {
      setTab('logs');
    } else {
      setTab(state.tab);
    }
    updateMonthChips();
    if (!opts.skipLoad) {
      loadEmployees();
      loadLogs();
      loadPlans();
    }
    if (!opts.skipScroll && window.scrollTo) {
      window.scrollTo({ top: 0, behavior: opts.instant ? 'auto' : 'smooth' });
    }
    if (!opts.skipUrl) writeMonthUrl();
  }

  function overlapDaysInMonth(log, year, month) {
    var start = toYmdKey(log && log.leave_date);
    var end = toYmdKey((log && log.end_date) || start) || start;
    if (!start) return 0;
    var ms = monthStartYmd(month, year);
    var me = monthEndYmd(month, year);
    var from = start > ms ? start : ms;
    var to = end < me ? end : me;
    if (from > to) return 0;
    var days = Math.round((new Date(to + 'T00:00:00') - new Date(from + 'T00:00:00')) / 86400000) + 1;
    return days > 0 ? days : 0;
  }

  function updateMonthChips() {
    periodYears().forEach(function (year) {
      var months = monthsForYear(year);
      months.forEach(function (m) {
        var key = year + '-' + m;
        var tags = document.querySelector('[data-month-chips="' + key + '"]');
        var metric = document.querySelector('[data-month-metric="' + key + '"]');
        var logs = (state.logs || []).filter(function (p) {
          return rangeOverlapsMonth(p.leave_date, p.end_date || p.leave_date, m, year);
        });
        var onLeaveIds = {};
        var sickDays = 0;
        var annualDays = 0;
        logs.forEach(function (p) {
          if (p.employee_id) onLeaveIds[p.employee_id] = true;
          var days = overlapDaysInMonth(p, year, m);
          if ((p.leave_type || '') === 'sick') sickDays += days;
          if ((p.leave_type || '') === 'annual') annualDays += days;
        });
        var onLeave = Object.keys(onLeaveIds).length;
        if (tags) {
          tags.innerHTML =
            '<span class="lt-chip">' +
            logs.length +
            ' log' +
            (logs.length === 1 ? '' : 's') +
            '</span>' +
            '<span class="lt-chip">' +
            fmtDays(sickDays) +
            ' sick</span>' +
            '<span class="lt-chip">' +
            fmtDays(annualDays) +
            ' annual</span>';
        }
        if (metric) metric.textContent = onLeave + ' on leave';
      });
    });
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
    var rows = (state.logs || []).filter(function (p) {
      return rangeOverlapsMonth(p.leave_date, p.end_date || p.leave_date, state.openMonth);
    });
    var filters = state.logColFilters || {};
    var leaveFrom = ($('ltLogLeaveFrom') && $('ltLogLeaveFrom').value) || '';
    var leaveTo = ($('ltLogLeaveTo') && $('ltLogLeaveTo').value) || '';
    var createdFrom = ($('ltLogCreatedFrom') && $('ltLogCreatedFrom').value) || '';
    var createdTo = ($('ltLogCreatedTo') && $('ltLogCreatedTo').value) || '';
    var editedFrom = ($('ltLogEditedFrom') && $('ltLogEditedFrom').value) || '';
    var editedTo = ($('ltLogEditedTo') && $('ltLogEditedTo').value) || '';
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
      if (!inYmdRange(p.updated_at || p.created_at, editedFrom, editedTo)) return false;
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
    var editedFrom = ($('ltLogEditedFrom') && $('ltLogEditedFrom').value) || '';
    var editedTo = ($('ltLogEditedTo') && $('ltLogEditedTo').value) || '';
    return (
      hasCol ||
      !!q.trim() ||
      (lt && lt !== 'all') ||
      (company && company !== 'all') ||
      !!leaveFrom ||
      !!leaveTo ||
      !!createdFrom ||
      !!createdTo ||
      !!editedFrom ||
      !!editedTo
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

  function logSortValue(p, key) {
    if (key === 'log_created') return String(p.created_at || '');
    if (key === 'log_edited') return String(p.updated_at || p.created_at || '');
    return '';
  }

  function sortedLogs(rows) {
    var key = state.logSort && state.logSort.key;
    if (!key) return rows;
    var dir = state.logSort.dir === 'asc' ? 1 : -1;
    return rows.slice().sort(function (a, b) {
      var av = logSortValue(a, key);
      var bv = logSortValue(b, key);
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return ((a.id || 0) - (b.id || 0)) * dir;
    });
  }

  function toggleLogSort(key) {
    if (!key) return;
    if (state.logSort.key === key) {
      state.logSort.dir = state.logSort.dir === 'desc' ? 'asc' : 'desc';
    } else {
      state.logSort.key = key;
      state.logSort.dir = 'desc';
    }
    renderLogs();
  }

  function syncLogSortButtons() {
    var key = state.logSort && state.logSort.key;
    var dir = (state.logSort && state.logSort.dir) || 'desc';
    document.querySelectorAll('.lt-sort-btn').forEach(function (btn) {
      var col = btn.getAttribute('data-sort-col');
      var active = col === key;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-sort', active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none');
      var th = btn.closest('th');
      if (th) th.setAttribute('aria-sort', active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none');
    });
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
    var month = state.openMonth;
    if (!rows.length) {
      tbody.innerHTML = state.employees.length
        ? '<tr><td colspan="8" class="lt-empty">No staff match these column filters.</td></tr>'
        : '<tr><td colspan="8" class="lt-empty">No staff yet. Click <strong>Add employee</strong> or <strong>Seed Staff</strong>, then use <strong>Log leave</strong> to record days.</td></tr>';
      syncColFilterButtons();
      return;
    }
    tbody.innerHTML = rows
      .map(function (e) {
        var sick = asOfSick(e, month);
        var alert = sick.alert || '';
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
          '<td class="lt-num lt-month-ro">' +
          esc(fmtDays(sick.thisMonth)) +
          '</td>' +
          '<td class="lt-num">' +
          esc(fmtDays(sick.ytd)) +
          '</td>' +
          '<td class="lt-num">' +
          esc(fmtDays(sick.remaining)) +
          '</td>' +
          '<td class="lt-col-alert">' +
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
    var month = state.openMonth;
    if (!rows.length) {
      tbody.innerHTML = state.employees.length
        ? '<tr><td colspan="8" class="lt-empty">No staff match these column filters.</td></tr>'
        : '<tr><td colspan="8" class="lt-empty">No staff yet. Click <strong>Add employee</strong> or <strong>Seed Staff</strong>.</td></tr>';
      syncColFilterButtons();
      return;
    }
    tbody.innerHTML = rows
      .map(function (e) {
        var an = asOfAnnual(e, month);
        var rem = an.remaining == null ? '—' : fmtDays(an.remaining);
        var bf = an.broughtForward == null ? '—' : fmtDays(an.broughtForward);
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
          '<td class="lt-num">' +
          '<input class="lt-cell lt-ent" type="number" min="0" step="1" ' +
          'data-emp="' +
          e.id +
          '" data-field="annual_entitlement" value="' +
          esc(e.annual_entitlement != null ? e.annual_entitlement : '') +
          '" placeholder="—" aria-label="Annual entitlement"></td>' +
          '<td class="lt-num lt-month-ro">' +
          esc(bf) +
          '</td>' +
          '<td class="lt-num lt-month-ro">' +
          esc(fmtDays(an.thisMonth)) +
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
    var logs = sortedLogs(filteredLogs());
    syncColFilterButtons();
    syncLogSortButtons();
    if (!all.length) {
      tbody.innerHTML =
        '<tr><td colspan="10" class="lt-empty">No leave logs in ' +
        esc(MONTH_FULL[state.openMonth] || 'this month') +
        ' yet. Click <strong>Log leave</strong> to add an entry.</td></tr>';
      return;
    }
    if (!logs.length) {
      tbody.innerHTML =
        '<tr><td colspan="10" class="lt-empty">No leave logs match these filters for ' +
        esc(MONTH_FULL[state.openMonth] || 'this month') +
        '.</td></tr>';
      return;
    }
    tbody.innerHTML = logs
      .map(function (p) {
        var end = p.end_date || p.leave_date;
        var chip = continuesHtml(p.leave_date, end, state.openMonth);
        return (
          '<tr class="lt-row-clickable" data-log="' +
          p.id +
          '" data-person-id="' +
          p.employee_id +
          '">' +
          '<td>' +
          esc(fmtDateDMY(p.leave_date)) +
          chip +
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

  function shortFirstName(name) {
    var parts = String(name || '')
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    return parts[0] || '—';
  }

  function plannerLeaveKindLabel(p) {
    if (p && p.kind === 'planned') return 'Planned';
    var t = String((p && p.leave_type) || 'annual').toLowerCase();
    if (t === 'annual') return 'Annual leave';
    if (t === 'sick') return 'Sick leave';
    return t ? t.charAt(0).toUpperCase() + t.slice(1) + ' leave' : 'Leave';
  }

  function plannerChipClass(p) {
    if (p && p.kind === 'planned') return 'is-planned';
    var t = String((p && p.leave_type) || 'annual').toLowerCase();
    if (t === 'sick') return 'is-sick';
    return 'is-annual';
  }

  function plannerChipLabel(p) {
    return shortFirstName(p && p.full_name) + ' - ' + plannerLeaveKindLabel(p);
  }

  function todayYmdDubai() {
    var now = new Date();
    try {
      var tz = (window.InjaazDateTimeUAE && InjaazDateTimeUAE.TZ) || 'Asia/Dubai';
      var parts = new Intl.DateTimeFormat('en-GB', {
        timeZone: tz,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(now);
      var map = {};
      parts.forEach(function (p) {
        if (p.type !== 'literal') map[p.type] = p.value;
      });
      if (map.year && map.month && map.day) return map.year + '-' + map.month + '-' + map.day;
    } catch (e) { /* ignore */ }
    return ymdFromParts(now.getFullYear(), now.getMonth() + 1, now.getDate());
  }

  function ymdAddDays(ymd, n) {
    var p = String(ymd).split('-').map(Number);
    var d = new Date(Date.UTC(p[0], p[1] - 1, p[2] + n));
    return ymdFromParts(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
  }

  function eachYmd(start, end, fn) {
    if (!start || !end || start > end) return;
    var cur = start;
    while (cur <= end) {
      fn(cur);
      cur = ymdAddDays(cur, 1);
    }
  }

  function weekdayMon0(ymd) {
    var p = String(ymd).split('-').map(Number);
    var d = new Date(Date.UTC(p[0], p[1] - 1, p[2]));
    return (d.getUTCDay() + 6) % 7;
  }

  function clipRangeToMonth(startYmd, endYmd, month, year) {
    var a = toYmdKey(startYmd);
    var b = toYmdKey(endYmd || startYmd) || a;
    if (!a) return null;
    var ms = monthStartYmd(month, year);
    var me = monthEndYmd(month, year);
    if (a > me || b < ms) return null;
    return { start: a < ms ? ms : a, end: b > me ? me : b };
  }

  function daysOnLeaveInMonth(month, year) {
    year = year == null ? state.openYear : year;
    month = month == null ? state.openMonth : month;
    var byDay = {};
    function dayBucket(ymd) {
      if (!byDay[ymd]) byDay[ymd] = { logged: [], planned: [] };
      return byDay[ymd];
    }
    function loggedKey(empId, ymd) {
      return String(empId) + '|' + ymd;
    }
    var loggedAnnualSet = {};

    (state.logs || []).forEach(function (log) {
      var leaveType = String(log.leave_type || '').toLowerCase();
      if (leaveType !== 'annual' && leaveType !== 'sick') return;
      var clip = clipRangeToMonth(log.leave_date, log.end_date || log.leave_date, month, year);
      if (!clip) return;
      var empId = log.employee_id;
      eachYmd(clip.start, clip.end, function (ymd) {
        if (leaveType === 'annual') loggedAnnualSet[loggedKey(empId, ymd)] = true;
        dayBucket(ymd).logged.push({
          kind: 'logged',
          leave_type: leaveType,
          employee_id: empId,
          emp_id: log.emp_id,
          full_name: log.full_name,
          start: log.leave_date,
          end: log.end_date || log.leave_date,
          notes: log.notes || '',
        });
      });
    });

    (state.plans || []).forEach(function (plan) {
      var clip = clipRangeToMonth(plan.start_date, plan.end_date, month, year);
      if (!clip) return;
      var empId = plan.employee_id;
      eachYmd(clip.start, clip.end, function (ymd) {
        if (loggedAnnualSet[loggedKey(empId, ymd)]) return;
        dayBucket(ymd).planned.push({
          kind: 'planned',
          leave_type: 'annual',
          plan_id: plan.id,
          employee_id: empId,
          emp_id: plan.emp_id,
          full_name: plan.full_name,
          start: plan.start_date,
          end: plan.end_date,
          notes: plan.notes || '',
        });
      });
    });

    Object.keys(byDay).forEach(function (ymd) {
      var b = byDay[ymd];
      function typeRank(p) {
        if (p.kind === 'planned') return 2;
        if (String(p.leave_type || '').toLowerCase() === 'sick') return 1;
        return 0;
      }
      function byTypeThenName(a, c) {
        var d = typeRank(a) - typeRank(c);
        if (d) return d;
        return String(a.full_name || '').localeCompare(String(c.full_name || ''));
      }
      b.logged.sort(byTypeThenName);
      b.planned.sort(byTypeThenName);
      b.all = b.logged.concat(b.planned);
    });
    return byDay;
  }

  function closePlannerPop() {
    var pop = $('ltPlannerPop');
    if (pop) {
      pop.hidden = true;
      pop.innerHTML = '';
    }
  }

  function openPlannerPop(ymd, people, anchor) {
    var pop = $('ltPlannerPop');
    if (!pop) return;
    var items = (people || [])
      .map(function (p) {
        var range = fmtDateDMY(p.start) + (p.end && p.end !== p.start ? ' → ' + fmtDateDMY(p.end) : '');
        var kind = p.kind === 'planned' ? 'Planned' : 'Logged';
        var typeLabel = plannerLeaveKindLabel(p);
        return (
          '<li class="lt-cal-pop-item">' +
          '<button type="button" class="lt-cal-pop-person" data-person-id="' +
          esc(String(p.employee_id || '')) +
          '">' +
          '<span class="lt-cal-pop-name">' +
          esc(p.full_name || '—') +
          '</span>' +
          '<span class="lt-cal-pop-meta">' +
          esc((p.emp_id || '') + (p.emp_id ? ' · ' : '') + typeLabel + ' · ' + kind + ' · ' + range) +
          '</span>' +
          '</button></li>'
        );
      })
      .join('');
    pop.innerHTML =
      '<p class="lt-cal-pop-date">' +
      esc(fmtDateDMY(ymd)) +
      '</p>' +
      (items
        ? '<ul class="lt-cal-pop-list">' + items + '</ul>'
        : '<p class="lt-empty" style="padding:0.5rem !important">No leave this day.</p>');
    pop.hidden = false;
    if (anchor && anchor.getBoundingClientRect) {
      var rect = anchor.getBoundingClientRect();
      var top = rect.bottom + 6;
      var left = Math.min(rect.left, window.innerWidth - 280);
      if (left < 8) left = 8;
      if (top + 220 > window.innerHeight) top = Math.max(8, rect.top - 220);
      pop.style.top = top + 'px';
      pop.style.left = left + 'px';
    }
  }

  function renderPlannerCalendar() {
    var root = $('ltPlannerCal');
    if (!root) return;
    closePlannerPop();
    var month = state.openMonth;
    var year = state.openYear;
    if (!month || !year) {
      root.innerHTML = '';
      return;
    }
    var byDay = daysOnLeaveInMonth(month, year);
    var ms = monthStartYmd(month, year);
    var me = monthEndYmd(month, year);
    var today = todayYmdDubai();
    var lead = weekdayMon0(ms);
    var gridStart = ymdAddDays(ms, -lead);
    var trail = 6 - weekdayMon0(me);
    var gridEnd = ymdAddDays(me, trail);
    var weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    var html =
      '<div class="lt-cal-weekdays" role="row">' +
      weekdays
        .map(function (d) {
          return '<div class="lt-cal-wd" role="columnheader">' + d + '</div>';
        })
        .join('') +
      '</div><div class="lt-cal-grid">';
    var CHIP_MAX = 3;
    eachYmd(gridStart, gridEnd, function (ymd) {
      var inMonth = ymd >= ms && ymd <= me;
      var dayNum = Number(ymd.slice(8, 10));
      var bucket = inMonth ? byDay[ymd] : null;
      var people = (bucket && bucket.all) || [];
      var shown = people.slice(0, CHIP_MAX);
      var extra = people.length - shown.length;
      var chips = shown
        .map(function (p) {
          return (
            '<span class="lt-cal-chip ' +
            plannerChipClass(p) +
            '" title="' +
            esc((p.full_name || '') + ' - ' + plannerLeaveKindLabel(p)) +
            '">' +
            esc(plannerChipLabel(p)) +
            '</span>'
          );
        })
        .join('');
      if (extra > 0) {
        chips +=
          '<button type="button" class="lt-cal-more" data-cal-more="' +
          ymd +
          '">+' +
          extra +
          '</button>';
      }
      var cls = 'lt-cal-cell';
      if (!inMonth) cls += ' is-out';
      if (ymd === today) cls += ' is-today';
      if (people.length) cls += ' has-leave';
      html +=
        '<div class="' +
        cls +
        '" role="gridcell" data-cal-day="' +
        ymd +
        '"' +
        (inMonth ? '' : ' aria-disabled="true"') +
        '>' +
        '<span class="lt-cal-num">' +
        dayNum +
        '</span>' +
        '<div class="lt-cal-chips">' +
        chips +
        '</div></div>';
    });
    html += '</div>';
    root.innerHTML = html;
    renderUpcomingPlans(month, year);
  }

  function renderUpcomingPlans(month, year) {
    var wrap = $('ltUpcomingPlans');
    var list = $('ltUpcomingPlansList');
    if (!wrap || !list) return;
    var plans = (state.plans || []).filter(function (p) {
      return rangeOverlapsMonth(p.start_date, p.end_date, month, year);
    });
    if (!plans.length) {
      wrap.hidden = true;
      list.innerHTML = '';
      return;
    }
    wrap.hidden = false;
    list.innerHTML = plans
      .map(function (p) {
        return (
          '<li class="lt-upcoming-item">' +
          '<div class="lt-upcoming-copy">' +
          '<strong>' +
          esc(p.full_name || '—') +
          '</strong>' +
          '<span>' +
          esc((p.emp_id || '') + ' · ' + fmtDateDMY(p.start_date) + ' → ' + fmtDateDMY(p.end_date) + ' · ' + p.days + 'd') +
          (p.notes ? ' · ' + esc(p.notes) : '') +
          '</span></div>' +
          '<div class="lt-actions">' +
          '<button type="button" data-apply="' +
          p.id +
          '" title="Create leave logs from this plan">Apply to logs</button>' +
          '<button type="button" data-del="' +
          p.id +
          '">Delete</button></div></li>'
        );
      })
      .join('');
  }

  function renderPlans() {
    renderPlannerCalendar();
  }

  function setTab(tab) {
    if (VALID_TABS.indexOf(tab) < 0) tab = 'logs';
    state.tab = tab;
    document.querySelectorAll('.lt-tab').forEach(function (btn) {
      var on = btn.getAttribute('data-tab') === tab;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    if ($('ltPanelSick')) $('ltPanelSick').hidden = tab !== 'sick';
    if ($('ltPanelAnnual')) $('ltPanelAnnual').hidden = tab !== 'annual';
    if ($('ltPanelLogs')) $('ltPanelLogs').hidden = tab !== 'logs';
    if ($('ltPanelPlanner')) $('ltPanelPlanner').hidden = tab !== 'planner';
    if (tab === 'planner') renderPlans();
    if (tab === 'logs') renderLogs();
    if (tab === 'sick') renderSick();
    if (tab === 'annual') renderAnnual();
    if (state.view === 'month') writeMonthUrl();
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
        updateMonthChips();
        if (!state.directory.length) {
          state.directory = data.employees || [];
        }
      })
      .catch(function (err) {
        if ($('ltSickBody')) {
          $('ltSickBody').innerHTML =
            '<tr><td colspan="8" class="lt-empty">' + esc(err.message) + '</td></tr>';
        }
        if ($('ltAnnualBody')) {
          $('ltAnnualBody').innerHTML =
            '<tr><td colspan="8" class="lt-empty">' + esc(err.message) + '</td></tr>';
        }
      });
  }

  function loadLogs() {
    var qs = logsQueryParams();
    var url = '/hr/api/leave-tracker/logs' + (qs ? '?' + qs : '');
    return apiGet(url)
      .then(function (data) {
        state.logs = data.logs || [];
        renderLogs();
        renderPlannerCalendar();
        updateMonthChips();
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
    if (state.openYear) params.set('year', String(state.openYear));
    if (state.view === 'month' && state.openMonth) params.set('month', String(state.openMonth));
    var url = '/hr/api/leave-tracker/plans' + (params.toString() ? '?' + params : '');
    return apiGet(url)
      .then(function (data) {
        state.plans = data.plans || [];
        renderPlans();
        updateMonthChips();
      })
      .catch(function (err) {
        showImportResult(err.message, true);
        renderPlannerCalendar();
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
        var iso = defaultDateInOpenMonth();
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
      el.innerHTML = '<p class="lt-person-empty">No leave logged in this tracker window yet.</p>';
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
    var month = state.openMonth;
    var qs = month ? '?month=' + encodeURIComponent(String(month)) : '';
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
      var iso = defaultDateInOpenMonth();
      if ($('ltPlanStart')) $('ltPlanStart').value = iso;
      if ($('ltPlanEnd')) $('ltPlanEnd').value = iso;
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
      return Promise.all([loadLogs(), loadPlans()]);
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
        if ((data.created || 0) > 0) {
          showRosterBanner(
            (data.created || 0) +
              ' new people are on the main roster and appear in every month with 0 used. Set annual entitlement where needed.'
          );
        }
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
        if ((data.created || 0) > 0) {
          showRosterBanner(
            (data.created || 0) +
              ' people were added to the main roster. They appear in every month with 0 used. Set annual entitlement where needed.'
          );
        }
        refreshAll();
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
    loadLogs();
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

  function openEmpModal() {
    if ($('ltEmpForm')) $('ltEmpForm').reset();
    if ($('ltEmpModal')) $('ltEmpModal').hidden = false;
    setTimeout(function () {
      $('ltEmpIdInput') && $('ltEmpIdInput').focus();
    }, 50);
  }

  function closeEmpModal() {
    if ($('ltEmpModal')) $('ltEmpModal').hidden = true;
  }

  function submitNewEmployee() {
    var payload = {
      emp_id: ($('ltEmpIdInput') && $('ltEmpIdInput').value) || '',
      full_name: ($('ltEmpName') && $('ltEmpName').value) || '',
      designation: ($('ltEmpDesig') && $('ltEmpDesig').value) || '',
      company: ($('ltEmpCompany') && $('ltEmpCompany').value) || 'Kynvera',
    };
    var ent = $('ltEmpEntitlement') && $('ltEmpEntitlement').value;
    if (ent) payload.annual_entitlement = Number(ent);
    return apiJson('/hr/api/leave-tracker/employees', 'POST', payload).then(function () {
      closeEmpModal();
      showImportResult('Employee added to the main list');
      showRosterBanner(
        'A new person is on the main roster and appears in every month with 0 used. Set annual entitlement if needed.'
      );
      state.directory = [];
      return loadDirectory().then(function () {
        return refreshAll();
      });
    });
  }

  function init() {
    var reload = debounce(function () {
      state.alertLevel = '';
      loadEmployees();
      loadLogs();
      loadPlans();
    }, 250);

    $('ltSearch') && $('ltSearch').addEventListener('input', reload);
    $('ltCompany') && $('ltCompany').addEventListener('change', reload);
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
        ['ltLogLeaveFrom', 'ltLogLeaveTo', 'ltLogCreatedFrom', 'ltLogCreatedTo', 'ltLogEditedFrom', 'ltLogEditedTo'].forEach(
          function (id) {
            if ($(id)) $(id).value = '';
          }
        );
        state.logSort = { key: null, dir: 'desc' };
        syncSearchClear('ltLogsSearch', 'ltLogsSearchClear');
        syncColFilterButtons();
        loadLogs();
      });
    $('ltAlertsOnly') &&
      $('ltAlertsOnly').addEventListener('change', function () {
        state.alertLevel = '';
        loadEmployees();
        loadLogs();
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
      var sortBtn = e.target.closest('[data-sort-col]');
      if (sortBtn) {
        e.preventDefault();
        e.stopPropagation();
        toggleLogSort(sortBtn.getAttribute('data-sort-col'));
        return;
      }
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
    ['ltLogLeaveFrom', 'ltLogLeaveTo', 'ltLogCreatedFrom', 'ltLogCreatedTo', 'ltLogEditedFrom', 'ltLogEditedTo'].forEach(
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

    $('ltUpcomingPlans') &&
      $('ltUpcomingPlans').addEventListener('click', function (e) {
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

    $('ltPlannerCal') &&
      $('ltPlannerCal').addEventListener('click', function (e) {
        var more = e.target.closest('[data-cal-more]');
        var cell = e.target.closest('[data-cal-day]');
        if (!cell || cell.classList.contains('is-out')) return;
        var ymd = (more && more.getAttribute('data-cal-more')) || cell.getAttribute('data-cal-day');
        if (!ymd) return;
        var bucket = daysOnLeaveInMonth()[ymd];
        var people = (bucket && bucket.all) || [];
        if (!people.length && !more) return;
        e.preventDefault();
        openPlannerPop(ymd, people, cell);
      });

    $('ltPlannerPop') &&
      $('ltPlannerPop').addEventListener('click', function (e) {
        var person = e.target.closest('[data-person-id]');
        if (!person) return;
        var id = Number(person.getAttribute('data-person-id'));
        closePlannerPop();
        if (id) openPersonModal(id);
      });

    document.addEventListener('click', function (e) {
      var pop = $('ltPlannerPop');
      if (!pop || pop.hidden) return;
      if (e.target.closest('#ltPlannerPop') || e.target.closest('#ltPlannerCal')) return;
      closePlannerPop();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closePlannerPop();
    });

    wireAutocomplete('ltLogEmployeeSearch', 'ltLogEmployeeResults', selectLogEmployee);
    wireAutocomplete('ltPlanEmployeeSearch', 'ltPlanEmployeeResults', selectPlanEmployee);

    $('ltLogDate') && $('ltLogDate').addEventListener('change', calcLogDays);
    $('ltLogEndDate') && $('ltLogEndDate').addEventListener('change', calcLogDays);
    $('ltLogDate') && $('ltLogDate').addEventListener('input', calcLogDays);
    $('ltLogEndDate') && $('ltLogEndDate').addEventListener('input', calcLogDays);

    $('ltMonthBoard') &&
      $('ltMonthBoard').addEventListener('click', function (e) {
        if (e.target.closest('.lt-add-card')) {
          e.preventDefault();
          openAddCardModal();
          return;
        }
        var btn = e.target.closest('[data-open-month]');
        var card = e.target.closest('.lt-month-card');
        if (!card) return;
        var m = btn ? Number(btn.getAttribute('data-open-month')) : Number(card.getAttribute('data-month'));
        var y = btn ? Number(btn.getAttribute('data-open-year')) : Number(card.getAttribute('data-year'));
        if (!m) return;
        e.preventDefault();
        setOpenMonth(m, { year: y });
      });
    $('ltMonthBoard') &&
      $('ltMonthBoard').addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var card = e.target.closest('.lt-month-card');
        if (!card || card.classList.contains('lt-add-card')) return;
        if (e.target !== card) return;
        e.preventDefault();
        setOpenMonth(Number(card.getAttribute('data-month')), {
          year: Number(card.getAttribute('data-year')),
        });
      });

    $('ltBackMonths') &&
      $('ltBackMonths').addEventListener('click', function () {
        showMonthGrid();
      });
    $('ltPrevMonth') &&
      $('ltPrevMonth').addEventListener('click', function () {
        shiftOpenMonth(-1);
      });
    $('ltNextMonth') &&
      $('ltNextMonth').addEventListener('click', function () {
        shiftOpenMonth(1);
      });

    $('ltRosterBannerDismiss') &&
      $('ltRosterBannerDismiss').addEventListener('click', hideRosterBanner);

    $('ltAddEmpBtn') && $('ltAddEmpBtn').addEventListener('click', openEmpModal);
    document.querySelectorAll('[data-close-emp-modal]').forEach(function (el) {
      el.addEventListener('click', closeEmpModal);
    });
    $('ltEmpForm') &&
      $('ltEmpForm').addEventListener('submit', function (e) {
        e.preventDefault();
        submitNewEmployee().catch(function (err) {
          showImportResult(err.message, true);
        });
      });
    document.querySelectorAll('[data-close-add-card]').forEach(function (el) {
      el.addEventListener('click', closeAddCardModal);
    });
    $('ltAddCardYear') && $('ltAddCardYear').addEventListener('input', syncAddCardNote);
    $('ltAddCardMode') && $('ltAddCardMode').addEventListener('change', syncAddCardNote);
    $('ltAddCardForm') &&
      $('ltAddCardForm').addEventListener('submit', function (e) {
        e.preventDefault();
        try {
          submitAddCard();
        } catch (err) {
          showImportResult(err.message, true);
        }
      });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      if ($('ltEmpModal') && !$('ltEmpModal').hidden) {
        closeEmpModal();
        return;
      }
      if ($('ltAddCardModal') && !$('ltAddCardModal').hidden) {
        closeAddCardModal();
      }
    });

    function bootView() {
      renderMonthBoard();
      var start = periodFromUrl();
      if (start) {
        if (start.tab) state.tab = start.tab;
        setOpenMonth(start.month, {
          year: start.year,
          skipTabReset: true,
          skipLoad: true,
          skipUrl: true,
          skipScroll: true,
        });
      } else {
        showMonthGrid();
      }
      loadDirectory();
      loadEmployees();
      loadLogs();
      loadPlans();
    }

    apiGet('/hr/api/leave-tracker/periods')
      .then(function (data) {
        if (data && data.periods) state.periods = normalizePeriods(data.periods);
      })
      .catch(function () { /* local defaults */ })
      .then(bootView);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
