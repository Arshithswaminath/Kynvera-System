/**
 * Manpower Tracker — Excel-like vacancy board
 */
(function () {
  'use strict';

  var state = {
    meta: null,
    vacancies: [],
    summary: null,
    saveTimers: {},
    status: 'all',
    colFilterKey: null,
    linkVacancyId: null,
    linkCandidateId: null,
    linkCandidates: [],
    colOrder: null,
    dragColKey: null,
  };

  var COL_ORDER_KEY = 'mpBoardColOrder.v1';
  var DEFAULT_COL_ORDER = [
    'trade', 'project', 'person', 'requirement_type', 'replacement', 'id',
    'candidate', 'contact', 'status', 'joined', 'remarks', 'actions',
  ];

  var COL_LABELS = {
    trade: 'Trade',
    project: 'Project',
    person: 'Person',
    requirement_type: 'Req type',
    replacement: 'Replacement',
    id: 'ID',
    candidate: 'Candidate',
    contact: 'Contact',
    status: 'Status',
    joined: 'Joined',
    remarks: 'Comment',
    actions: '',
  };

  var FILTERABLE_COLS = {
    trade: true,
    project: true,
    requirement_type: true,
    status: true,
  };

  /** Canonical status list — used when meta is missing or stale (server not restarted). */
  var DEFAULT_STATUSES = [
    { key: 'open', label: 'Open' },
    { key: 'interviewing', label: 'Interviewing' },
    { key: 'selected', label: 'Selected' },
    { key: 'filled', label: 'Filled' },
    { key: 'joined', label: 'Joined' },
    { key: 'on_hold', label: 'On Hold' },
  ];

  function statusList() {
    var fromMeta = (state.meta && state.meta.statuses) || [];
    if (!fromMeta.length) return DEFAULT_STATUSES.slice();
    var byKey = {};
    fromMeta.forEach(function (s) {
      if (s && s.key) byKey[s.key] = { key: s.key, label: s.label || s.key };
    });
    // Ensure every canonical status is present (e.g. after adding Filled before restart)
    DEFAULT_STATUSES.forEach(function (s) {
      if (!byKey[s.key]) byKey[s.key] = s;
    });
    return DEFAULT_STATUSES.map(function (s) {
      return byKey[s.key] || s;
    }).concat(fromMeta.filter(function (s) {
      return s && s.key && !DEFAULT_STATUSES.some(function (d) { return d.key === s.key; });
    }).map(function (s) {
      return byKey[s.key];
    }));
  }

  var COL_CLASS = {
    trade: 'mp-col-trade',
    project: 'mp-col-project',
    person: 'mp-col-person',
    requirement_type: 'mp-col-reqtype',
    replacement: 'mp-col-replacement',
    id: 'mp-col-id',
    candidate: 'mp-col-candidate',
    contact: 'mp-col-contact',
    status: 'mp-col-status',
    joined: 'mp-col-joined',
    remarks: 'mp-col-remarks',
    actions: 'mp-th-actions',
  };

  function $(id) {
    return document.getElementById(id);
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

  /** Prefer dashboard authenticatedFetch / ApiClient so expired JWTs refresh once. */
  function authFetch(url, options) {
    var opts = Object.assign({ credentials: 'same-origin' }, options || {});
    if (typeof authenticatedFetch === 'function') {
      return authenticatedFetch(url, opts).then(function (r) {
        if (r && typeof r.json === 'function') return r;
        return Promise.reject(new Error('Session expired — please log in again'));
      });
    }
    if (window.ApiClient && typeof window.ApiClient.fetch === 'function') {
      return window.ApiClient.fetch(url, opts);
    }
    var headers = Object.assign({}, opts.headers || {}, authHeaders());
    return fetch(url, Object.assign({}, opts, { headers: headers }));
  }

  function unwrap(body) {
    if (!body) return {};
    if (body.data != null && typeof body.data === 'object' && !Array.isArray(body.data)) {
      return Object.assign({}, body, body.data);
    }
    return body;
  }

  function apiGet(url) {
    return authFetch(url, {
      headers: { Accept: 'application/json' },
    }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok || body.success === false) {
          throw new Error((body && (body.error || body.message || body.msg)) || 'Request failed');
        }
        return unwrap(body);
      });
    });
  }

  function apiJson(url, method, payload) {
    return authFetch(url, {
      method: method,
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: payload != null ? JSON.stringify(payload) : undefined,
    }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok || body.success === false) {
          throw new Error((body && (body.error || body.message || body.msg)) || 'Request failed');
        }
        return unwrap(body);
      });
    });
  }

  function downloadBlob(url, filename) {
    return authFetch(url, {}).then(function (r) {
      if (!r.ok) throw new Error('Download failed');
      return r.blob();
    }).then(function (blob) {
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        URL.revokeObjectURL(a.href);
        a.remove();
      }, 1000);
    });
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function showImportResult(msg, isError) {
    var el = $('mpImportResult');
    if (!el) return;
    el.hidden = false;
    el.className = 'hh-import-result' + (isError ? ' hh-import-error' : '');
    el.textContent = msg;
    clearTimeout(showImportResult._t);
    showImportResult._t = setTimeout(function () { el.hidden = true; }, 5000);
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
      var modal = $('mpConfirmModal');
      if (!modal) {
        modal = document.createElement('div');
        modal.id = 'mpConfirmModal';
        modal.className = 'hh-modal';
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        modal.innerHTML =
          '<div class="hh-modal-backdrop" data-mp-confirm-cancel></div>' +
          '<div class="hh-modal-panel mp-confirm-panel" role="dialog" aria-modal="true" aria-labelledby="mpConfirmTitle">' +
            '<div class="hh-modal-head">' +
              '<h2 id="mpConfirmTitle"></h2>' +
              '<button type="button" class="hh-modal-close" data-mp-confirm-cancel aria-label="Close">&times;</button>' +
            '</div>' +
            '<p class="mp-confirm-message" id="mpConfirmMessage"></p>' +
            '<div class="mp-confirm-actions">' +
              '<button type="button" class="hh-btn hh-btn-secondary" data-mp-confirm-cancel></button>' +
              '<button type="button" class="hh-btn" data-mp-confirm-ok></button>' +
            '</div>' +
          '</div>';
        document.body.appendChild(modal);
      }

      var titleEl = modal.querySelector('#mpConfirmTitle');
      var msgEl = modal.querySelector('#mpConfirmMessage');
      var cancelBtns = modal.querySelectorAll('[data-mp-confirm-cancel]');
      var okBtn = modal.querySelector('[data-mp-confirm-ok]');

      titleEl.textContent = title;
      msgEl.textContent = message;
      cancelBtns.forEach(function (btn) {
        if (btn.tagName === 'BUTTON' && btn.classList.contains('hh-btn')) {
          btn.textContent = cancelLabel;
        }
      });
      okBtn.textContent = confirmLabel;
      okBtn.className = 'hh-btn ' + (danger ? 'hh-btn-danger' : 'hh-btn-primary');

      function cleanup(result) {
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        modal.removeEventListener('click', onClick);
        document.removeEventListener('keydown', onKey);
        resolve(result);
      }

      function onClick(e) {
        if (e.target.closest('[data-mp-confirm-ok]')) {
          cleanup(true);
          return;
        }
        if (e.target.closest('[data-mp-confirm-cancel]')) {
          cleanup(false);
        }
      }

      function onKey(e) {
        if (e.key === 'Escape') cleanup(false);
      }

      modal.addEventListener('click', onClick);
      document.addEventListener('keydown', onKey);
      modal.hidden = false;
      modal.setAttribute('aria-hidden', 'false');
      okBtn.focus();
    });
  }

  function openModal(id) {
    var el = $(id);
    if (!el) return;
    el.hidden = false;
    el.setAttribute('aria-hidden', 'false');
  }

  function closeModal(el) {
    var modal = el && el.closest ? el.closest('.hh-modal') : el;
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute('aria-hidden', 'true');
  }

  function filterQuery() {
    var params = new URLSearchParams();
    var q = ($('mpSearch') && $('mpSearch').value) || '';
    var project = ($('mpFilterProject') && $('mpFilterProject').value) || 'all';
    var trade = ($('mpFilterTrade') && $('mpFilterTrade').value) || 'all';
    var reqType = ($('mpFilterReqType') && $('mpFilterReqType').value) || 'all';
    var linked = ($('mpFilterLinked') && $('mpFilterLinked').value) || 'all';
    var status = state.status || 'all';
    if (q.trim()) params.set('q', q.trim());
    if (project && project !== 'all') params.set('project_id', project);
    if (trade && trade !== 'all') params.set('trade_id', trade);
    if (status && status !== 'all') params.set('status', status);
    if (reqType && reqType !== 'all') params.set('requirement_type', reqType);
    if (linked && linked !== 'all') params.set('linked', linked);
    return params.toString();
  }

  function hasActiveFilters() {
    var q = ($('mpSearch') && $('mpSearch').value) || '';
    var project = ($('mpFilterProject') && $('mpFilterProject').value) || 'all';
    var trade = ($('mpFilterTrade') && $('mpFilterTrade').value) || 'all';
    var reqType = ($('mpFilterReqType') && $('mpFilterReqType').value) || 'all';
    var linked = ($('mpFilterLinked') && $('mpFilterLinked').value) || 'all';
    var status = state.status || 'all';
    return !!(q.trim() || (project && project !== 'all') || (trade && trade !== 'all') ||
      (reqType && reqType !== 'all') || (linked && linked !== 'all') ||
      (status && status !== 'all'));
  }

  function syncStatusChips() {
    var status = state.status || 'all';
    document.querySelectorAll('#mpStatusChips .mp-chip').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.getAttribute('data-status') === status);
    });
  }

  function syncFilterChrome() {
    var clearBtn = $('mpClearFilters');
    if (clearBtn) clearBtn.hidden = !hasActiveFilters();

    var countEl = $('mpFilterCount');
    if (countEl) {
      var n = (state.vacancies || []).length;
      countEl.textContent = n + (n === 1 ? ' vacancy' : ' vacancies');
    }

    syncStatusChips();

    document.querySelectorAll('.mp-col-filter-btn').forEach(function (btn) {
      var key = btn.getAttribute('data-col-filter');
      var active = false;
      if (key === 'trade') active = ($('mpFilterTrade') && $('mpFilterTrade').value !== 'all');
      if (key === 'project') active = ($('mpFilterProject') && $('mpFilterProject').value !== 'all');
      if (key === 'requirement_type') active = ($('mpFilterReqType') && $('mpFilterReqType').value !== 'all');
      if (key === 'status') active = !!(state.status && state.status !== 'all');
      btn.classList.toggle('is-active', !!active);
    });

    var badge = $('mpFiltersBadge');
    var toggle = $('mpFiltersToggle');
    var activeN = 0;
    if (state.status && state.status !== 'all') activeN += 1;
    if ($('mpFilterTrade') && $('mpFilterTrade').value !== 'all') activeN += 1;
    if ($('mpFilterProject') && $('mpFilterProject').value !== 'all') activeN += 1;
    if ($('mpFilterReqType') && $('mpFilterReqType').value !== 'all') activeN += 1;
    if ($('mpFilterLinked') && $('mpFilterLinked').value !== 'all') activeN += 1;
    if (badge) {
      if (activeN) {
        badge.hidden = false;
        badge.textContent = String(activeN);
      } else {
        badge.hidden = true;
        badge.textContent = '';
      }
    }
    if (toggle) toggle.classList.toggle('has-filters', activeN > 0);

  }

  function clearFilters() {
    if ($('mpSearch')) $('mpSearch').value = '';
    if ($('mpFilterProject')) $('mpFilterProject').value = 'all';
    if ($('mpFilterTrade')) $('mpFilterTrade').value = 'all';
    if ($('mpFilterReqType')) $('mpFilterReqType').value = 'all';
    if ($('mpFilterLinked')) $('mpFilterLinked').value = 'all';
    state.status = 'all';
    closeColMenu();
    loadVacancies();
  }

  function closeColMenu() {
    var menu = $('mpColMenu');
    if (menu) menu.hidden = true;
    state.colFilterKey = null;
    document.querySelectorAll('.mp-col-filter-btn.is-open').forEach(function (b) {
      b.classList.remove('is-open');
    });
  }

  function openColMenu(btn) {
    var key = btn.getAttribute('data-col-filter');
    var menu = $('mpColMenu');
    var list = $('mpColMenuList');
    var label = $('mpColMenuLabel');
    if (!menu || !list || !key) return;

    document.querySelectorAll('.mp-col-filter-btn.is-open').forEach(function (b) {
      b.classList.remove('is-open');
    });
    btn.classList.add('is-open');
    state.colFilterKey = key;
    if (label) label.textContent = 'Filter ' + (COL_LABELS[key] || key);

    var items = [];
    var current = 'all';
    if (key === 'trade') {
      items = ((state.meta && state.meta.trades) || []).filter(function (t) {
        return t.active !== false;
      }).map(function (t) {
        return { value: String(t.id), label: t.name };
      });
      current = ($('mpFilterTrade') && $('mpFilterTrade').value) || 'all';
    } else if (key === 'project') {
      items = ((state.meta && state.meta.projects) || []).filter(function (p) {
        return p.active !== false;
      }).map(function (p) {
        return { value: String(p.id), label: p.name };
      });
      current = ($('mpFilterProject') && $('mpFilterProject').value) || 'all';
    } else if (key === 'requirement_type') {
      items = ((state.meta && state.meta.requirement_types) || [
        { key: 'new', label: 'New' },
        { key: 'replacement', label: 'Replacement' },
      ]).map(function (r) {
        return { value: r.key, label: r.label };
      });
      current = ($('mpFilterReqType') && $('mpFilterReqType').value) || 'all';
    } else if (key === 'status') {
      items = statusList().map(function (s) {
        return { value: s.key, label: s.label };
      });
      current = state.status || 'all';
    }

    var html = '<label class="mp-col-menu-opt"><input type="radio" name="mpColPick" value="all"' +
      (current === 'all' ? ' checked' : '') + '><span>All</span></label>';
    items.forEach(function (it) {
      html += '<label class="mp-col-menu-opt"><input type="radio" name="mpColPick" value="' +
        esc(it.value) + '"' + (String(current) === String(it.value) ? ' checked' : '') +
        '><span>' + esc(it.label) + '</span></label>';
    });
    list.innerHTML = html;

    menu.hidden = false;
    var rect = btn.getBoundingClientRect();
    var menuH = Math.min(menu.offsetHeight || 320, window.innerHeight - 16);
    var top = rect.bottom + 6;
    var left = Math.min(rect.left, window.innerWidth - 240);
    if (left < 8) left = 8;
    if (top + menuH > window.innerHeight - 8) {
      top = Math.max(8, rect.top - menuH - 6);
    }
    menu.style.top = top + 'px';
    menu.style.left = left + 'px';
    menu.style.maxHeight = Math.max(160, window.innerHeight - top - 8) + 'px';
  }

  function applyColMenu() {
    var key = state.colFilterKey;
    if (!key) return;
    var picked = document.querySelector('#mpColMenuList input[name="mpColPick"]:checked');
    var val = picked ? picked.value : 'all';
    if (key === 'trade' && $('mpFilterTrade')) $('mpFilterTrade').value = val;
    if (key === 'project' && $('mpFilterProject')) $('mpFilterProject').value = val;
    if (key === 'requirement_type' && $('mpFilterReqType')) $('mpFilterReqType').value = val;
    if (key === 'status') state.status = val || 'all';
    closeColMenu();
    loadVacancies();
  }

  function fillSelect(sel, items, valueKey, labelKey, allLabel) {
    if (!sel) return;
    var current = sel.value;
    var html = '';
    if (allLabel) html += '<option value="all">' + esc(allLabel) + '</option>';
    (items || []).forEach(function (it) {
      if (it && it.active === false) return;
      html += '<option value="' + esc(it[valueKey]) + '">' + esc(it[labelKey]) + '</option>';
    });
    sel.innerHTML = html;
    if (current) {
      try {
        sel.value = current;
      } catch (e) { /* ignore */ }
    }
  }

  function optionHtml(items, selectedId, valueKey, labelKey) {
    var html = '';
    (items || []).forEach(function (it) {
      if (!it) return;
      if (it.active === false && String(it[valueKey]) !== String(selectedId)) return;
      var sel = String(it[valueKey]) === String(selectedId) ? ' selected' : '';
      var label = it[labelKey];
      if (it.active === false) label = label + ' (inactive)';
      html += '<option value="' + esc(it[valueKey]) + '"' + sel + '>' + esc(label) + '</option>';
    });
    return html;
  }

  function statusOptions(selected) {
    return optionHtml(statusList(), selected, 'key', 'label');
  }

  function reqTypeOptions(selected) {
    var list = (state.meta && state.meta.requirement_types) || [
      { key: 'new', label: 'New' },
      { key: 'replacement', label: 'Replacement' },
    ];
    return optionHtml(list, selected, 'key', 'label');
  }

  function renderSummary() {
    var s = state.summary || {};
    if ($('mpStatTotal')) $('mpStatTotal').textContent = s.total_required != null ? s.total_required : '—';
    if ($('mpStatJoined')) $('mpStatJoined').textContent = s.joined != null ? s.joined : '—';
    if ($('mpStatProgress')) $('mpStatProgress').textContent = s.in_progress != null ? s.in_progress : '—';
    if ($('mpStatOpen')) $('mpStatOpen').textContent = s.still_open != null ? s.still_open : '—';
  }

  function renderMatrix() {
    var s = state.summary || {};
    var head = $('mpMatrixHead');
    var body = $('mpMatrixBody');
    if (!head || !body) return;

    var projects = s.matrix_projects || [];
    var rows = s.matrix || [];

    if (!projects.length || !rows.length) {
      head.innerHTML = '';
      body.innerHTML = '<tr><td class="mp-empty">Add trades and projects in Settings, then enter headcounts here.</td></tr>';
      return;
    }

    var th = '<tr><th class="mp-matrix-trade">Trade</th>';
    projects.forEach(function (p) {
      th += '<th>' + esc(p.name) + '</th>';
    });
    th += '<th>Required</th><th>Joined</th><th>Open</th></tr>';
    head.innerHTML = th;

    var html = '';
    rows.forEach(function (row) {
      html += '<tr data-trade-id="' + row.trade_id + '">';
      html += '<td class="mp-matrix-trade">' + esc(row.trade_name) + '</td>';
      projects.forEach(function (p) {
        var n = (row.cells && row.cells[String(p.id)]) || 0;
        var zeroCls = n ? '' : ' mp-matrix-zero';
        html += '<td class="mp-matrix-num' + zeroCls + '">';
        html += '<input type="number" class="mp-matrix-input" min="0" max="200" step="1" inputmode="numeric"';
        html += ' data-trade-id="' + row.trade_id + '" data-project-id="' + p.id + '"';
        html += ' data-prev="' + n + '" value="' + n + '"';
        html += ' title="Edit headcount — updates the main vacancy table"';
        html += ' aria-label="' + esc(row.trade_name) + ' × ' + esc(p.name) + ' required count">';
        html += '</td>';
      });
      html += '<td class="mp-matrix-num mp-matrix-total">' + (row.required || 0) + '</td>';
      html += '<td class="mp-matrix-num mp-matrix-total">' + (row.joined || 0) + '</td>';
      html += '<td class="mp-matrix-num mp-matrix-total">' + (row.open || 0) + '</td></tr>';
    });
    body.innerHTML = html;
  }

  function scheduleMatrixSave(input) {
    if (!input) return;
    var tradeId = input.getAttribute('data-trade-id');
    var projectId = input.getAttribute('data-project-id');
    if (!tradeId || !projectId) return;
    var key = 'matrix:' + tradeId + ':' + projectId;
    if (state.saveTimers[key]) clearTimeout(state.saveTimers[key]);
    state.saveTimers[key] = setTimeout(function () {
      var current = document.querySelector(
        '.mp-matrix-input[data-trade-id="' + tradeId + '"][data-project-id="' + projectId + '"]'
      );
      if (current) commitMatrixCell(current);
    }, 450);
  }

  function commitMatrixCell(input) {
    if (!input || input.disabled) return;
    var tradeId = parseInt(input.getAttribute('data-trade-id'), 10);
    var projectId = parseInt(input.getAttribute('data-project-id'), 10);
    var prev = parseInt(input.getAttribute('data-prev'), 10);
    if (isNaN(prev)) prev = 0;

    var raw = String(input.value == null ? '' : input.value).trim();
    var count = raw === '' ? 0 : parseInt(raw, 10);
    if (isNaN(count) || count < 0) {
      input.value = String(prev);
      showImportResult('Enter a whole number 0 or greater.', true);
      return;
    }
    if (count > 200) {
      input.value = String(prev);
      showImportResult('Max 200 vacancies per trade × project cell.', true);
      return;
    }
    if (count === prev) {
      input.value = String(prev);
      return;
    }

    var drop = prev - count;
    if (drop > 0) {
      var msg = drop === 1
        ? 'Remove 1 vacancy row from the main table for this trade × project?'
        : 'Remove ' + drop + ' vacancy rows from the main table for this trade × project?';
      msg += ' Empty open rows are removed first.';
      confirmDialog({
        title: 'Reduce headcount',
        message: msg,
        confirmLabel: 'Remove',
        danger: true,
      }).then(function (ok) {
        if (!ok) {
          input.value = String(prev);
          var td = input.closest('td');
          if (td) td.classList.toggle('mp-matrix-zero', !prev);
          return;
        }
        applyMatrixCell(input, tradeId, projectId, count, prev);
      });
      return;
    }

    applyMatrixCell(input, tradeId, projectId, count, prev);
  }

  function applyMatrixCell(input, tradeId, projectId, count, prev) {
    input.disabled = true;
    input.classList.add('is-saving');
    apiJson('/hr/api/manpower/matrix/cell', 'PUT', {
      trade_id: tradeId,
      project_id: projectId,
      count: count,
    })
      .then(function (data) {
        if (data.summary) {
          state.summary = data.summary;
          renderSummary();
          renderMatrix();
        } else {
          input.setAttribute('data-prev', String(count));
          input.value = String(count);
          var td = input.closest('td');
          if (td) td.classList.toggle('mp-matrix-zero', !count);
        }
        return loadVacancies();
      })
      .catch(function (err) {
        input.value = String(prev);
        showImportResult(err.message || 'Matrix update failed', true);
        return loadSummary();
      })
      .finally(function () {
        if (input.isConnected) {
          input.disabled = false;
          input.classList.remove('is-saving');
        }
      });
  }

  function onMatrixInput(e) {
    var t = e.target;
    if (!t || !t.classList || !t.classList.contains('mp-matrix-input')) return;
    var td = t.closest('td');
    var n = parseInt(t.value, 10);
    if (td) td.classList.toggle('mp-matrix-zero', !(n > 0));
    scheduleMatrixSave(t);
  }

  function onMatrixChange(e) {
    var t = e.target;
    if (!t || !t.classList || !t.classList.contains('mp-matrix-input')) return;
    var key = 'matrix:' + t.getAttribute('data-trade-id') + ':' + t.getAttribute('data-project-id');
    if (state.saveTimers[key]) {
      clearTimeout(state.saveTimers[key]);
      state.saveTimers[key] = null;
    }
    commitMatrixCell(t);
  }

  function renderListsModal() {
    var trades = (state.meta && state.meta.trades) || [];
    var projects = (state.meta && state.meta.projects) || [];
    var tl = $('mpTradeList');
    var pl = $('mpProjectList');
    if (tl) tl.innerHTML = renderSettingsListItems(trades, 'trade');
    if (pl) pl.innerHTML = renderSettingsListItems(projects, 'project');
  }

  function renderSettingsListItems(items, kind) {
    if (!items || !items.length) {
      return '<li><span class="mp-empty">None yet — add one below or import Excel.</span></li>';
    }
    var active = items.filter(function (x) { return x.active !== false; });
    var inactive = items.filter(function (x) { return x.active === false; });
    var html = '';
    if (!active.length) {
      html += '<li><span class="mp-empty">No active ' + (kind === 'trade' ? 'trades' : 'projects') + '</span></li>';
    }
    active.forEach(function (item) {
      html += settingsListItemHtml(item, kind, false);
    });
    if (inactive.length) {
      html += '<li class="mp-list-divider"><span>Removed</span></li>';
      inactive.forEach(function (item) {
        html += settingsListItemHtml(item, kind, true);
      });
    }
    return html;
  }

  function settingsListItemHtml(item, kind, isInactive) {
    var count = item.vacancy_count != null ? item.vacancy_count : 0;
    var meta = count === 1 ? '1 vacancy' : (count + ' vacancies');
    var html = '<li class="mp-list-item' + (isInactive ? ' is-inactive' : '') + '" data-kind="' + kind + '" data-id="' + item.id + '">';
    html += '<div class="mp-list-item-main">';
    html += '<span class="mp-list-item-name">' + esc(item.name) + '</span>';
    html += '<span class="mp-list-item-meta">' + esc(meta) + '</span>';
    html += '</div><div class="mp-list-item-actions">';
    if (isInactive) {
      html += '<button type="button" class="hh-btn hh-btn-secondary hh-btn-sm" data-list-action="restore">Restore</button>';
    } else {
      html += '<button type="button" class="hh-btn hh-btn-ghost hh-btn-sm mp-list-remove" data-list-action="remove">Remove</button>';
    }
    html += '</div></li>';
    return html;
  }

  function onSettingsListClick(e) {
    var btn = e.target.closest('[data-list-action]');
    if (!btn) return;
    var li = btn.closest('.mp-list-item');
    if (!li) return;
    var kind = li.getAttribute('data-kind');
    var id = li.getAttribute('data-id');
    var action = btn.getAttribute('data-list-action');
    if (!kind || !id || !action) return;

    var items = kind === 'trade'
      ? ((state.meta && state.meta.trades) || [])
      : ((state.meta && state.meta.projects) || []);
    var item = null;
    items.forEach(function (x) {
      if (String(x.id) === String(id)) item = x;
    });
    var name = item ? item.name : (kind === 'trade' ? 'trade' : 'project');
    var count = item && item.vacancy_count != null ? item.vacancy_count : 0;
    var url = kind === 'trade'
      ? '/hr/api/manpower/trades/' + id
      : '/hr/api/manpower/projects/' + id;

    if (action === 'remove') {
      var msg = 'Remove "' + name + '" from dropdowns and the Excel Lists sheet?';
      if (count > 0) {
        msg += ' ' + count + ' linked vacanc' + (count === 1 ? 'y stays' : 'ies stay') + ' on the board.';
      }
      confirmDialog({
        title: 'Remove ' + kind,
        message: msg,
        confirmLabel: 'Remove',
        danger: true,
      }).then(function (ok) {
        if (!ok) return;
        apiJson(url, 'PATCH', { active: false })
          .then(function () { return Promise.all([loadMeta(), loadSummary()]); })
          .catch(function (err) { showImportResult(err.message, true); });
      });
      return;
    }

    if (action === 'restore') {
      apiJson(url, 'PATCH', { active: true })
        .then(function () { return Promise.all([loadMeta(), loadSummary()]); })
        .catch(function (err) { showImportResult(err.message, true); });
    }
  }

  function getColOrder() {
    if (state.colOrder && state.colOrder.length) return state.colOrder;
    state.colOrder = loadColOrder();
    return state.colOrder;
  }

  function loadColOrder() {
    try {
      var raw = localStorage.getItem(COL_ORDER_KEY);
      if (!raw) return DEFAULT_COL_ORDER.slice();
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return DEFAULT_COL_ORDER.slice();
      var known = {};
      DEFAULT_COL_ORDER.forEach(function (k) { known[k] = true; });
      var out = [];
      parsed.forEach(function (k) {
        if (known[k] && out.indexOf(k) === -1) out.push(k);
      });
      DEFAULT_COL_ORDER.forEach(function (k) {
        if (out.indexOf(k) === -1) out.push(k);
      });
      return out;
    } catch (e) {
      return DEFAULT_COL_ORDER.slice();
    }
  }

  function saveColOrder(order) {
    state.colOrder = order.slice();
    try {
      localStorage.setItem(COL_ORDER_KEY, JSON.stringify(state.colOrder));
    } catch (e) { /* ignore */ }
  }

  function moveColOrder(fromKey, toKey) {
    if (!fromKey || !toKey || fromKey === toKey) return false;
    var order = getColOrder().slice();
    var fromIdx = order.indexOf(fromKey);
    var toIdx = order.indexOf(toKey);
    if (fromIdx < 0 || toIdx < 0) return false;
    order.splice(fromIdx, 1);
    order.splice(toIdx, 0, fromKey);
    saveColOrder(order);
    return true;
  }

  function renderBoardHead() {
    var head = $('mpBoardHead');
    if (!head) return;
    var html = '';
    getColOrder().forEach(function (key) {
      var cls = COL_CLASS[key] || '';
      var label = COL_LABELS[key] != null ? COL_LABELS[key] : key;
      var filterable = !!FILTERABLE_COLS[key];
      var thClass = cls;
      if (filterable) thClass += ' mp-th-filterable';
      if (key === 'actions') thClass += (thClass ? ' ' : '') + 'mp-th-actions';
      if (key === 'status') thClass += (thClass ? ' ' : '') + 'mp-th-filterable';
      var drag = key !== 'actions';
      html += '<th class="' + thClass.trim() + '" data-col="' + key + '"' +
        (drag ? ' draggable="true" title="Drag to reorder columns"' : '') + '>';
      if (key === 'actions') {
        html += '</th>';
        return;
      }
      if (filterable) {
        html += '<span class="mp-th-label">' + esc(label) + '</span>';
        html += '<button type="button" class="mp-col-filter-btn" data-col-filter="' + key + '"' +
          ' aria-label="Filter ' + esc(label) + '" title="Filter ' + esc(label) + '">▾</button>';
      } else {
        html += '<span class="mp-th-label">' + esc(label) + '</span>';
      }
      html += '</th>';
    });
    head.innerHTML = html;
  }

  function buildBoardCell(key, v, trades, projects) {
    if (key === 'trade') {
      return '<td class="mp-col-trade"><select class="mp-cell-select" data-field="trade_id" title="' +
        esc(v.trade_name || '') + '">' +
        optionHtml(trades, v.trade_id, 'id', 'name') + '</select></td>';
    }
    if (key === 'project') {
      return '<td class="mp-col-project"><select class="mp-cell-select" data-field="project_id" title="' +
        esc(v.project_name || '') + '">' +
        optionHtml(projects, v.project_id, 'id', 'name') + '</select></td>';
    }
    if (key === 'person') {
      return '<td class="mp-col-person"><span class="mp-person">' + esc(v.person_label || '—') + '</span></td>';
    }
    if (key === 'requirement_type') {
      return '<td class="mp-col-reqtype"><select class="mp-cell-select" data-field="requirement_type">' +
        reqTypeOptions(v.requirement_type) + '</select></td>';
    }
    if (key === 'replacement') {
      return '<td class="mp-col-replacement"><input class="mp-cell-input" data-field="replacement_name" value="' +
        esc(v.replacement_name) + '" autocomplete="off"></td>';
    }
    if (key === 'id') {
      return '<td class="mp-col-id"><input class="mp-cell-input" data-field="replacement_employee_id" value="' +
        esc(v.replacement_employee_id) + '" autocomplete="off"></td>';
    }
    if (key === 'candidate') {
      if (v.hiring_candidate_id && v.hiring_candidate) {
        var hc = v.hiring_candidate;
        return '<td class="mp-col-candidate"><div class="mp-linked-candidate">' +
          '<div class="mp-linked-main">' +
            '<a class="mp-linked-name" href="' + esc(hc.url || ('/hr/hiring/candidates/' + hc.id)) + '" title="' +
              esc((hc.full_name || v.candidate_name || '') + (hc.pipeline_label ? ' — ' + hc.pipeline_label : '')) + '">' +
              esc(hc.full_name || v.candidate_name) +
            '</a>' +
            (hc.pipeline_label
              ? '<span class="mp-linked-pipe" title="' + esc(hc.pipeline_label) + '">' + esc(hc.pipeline_label) + '</span>'
              : '') +
          '</div>' +
          '<button type="button" class="mp-unlink-btn" data-action="unlink" data-vacancy-id="' + v.id + '" title="Unlink from Hiring">Unlink</button>' +
          '</div></td>';
      }
      return '<td class="mp-col-candidate"><div class="mp-candidate-wrap">' +
        '<input class="mp-cell-input" data-field="candidate_name" value="' +
          esc(v.candidate_name) + '" autocomplete="off">' +
        '<button type="button" class="mp-link-btn" data-action="link-candidate" data-vacancy-id="' + v.id + '" title="Link Hiring candidate">Link</button>' +
        '</div></td>';
    }
    if (key === 'contact') {
      if (v.hiring_candidate_id && v.hiring_candidate) {
        return '<td class="mp-col-contact"><input class="mp-cell-input" data-field="contact_number" value="' +
          esc(v.contact_number) + '" autocomplete="off" readonly title="Synced from Hiring"></td>';
      }
      return '<td class="mp-col-contact"><input class="mp-cell-input" data-field="contact_number" value="' +
        esc(v.contact_number) + '" autocomplete="off"></td>';
    }
    if (key === 'status') {
      return '<td class="mp-col-status"><span class="mp-status-tag mp-status-' +
        esc(v.status || 'open') + '"><select class="mp-cell-select mp-status-select" data-field="status" aria-label="Status">' +
        statusOptions(v.status) + '</select></span></td>';
    }
    if (key === 'joined') {
      return '<td class="mp-col-joined"><input class="mp-cell-input" type="date" data-field="date_joined" value="' +
        esc(v.date_joined || '') + '"></td>';
    }
    if (key === 'remarks') {
      return '<td class="mp-col-remarks"><input class="mp-cell-input" data-field="remarks" value="' +
        esc(v.remarks) + '" autocomplete="off" placeholder="Comment"></td>';
    }
    if (key === 'actions') {
      var html = '<td class="mp-td-actions"><div class="mp-row-actions">';
      html += '<button type="button" class="mp-icon-btn" data-action="duplicate" title="Duplicate" aria-label="Duplicate">';
      html += '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75m9.75 10.5V7.875c0-.621-.504-1.125-1.125-1.125H9.375c-.621 0-1.125.504-1.125 1.125v10.5m9.75 0h2.625c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a.75.75 0 00-.75.75v.375"/></svg>';
      html += '</button>';
      html += '<button type="button" class="mp-icon-btn mp-danger" data-action="delete" title="Delete" aria-label="Delete">';
      html += '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>';
      html += '</button></div></td>';
      return html;
    }
    return '<td></td>';
  }

  function renderBoard() {
    var body = $('mpBoardBody');
    if (!body) return;
    renderBoardHead();
    var order = getColOrder();
    var colSpan = order.length;
    var rows = state.vacancies || [];
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="' + colSpan + '" class="mp-empty">No vacancies match. Add a vacancy or import the Excel tracker.</td></tr>';
      return;
    }

    var trades = (state.meta && state.meta.trades) || [];
    var projects = (state.meta && state.meta.projects) || [];
    var html = '';
    var lastTradeId = null;
    var shade = false;

    rows.forEach(function (v) {
      var groupStart = v.trade_id !== lastTradeId;
      if (groupStart) {
        shade = !shade;
        lastTradeId = v.trade_id;
      }
      var cls = [];
      if (groupStart) cls.push('mp-group-start');
      if (shade) cls.push('mp-trade-shade');

      html += '<tr class="' + cls.join(' ') + '" data-id="' + v.id + '">';
      order.forEach(function (key) {
        html += buildBoardCell(key, v, trades, projects);
      });
      html += '</tr>';
    });

    body.innerHTML = html;
  }

  function initColDrag() {
    var table = $('mpBoard');
    if (!table || table._mpColDragBound) return;
    table._mpColDragBound = true;

    table.addEventListener('dragstart', function (e) {
      var th = e.target.closest('thead th[data-col]');
      if (!th || th.getAttribute('data-col') === 'actions') return;
      if (e.target.closest('.mp-col-filter-btn')) {
        e.preventDefault();
        return;
      }
      state.dragColKey = th.getAttribute('data-col');
      th.classList.add('is-dragging');
      try {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', state.dragColKey);
      } catch (err) { /* ignore */ }
    });

    table.addEventListener('dragend', function () {
      state.dragColKey = null;
      table.querySelectorAll('thead th.is-dragging, thead th.is-drop-target').forEach(function (el) {
        el.classList.remove('is-dragging', 'is-drop-target');
      });
    });

    table.addEventListener('dragover', function (e) {
      var th = e.target.closest('thead th[data-col]');
      if (!th || !state.dragColKey) return;
      if (th.getAttribute('data-col') === 'actions') return;
      e.preventDefault();
      try { e.dataTransfer.dropEffect = 'move'; } catch (err) { /* ignore */ }
      table.querySelectorAll('thead th.is-drop-target').forEach(function (el) {
        if (el !== th) el.classList.remove('is-drop-target');
      });
      th.classList.add('is-drop-target');
    });

    table.addEventListener('dragleave', function (e) {
      var th = e.target.closest('thead th[data-col]');
      if (!th) return;
      if (th.contains(e.relatedTarget)) return;
      th.classList.remove('is-drop-target');
    });

    table.addEventListener('drop', function (e) {
      var th = e.target.closest('thead th[data-col]');
      if (!th || !state.dragColKey) return;
      var toKey = th.getAttribute('data-col');
      if (toKey === 'actions') return;
      e.preventDefault();
      th.classList.remove('is-drop-target');
      if (moveColOrder(state.dragColKey, toKey)) {
        renderBoard();
        syncFilterChrome();
      }
      state.dragColKey = null;
    });
  }

  function loadMeta() {
    return apiGet('/hr/api/manpower/meta').then(function (data) {
      state.meta = data;
      fillSelect($('mpFilterProject'), data.projects, 'id', 'name', 'All projects');
      fillSelect($('mpFilterTrade'), data.trades, 'id', 'name', 'All trades');
      fillSelect($('mpAddTrade'), data.trades, 'id', 'name');
      fillSelect($('mpAddProject'), data.projects, 'id', 'name');
      renderListsModal();
    });
  }

  function loadSummary() {
    return apiGet('/hr/api/manpower/summary').then(function (data) {
      state.summary = data;
      renderSummary();
      renderMatrix();
    });
  }

  function loadVacancies() {
    var qs = filterQuery();
    var url = '/hr/api/manpower/vacancies' + (qs ? '?' + qs : '');
    return apiGet(url).then(function (data) {
      state.vacancies = data.vacancies || [];
      renderBoard();
      syncFilterChrome();
    });
  }

  function refreshAll() {
    return loadMeta()
      .then(loadSummary)
      .then(loadVacancies)
      .catch(function (err) {
        var body = $('mpBoardBody');
        if (body) {
          body.innerHTML = '<tr><td colspan="12" class="mp-empty">' +
            esc(err.message || 'Failed to load') + '</td></tr>';
        }
      });
  }

  function scheduleSave(id, field, value) {
    var key = id + ':' + field;
    if (state.saveTimers[key]) clearTimeout(state.saveTimers[key]);
    state.saveTimers[key] = setTimeout(function () {
      var payload = {};
      payload[field] = value === '' ? null : value;
      if (field === 'trade_id' || field === 'project_id') {
        payload[field] = parseInt(value, 10);
      }
      apiJson('/hr/api/manpower/vacancies/' + id, 'PATCH', payload)
        .then(function () {
          return Promise.all([loadSummary(), loadVacancies()]);
        })
        .catch(function (err) {
          showImportResult(err.message || 'Save failed', true);
        });
    }, 400);
  }

  function patchStatus(id, newStatus) {
    return apiJson('/hr/api/manpower/vacancies/' + id, 'PATCH', { status: newStatus })
      .then(function () {
        return Promise.all([loadSummary(), loadVacancies()]);
      })
      .catch(function (err) {
        showImportResult(err.message || 'Status update failed', true);
        return loadVacancies();
      });
  }

  function onBoardChange(e) {
    var t = e.target;
    if (!t || !t.getAttribute) return;
    var field = t.getAttribute('data-field');
    if (!field) return;
    var tr = t.closest('tr');
    if (!tr) return;
    var id = tr.getAttribute('data-id');
    if (!id) return;

    if (field === 'status') {
      var wrap = t.closest('.mp-status-tag');
      if (wrap) {
        wrap.className = 'mp-status-tag mp-status-' + (t.value || 'open');
      }
    }

    if ((field === 'trade_id' || field === 'project_id') && t.options && t.selectedIndex >= 0) {
      t.title = t.options[t.selectedIndex].text || '';
    }

    scheduleSave(id, field, t.value);
  }

  function onBoardClick(e) {
    var btn = e.target.closest('[data-action]');
    if (!btn) return;
    var tr = btn.closest('tr');
    if (!tr) return;
    var id = tr.getAttribute('data-id');
    if (!id) return;
    var action = btn.getAttribute('data-action');

    if (action === 'delete') {
      confirmDialog({
        title: 'Delete vacancy',
        message: 'Delete this vacancy? This cannot be undone.',
        confirmLabel: 'Delete',
        danger: true,
      }).then(function (ok) {
        if (!ok) return;
        apiJson('/hr/api/manpower/vacancies/' + id, 'DELETE', {})
          .then(function () { return Promise.all([loadSummary(), loadVacancies()]); })
          .catch(function (err) { showImportResult(err.message, true); });
      });
      return;
    }
    if (action === 'duplicate') {
      apiJson('/hr/api/manpower/vacancies/' + id + '/duplicate', 'POST', {})
        .then(function () { return Promise.all([loadSummary(), loadVacancies()]); })
        .catch(function (err) { showImportResult(err.message, true); });
      return;
    }
    if (action === 'unlink') {
      e.preventDefault();
      confirmDialog({
        title: 'Unlink hiring candidate',
        message: 'Remove the Hiring Docs link? Name and contact stay on this vacancy as text.',
        confirmLabel: 'Unlink',
      }).then(function (ok) {
        if (!ok) return;
        apiJson('/hr/api/staffing/unassign', 'POST', { vacancy_id: parseInt(id, 10) })
          .then(function () { return Promise.all([loadSummary(), loadVacancies()]); })
          .catch(function (err) { showImportResult(err.message, true); });
      });
      return;
    }
    if (action === 'link-candidate') {
      e.preventDefault();
      openLinkCandidatePicker(parseInt(id, 10));
    }
  }

  function getLinkVacancy() {
    var id = state.linkVacancyId;
    if (!id) return null;
    return (state.vacancies || []).find(function (v) {
      return Number(v.id) === Number(id);
    }) || null;
  }

  function normalizeMatchText(s) {
    return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  }

  function candidateMatchScore(candidate, vac) {
    if (!vac) return 0;
    var nameHint = normalizeMatchText(vac.candidate_name);
    var phoneHint = normalizeMatchText(vac.contact_number).replace(/\s/g, '');
    var cName = normalizeMatchText(candidate.full_name);
    var cPhone = normalizeMatchText(candidate.phone).replace(/\s/g, '');
    var score = 0;
    if (nameHint && cName) {
      if (cName === nameHint) score += 100;
      else if (cName.indexOf(nameHint) !== -1 || nameHint.indexOf(cName) !== -1) score += 60;
      else {
        var tokens = nameHint.split(/\s+/).filter(function (t) { return t.length > 1; });
        var hits = 0;
        tokens.forEach(function (t) {
          if (cName.indexOf(t) !== -1) hits += 1;
        });
        if (hits) score += hits * 15;
      }
    }
    if (phoneHint && cPhone && phoneHint.length >= 5) {
      if (cPhone.indexOf(phoneHint) !== -1 || phoneHint.indexOf(cPhone) !== -1) score += 40;
    }
    return score;
  }

  function isEmployedCandidate(c) {
    return !!(c && (
      c.link_state === 'employee' ||
      c.pipeline_status === 'candidate_employee'
    ));
  }

  function hasAssignedVacancy(c) {
    return !!(c && c.assigned_vacancy && (
      c.assigned_vacancy.id ||
      c.assigned_vacancy.project_name ||
      c.assigned_vacancy.person_label
    ));
  }

  function effectiveLinkState(c) {
    if (hasAssignedVacancy(c) && isEmployedCandidate(c)) return 'employee';
    if (hasAssignedVacancy(c)) return 'assigned';
    if (isEmployedCandidate(c)) return 'employee';
    if (c && (c.link_state === 'assigned' || c.link_state === 'employee')) {
      return c.link_state;
    }
    return 'available';
  }

  function isRestrictedCandidate(c) {
    var stateKey = effectiveLinkState(c);
    return stateKey === 'assigned' || stateKey === 'employee';
  }

  function fromProjectLabel(c) {
    if (!c || !c.assigned_vacancy) return '';
    return c.assigned_vacancy.project_name ||
      c.assigned_vacancy.person_label ||
      [c.assigned_vacancy.trade_name, c.assigned_vacancy.project_name].filter(Boolean).join(' · ') ||
      '';
  }

  function toProjectLabel(vac) {
    if (!vac) return 'this vacancy';
    return vac.project_name || vac.trade_name || 'this vacancy';
  }

  function assignedWhereLabel(c) {
    if (!c || !c.assigned_vacancy) return 'another vacancy';
    var project = c.assigned_vacancy.project_name;
    var trade = c.assigned_vacancy.trade_name;
    if (project && trade) return project + ' (' + trade + ')';
    return c.assigned_vacancy.person_label || project || trade || 'another vacancy';
  }

  function linkStateBadge(c) {
    var stateKey = effectiveLinkState(c);
    if (hasAssignedVacancy(c)) {
      var project = fromProjectLabel(c) || 'another project';
      var full = assignedWhereLabel(c);
      return '<span class="mp-link-badge is-assigned" title="' + esc('Assigned · ' + full) + '">Assigned</span>' +
        '<span class="mp-link-on-project">on ' + esc(project) + '</span>' +
        (isEmployedCandidate(c)
          ? '<span class="mp-link-badge is-employee">Employee</span>'
          : '');
    }
    if (stateKey === 'employee') {
      return '<span class="mp-link-badge is-employee">Employee</span>';
    }
    return '<span class="mp-link-badge is-available">Available</span>';
  }

  function initialsFromName(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
  }

  function enrichLinkCandidatesFromBoard(apiCandidates) {
    var byId = {};
    (apiCandidates || []).forEach(function (c) {
      if (!c || c.id == null) return;
      byId[String(c.id)] = Object.assign({}, c);
    });

    (state.vacancies || []).forEach(function (v) {
      if (!v || !v.hiring_candidate_id || !v.hiring_candidate) return;
      var hc = v.hiring_candidate;
      var idKey = String(hc.id || v.hiring_candidate_id);
      var assigned = {
        id: v.id,
        trade_name: v.trade_name || null,
        project_name: v.project_name || null,
        person_label: [v.trade_name, v.project_name].filter(Boolean).join(' · ') ||
          ('Vacancy #' + v.id),
      };
      var existing = byId[idKey];
      if (existing) {
        if (!existing.assigned_vacancy) existing.assigned_vacancy = assigned;
        if (existing.link_state === 'available' || !existing.link_state) {
          existing.link_state = existing.pipeline_status === 'candidate_employee'
            ? 'employee'
            : 'assigned';
        }
        return;
      }
      byId[idKey] = {
        id: hc.id || v.hiring_candidate_id,
        full_name: hc.full_name || v.candidate_name || 'Candidate',
        role: hc.role || '',
        department: '',
        phone: hc.phone || v.contact_number || '',
        pipeline_status: hc.pipeline_status || '',
        pipeline_label: hc.pipeline_label || '',
        progress_label: hc.progress_label || '',
        initials: initialsFromName(hc.full_name || v.candidate_name),
        url: hc.url || ('/hr/hiring/candidates/' + (hc.id || v.hiring_candidate_id)),
        link_state: hc.pipeline_status === 'candidate_employee' ? 'employee' : 'assigned',
        assigned_vacancy: assigned,
        is_selectable: true,
      };
    });

    return Object.keys(byId).map(function (k) { return byId[k]; });
  }

  function candidateSearchHay(c) {
    return [
      c.full_name, c.role, c.department, c.phone, c.pipeline_label, c.link_state,
      c.assigned_vacancy && c.assigned_vacancy.person_label,
      c.assigned_vacancy && c.assigned_vacancy.trade_name,
      c.assigned_vacancy && c.assigned_vacancy.project_name,
    ].join(' ').toLowerCase();
  }

  function candidateMatchesQuery(c, query) {
    var q = String(query || '').trim().toLowerCase();
    if (!q) return true;
    var hay = candidateSearchHay(c);
    if (hay.indexOf(q) !== -1) return true;
    var compactQ = q.replace(/[^a-z0-9]/g, '');
    if (!compactQ) return false;
    var compactHay = hay.replace(/[^a-z0-9]/g, '');
    return compactHay.indexOf(compactQ) !== -1;
  }

  function openLinkCandidatePicker(vacancyId) {
    var modal = $('mpLinkModal');
    var listEl = $('mpLinkList');
    var emptyEl = $('mpLinkEmpty');
    var metaEl = $('mpLinkVacancyMeta');
    var searchEl = $('mpLinkSearch');
    var confirmBtn = $('mpLinkConfirm');
    if (!modal || !listEl || !confirmBtn) return;

    state.linkVacancyId = vacancyId;
    state.linkCandidateId = null;
    state.linkCandidates = [];
    confirmBtn.disabled = true;

    var vac = (state.vacancies || []).find(function (v) {
      return Number(v.id) === Number(vacancyId);
    });
    if (metaEl) {
      if (vac) {
        metaEl.hidden = false;
        metaEl.innerHTML =
          '<div class="mp-link-vacancy-kicker">Vacancy</div>' +
          '<div class="mp-link-vacancy-title">' +
            esc(vac.trade_name || 'Trade') +
            ' <span aria-hidden="true">·</span> ' +
            esc(vac.project_name || 'Project') +
          '</div>' +
          '<div class="mp-link-vacancy-meta">' +
            esc(vac.person_label || '—') +
            ' · ' +
            esc((vac.requirement_type || 'new') === 'replacement' ? 'Replacement' : 'New') +
            (vac.status ? ' · ' + esc(String(vac.status).replace(/_/g, ' ')) : '') +
            (vac.candidate_name
              ? ' · typed: ' + esc(vac.candidate_name)
              : '') +
          '</div>';
      } else {
        metaEl.hidden = true;
        metaEl.innerHTML = '';
      }
    }

    listEl.innerHTML = '<div class="mp-link-loading">Loading candidates…</div>';
    if (emptyEl) emptyEl.hidden = true;
    if (searchEl) searchEl.value = '';
    openModal('mpLinkModal');
    if (searchEl) {
      setTimeout(function () { searchEl.focus(); }, 40);
    }

    apiGet('/hr/api/staffing/unassigned-candidates').then(function (data) {
      state.linkCandidates = enrichLinkCandidatesFromBoard(data.candidates || []);
      if (!state.linkCandidates.length) {
        listEl.innerHTML = '';
        if (emptyEl) {
          emptyEl.hidden = false;
          emptyEl.textContent = 'No Hiring candidates found. Add one in Hiring Docs first (HR access required).';
        }
        return;
      }
      // Prefill search from typed vacancy name to surface suggested + assigned matches
      var seed = '';
      if (vac && vac.candidate_name) {
        seed = String(vac.candidate_name).replace(/\(.*?\)/g, ' ').trim().split(/\s+/)[0] || '';
        if (seed.length < 2) seed = '';
      }
      if (searchEl && seed) searchEl.value = seed;
      renderLinkCandidateList(seed);
    }).catch(function (err) {
      // Still show people already linked on this board if the staffing API is denied
      state.linkCandidates = enrichLinkCandidatesFromBoard([]);
      if (state.linkCandidates.length) {
        renderLinkCandidateList('');
        showImportResult(
          (err && err.message ? err.message + ' — ' : '') +
          'Showing candidates already linked on this board. HR permission is required to load the full Hiring Docs list and to switch projects.',
          true
        );
        return;
      }
      closeModal(modal);
      showImportResult(
        (err && err.message) ||
        'Could not load candidates. You need HR / staffing permission to link Hiring Docs people.',
        true
      );
    });
  }

  function renderLinkCandidateList(query) {
    var listEl = $('mpLinkList');
    var emptyEl = $('mpLinkEmpty');
    var confirmBtn = $('mpLinkConfirm');
    if (!listEl) return;

    var vac = getLinkVacancy();
    var q = (query || '').trim();
    var rows = (state.linkCandidates || []).filter(function (c) {
      return candidateMatchesQuery(c, q);
    }).map(function (c) {
      var score = candidateMatchScore(c, vac);
      var stateKey = effectiveLinkState(c);
      return Object.assign({}, c, {
        _matchScore: score,
        _suggested: score >= 30,
        _linkState: stateKey,
      });
    });

    rows.sort(function (a, b) {
      if (b._matchScore !== a._matchScore) return b._matchScore - a._matchScore;
      var rank = { available: 0, assigned: 1, employee: 2 };
      var ra = rank[a._linkState] != null ? rank[a._linkState] : 9;
      var rb = rank[b._linkState] != null ? rank[b._linkState] : 9;
      if (ra !== rb) return ra - rb;
      return String(b.updated_at || '').localeCompare(String(a.updated_at || ''));
    });

    if (!rows.length) {
      listEl.innerHTML = '';
      if (emptyEl) {
        emptyEl.hidden = false;
        emptyEl.innerHTML = q
          ? 'No matches for “' + esc(q) + '”. Clear search to see everyone, including people already assigned to another project/role (shown greyed). Switching them here needs HR permission and a confirm.'
          : 'No Hiring candidates available. Add people in Hiring Docs (HR access required).';
      }
      if (confirmBtn) confirmBtn.disabled = true;
      state.linkCandidateId = null;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;

    var selectedStillVisible = rows.some(function (c) {
      return Number(c.id) === Number(state.linkCandidateId);
    });
    if (!selectedStillVisible) {
      state.linkCandidateId = null;
      if (confirmBtn) confirmBtn.disabled = true;
    }

    listEl.innerHTML = rows.map(function (c) {
      var selected = Number(c.id) === Number(state.linkCandidateId);
      var restricted = isRestrictedCandidate(c);
      var classes = 'mp-link-option' +
        (selected ? ' is-selected' : '') +
        (restricted ? ' is-restricted' : '') +
        (c._suggested ? ' is-suggested' : '');
      return (
        '<button type="button" class="' + classes + '"' +
          ' role="option" aria-selected="' + (selected ? 'true' : 'false') + '"' +
          ' data-candidate-id="' + c.id + '"' +
          ' data-link-state="' + esc(c._linkState || 'available') + '">' +
          '<span class="mp-link-avatar" aria-hidden="true">' + esc(c.initials || '?') + '</span>' +
          '<span class="mp-link-option-main">' +
            '<span class="mp-link-option-name">' +
              '<span class="mp-link-option-name-text">' + esc(c.full_name || 'Candidate') + '</span>' +
              (c._suggested ? '<span class="mp-link-suggested">Suggested</span>' : '') +
            '</span>' +
            '<span class="mp-link-option-sub">' +
              esc(c.role || 'No role set') +
              (c.phone ? ' · ' + esc(c.phone) : '') +
            '</span>' +
            '<span class="mp-link-option-flags">' + linkStateBadge(c) + '</span>' +
          '</span>' +
          '<span class="mp-link-option-meta">' +
            '<span class="mp-link-pipe">' + esc(c.pipeline_label || '—') + '</span>' +
            (c.progress_label ? '<span class="mp-link-docs">' + esc(c.progress_label) + ' docs</span>' : '') +
          '</span>' +
        '</button>'
      );
    }).join('');
  }

  function buildRestrictedConfirm(candidate) {
    var name = candidate.full_name || 'This candidate';
    var vac = getLinkVacancy();
    var toProject = toProjectLabel(vac);
    var employed = isEmployedCandidate(candidate);
    var assigned = hasAssignedVacancy(candidate);
    var fromProject = fromProjectLabel(candidate) || assignedWhereLabel(candidate);

    if (assigned && employed) {
      return {
        title: 'Switch project?',
        message: name + ' is marked Candidate employed and assigned to ' + fromProject +
          '. Do you agree to switch them to ' + toProject + '?',
        confirmLabel: 'Yes, switch',
      };
    }
    if (assigned) {
      return {
        title: 'Switch project?',
        message: name + ' is assigned to ' + fromProject +
          '. Do you agree to switch them to ' + toProject + '?',
        confirmLabel: 'Yes, switch',
      };
    }
    return {
      title: 'Link employed candidate?',
      message: name + ' is marked Candidate employed. Link them to ' + toProject + ' anyway?',
      confirmLabel: 'Yes, link',
    };
  }

  function performLinkAssign(candidateId, allowReassign) {
    var vacancyId = state.linkVacancyId;
    var confirmBtn = $('mpLinkConfirm');
    if (!vacancyId || !candidateId) return Promise.resolve();
    if (confirmBtn) confirmBtn.disabled = true;
    return apiJson('/hr/api/staffing/assign', 'POST', {
      candidate_id: parseInt(candidateId, 10),
      vacancy_id: parseInt(vacancyId, 10),
      allow_reassign: !!allowReassign,
    }).then(function () {
      closeModal($('mpLinkModal'));
      return Promise.all([loadSummary(), loadVacancies()]);
    }).catch(function (err) {
      if (confirmBtn) confirmBtn.disabled = false;
      showImportResult(err.message || 'Link failed', true);
    });
  }

  function confirmLinkCandidate() {
    var candidateId = state.linkCandidateId;
    if (!state.linkVacancyId || !candidateId) return;
    var candidate = (state.linkCandidates || []).find(function (c) {
      return Number(c.id) === Number(candidateId);
    });
    if (!candidate) return;

    if (!isRestrictedCandidate(candidate)) {
      performLinkAssign(candidateId, false);
      return;
    }

    var dlg = buildRestrictedConfirm(candidate);
    confirmDialog({
      title: dlg.title,
      message: dlg.message,
      confirmLabel: dlg.confirmLabel,
      cancelLabel: 'No',
      danger: false,
    }).then(function (ok) {
      if (!ok) {
        state.linkCandidateId = null;
        renderLinkCandidateList(($('mpLinkSearch') && $('mpLinkSearch').value) || '');
        if ($('mpLinkConfirm')) $('mpLinkConfirm').disabled = true;
        return;
      }
      performLinkAssign(candidateId, true);
    });
  }

  function openSettingsModal() {
    renderListsModal();
    var boardView = $('mpBoardView');
    var settingsView = $('mpSettingsView');
    if (boardView) boardView.hidden = true;
    if (settingsView) settingsView.hidden = false;
    var title = document.querySelector('.mp-page .hh-title');
    var subtitle = document.querySelector('.mp-page .hh-subtitle');
    if (title) title.textContent = 'Settings';
    if (subtitle) subtitle.textContent = 'Trades, projects, and Excel tools';
    var side = $('mpSidebarSettings');
    var board = $('mpSidebarBoard');
    if (side) side.classList.add('active');
    if (board) board.classList.add('active');
    try {
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, '', '#settings');
      } else {
        window.location.hash = 'settings';
      }
    } catch (e) { /* ignore */ }
  }

  function closeSettingsModal() {
    var boardView = $('mpBoardView');
    var settingsView = $('mpSettingsView');
    if (settingsView) settingsView.hidden = true;
    if (boardView) boardView.hidden = false;
    var title = document.querySelector('.mp-page .hh-title');
    var subtitle = document.querySelector('.mp-page .hh-subtitle');
    if (title) title.textContent = 'Manpower Tracker';
    if (subtitle) subtitle.textContent = 'Project vacancies by trade — live board';
    var side = $('mpSidebarSettings');
    var board = $('mpSidebarBoard');
    if (side) side.classList.remove('active');
    if (board) board.classList.add('active');
    try {
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, '', window.location.pathname + window.location.search);
      } else if (window.location.hash === '#settings') {
        window.location.hash = '';
      }
    } catch (e) { /* ignore */ }
  }

  function openAddVacancy() {
    if (!state.meta || !(state.meta.trades || []).some(function (t) { return t.active !== false; }) ||
        !(state.meta.projects || []).some(function (p) { return p.active !== false; })) {
      showImportResult('Add at least one trade and project in Settings, or import Excel.', true);
      openSettingsModal();
      return;
    }
    openModal('mpAddModal');
  }

  function setMatrixOpen(open) {
    var panel = $('mpMatrixPanel');
    var toggle = $('mpMatrixToggle');
    var hint = $('mpMatrixToggleHint');
    var tile = toggle && toggle.closest('.mp-bento-matrix');
    if (!panel || !toggle) return;
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (hint) hint.textContent = open ? 'Collapse' : 'Expand';
    if (tile) tile.classList.toggle('is-open', open);
  }

  function bindEvents() {
    var searchTimer;
    if ($('mpSearch')) {
      $('mpSearch').addEventListener('input', function () {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(loadVacancies, 250);
      });
    }
    ['mpFilterProject', 'mpFilterTrade', 'mpFilterReqType', 'mpFilterLinked'].forEach(function (id) {
      if ($(id)) $(id).addEventListener('change', loadVacancies);
    });

    if ($('mpStatusChips')) {
      $('mpStatusChips').addEventListener('click', function (e) {
        var chip = e.target.closest('[data-status]');
        if (!chip) return;
        state.status = chip.getAttribute('data-status') || 'all';
        loadVacancies();
      });
    }

    if ($('mpMatrixToggle')) {
      $('mpMatrixToggle').addEventListener('click', function () {
        var open = $('mpMatrixToggle').getAttribute('aria-expanded') !== 'true';
        setMatrixOpen(open);
      });
    }
    if ($('mpMatrixCollapse')) {
      $('mpMatrixCollapse').addEventListener('click', function () {
        setMatrixOpen(false);
      });
    }

    if ($('mpMatrixBody')) {
      $('mpMatrixBody').addEventListener('input', onMatrixInput);
      $('mpMatrixBody').addEventListener('change', onMatrixChange);
      $('mpMatrixBody').addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        var t = e.target;
        if (!t || !t.classList || !t.classList.contains('mp-matrix-input')) return;
        e.preventDefault();
        t.blur();
      });
    }

    if ($('mpClearFilters')) {
      $('mpClearFilters').addEventListener('click', clearFilters);
    }

    if ($('mpFiltersToggle')) {
      $('mpFiltersToggle').addEventListener('click', function () {
        var panel = $('mpFiltersPanel');
        var btn = $('mpFiltersToggle');
        if (!panel || !btn) return;
        var open = panel.hidden;
        panel.hidden = !open;
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        btn.classList.toggle('is-open', open);
      });
    }

    var board = $('mpBoard');
    if (board) {
      board.addEventListener('click', function (e) {
        var filterBtn = e.target.closest('[data-col-filter]');
        if (!filterBtn) return;
        e.preventDefault();
        e.stopPropagation();
        if (state.colFilterKey === filterBtn.getAttribute('data-col-filter') && $('mpColMenu') && !$('mpColMenu').hidden) {
          closeColMenu();
          return;
        }
        openColMenu(filterBtn);
      });
    }

    if ($('mpColMenuApply')) {
      $('mpColMenuApply').addEventListener('click', applyColMenu);
    }
    if ($('mpColMenuClear')) {
      $('mpColMenuClear').addEventListener('click', function () {
        var key = state.colFilterKey;
        if (key === 'trade' && $('mpFilterTrade')) $('mpFilterTrade').value = 'all';
        if (key === 'project' && $('mpFilterProject')) $('mpFilterProject').value = 'all';
        if (key === 'requirement_type' && $('mpFilterReqType')) $('mpFilterReqType').value = 'all';
        if (key === 'status') state.status = 'all';
        closeColMenu();
        loadVacancies();
      });
    }
    document.addEventListener('click', function (e) {
      if (!$('mpColMenu') || $('mpColMenu').hidden) return;
      if (e.target.closest('#mpColMenu') || e.target.closest('[data-col-filter]')) return;
      closeColMenu();
    });
    // Close on page/board scroll, but allow scrolling inside the filter list itself
    window.addEventListener('scroll', function (e) {
      var menu = $('mpColMenu');
      if (!menu || menu.hidden) return;
      var target = e.target;
      if (target && menu.contains(target)) return;
      closeColMenu();
    }, true);

    var colMenu = $('mpColMenu');
    if (colMenu) {
      // Keep wheel/trackpad gestures on the menu; don't scroll the board underneath
      colMenu.addEventListener('wheel', function (e) {
        e.stopPropagation();
      }, { passive: true });
    }

    if ($('mpLinkList')) {
      $('mpLinkList').addEventListener('click', function (e) {
        var opt = e.target.closest('[data-candidate-id]');
        if (!opt) return;
        state.linkCandidateId = parseInt(opt.getAttribute('data-candidate-id'), 10);
        var q = ($('mpLinkSearch') && $('mpLinkSearch').value) || '';
        renderLinkCandidateList(q);
        if ($('mpLinkConfirm')) $('mpLinkConfirm').disabled = !state.linkCandidateId;
      });
    }
    if ($('mpLinkSearch')) {
      $('mpLinkSearch').addEventListener('input', function () {
        renderLinkCandidateList($('mpLinkSearch').value || '');
      });
    }
    if ($('mpLinkConfirm')) {
      $('mpLinkConfirm').addEventListener('click', confirmLinkCandidate);
    }

    if ($('mpBoardBody')) {
      $('mpBoardBody').addEventListener('change', onBoardChange);
      $('mpBoardBody').addEventListener('click', onBoardClick);
    }

    document.querySelectorAll('[data-close-modal]').forEach(function (el) {
      el.addEventListener('click', function () {
        closeModal(el);
      });
    });

    if ($('mpAddBtn')) {
      $('mpAddBtn').addEventListener('click', openAddVacancy);
    }

    if ($('mpAddForm')) {
      $('mpAddForm').addEventListener('submit', function (e) {
        e.preventDefault();
        var payload = {
          trade_id: parseInt($('mpAddTrade').value, 10),
          project_id: parseInt($('mpAddProject').value, 10),
          requirement_type: $('mpAddReqType').value,
          status: $('mpAddStatus').value,
          replacement_name: $('mpAddReplName').value,
          replacement_employee_id: $('mpAddReplId').value,
          candidate_name: $('mpAddCandidate').value,
          contact_number: $('mpAddContact').value,
          remarks: $('mpAddRemarks').value,
        };
        apiJson('/hr/api/manpower/vacancies', 'POST', payload)
          .then(function () {
            closeModal($('mpAddModal'));
            $('mpAddForm').reset();
            return Promise.all([loadSummary(), loadVacancies()]);
          })
          .catch(function (err) { alert(err.message); });
      });
    }

    if ($('mpManageListsBtn')) {
      $('mpManageListsBtn').addEventListener('click', openSettingsModal);
    }

    if ($('mpSidebarSettings')) {
      $('mpSidebarSettings').addEventListener('click', openSettingsModal);
    }

    if ($('mpSidebarBoard')) {
      $('mpSidebarBoard').addEventListener('click', function (e) {
        if ($('mpSettingsView') && !$('mpSettingsView').hidden) {
          e.preventDefault();
          closeSettingsModal();
        }
      });
    }

    if ($('mpSettingsBackBtn')) {
      $('mpSettingsBackBtn').addEventListener('click', closeSettingsModal);
    }

    if ($('mpAddOpenSettings')) {
      $('mpAddOpenSettings').addEventListener('click', function () {
        closeModal($('mpAddModal'));
        openSettingsModal();
      });
    }

    if ($('mpTradeList')) {
      $('mpTradeList').addEventListener('click', onSettingsListClick);
    }
    if ($('mpProjectList')) {
      $('mpProjectList').addEventListener('click', onSettingsListClick);
    }

    if ($('mpTradeAddForm')) {
      $('mpTradeAddForm').addEventListener('submit', function (e) {
        e.preventDefault();
        var name = ($('mpTradeAddName').value || '').trim();
        if (!name) return;
        apiJson('/hr/api/manpower/trades', 'POST', { name: name })
          .then(function () {
            $('mpTradeAddName').value = '';
            return loadMeta();
          })
          .catch(function (err) { showImportResult(err.message, true); });
      });
    }

    if ($('mpProjectAddForm')) {
      $('mpProjectAddForm').addEventListener('submit', function (e) {
        e.preventDefault();
        var name = ($('mpProjectAddName').value || '').trim();
        if (!name) return;
        apiJson('/hr/api/manpower/projects', 'POST', { name: name })
          .then(function () {
            $('mpProjectAddName').value = '';
            return loadMeta();
          })
          .catch(function (err) { showImportResult(err.message, true); });
      });
    }

    function openTemplateDownload() {
      downloadBlob('/hr/api/manpower/template', 'Manpower_Tracker_Template.xlsx')
        .catch(function (err) { showImportResult(err.message, true); });
    }
    function openExportDownload() {
      downloadBlob('/hr/api/manpower/export', 'Manpower_Tracker_Export.xlsx')
        .catch(function (err) { showImportResult(err.message, true); });
    }
    function openImportFlow() {
      openModal('mpImportModal');
    }

    if ($('mpTemplateBtn')) {
      $('mpTemplateBtn').addEventListener('click', openTemplateDownload);
    }
    if ($('mpExportBtn')) {
      $('mpExportBtn').addEventListener('click', openExportDownload);
    }
    if ($('mpImportBtn')) {
      $('mpImportBtn').addEventListener('click', function () {
        openModal('mpImportModal');
      });
    }
    if ($('mpSettingsTemplateBtn')) {
      $('mpSettingsTemplateBtn').addEventListener('click', openTemplateDownload);
    }
    if ($('mpSettingsExportBtn')) {
      $('mpSettingsExportBtn').addEventListener('click', openExportDownload);
    }
    if ($('mpSettingsImportBtn')) {
      $('mpSettingsImportBtn').addEventListener('click', openImportFlow);
    }
    if ($('mpImportConfirm')) {
      $('mpImportConfirm').addEventListener('click', function () {
        closeModal($('mpImportModal'));
        if ($('mpImportFile')) $('mpImportFile').click();
      });
    }
    if ($('mpImportFile')) {
      $('mpImportFile').addEventListener('change', function () {
        var file = $('mpImportFile').files && $('mpImportFile').files[0];
        if (!file) return;
        var fd = new FormData();
        fd.append('file', file);
        if ($('mpImportReplace') && $('mpImportReplace').checked) {
          fd.append('replace', '1');
        }
        authFetch('/hr/api/manpower/import', {
          method: 'POST',
          body: fd,
        }).then(function (r) {
          return r.json().then(function (body) {
            if (!r.ok || body.success === false) {
              throw new Error((body && (body.error || body.message || body.msg)) || 'Import failed');
            }
            return unwrap(body);
          });
        }).then(function (data) {
          var msg = 'Imported ' + (data.created || 0) + ' vacancies';
          if (data.deleted) msg += ' (replaced ' + data.deleted + ')';
          if (data.trades_created) msg += ', +' + data.trades_created + ' trades';
          if (data.projects_created) msg += ', +' + data.projects_created + ' projects';
          if (data.errors && data.errors.length) {
            msg += '. Warnings: ' + data.errors.slice(0, 3).join('; ');
          }
          showImportResult(msg, false);
          $('mpImportFile').value = '';
          return refreshAll();
        }).catch(function (err) {
          showImportResult(err.message || 'Import failed', true);
          $('mpImportFile').value = '';
        });
      });
    }
  }

  function init() {
    if (!$('mpRoot')) return;
    state.colOrder = loadColOrder();
    renderBoardHead();
    initColDrag();
    bindEvents();
    refreshAll().then(function () {
      if (window.location.hash === '#settings') {
        openSettingsModal();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
