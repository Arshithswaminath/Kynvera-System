/**
 * Employee from hiring — pending Candidate employed people, and the
 * Move to Employee List modal used on this page and Employee List.
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
    var token = localStorage.getItem('access_token') || localStorage.getItem('token');
    if (token) h.Authorization = 'Bearer ' + token;
    return h;
  }

  function unwrap(body) {
    if (!body) return {};
    if (body.data != null && typeof body.data === 'object' && !Array.isArray(body.data)) {
      return Object.assign({}, body, body.data);
    }
    return body;
  }

  function initials(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    var a = parts[0].charAt(0);
    var b = parts.length > 1 ? parts[parts.length - 1].charAt(0) : '';
    return (a + b).toUpperCase();
  }

  function fieldMissing(value) {
    var s = String(value == null ? '' : value).trim();
    if (!s) return true;
    var lower = s.toLowerCase();
    return s === '—' || s === '-' || s === '–' || lower === 'n/a' || lower === 'na' || lower === 'none';
  }

  function requiredReasons(row, pendingHire) {
    var reasons = [];
    if (pendingHire || fieldMissing(row && row.emp_id)) reasons.push('emp_id');
    if (fieldMissing(row && row.full_name)) reasons.push('full_name');
    return reasons;
  }

  var REASON_LABELS = {
    emp_id: 'Emp ID required',
    full_name: 'Name required',
  };

  function reasonChipsHtml(reasons) {
    if (!reasons || !reasons.length) return '';
    return (
      '<span class="el-reasons">' +
      reasons
        .map(function (key) {
          return '<span class="el-reason">' + esc(REASON_LABELS[key] || key) + '</span>';
        })
        .join('') +
      '</span>'
    );
  }

  function cardHtml(row, extraClass) {
    var extra = extraClass ? ' ' + extraClass : '';
    if (row.already_on_list) extra += ' is-listed';
    if (row.pending_hire) extra += ' is-listed';
    var isRosterFromHiring = !!(row.from_hiring && row.source !== 'hiring');
    if (isRosterFromHiring) extra += ' is-listed';
    var fromHiring = row.source === 'hiring';
    var openAttr = fromHiring
      ? ' data-efh-open="' + esc(row.hiring_candidate_id) + '"'
      : ' data-emp-open="' + esc(row.id) + '"';
    var listedHint = '';
    if (row.already_on_list) {
      var match = row.matched_employee || {};
      var who = match.emp_id || match.full_name || 'the staff list';
      listedHint =
        '<span class="el-listed-hint">Already on the Employee List as ' +
        esc(who) +
        '.<br>' +
        (match.name_can_update
          ? 'Merge and use this full name, or create a new record?</span>'
          : 'Merge into one record, or create a new one?</span>');
    } else if (row.pending_hire) {
      var hire = row.pending_hire || {};
      var hireName = hire.full_name || 'hiring';
      listedHint =
        '<span class="el-listed-hint">Hiring has ' +
        esc(hireName) +
        '.<br>Merge into one record?</span>';
    } else if (isRosterFromHiring) {
      listedHint = '<span class="el-listed-hint">Added through the hiring module</span>';
    }
    return (
      '<button type="button" class="el-card' + extra + '"' + openAttr + '>' +
      '<span class="el-card-main">' +
      '<span class="el-avatar">' + esc(initials(row.full_name)) + '</span>' +
      '<span class="el-card-body">' +
      '<span class="el-card-name">' + esc(row.full_name || '—') + '</span>' +
      '<span class="el-card-role">' + esc(row.designation || row.role || '—') + '</span>' +
      '<span class="el-card-foot">' +
      '<span class="el-card-id">' + esc(row.emp_id || '—') + '</span>' +
      '<span class="el-company">' + esc(row.company || 'Kynvera') + '</span>' +
      '</span></span></span>' +
      listedHint +
      '</button>'
    );
  }

  var TOAST_MS = 10000;

  function hideToast(force) {
    var el = $('elToast');
    if (!el) return;
    if (!force && hideToast._hovering) return;
    hideToast._hovering = false;
    clearTimeout(hideToast._t);
    el.classList.remove('is-show');
    clearTimeout(hideToast._hide);
    hideToast._hide = setTimeout(function () {
      if (!force && hideToast._hovering) return;
      el.hidden = true;
      el.classList.remove('is-error');
    }, 220);
  }

  function scheduleToastHide() {
    clearTimeout(hideToast._t);
    hideToast._t = setTimeout(hideToast, TOAST_MS);
  }

  function toast(msg, isError) {
    var el = $('elToast');
    var text = $('elToastMsg');
    if (!el) return;
    if (text) text.textContent = msg;
    else el.textContent = msg;
    el.hidden = false;
    el.classList.toggle('is-error', !!isError);
    el.classList.remove('is-show');
    el.setAttribute('role', isError ? 'alert' : 'status');
    hideToast._hovering = false;
    requestAnimationFrame(function () {
      el.classList.add('is-show');
    });
    scheduleToastHide();
  }

  function apiJson(url, method, payload) {
    var headers = authHeaders();
    headers['Content-Type'] = 'application/json';
    var opts = {
      method: method,
      credentials: 'same-origin',
      headers: headers,
    };
    if (payload !== undefined) opts.body = JSON.stringify(payload);
    return fetch(url, opts).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok || body.success === false) {
          throw new Error((body && (body.error || body.message)) || 'Request failed');
        }
        return unwrap(body);
      });
    });
  }

  function loadPending() {
    return fetch('/hr/api/employee-from-hiring', {
      credentials: 'same-origin',
      headers: authHeaders(),
    }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok || body.success === false) {
          throw new Error((body && (body.error || body.message)) || 'Request failed');
        }
        return unwrap(body);
      });
    }).then(function (data) {
      return data.pending || [];
    });
  }

  var dismissBusy = false;
  var dismissRow = null;

  function openDismissModal(row) {
    var modal = $('efhDismissModal');
    if (!modal || !row) return;
    dismissRow = {
      hiring_candidate_id: row.hiring_candidate_id,
      emp_id: row.emp_id || '',
      full_name: row.full_name || '',
      designation: row.designation || row.role || '',
      company: row.company || 'Kynvera',
      matched_employee: row.matched_employee || {},
    };
    modal.setAttribute('data-candidate-id', String(row.hiring_candidate_id || ''));
    var match = row.matched_employee || {};
    modal.setAttribute('data-emp-id', String(match.emp_id || ''));
    var copy = $('efhDismissCopy');
    var empLine = $('efhDismissEmpId');
    var name = row.full_name || 'This person';
    var listName = match.full_name || '';
    var empId = match.emp_id || '';
    var canUpdate = !!(match.name_can_update);
    if (copy) {
      if (canUpdate && listName && listName !== name) {
        copy.textContent =
          (empId ? name + ' is already on the Employee List as ' + empId + '. ' : '') +
          'The staff list has a shorter name. Merge and use the full name from hiring, or create a new record if this is a different person.';
      } else {
        copy.textContent = empId
          ? name + ' is already on the Employee List as ' + empId + '. Merge into one record, or create a new record if this is a different person.'
          : name + ' is already on the Employee List. Merge into one record, or create a new record if this is a different person.';
      }
    }
    if (empLine) empLine.textContent = empId || listName || '—';
    var names = $('efhDismissNames');
    if (names) {
      if (canUpdate && listName && listName !== name) {
        names.hidden = false;
        names.textContent = 'Employee List: ' + listName + ' → Hiring: ' + name;
      } else {
        names.hidden = true;
        names.textContent = '';
      }
    }
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeDismissModal() {
    var modal = $('efhDismissModal');
    if (modal) {
      modal.hidden = true;
      modal.removeAttribute('data-candidate-id');
      modal.removeAttribute('data-emp-id');
    }
    dismissRow = null;
    if (!otherModalsOpen() && !($('efhPromoteModal') && !$('efhPromoteModal').hidden)) {
      document.body.style.overflow = '';
    }
  }

  function openCreateNewFromDismiss() {
    if (dismissBusy) return Promise.resolve();
    var row = dismissRow;
    if (!row || !row.hiring_candidate_id) {
      return Promise.reject(new Error('Candidate is missing'));
    }
    var match = row.matched_employee || {};
    closeDismissModal();
    openPromoteModal({
      hiring_candidate_id: row.hiring_candidate_id,
      emp_id: '',
      full_name: row.full_name || '',
      designation: row.designation || '',
      company: row.company || 'Kynvera',
    }, {
      createNew: true,
      takenEmpId: match.emp_id || '',
    });
    return Promise.resolve();
  }

  function submitDismiss() {
    if (dismissBusy) return Promise.resolve();
    var modal = $('efhDismissModal');
    var candidateId = ((modal && modal.getAttribute('data-candidate-id')) || '').trim();
    if (!candidateId) return Promise.reject(new Error('Candidate is missing'));
    var empId = ((modal && modal.getAttribute('data-emp-id')) || '').trim();
    dismissBusy = true;
    var confirmBtn = $('efhDismissConfirm');
    var createBtn = $('efhDismissCreate');
    if (confirmBtn) confirmBtn.disabled = true;
    if (createBtn) createBtn.disabled = true;
    return apiJson(
      '/hr/api/employee-from-hiring/' + candidateId + '/dismiss',
      'POST',
      empId ? { emp_id: empId } : {}
    )
      .then(function (data) {
        closeDismissModal();
        toast(
          (data && data.name_updated)
            ? 'Merged and updated the name on Employee List'
            : 'Merged into one record on Employee List'
        );
        if (typeof promoteOnSuccess === 'function') return promoteOnSuccess(data);
        return data;
      })
      .finally(function () {
        dismissBusy = false;
        if (confirmBtn) confirmBtn.disabled = false;
        if (createBtn) createBtn.disabled = false;
      });
  }

  function openHiringCard(row) {
    if (!row) return;
    if (row.already_on_list) {
      openDismissModal(row);
      return;
    }
    openPromoteModal(row);
  }

  function otherModalsOpen() {
    var add = $('elAddModal');
    var view = $('elModal');
    var dismiss = $('efhDismissModal');
    return (add && !add.hidden) || (view && !view.hidden) || (dismiss && !dismiss.hidden);
  }

  var promoteBusy = false;
  var promoteOnSuccess = null;
  var PROMOTE_TITLE = 'Move to Employee List';
  var PROMOTE_HINT = 'Add this person to the general Employee List? Emp ID and full name are required.';
  var PROMOTE_SUBMIT = 'Move to Employee List';

  function setPromoteCopy(opts) {
    opts = opts || {};
    var title = $('efhPromoteTitle');
    var hint = $('efhPromoteHint');
    var submit = $('efhPromoteSubmit');
    var empIdField = $('efhPromoteEmpId');
    if (opts.createNew) {
      if (title) title.textContent = 'Create new Employee List record';
      if (hint) {
        hint.textContent = opts.takenEmpId
          ? 'Emp ID ' + opts.takenEmpId + ' is already on the list. Enter a new Emp ID to add a separate person.'
          : 'Enter a new Emp ID to add a separate person to the Employee List.';
      }
      if (submit) submit.textContent = 'Create new record';
      if (empIdField) empIdField.placeholder = 'New Emp ID';
    } else {
      if (title) title.textContent = PROMOTE_TITLE;
      if (hint) hint.textContent = PROMOTE_HINT;
      if (submit) submit.textContent = PROMOTE_SUBMIT;
      if (empIdField) empIdField.placeholder = 'INJ-0042';
    }
  }

  function openPromoteModal(row, opts) {
    var modal = $('efhPromoteModal');
    if (!modal || !row) return;
    opts = opts || {};
    $('efhPromoteCandidateId').value = String(row.hiring_candidate_id || '');
    if ($('efhPromoteEmpId')) $('efhPromoteEmpId').value = opts.createNew ? '' : (row.emp_id || '');
    if ($('efhPromoteName')) $('efhPromoteName').value = row.full_name || '';
    if ($('efhPromoteDesig')) $('efhPromoteDesig').value = row.designation || row.role || '';
    if ($('efhPromoteCompany')) $('efhPromoteCompany').value = row.company || 'Kynvera';
    setPromoteCopy(opts);
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
    setTimeout(function () {
      $('efhPromoteEmpId') && $('efhPromoteEmpId').focus();
    }, 50);
  }

  function closePromoteModal() {
    var modal = $('efhPromoteModal');
    if (modal) modal.hidden = true;
    setPromoteCopy();
    if (!otherModalsOpen()) document.body.style.overflow = '';
  }

  function submitPromote() {
    if (promoteBusy) return Promise.resolve();
    var candidateId = (($('efhPromoteCandidateId') && $('efhPromoteCandidateId').value) || '').trim();
    if (!candidateId) return Promise.reject(new Error('Candidate is missing'));
    var payload = {
      emp_id: (($('efhPromoteEmpId') && $('efhPromoteEmpId').value) || '').trim(),
      full_name: (($('efhPromoteName') && $('efhPromoteName').value) || '').trim(),
      designation: (($('efhPromoteDesig') && $('efhPromoteDesig').value) || '').trim(),
      company: (($('efhPromoteCompany') && $('efhPromoteCompany').value) || '').trim(),
    };
    if (!payload.emp_id || !payload.full_name) {
      return Promise.reject(new Error('Emp ID and full name are required'));
    }
    promoteBusy = true;
    var submit = $('efhPromoteSubmit');
    if (submit) submit.disabled = true;
    var headers = authHeaders();
    headers['Content-Type'] = 'application/json';
    return fetch('/hr/api/employee-from-hiring/' + candidateId + '/promote', {
      method: 'POST',
      credentials: 'same-origin',
      headers: headers,
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (body) {
          var details = (body && body.details) || {};
          if (r.status === 409 && (body.error_code === 'NEEDS_MERGE' || details.needs_merge)) {
            closePromoteModal();
            openDismissModal({
              hiring_candidate_id: candidateId,
              full_name: payload.full_name,
              designation: payload.designation,
              company: payload.company,
              matched_employee: details.matched_employee || {
                emp_id: payload.emp_id,
                full_name: '',
                name_can_update: false,
              },
            });
            return { offeredMerge: true };
          }
          if (!r.ok || body.success === false) {
            throw new Error((body && (body.error || body.message)) || 'Request failed');
          }
          return unwrap(body);
        });
      })
      .then(function (data) {
        if (data && data.offeredMerge) return data;
        closePromoteModal();
        var name = (data.employee && data.employee.full_name) || payload.full_name;
        toast((name || 'This person') + ' was added to the Employee List');
        if (typeof promoteOnSuccess === 'function') return promoteOnSuccess(data);
        return data;
      })
      .finally(function () {
        promoteBusy = false;
        if (submit) submit.disabled = false;
      });
  }

  function bindPromoteModal(onSuccess) {
    promoteOnSuccess = onSuccess || null;
    var modal = $('efhPromoteModal');
    if (modal && !modal._efhBound) {
      modal._efhBound = true;
      modal.addEventListener('click', function (e) {
        if (e.target && e.target.hasAttribute && e.target.hasAttribute('data-close-efh-promote')) {
          closePromoteModal();
        }
      });
      var form = $('efhPromoteForm');
      if (form) {
        form.addEventListener('submit', function (e) {
          e.preventDefault();
          submitPromote().catch(function (err) {
            toast(err.message || 'Could not add to Employee List', true);
            $('efhPromoteEmpId') && $('efhPromoteEmpId').focus();
          });
        });
      }
    }
    var dismiss = $('efhDismissModal');
    if (dismiss && !dismiss._efhBound) {
      dismiss._efhBound = true;
      dismiss.addEventListener('click', function (e) {
        if (e.target && e.target.hasAttribute && e.target.hasAttribute('data-close-efh-dismiss')) {
          closeDismissModal();
        }
      });
      var confirmBtn = $('efhDismissConfirm');
      if (confirmBtn) {
        confirmBtn.addEventListener('click', function () {
          submitDismiss().catch(function (err) {
            toast(err.message || 'Could not merge with Employee List', true);
          });
        });
      }
      var createBtn = $('efhDismissCreate');
      if (createBtn) {
        createBtn.addEventListener('click', function () {
          openCreateNewFromDismiss().catch(function (err) {
            toast(err.message || 'Could not start a new Employee List record', true);
          });
        });
      }
    }
    if (!bindPromoteModal._escBound) {
      bindPromoteModal._escBound = true;
      document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        if (dismiss && !dismiss.hidden) {
          closeDismissModal();
          return;
        }
        if (modal && !modal.hidden) closePromoteModal();
      });
    }
    var notice = $('elToast');
    if (notice && !notice._efhToastBound) {
      notice._efhToastBound = true;
      notice.addEventListener('mouseenter', function () {
        hideToast._hovering = true;
        clearTimeout(hideToast._t);
        clearTimeout(hideToast._hide);
        notice.hidden = false;
        notice.classList.add('is-show');
      });
      notice.addEventListener('mouseleave', function () {
        hideToast._hovering = false;
        scheduleToastHide();
      });
      var closeBtn = $('elToastClose');
      if (closeBtn) {
        closeBtn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          hideToast(true);
        });
      }
    }
  }

  window.Efh = {
    $,
    esc: esc,
    authHeaders: authHeaders,
    unwrap: unwrap,
    initials: initials,
    fieldMissing: fieldMissing,
    requiredReasons: requiredReasons,
    reasonChipsHtml: reasonChipsHtml,
    cardHtml: cardHtml,
    toast: toast,
    apiJson: apiJson,
    loadPending: loadPending,
    openPromoteModal: openPromoteModal,
    closePromoteModal: closePromoteModal,
    openDismissModal: openDismissModal,
    closeDismissModal: closeDismissModal,
    openHiringCard: openHiringCard,
    bindPromoteModal: bindPromoteModal,
  };

  function runDedicatedPage() {
    var pending = [];
    var filtered = [];

    function queryNorm() {
      return (($('efhSearch') && $('efhSearch').value) || '').trim().toLowerCase();
    }

    function companyFilter() {
      return (($('efhCompany') && $('efhCompany').value) || 'all').trim();
    }

    function incompleteOnly() {
      var box = $('efhIncompleteOnly');
      return !!(box && box.checked);
    }

    function withReasons(row) {
      var next = Object.assign({}, row, { source: 'hiring' });
      next.required_reasons = next.required_reasons && next.required_reasons.length
        ? next.required_reasons
        : requiredReasons(next, true);
      return next;
    }

    function matchesQuery(row, q) {
      if (!q) return true;
      var id = String(row.emp_id || '').toLowerCase();
      var name = String(row.full_name || '').toLowerCase();
      var role = String(row.designation || row.role || '').toLowerCase();
      return id.indexOf(q) !== -1 || name.indexOf(q) !== -1 || role.indexOf(q) !== -1;
    }

    function uniqueCompanyNames(list) {
      var seen = { Kynvera: true, Tourism: true, 'L&P': true };
      var names = ['Kynvera', 'Tourism', 'L&P'];
      (list || []).forEach(function (e) {
        var c = (e.company || '').trim();
        if (c && !seen[c]) {
          seen[c] = true;
          names.push(c);
        }
      });
      return names;
    }

    function refreshCompanyChoices() {
      var names = uniqueCompanyNames(pending);
      var filter = $('efhCompany');
      if (!filter) return;
      var current = filter.value || 'all';
      filter.innerHTML =
        '<option value="all">All companies</option>' +
        names.map(function (n) {
          return '<option value="' + esc(n) + '">' + esc(n) + '</option>';
        }).join('');
      filter.value = current;
      if (filter.value !== current) filter.value = 'all';
    }

    function currentRows() {
      var q = queryNorm();
      var company = companyFilter();
      var incomplete = incompleteOnly();
      return pending.filter(function (row) {
        if (company && company !== 'all') {
          if (String(row.company || '') !== company) return false;
        }
        if (incomplete && !(row.required_reasons && row.required_reasons.length)) return false;
        return matchesQuery(row, q);
      });
    }

    function updateBanner() {
      var banner = $('efhHiringBanner');
      var text = $('efhHiringBannerText');
      var n = pending.length;
      if (!banner) return;
      if (!n) {
        banner.hidden = true;
        return;
      }
      banner.hidden = false;
      if (text) {
        text.textContent =
          n === 1
            ? '1 person from hiring is waiting to be added'
            : n + ' people from hiring are waiting to be added';
      }
    }

    function renderGrid() {
      var grid = $('efhGrid');
      var status = $('efhStatus');
      var clearBtn = $('efhSearchClear');
      var incompleteCount = pending.filter(function (e) {
        return e.required_reasons && e.required_reasons.length;
      }).length;
      filtered = currentRows();
      if (clearBtn) clearBtn.hidden = !queryNorm();
      if ($('efhStatTotal')) $('efhStatTotal').textContent = String(pending.length);
      if ($('efhStatShown')) $('efhStatShown').textContent = String(filtered.length);
      if ($('efhStatIncomplete')) $('efhStatIncomplete').textContent = String(incompleteCount);
      updateBanner();

      if (!pending.length) {
        if (status) {
          status.hidden = false;
          status.textContent =
            'When you mark someone Candidate employed in Hiring Docs, they show up here to add to the staff list.';
        }
        if (grid) {
          grid.hidden = true;
          grid.innerHTML = '';
        }
        return;
      }
      if (!filtered.length) {
        if (status) {
          status.hidden = false;
          status.textContent = incompleteOnly()
            ? 'No incomplete records.'
            : 'No staff match that Emp ID or name.';
        }
        if (grid) {
          grid.hidden = true;
          grid.innerHTML = '';
        }
        return;
      }
      if (status) {
        status.hidden = true;
        status.textContent = '';
      }
      if (!grid) return;
      grid.hidden = false;
      grid.innerHTML = filtered.map(function (row) {
        return cardHtml(row);
      }).join('');
    }

    function findPending(id) {
      var key = String(id);
      for (var i = 0; i < pending.length; i++) {
        if (String(pending[i].hiring_candidate_id) === key) return pending[i];
      }
      return null;
    }

    function reload() {
      var status = $('efhStatus');
      if (status) {
        status.hidden = false;
        status.textContent = 'Loading people from hiring…';
      }
      return loadPending()
        .then(function (rows) {
          pending = (rows || []).map(withReasons);
          refreshCompanyChoices();
          renderGrid();
        })
        .catch(function (err) {
          if (status) {
            status.hidden = false;
            status.textContent = 'Could not load people from hiring.';
          }
          toast(err.message || 'Could not load people from hiring', true);
        });
    }

    var search = $('efhSearch');
    var clearBtn = $('efhSearchClear');
    var grid = $('efhGrid');
    var company = $('efhCompany');
    var incompleteBox = $('efhIncompleteOnly');
    if (search) {
      search.addEventListener('input', renderGrid);
      search.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') search.blur();
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        if (search) search.value = '';
        renderGrid();
        if (search) search.focus();
      });
    }
    if (company) company.addEventListener('change', renderGrid);
    if (incompleteBox) incompleteBox.addEventListener('change', renderGrid);
    if (grid) {
      grid.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest('[data-efh-open]');
        if (!btn) return;
        openHiringCard(findPending(btn.getAttribute('data-efh-open')));
      });
    }
    bindPromoteModal(function () {
      return reload();
    });
    reload();
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!$('efhGrid')) return;
    if (!localStorage.getItem('access_token') && !localStorage.getItem('token')) {
      window.location.href = '/login';
      return;
    }
    runDedicatedPage();
  });
})();
