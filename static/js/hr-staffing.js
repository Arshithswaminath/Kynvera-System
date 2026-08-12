/**
 * Staffing Assignments — match open vacancies to Hiring candidates
 */
(function () {
  'use strict';

  function authHeaders(extra) {
    var headers = Object.assign({}, extra || {});
    try {
      var token = localStorage.getItem('access_token') || '';
      if (token) headers.Authorization = 'Bearer ' + token;
    } catch (_) {}
    return headers;
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function toast(msg, isError) {
    var el = document.getElementById('stToast');
    if (!el) return;
    el.hidden = false;
    el.textContent = msg;
    el.classList.toggle('error', !!isError);
    el.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(function () {
      el.classList.remove('show');
      el.hidden = true;
    }, 2800);
  }

  async function api(url, opts) {
    var options = opts || {};
    var headers = authHeaders(options.headers || {});
    if (options.json) headers['Content-Type'] = 'application/json';
    var res = await fetch(url, {
      method: options.method || 'GET',
      headers: headers,
      body: options.json ? JSON.stringify(options.json) : options.body,
    });
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!res.ok || (data && data.success === false)) {
      throw new Error((data && (data.error || data.message)) || ('Request failed (' + res.status + ')'));
    }
    return data;
  }

  var state = {
    q: '',
    vacId: null,
    candId: null,
    openVacancies: [],
    candidates: [],
    linked: [],
  };

  function selectedVacancy() {
    return state.openVacancies.find(function (v) {
      return String(v.id) === String(state.vacId);
    }) || null;
  }

  function selectedCandidate() {
    return state.candidates.find(function (c) {
      return String(c.id) === String(state.candId);
    }) || null;
  }

  function syncMatchBar() {
    var btn = document.getElementById('stMatchBtn');
    var bar = document.getElementById('stMatchBar');
    var pair = document.getElementById('stMatchPair');
    var vac = selectedVacancy();
    var cand = selectedCandidate();
    var ready = !!(vac && cand);

    if (btn) {
      btn.disabled = !ready;
      btn.classList.toggle('is-ready', ready);
      btn.textContent = ready ? 'Match selected' : 'Select both sides';
    }

    if (!bar || !pair) return;
    if (!ready) {
      bar.hidden = true;
      pair.innerHTML = '';
      return;
    }
    bar.hidden = false;
    pair.innerHTML =
      '<span class="st-match-chip">' + esc(vac.label || ('Vacancy #' + vac.id)) + '</span>' +
      '<span class="st-match-arrow" aria-hidden="true">→</span>' +
      '<span class="st-match-chip">' + esc(cand.full_name) + '</span>';
  }

  function renderVacancies() {
    var el = document.getElementById('stVacList');
    var count = document.getElementById('stVacCount');
    if (count) count.textContent = String(state.openVacancies.length);
    if (!el) return;
    if (!state.openVacancies.length) {
      el.innerHTML =
        '<div class="st-empty">' +
          '<div>No open vacancies</div>' +
          '<div class="st-empty-sub">Add or free a slot in Manpower Tracker first.</div>' +
        '</div>';
      return;
    }
    el.innerHTML = state.openVacancies.map(function (v) {
      var selected = String(v.id) === String(state.vacId);
      var isRepl = v.requirement_type === 'replacement';
      var tags =
        '<div class="st-item-tags">' +
          '<span class="st-tag ' + (isRepl ? 'is-repl' : 'is-new') + '">' +
            (isRepl ? 'Replacement' : 'New') +
          '</span>' +
          (isRepl && v.replacement_name
            ? '<span class="st-tag is-repl">Replacing ' + esc(v.replacement_name) + '</span>'
            : '') +
        '</div>';
      return (
        '<button type="button" class="st-item' + (selected ? ' is-selected' : '') +
          '" data-vac="' + v.id + '" role="option" aria-selected="' + (selected ? 'true' : 'false') + '">' +
          '<span class="st-item-title">' + esc(v.label || ('Vacancy #' + v.id)) + '</span>' +
          '<span class="st-item-meta">Vacancy #' + esc(String(v.id)) +
            (v.project_name ? ' · ' + esc(v.project_name) : '') +
          '</span>' +
          tags +
        '</button>'
      );
    }).join('');
  }

  function renderCandidates() {
    var el = document.getElementById('stCandList');
    var count = document.getElementById('stCandCount');
    if (count) count.textContent = String(state.candidates.length);
    if (!el) return;
    if (!state.candidates.length) {
      el.innerHTML =
        '<div class="st-empty">' +
          '<div>No unassigned candidates</div>' +
          '<div class="st-empty-sub">Create a candidate in Hiring Docs, or unlink one from Manpower.</div>' +
        '</div>';
      return;
    }
    el.innerHTML = state.candidates.map(function (c) {
      var selected = String(c.id) === String(state.candId);
      return (
        '<button type="button" class="st-item' + (selected ? ' is-selected' : '') +
          '" data-cand="' + c.id + '" role="option" aria-selected="' + (selected ? 'true' : 'false') + '">' +
          '<span class="st-item-title">' + esc(c.full_name) + '</span>' +
          '<span class="st-item-meta">' + esc(c.role || 'No role set') + '</span>' +
          '<div class="st-item-tags">' +
            '<span class="st-tag is-pipe">' + esc(c.pipeline_label || c.pipeline_status || '—') + '</span>' +
            (c.progress_label
              ? '<span class="st-tag">' + esc(c.progress_label) + ' docs</span>'
              : '') +
          '</div>' +
        '</button>'
      );
    }).join('');
  }

  function renderLinked() {
    var el = document.getElementById('stLinkedList');
    var count = document.getElementById('stLinkedCount');
    if (count) count.textContent = String(state.linked.length);
    if (!el) return;
    if (!state.linked.length) {
      el.innerHTML =
        '<div class="st-empty">' +
          '<div>No linked pairs yet</div>' +
          '<div class="st-empty-sub">Select a vacancy and a candidate above, then click Match selected.</div>' +
        '</div>';
      return;
    }
    el.innerHTML = state.linked.map(function (pair) {
      var v = pair.vacancy || {};
      var c = pair.candidate || {};
      return (
        '<div class="st-linked-row">' +
          '<div class="st-linked-main">' +
            '<a href="' + esc(c.url || '#') + '">' + esc(c.full_name || '—') + '</a>' +
            '<span class="st-linked-arrow" aria-hidden="true">→</span>' +
            '<span class="st-linked-vac">' + esc(v.label || ('Vacancy #' + v.id)) + '</span>' +
          '</div>' +
          '<div class="st-linked-actions">' +
            '<button type="button" class="hh-btn hh-btn-ghost hh-btn-sm" data-unlink-vac="' +
              esc(String(v.id)) + '">Unlink</button>' +
          '</div>' +
          '<div class="st-linked-meta">' +
            esc(c.pipeline_label || '') +
            ' · <a href="/hr/manpower-tracker">Open Manpower</a>' +
            ' · <a href="' + esc(c.url || '#') + '">Hiring Docs</a>' +
          '</div>' +
        '</div>'
      );
    }).join('');
  }

  async function load() {
    var qs = state.q ? ('?q=' + encodeURIComponent(state.q)) : '';
    var data = await api('/hr/api/staffing/assignments' + qs);
    state.openVacancies = data.open_vacancies || [];
    state.candidates = data.unassigned_candidates || [];
    state.linked = data.linked || [];
    if (state.vacId && !state.openVacancies.some(function (v) {
      return String(v.id) === String(state.vacId);
    })) {
      state.vacId = null;
    }
    if (state.candId && !state.candidates.some(function (c) {
      return String(c.id) === String(state.candId);
    })) {
      state.candId = null;
    }
    renderVacancies();
    renderCandidates();
    renderLinked();
    syncMatchBar();
  }

  async function matchSelected() {
    if (!state.vacId || !state.candId) return;
    var btn = document.getElementById('stMatchBtn');
    if (btn) btn.disabled = true;
    try {
      await api('/hr/api/staffing/assign', {
        method: 'POST',
        json: { candidate_id: state.candId, vacancy_id: state.vacId },
      });
      toast('Assigned');
      state.vacId = null;
      state.candId = null;
      await load();
    } catch (err) {
      toast(err.message, true);
      syncMatchBar();
    }
  }

  function bind() {
    var root = document.getElementById('stRoot');
    if (!root) return;

    var search = document.getElementById('stSearch');
    var timer;
    if (search) {
      search.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          state.q = (search.value || '').trim();
          load().catch(function (e) { toast(e.message, true); });
        }, 250);
      });
    }

    var matchBtn = document.getElementById('stMatchBtn');
    if (matchBtn) matchBtn.addEventListener('click', matchSelected);

    var vacList = document.getElementById('stVacList');
    if (vacList) {
      vacList.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-vac]');
        if (!btn) return;
        var id = parseInt(btn.getAttribute('data-vac'), 10);
        state.vacId = String(state.vacId) === String(id) ? null : id;
        renderVacancies();
        syncMatchBar();
      });
    }

    var candList = document.getElementById('stCandList');
    if (candList) {
      candList.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-cand]');
        if (!btn) return;
        var id = parseInt(btn.getAttribute('data-cand'), 10);
        state.candId = String(state.candId) === String(id) ? null : id;
        renderCandidates();
        syncMatchBar();
      });
    }

    var linked = document.getElementById('stLinkedList');
    if (linked) {
      linked.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-unlink-vac]');
        if (!btn) return;
        var vid = parseInt(btn.getAttribute('data-unlink-vac'), 10);
        if (!vid) return;
        btn.disabled = true;
        api('/hr/api/staffing/unassign', {
          method: 'POST',
          json: { vacancy_id: vid },
        }).then(function () {
          toast('Unlinked');
          return load();
        }).catch(function (err) {
          toast(err.message, true);
          btn.disabled = false;
        });
      });
    }

    load().catch(function (e) {
      toast(e.message, true);
      var vacListEl = document.getElementById('stVacList');
      if (vacListEl) {
        vacListEl.innerHTML = '<div class="st-empty">' + esc(e.message) + '</div>';
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
