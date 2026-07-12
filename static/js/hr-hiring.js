/**
 * Hiring Document Tracker — list + detail client logic
 */
(function () {
  'use strict';

  const STATUS_LABELS = {
    not_started: 'Not Started',
    in_progress: 'In Progress',
    complete: 'Complete',
  };

  const PHASE2_FALLBACK = [
    { doc_type: 'offer_letter', label: 'Offer Letter (Department Signed)', phase: 2, status: 'missing', has_file: false, is_complete: false, allowed_extensions: ['pdf'], upload_locked: false },
    { doc_type: 'insurance', label: 'Insurance Paper', phase: 2, status: 'missing', has_file: false, is_complete: false, allowed_extensions: ['pdf', 'jpg', 'jpeg', 'png'], upload_locked: true },
    { doc_type: 'e_visa', label: 'E-Visa', phase: 2, status: 'missing', has_file: false, is_complete: false, allowed_extensions: ['pdf', 'jpg', 'jpeg', 'png'], upload_locked: true },
    { doc_type: 'contract', label: 'Employment Contract', phase: 2, status: 'missing', has_file: false, is_complete: false, allowed_extensions: ['pdf'], upload_locked: true },
  ];

  const PIPELINE_LABELS = {
    interview_completed: 'Interview completed',
    gathering_documents: 'Gathering documents',
    offer_letter_prepared: 'Offer letter prepared',
    offer_letter_signed: 'Offer letter signed',
    md_signed_offer_received: 'Signed offer letter from MD received',
    visa_process_started: 'Visa process started',
  };

  const PIPELINE_SHORT = {
    interview_completed: 'Interview',
    gathering_documents: 'Documents',
    offer_letter_prepared: 'Offer ready',
    offer_letter_signed: 'Offer signed',
    md_signed_offer_received: 'MD signed',
    visa_process_started: 'Visa started',
  };

  const PIPELINE_META = {
    interview_completed: {
      focus: 'Interview done — start collecting identity papers',
      next: 'Move to Gathering documents when HR begins the checklist',
      hint: 'Passport, Emirates ID, photo, PCC, and education certificate come next.',
    },
    gathering_documents: {
      focus: 'Collecting identity & clearance documents',
      next: 'Advance when Phase 1 uploads are underway or complete',
      hint: 'Track passport, Emirates ID, photograph, PCC (attested), and education certificate.',
    },
    offer_letter_prepared: {
      focus: 'Department offer letter is prepared',
      next: 'Advance once the candidate has signed the offer',
      hint: 'Upload the department-signed offer letter anytime — it is never locked.',
    },
    offer_letter_signed: {
      focus: 'Candidate has signed the offer letter',
      next: 'Advance when the MD-signed offer is received',
      hint: 'Keep the signed offer on file; MD countersignature is the next gate.',
    },
    md_signed_offer_received: {
      focus: 'MD-signed offer is on file',
      next: 'Start visa process to unlock insurance, e-visa, and contract',
      hint: 'Visa pack stays locked until you mark Visa process started.',
    },
    visa_process_started: {
      focus: 'Visa process open — upload remaining pack',
      next: 'Finish insurance, e-visa, and employment contract',
      hint: 'Insurance, e-visa, and contract uploads are unlocked at this stage.',
    },
  };

  const PIPELINE_ORDER = Object.keys(PIPELINE_LABELS);

  const VISA_GATED = { insurance: true, e_visa: true, contract: true };

  function docCompleteCount(docs, types) {
    const byType = {};
    (docs || []).forEach(function (d) { byType[d.doc_type] = d; });
    let done = 0;
    types.forEach(function (t) {
      const d = byType[t];
      if (d && d.is_complete) done += 1;
    });
    return { done: done, total: types.length };
  }

  function token() {
    return localStorage.getItem('access_token') || '';
  }

  function authHeaders(extra) {
    const h = Object.assign({ Authorization: 'Bearer ' + token() }, extra || {});
    return h;
  }

  function confirmDialog(opts) {
    const options = opts || {};
    const title = options.title || 'Confirm';
    const message = options.message || 'Are you sure?';
    const confirmLabel = options.confirmLabel || 'Confirm';
    const cancelLabel = options.cancelLabel || 'Cancel';
    const danger = options.danger !== false;

    return new Promise(function (resolve) {
      let backdrop = document.getElementById('hhConfirmModal');
      if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.id = 'hhConfirmModal';
        backdrop.className = 'hh-modal-backdrop';
        backdrop.setAttribute('role', 'dialog');
        backdrop.setAttribute('aria-modal', 'true');
        backdrop.innerHTML =
          '<div class="hh-modal hh-confirm-modal">' +
            '<h2 id="hhConfirmTitle"></h2>' +
            '<p class="hh-modal-sub" id="hhConfirmMessage"></p>' +
            '<div class="hh-modal-actions">' +
              '<button type="button" class="hh-btn hh-btn-ghost" data-hh-confirm-cancel></button>' +
              '<button type="button" class="hh-btn" data-hh-confirm-ok></button>' +
            '</div>' +
          '</div>';
        document.body.appendChild(backdrop);
      }

      const titleEl = backdrop.querySelector('#hhConfirmTitle');
      const msgEl = backdrop.querySelector('#hhConfirmMessage');
      const cancelBtn = backdrop.querySelector('[data-hh-confirm-cancel]');
      const okBtn = backdrop.querySelector('[data-hh-confirm-ok]');

      titleEl.textContent = title;
      msgEl.textContent = message;
      cancelBtn.textContent = cancelLabel;
      okBtn.textContent = confirmLabel;
      okBtn.className = 'hh-btn ' + (danger ? 'hh-btn-danger' : 'hh-btn-primary');
      backdrop.setAttribute('aria-labelledby', 'hhConfirmTitle');

      function cleanup(result) {
        backdrop.classList.remove('open');
        backdrop.removeEventListener('click', onBackdrop);
        cancelBtn.removeEventListener('click', onCancel);
        okBtn.removeEventListener('click', onOk);
        document.removeEventListener('keydown', onKey);
        resolve(result);
      }

      function onCancel() { cleanup(false); }
      function onOk() { cleanup(true); }
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

  function toast(msg, isError) {
    let el = document.getElementById('hhToast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'hhToast';
      el.className = 'hh-toast';
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.toggle('error', !!isError);
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(function () {
      el.classList.remove('show');
    }, 2800);
  }

  async function api(url, opts) {
    const options = opts || {};
    const headers = authHeaders(options.headers || {});
    if (options.json) {
      headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(url, {
      method: options.method || 'GET',
      headers: headers,
      body: options.json ? JSON.stringify(options.json) : options.body,
    });
    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      data = null;
    }
    if (!res.ok || (data && data.success === false)) {
      const err = (data && (data.error || data.message)) || ('Request failed (' + res.status + ')');
      throw new Error(err);
    }
    return data;
  }

  function avatarClass(name) {
    let n = 0;
    const s = name || '';
    for (let i = 0; i < s.length; i++) n += s.charCodeAt(i);
    return 'c' + (n % 6);
  }

  function statusIcon(status) {
    if (status === 'complete') {
      return '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5"/></svg>';
    }
    if (status === 'in_progress') {
      return '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
    }
    return '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14"/></svg>';
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* ── List page ─────────────────────────────────────────── */
  function initList() {
    const root = document.getElementById('hhListRoot');
    if (!root) return;

    const state = {
      q: '',
      status: 'all',
      pipeline: 'all',
      page: 1,
      perPage: 12,
      pages: 1,
      count: 0,
    };

    const listEl = document.getElementById('hhCandidateList');
    const searchEl = document.getElementById('hhSearch');
    const filterBtns = document.querySelectorAll('.hh-filter-btn');
    const pipelineFilter = document.getElementById('hhPipelineFilter');
    const pagEl = document.getElementById('hhPagination');
    const modal = document.getElementById('hhAddModal');
    const form = document.getElementById('hhAddForm');
    const interviewPick = document.getElementById('hhInterviewPick');
    const interviewApply = document.getElementById('hhInterviewApply');

    let searchTimer = null;
    let assessmentsCache = [];

    async function load() {
      listEl.innerHTML = '<div class="hh-loading"><div class="hh-spinner"></div>Loading candidates…</div>';
      try {
        const qs = new URLSearchParams({
          q: state.q,
          status: state.status,
          pipeline: state.pipeline,
          page: String(state.page),
          per_page: String(state.perPage),
        });
        const data = await api('/hr/api/hiring/candidates?' + qs.toString());
        const items = data.candidates || [];
        state.count = data.count || 0;
        state.pages = data.pages || 1;
        renderList(items);
        renderPagination();
      } catch (e) {
        listEl.innerHTML = '<div class="hh-empty">' + escapeHtml(e.message) + '</div>';
        pagEl.innerHTML = '';
      }
    }

    function renderList(items) {
      if (!items.length) {
        listEl.innerHTML =
          '<div class="hh-empty">' +
            '<p class="hh-empty-title">No candidates yet</p>' +
            '<p class="hh-empty-sub">Add a candidate with their details to start tracking onboarding documents.</p>' +
            '<button type="button" class="hh-btn hh-btn-primary" data-hh-add>' +
              '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>' +
              'Add Candidate' +
            '</button>' +
          '</div>';
        return;
      }
      listEl.innerHTML = items.map(function (c) {
        const pct = c.total ? Math.round((c.completed / c.total) * 100) : 0;
        const pipeKey = c.pipeline_status || 'interview_completed';
        const pipeLabel = c.pipeline_label || PIPELINE_LABELS[pipeKey] || pipeKey;
        return (
          '<a class="hh-row" href="/hr/hiring/candidates/' + c.id + '">' +
            '<div class="hh-avatar ' + avatarClass(c.full_name) + '">' + escapeHtml(c.initials || '?') + '</div>' +
            '<div class="hh-row-info">' +
              '<div class="hh-row-name">' + escapeHtml(c.full_name) + '</div>' +
              '<div class="hh-row-role">' + escapeHtml(c.role || '—') + '</div>' +
            '</div>' +
            '<div class="hh-row-progress">' +
              '<div class="hh-progress-label"><span>Documents</span><span>' + escapeHtml(c.progress_label) + '</span></div>' +
              '<div class="hh-progress-track"><div class="hh-progress-fill" style="width:' + pct + '%"></div></div>' +
            '</div>' +
            '<span class="hh-status pipeline ' + escapeHtml(pipeKey) + '">' +
              escapeHtml(pipeLabel) +
            '</span>' +
          '</a>'
        );
      }).join('');
    }

    function renderPagination() {
      if (state.count <= state.perPage) {
        pagEl.innerHTML = state.count
          ? '<span>Showing ' + state.count + ' candidate' + (state.count === 1 ? '' : 's') + '</span>'
          : '';
        return;
      }
      const start = (state.page - 1) * state.perPage + 1;
      const end = Math.min(state.page * state.perPage, state.count);
      let btns = '';
      btns += '<button type="button" class="hh-page-btn" data-page="prev" ' + (state.page <= 1 ? 'disabled' : '') + '>Previous</button>';
      for (let p = 1; p <= state.pages; p++) {
        btns += '<button type="button" class="hh-page-btn' + (p === state.page ? ' active' : '') + '" data-page="' + p + '">' + p + '</button>';
      }
      btns += '<button type="button" class="hh-page-btn" data-page="next" ' + (state.page >= state.pages ? 'disabled' : '') + '>Next</button>';
      pagEl.innerHTML =
        '<span>Showing ' + start + ' to ' + end + ' of ' + state.count + ' candidates</span>' +
        '<div class="hh-page-btns">' + btns + '</div>';
    }

    if (searchEl) {
      searchEl.addEventListener('input', function () {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function () {
          state.q = searchEl.value.trim();
          state.page = 1;
          load();
        }, 250);
      });
    }

    filterBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        filterBtns.forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        state.status = btn.getAttribute('data-status') || 'all';
        state.page = 1;
        load();
      });
    });

    if (pipelineFilter) {
      pipelineFilter.addEventListener('change', function () {
        state.pipeline = pipelineFilter.value || 'all';
        state.page = 1;
        load();
      });
    }

    pagEl.addEventListener('click', function (e) {
      const btn = e.target.closest('[data-page]');
      if (!btn || btn.disabled) return;
      const v = btn.getAttribute('data-page');
      if (v === 'prev') state.page = Math.max(1, state.page - 1);
      else if (v === 'next') state.page = Math.min(state.pages, state.page + 1);
      else state.page = parseInt(v, 10) || 1;
      load();
    });

    async function loadAssessments() {
      if (!interviewPick) return;
      interviewPick.innerHTML = '<option value="">Loading assessments…</option>';
      if (interviewApply) interviewApply.disabled = true;
      try {
        const data = await api('/hr/api/hiring/interview-assessments?limit=40');
        assessmentsCache = data.assessments || [];
        if (!assessmentsCache.length) {
          interviewPick.innerHTML = '<option value="">No interview assessments found</option>';
          return;
        }
        interviewPick.innerHTML =
          '<option value="">Select an interview assessment…</option>' +
          assessmentsCache.map(function (a, i) {
            const label = a.full_name + (a.role ? ' — ' + a.role : '') +
              (a.interview_date ? ' (' + a.interview_date + ')' : '');
            return '<option value="' + i + '">' + escapeHtml(label) + '</option>';
          }).join('');
      } catch (e) {
        interviewPick.innerHTML = '<option value="">Could not load assessments</option>';
      }
    }

    function applyAssessment() {
      if (!interviewPick || !form) return;
      const idx = parseInt(interviewPick.value, 10);
      if (Number.isNaN(idx) || !assessmentsCache[idx]) {
        toast('Select an interview assessment first', true);
        return;
      }
      const a = assessmentsCache[idx];
      const nameEl = form.querySelector('[name="full_name"]');
      const roleEl = form.querySelector('[name="role"]');
      if (nameEl) nameEl.value = a.full_name || '';
      if (roleEl) roleEl.value = a.role || '';
      toast('Filled from interview assessment');
    }

    function openModal() {
      if (!modal) return;
      modal.classList.add('open');
      loadAssessments();
      const first = modal.querySelector('input[name="full_name"]');
      if (first) first.focus();
    }

    function closeModal() {
      if (!modal) return;
      modal.classList.remove('open');
      if (form) form.reset();
      if (interviewPick) interviewPick.innerHTML = '<option value="">Select an interview assessment…</option>';
      if (interviewApply) interviewApply.disabled = true;
    }

    function bindAddTriggers() {
      document.querySelectorAll('#hhAddBtnToolbar, [data-hh-add]').forEach(function (btn) {
        if (btn._hhBound) return;
        btn._hhBound = true;
        btn.addEventListener('click', openModal);
      });
    }

    bindAddTriggers();
    // Empty-state button is re-rendered — delegate
    listEl.addEventListener('click', function (e) {
      const btn = e.target.closest('[data-hh-add]');
      if (btn) openModal();
    });

    if (interviewPick) {
      interviewPick.addEventListener('change', function () {
        if (interviewApply) interviewApply.disabled = interviewPick.value === '';
      });
    }
    if (interviewApply) interviewApply.addEventListener('click', applyAssessment);

    async function downloadExcel(url, fallbackName) {
      const res = await fetch(url, { headers: authHeaders() });
      if (!res.ok) {
        let msg = 'Download failed';
        try {
          const data = await res.json();
          msg = (data && (data.error || data.message)) || msg;
        } catch (_) {}
        throw new Error(msg);
      }
      const blob = await res.blob();
      const cd = res.headers.get('Content-Disposition') || '';
      let filename = fallbackName;
      const m = /filename="?([^";]+)"?/i.exec(cd);
      if (m) filename = m[1];
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    }

    function showImportResult(result, message) {
      const el = document.getElementById('hhImportResult');
      if (!el) return;
      const errs = (result && result.errors) || [];
      let html =
        '<div class="hh-import-result-inner">' +
          '<strong>' + escapeHtml(message || 'Import complete') + '</strong>';
      if (errs.length) {
        html += '<ul class="hh-import-errors">';
        errs.slice(0, 8).forEach(function (e) {
          html += '<li>Row ' + escapeHtml(String(e.row)) + ': ' + escapeHtml(e.error || '') + '</li>';
        });
        if (errs.length > 8) {
          html += '<li>…and ' + (errs.length - 8) + ' more</li>';
        }
        html += '</ul>';
      }
      html +=
        '<button type="button" class="hh-btn hh-btn-ghost hh-btn-sm" data-hh-import-dismiss>Dismiss</button>' +
        '</div>';
      el.innerHTML = html;
      el.hidden = false;
      el.classList.toggle('has-errors', errs.length > 0);
    }

    const templateBtn = document.getElementById('hhExcelTemplate');
    const exportBtn = document.getElementById('hhExcelExport');
    const importBtn = document.getElementById('hhExcelImport');
    const excelFile = document.getElementById('hhExcelFile');
    const importResultEl = document.getElementById('hhImportResult');

    if (templateBtn) {
      templateBtn.addEventListener('click', async function () {
        templateBtn.disabled = true;
        try {
          await downloadExcel('/hr/api/hiring/import-template', 'Hiring_Document_Tracker_Template.xlsx');
          toast('Template downloaded');
        } catch (err) {
          toast(err.message, true);
        } finally {
          templateBtn.disabled = false;
        }
      });
    }

    if (exportBtn) {
      exportBtn.addEventListener('click', async function () {
        exportBtn.disabled = true;
        try {
          await downloadExcel('/hr/api/hiring/export', 'Hiring_Document_Tracker_Export.xlsx');
          toast('Export downloaded');
        } catch (err) {
          toast(err.message, true);
        } finally {
          exportBtn.disabled = false;
        }
      });
    }

    if (importBtn && excelFile) {
      importBtn.addEventListener('click', function () {
        excelFile.value = '';
        excelFile.click();
      });
      excelFile.addEventListener('change', async function () {
        const file = excelFile.files && excelFile.files[0];
        if (!file) return;
        importBtn.disabled = true;
        toast('Importing…');
        try {
          const fd = new FormData();
          fd.append('file', file);
          const res = await fetch('/hr/api/hiring/import', {
            method: 'POST',
            headers: authHeaders(),
            body: fd,
          });
          const data = await res.json().catch(function () { return null; });
          if (!res.ok || (data && data.success === false)) {
            throw new Error((data && (data.error || data.message)) || 'Import failed');
          }
          const result = {
            created: data.created || 0,
            updated: data.updated || 0,
            skipped: data.skipped || 0,
            errors: data.errors || [],
            processed: data.processed || 0,
          };
          const msg = data.message || 'Import complete';
          toast(msg);
          showImportResult(result, msg);
          state.page = 1;
          await load();
        } catch (err) {
          toast(err.message, true);
        } finally {
          importBtn.disabled = false;
          excelFile.value = '';
        }
      });
    }

    if (importResultEl) {
      importResultEl.addEventListener('click', function (e) {
        if (e.target.closest('[data-hh-import-dismiss]')) {
          importResultEl.hidden = true;
          importResultEl.innerHTML = '';
        }
      });
    }

    if (modal) {
      modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
      });
      const cancel = modal.querySelector('[data-close]');
      if (cancel) cancel.addEventListener('click', closeModal);
    }

    if (form) {
      form.addEventListener('submit', async function (e) {
        e.preventDefault();
        const fd = new FormData(form);
        const payload = {
          full_name: (fd.get('full_name') || '').toString().trim(),
          role: (fd.get('role') || '').toString().trim(),
          department: (fd.get('department') || '').toString().trim(),
          phone: (fd.get('phone') || '').toString().trim(),
          email: (fd.get('email') || '').toString().trim(),
          replacement_name: (fd.get('replacement_name') || '').toString().trim(),
          replacement_employee_id: (fd.get('replacement_employee_id') || '').toString().trim(),
          comments: (fd.get('comments') || '').toString().trim(),
        };
        if (!payload.full_name) {
          toast('Full name is required', true);
          return;
        }
        if (!payload.role) {
          toast('Role / position is required', true);
          return;
        }
        const submitBtn = form.querySelector('[type="submit"]');
        if (submitBtn) submitBtn.disabled = true;
        try {
          const data = await api('/hr/api/hiring/candidates', { method: 'POST', json: payload });
          toast('Candidate added');
          closeModal();
          if (data.candidate && data.candidate.id) {
            window.location.href = '/hr/hiring/candidates/' + data.candidate.id;
            return;
          }
          state.page = 1;
          load();
        } catch (err) {
          toast(err.message, true);
        } finally {
          if (submitBtn) submitBtn.disabled = false;
        }
      });
    }

    load();
  }

  /* ── Detail page ───────────────────────────────────────── */
  function initDetail() {
    const root = document.getElementById('hhDetailRoot');
    if (!root) return;

    const candidateId = parseInt(root.getAttribute('data-candidate-id'), 10);
    if (!candidateId) return;

    const phase1El = document.getElementById('hhChecklistPhase1');
    const phase2El = document.getElementById('hhChecklistPhase2');
    const phase2Section = document.getElementById('hhPhase2Section');
    const phase2Sub = document.getElementById('hhPhase2Sub');
    const headerEl = document.getElementById('hhDetailHeader');
    const sectionsEl = document.getElementById('hhDocSections');
    let fileInput = document.getElementById('hhFileInput');
    let candidateState = null;

    function applyCandidate(c, extras) {
      if (!c) return null;
      const next = Object.assign({}, c, extras || {});
      if (!next.pipeline_status) {
        next.pipeline_status = (candidateState && candidateState.pipeline_status) || 'interview_completed';
      }
      if (!next.pipeline_label) {
        next.pipeline_label = PIPELINE_LABELS[next.pipeline_status] || next.pipeline_status;
      }
      if (typeof next.visa_docs_unlocked !== 'boolean') {
        next.visa_docs_unlocked = PIPELINE_ORDER.indexOf(next.pipeline_status) >= PIPELINE_ORDER.indexOf('visa_process_started');
      }
      candidateState = next;
      return next;
    }

    async function load() {
      try {
        const data = await api('/hr/api/hiring/candidates/' + candidateId);
        render(applyCandidate(data.candidate));
      } catch (e) {
        if (phase1El) {
          phase1El.innerHTML = '<div class="hh-empty">' + escapeHtml(e.message) + '</div>';
        }
      }
    }

    function renderDocRow(d) {
      const locked = !!d.upload_locked;
      const accept = (d.allowed_extensions || []).map(function (x) { return '.' + x; }).join(',');
      let statusHtml = '';
      let toolsHtml = '';

      if (locked) {
        statusHtml = '<span class="hh-doc-badge is-locked">Locked</span>';
      } else {
        if (d.is_complete) {
          statusHtml = '<span class="hh-doc-badge is-done">Complete</span>';
        } else if (d.doc_type === 'pcc' && d.has_file && d.status === 'uploaded') {
          statusHtml = '<span class="hh-doc-badge is-wait">Awaiting attest</span>';
        } else if (d.has_file) {
          statusHtml = '<span class="hh-doc-badge is-done">Uploaded</span>';
        } else {
          statusHtml = '<span class="hh-doc-badge is-idle">Needed</span>';
        }

        if (d.has_file && d.id) {
          toolsHtml += '<button type="button" class="hh-doc-tool" data-view="' + d.id + '" data-filename="' + escapeHtml(d.filename || 'document') + '">View</button>';
        }
        if (d.doc_type === 'pcc' && d.has_file && d.status === 'uploaded') {
          toolsHtml += '<button type="button" class="hh-doc-tool is-primary" data-attest="pcc">Mark attested</button>';
        }
        toolsHtml +=
          '<button type="button" class="hh-doc-tool' + (d.has_file ? '' : ' is-primary') + '" data-upload="' + escapeHtml(d.doc_type) + '" data-accept="' + escapeHtml(accept) + '">' +
            (d.has_file ? 'Re-upload' : 'Upload') +
          '</button>';
        if (d.has_file && d.id) {
          toolsHtml += '<button type="button" class="hh-doc-tool is-danger" data-clear="' + d.id + '">Clear</button>';
        }
      }

      let sub = '';
      if (locked) {
        sub = 'Available after Visa process started';
      } else if (d.filename) {
        sub = escapeHtml(d.filename);
        if (d.uploaded_at) sub += ' · ' + escapeHtml(String(d.uploaded_at).slice(0, 10));
      } else {
        const exts = (d.allowed_extensions || []).join(', ').toUpperCase();
        sub = 'Accepted: ' + escapeHtml(exts || '—');
      }

      return (
        '<div class="hh-doc-row' + (locked ? ' is-locked' : '') + '" data-doc-type="' + escapeHtml(d.doc_type) + '">' +
          '<div class="hh-doc-icon">' +
            '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/></svg>' +
          '</div>' +
          '<div class="hh-doc-info">' +
            '<div class="hh-doc-label">' + escapeHtml(d.label || d.doc_type) + '</div>' +
            '<div class="hh-doc-sub">' + sub + '</div>' +
          '</div>' +
          '<div class="hh-doc-actions">' +
            '<div class="hh-doc-actions-top">' + statusHtml + '</div>' +
            (toolsHtml ? '<div class="hh-doc-tools">' + toolsHtml + '</div>' : '') +
          '</div>' +
        '</div>'
      );
    }

    async function setPipelineStatus(value) {
      const select = document.getElementById('hhPipelineSelect');
      const body = document.getElementById('hhPipelineBody');
      if (!value || !PIPELINE_LABELS[value]) return;
      if (select) select.disabled = true;
      if (body) body.classList.add('is-busy');

      // Optimistic update so bar + fields move immediately with the chosen stage
      const optimistic = applyCandidate(candidateState || {}, {
        pipeline_status: value,
        pipeline_label: PIPELINE_LABELS[value],
        visa_docs_unlocked: PIPELINE_ORDER.indexOf(value) >= PIPELINE_ORDER.indexOf('visa_process_started'),
        updated_at: new Date().toISOString(),
      });
      render(optimistic);

      try {
        const data = await api('/hr/api/hiring/candidates/' + candidateId, {
          method: 'PATCH',
          json: { pipeline_status: value },
        });
        toast('Status updated');
        render(applyCandidate(data.candidate || candidateState, {
          pipeline_status: value,
          pipeline_label: PIPELINE_LABELS[value],
          visa_docs_unlocked: PIPELINE_ORDER.indexOf(value) >= PIPELINE_ORDER.indexOf('visa_process_started'),
        }));
      } catch (err) {
        toast(err.message, true);
        try {
          await load();
        } catch (_) {
          if (select) select.disabled = false;
          if (body) body.classList.remove('is-busy');
        }
      }
    }

    function bindPipelineBody(body) {
      if (!body || body._hhBound) return;
      body._hhBound = true;
      body.addEventListener('click', function (e) {
        const btn = e.target.closest('[data-pipeline]');
        if (!btn || btn.disabled) return;
        const value = btn.getAttribute('data-pipeline');
        const select = document.getElementById('hhPipelineSelect');
        if (!value || (select && value === select.value)) return;
        setPipelineStatus(value);
      });
      body.addEventListener('change', function (e) {
        const select = e.target.closest('#hhPipelineSelectInline');
        if (!select) return;
        setPipelineStatus(select.value);
      });
    }

    function renderPipeline(c) {
      const body = document.getElementById('hhPipelineBody');
      const select = document.getElementById('hhPipelineSelect');
      if (!body) return;

      const pipeKey = c.pipeline_status || 'interview_completed';
      const pipeLabel = c.pipeline_label || PIPELINE_LABELS[pipeKey] || pipeKey;
      const meta = PIPELINE_META[pipeKey] || PIPELINE_META.interview_completed;
      const keys = PIPELINE_ORDER;
      const currentIdx = Math.max(0, keys.indexOf(pipeKey));
      const nextKey = keys[currentIdx + 1] || null;
      const nextLabel = nextKey ? (PIPELINE_LABELS[nextKey] || nextKey) : null;
      const visaUnlocked = !!c.visa_docs_unlocked;

      const overallDone = c.completed || 0;
      const overallTotal = c.total || 9;

      const daysInStage = (function () {
        const raw = c.updated_at || c.created_at;
        if (!raw) return null;
        const t = Date.parse(raw);
        if (Number.isNaN(t)) return null;
        return Math.max(0, Math.floor((Date.now() - t) / 86400000));
      })();

      const selectOptions = keys.map(function (key) {
        return '<option value="' + escapeHtml(key) + '"' +
          (key === pipeKey ? ' selected' : '') + '>' +
          escapeHtml(PIPELINE_LABELS[key]) + '</option>';
      }).join('');

      const stepsHtml = keys.map(function (key, i) {
        const label = PIPELINE_LABELS[key] || key;
        const short = PIPELINE_SHORT[key] || label;
        const current = key === pipeKey;
        const done = currentIdx > i;
        return (
          '<li class="hh-pipe-step' + (current ? ' is-current' : '') + (done ? ' is-done' : '') + '">' +
            '<button type="button" class="hh-pipe-btn" data-pipeline="' + escapeHtml(key) + '"' +
              ' title="' + escapeHtml(label) + '"' +
              ' aria-current="' + (current ? 'step' : 'false') + '"' +
              ' aria-label="Set stage: ' + escapeHtml(label) + '">' +
              '<span class="hh-pipe-dot" aria-hidden="true">' + (done ? '✓' : String(i + 1)) + '</span>' +
              '<span class="hh-pipe-label">' + escapeHtml(short) + '</span>' +
            '</button>' +
          '</li>'
        );
      }).join('');

      body.innerHTML =
        '<div class="hh-pipeline-top">' +
          '<div class="hh-pipeline-stage">' +
            '<div class="hh-pipeline-kicker">Stage ' + (currentIdx + 1) + ' of ' + keys.length + '</div>' +
            '<h2 class="hh-pipeline-title">' + escapeHtml(pipeLabel) + '</h2>' +
            '<p class="hh-pipeline-focus">' + escapeHtml(meta.focus) + '</p>' +
          '</div>' +
          '<div class="hh-pipeline-aside">' +
            renderCommentsBlock(c) +
            '<div class="hh-pipeline-controls">' +
              '<label class="hh-pipeline-select-wrap">' +
                '<span class="hh-pipeline-select-label">Jump to</span>' +
                '<select id="hhPipelineSelectInline" class="hh-select hh-pipeline-select" aria-label="Update pipeline status">' +
                  selectOptions +
                '</select>' +
              '</label>' +
              (nextKey
                ? '<button type="button" class="hh-btn hh-btn-primary hh-btn-sm" data-pipeline="' + escapeHtml(nextKey) + '">' +
                    'Advance to ' + escapeHtml(PIPELINE_SHORT[nextKey] || nextLabel) +
                  '</button>'
                : '<span class="hh-pipeline-final">Final stage</span>') +
            '</div>' +
          '</div>' +
        '</div>' +

        '<div class="hh-pipeline-segments" role="img" aria-label="Stage ' + (currentIdx + 1) + ' of ' + keys.length + '">' +
          keys.map(function (key, i) {
            const cls = i < currentIdx ? 'is-done' : (i === currentIdx ? 'is-current' : '');
            return '<span class="hh-pipeline-seg ' + cls + '" title="' + escapeHtml(PIPELINE_LABELS[key] || key) + '"></span>';
          }).join('') +
          '<span class="hh-pipeline-seg-caption">Stage ' + (currentIdx + 1) + ' / ' + keys.length + '</span>' +
        '</div>' +

        '<ol class="hh-pipeline-stepper">' + stepsHtml + '</ol>' +

        '<div class="hh-pipe-stats hh-pipe-stats-row">' +
          '<div class="hh-pipe-stat">' +
            '<span class="hh-pipe-stat-val">' + overallDone + '/' + overallTotal + '</span>' +
            '<span class="hh-pipe-stat-lbl">Docs done</span>' +
          '</div>' +
          '<div class="hh-pipe-stat">' +
            '<span class="hh-pipe-stat-val">' + (currentIdx + 1) + '/' + keys.length + '</span>' +
            '<span class="hh-pipe-stat-lbl">Stage</span>' +
          '</div>' +
          '<div class="hh-pipe-stat">' +
            '<span class="hh-pipe-stat-val">' + (daysInStage == null ? '—' : (daysInStage === 0 ? 'Today' : daysInStage + 'd')) + '</span>' +
            '<span class="hh-pipe-stat-lbl">In stage</span>' +
          '</div>' +
          '<div class="hh-pipe-stat ' + (visaUnlocked ? 'is-open' : 'is-locked') + '">' +
            '<span class="hh-pipe-stat-val">' + (visaUnlocked ? 'Open' : 'Locked') + '</span>' +
            '<span class="hh-pipe-stat-lbl">Visa pack</span>' +
          '</div>' +
        '</div>';

      body.classList.remove('is-busy');
      bindPipelineBody(body);
      bindCommentsEditors();

      if (select) {
        select.value = pipeKey;
        select.disabled = false;
      }
    }

    function renderReplacementBlock(c) {
      const name = (c.replacement_name || '').trim();
      const empId = (c.replacement_employee_id || '').trim();
      const has = !!(name || empId);
      return (
        '<div class="hh-replacement" id="hhReplacementBlock" data-has-replacement="' + (has ? '1' : '0') + '">' +
          '<div class="hh-replacement-head">' +
            '<span class="hh-replacement-kicker">Replacing</span>' +
            '<button type="button" class="hh-replacement-edit" id="hhReplacementEdit">' +
              (has ? 'Edit' : 'Add') +
            '</button>' +
          '</div>' +
          '<input type="text" class="hh-replacement-name-input" id="hhReplacementName" ' +
            'name="replacement_name" maxlength="200" autocomplete="name" ' +
            'placeholder="Name" aria-label="Replacement name" value="' + escapeHtml(name) + '" readonly>' +
          '<div class="hh-replacement-id-row">' +
            '<span class="hh-replacement-id-prefix" aria-hidden="true">ID ·</span>' +
            '<input type="text" class="hh-replacement-id-input" id="hhReplacementId" ' +
              'name="replacement_employee_id" maxlength="80" autocomplete="off" ' +
              'placeholder="Not set" aria-label="Replacement employee ID" value="' + escapeHtml(empId) + '" readonly>' +
          '</div>' +
        '</div>'
      );
    }

    function renderCommentsBlock(c) {
      const comments = (c.comments || '').trim();
      return (
        '<div class="hh-comments' + (comments ? ' has-comment' : '') + '" id="hhCommentsBlock">' +
          '<textarea class="hh-comments-input" id="hhCommentsInput" rows="1" maxlength="4000" ' +
            'placeholder="Add a note…" aria-label="Comments">' +
            escapeHtml(comments) +
          '</textarea>' +
        '</div>'
      );
    }

    function bindReplacementEditors() {
      const block = document.getElementById('hhReplacementBlock');
      const editBtn = document.getElementById('hhReplacementEdit');
      const nameInput = document.getElementById('hhReplacementName');
      const idInput = document.getElementById('hhReplacementId');
      if (!block || !editBtn || !nameInput || !idInput) return;

      let lastSaved = {
        replacement_name: (nameInput.value || '').trim(),
        replacement_employee_id: (idInput.value || '').trim(),
      };
      let saving = false;
      let editing = false;

      function syncEmptyState() {
        const has = !!(nameInput.value.trim() || idInput.value.trim());
        block.dataset.hasReplacement = has ? '1' : '0';
        editBtn.textContent = editing ? 'Done' : (has ? 'Edit' : 'Add');
      }

      function setEditing(on, focusEl) {
        editing = !!on;
        block.classList.toggle('is-editing', editing);
        nameInput.readOnly = !editing;
        idInput.readOnly = !editing;
        syncEmptyState();
        if (editing) {
          const target = focusEl || nameInput;
          target.focus();
          const len = target.value.length;
          try { target.setSelectionRange(len, len); } catch (e) { /* ignore */ }
        }
      }

      async function saveIfChanged() {
        const payload = {
          replacement_name: (nameInput.value || '').trim(),
          replacement_employee_id: (idInput.value || '').trim(),
        };
        if (
          payload.replacement_name === lastSaved.replacement_name &&
          payload.replacement_employee_id === lastSaved.replacement_employee_id
        ) {
          nameInput.value = lastSaved.replacement_name;
          idInput.value = lastSaved.replacement_employee_id;
          syncEmptyState();
          return;
        }
        if (saving) return;
        saving = true;
        nameInput.disabled = true;
        idInput.disabled = true;
        try {
          const data = await api('/hr/api/hiring/candidates/' + candidateId, {
            method: 'PATCH',
            json: payload,
          });
          lastSaved = payload;
          applyCandidate(data.candidate, payload);
          syncEmptyState();
          toast('Replacement details saved');
        } catch (err) {
          nameInput.value = lastSaved.replacement_name;
          idInput.value = lastSaved.replacement_employee_id;
          syncEmptyState();
          toast(err.message, true);
        } finally {
          saving = false;
          nameInput.disabled = false;
          idInput.disabled = false;
        }
      }

      editBtn.addEventListener('click', function () {
        if (editing) {
          setEditing(false);
          saveIfChanged();
          return;
        }
        setEditing(true, nameInput);
      });

      function beginEdit(el) {
        if (!editing) setEditing(true, el);
      }

      nameInput.addEventListener('click', function () { beginEdit(nameInput); });
      idInput.addEventListener('click', function () { beginEdit(idInput); });
      nameInput.addEventListener('focus', function () { beginEdit(nameInput); });
      idInput.addEventListener('focus', function () { beginEdit(idInput); });

      nameInput.addEventListener('input', syncEmptyState);
      idInput.addEventListener('input', syncEmptyState);

      nameInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          idInput.focus();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          nameInput.value = lastSaved.replacement_name;
          idInput.value = lastSaved.replacement_employee_id;
          setEditing(false);
        }
      });

      idInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          setEditing(false);
          saveIfChanged();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          nameInput.value = lastSaved.replacement_name;
          idInput.value = lastSaved.replacement_employee_id;
          setEditing(false);
        }
      });

      block.addEventListener('focusout', function (e) {
        if (!editing) return;
        if (block.contains(e.relatedTarget)) return;
        setEditing(false);
        saveIfChanged();
      });
    }

    function bindCommentsEditors() {
      const block = document.getElementById('hhCommentsBlock');
      const input = document.getElementById('hhCommentsInput');
      if (!block || !input) return;

      let lastSaved = (input.value || '').trim();
      let saving = false;

      function syncHasComment(value) {
        block.classList.toggle('has-comment', !!value);
      }

      function fitSize() {
        const styles = window.getComputedStyle(input);
        const lineHeight = parseFloat(styles.lineHeight) || 22;
        const padX = (parseFloat(styles.paddingLeft) || 0) + (parseFloat(styles.paddingRight) || 0);
        const padY = (parseFloat(styles.paddingTop) || 0) + (parseFloat(styles.paddingBottom) || 0);
        const maxW = Math.min(420, Math.max(160, (block.parentElement && block.parentElement.clientWidth) || 420));
        const minW = 112;

        const mirror = document.createElement('span');
        mirror.setAttribute('aria-hidden', 'true');
        mirror.textContent = (input.value || input.placeholder || 'Add a note…') + ' ';
        mirror.style.cssText = [
          'position:absolute',
          'visibility:hidden',
          'white-space:pre',
          'font:' + styles.font,
          'letter-spacing:' + styles.letterSpacing,
          'padding:0',
          'border:0',
          'left:-9999px',
          'top:0',
        ].join(';');
        document.body.appendChild(mirror);
        const textW = Math.ceil(mirror.getBoundingClientRect().width) + padX + 4;
        document.body.removeChild(mirror);

        const nextW = Math.max(minW, Math.min(maxW, textW));
        input.style.width = nextW + 'px';

        input.style.height = 'auto';
        const maxH = (lineHeight * 2) + padY;
        const nextH = Math.min(Math.max(lineHeight + padY, input.scrollHeight), maxH);
        input.style.height = nextH + 'px';
        input.style.overflowY = input.scrollHeight > maxH + 1 ? 'auto' : 'hidden';
      }

      async function saveIfChanged() {
        const value = (input.value || '').trim();
        if (value === lastSaved || saving) {
          syncHasComment(lastSaved);
          input.value = lastSaved;
          fitSize();
          return;
        }
        saving = true;
        input.disabled = true;
        try {
          const data = await api('/hr/api/hiring/candidates/' + candidateId, {
            method: 'PATCH',
            json: { comments: value },
          });
          lastSaved = value;
          syncHasComment(value);
          applyCandidate(data.candidate, { comments: value });
          toast(value ? 'Comment saved' : 'Comment cleared');
        } catch (err) {
          input.value = lastSaved;
          syncHasComment(lastSaved);
          toast(err.message, true);
        } finally {
          saving = false;
          input.disabled = false;
          fitSize();
        }
      }

      input.addEventListener('blur', function () {
        saveIfChanged();
      });

      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          input.blur();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          input.value = lastSaved;
          syncHasComment(lastSaved);
          fitSize();
          input.blur();
        }
      });

      input.addEventListener('input', function () {
        syncHasComment((input.value || '').trim());
        fitSize();
      });

      fitSize();
    }

    function render(c) {
      if (!c) return;
      const contacts = [];
      if (c.email) contacts.push(escapeHtml(c.email));
      if (c.phone) contacts.push(escapeHtml(c.phone));
      const pipeKey = c.pipeline_status || 'interview_completed';
      const pipeLabel = c.pipeline_label || PIPELINE_LABELS[pipeKey] || pipeKey;
      headerEl.innerHTML =
        '<div class="hh-profile-main">' +
          '<div class="hh-avatar">' + escapeHtml(c.initials || '?') + '</div>' +
          '<div class="hh-detail-meta">' +
            '<h1>' + escapeHtml(c.full_name) + '</h1>' +
            '<p>' + escapeHtml([c.role, c.department].filter(Boolean).join(' · ') || '—') + '</p>' +
            (contacts.length ? '<div class="hh-detail-contacts">' + contacts.join('<span aria-hidden="true"> · </span>') + '</div>' : '') +
          '</div>' +
        '</div>' +
        renderReplacementBlock(c) +
        '<div class="hh-profile-aside">' +
          '<span class="hh-status pipeline ' + escapeHtml(pipeKey) + '">' +
            escapeHtml(pipeLabel) +
          '</span>' +
          '<button type="button" class="hh-btn hh-btn-sm hh-btn-on-brand-danger" id="hhDeleteCandidate">Delete</button>' +
        '</div>';

      const deleteBtn = document.getElementById('hhDeleteCandidate');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', onDeleteCandidate);
      }
      bindReplacementEditors();

      renderPipeline(c);

      const visaUnlocked = !!c.visa_docs_unlocked;
      const allDocs = c.documents || [];
      const phase1 = (c.phase1_documents && c.phase1_documents.length)
        ? c.phase1_documents
        : allDocs.filter(function (d) { return (d.phase || 1) === 1; });
      let phase2 = (c.phase2_documents && c.phase2_documents.length)
        ? c.phase2_documents
        : allDocs.filter(function (d) { return d.phase === 2 || ['offer_letter', 'insurance', 'e_visa', 'contract'].indexOf(d.doc_type) !== -1; });
      if (!phase2.length) {
        phase2 = PHASE2_FALLBACK.map(function (d) {
          const copy = Object.assign({}, d);
          if (VISA_GATED[copy.doc_type]) {
            copy.upload_locked = !visaUnlocked;
          }
          return copy;
        });
      } else {
        phase2 = phase2.map(function (d) {
          const copy = Object.assign({}, d);
          if (VISA_GATED[copy.doc_type] && typeof copy.upload_locked !== 'boolean') {
            copy.upload_locked = !visaUnlocked;
          }
          return copy;
        });
      }

      if (phase1El) {
        phase1El.innerHTML = phase1.map(function (d) { return renderDocRow(d); }).join('');
      }

      if (phase2Section) {
        phase2Section.classList.remove('is-locked');
      }
      if (phase2Sub) {
        phase2Sub.textContent = visaUnlocked
          ? 'Upload the department-signed offer letter, insurance paper, e-visa, and employment contract.'
          : 'Offer letter can be uploaded now. Insurance, e-visa, and contract unlock after Visa process started.';
      }
      if (phase2El) {
        phase2El.innerHTML = phase2.map(function (d) { return renderDocRow(d); }).join('');
      }
    }

    function ensureFileInput() {
      if (!fileInput) {
        fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.id = 'hhFileInput';
        fileInput.className = 'hh-upload-zone';
        fileInput.setAttribute('capture', 'environment');
        document.body.appendChild(fileInput);
      }
      return fileInput;
    }

    let pendingDocType = null;

    async function handleDocClick(e) {
      const uploadBtn = e.target.closest('[data-upload]');
      if (uploadBtn) {
        pendingDocType = uploadBtn.getAttribute('data-upload');
        const accept = uploadBtn.getAttribute('data-accept') || '';
        const input = ensureFileInput();
        input.accept = accept;
        input.value = '';
        input.click();
        return;
      }

      const viewBtn = e.target.closest('[data-view]');
      if (viewBtn) {
        const id = viewBtn.getAttribute('data-view');
        const filename = viewBtn.getAttribute('data-filename') || 'document';
        viewBtn.disabled = true;
        try {
          const res = await fetch('/hr/api/hiring/documents/' + id + '/file', {
            headers: { Authorization: 'Bearer ' + token() },
          });
          if (!res.ok) throw new Error('Could not open file');
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = filename;
          a.target = '_blank';
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
        } catch (err) {
          toast(err.message, true);
        } finally {
          viewBtn.disabled = false;
        }
        return;
      }

      const attestBtn = e.target.closest('[data-attest]');
      if (attestBtn) {
        attestBtn.disabled = true;
        try {
          await api('/hr/api/hiring/candidates/' + candidateId + '/documents/pcc/attest', { method: 'POST', json: {} });
          toast('PCC marked attested');
          await load();
        } catch (err) {
          toast(err.message, true);
        } finally {
          attestBtn.disabled = false;
        }
        return;
      }

      const clearBtn = e.target.closest('[data-clear]');
      if (clearBtn) {
        const id = clearBtn.getAttribute('data-clear');
        const ok = await confirmDialog({
          title: 'Clear document',
          message: 'Clear this document? The uploaded file will be removed.',
          confirmLabel: 'Clear',
          danger: true,
        });
        if (!ok) return;
        clearBtn.disabled = true;
        try {
          await api('/hr/api/hiring/documents/' + id, { method: 'DELETE' });
          toast('Document cleared');
          await load();
        } catch (err) {
          toast(err.message, true);
        } finally {
          clearBtn.disabled = false;
        }
      }
    }

    function bindChecklistDnD(el) {
      if (!el) return;
      el.addEventListener('click', handleDocClick);
      el.addEventListener('dragover', function (e) {
        const row = e.target.closest('.hh-doc-row');
        if (!row || row.classList.contains('is-locked')) return;
        e.preventDefault();
        row.style.background = 'rgba(18, 84, 53, 0.06)';
      });
      el.addEventListener('dragleave', function (e) {
        const row = e.target.closest('.hh-doc-row');
        if (!row || row.classList.contains('is-locked')) return;
        row.style.background = '';
      });
      el.addEventListener('drop', async function (e) {
        const row = e.target.closest('.hh-doc-row');
        if (!row || row.classList.contains('is-locked')) return;
        e.preventDefault();
        row.style.background = '';
        const docType = row.getAttribute('data-doc-type');
        const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (file && docType) {
          await uploadFile(docType, file);
        }
      });
    }

    bindChecklistDnD(phase1El);
    bindChecklistDnD(phase2El);
    if (sectionsEl && !phase1El) {
      sectionsEl.addEventListener('click', handleDocClick);
    }

    ensureFileInput().addEventListener('change', async function () {
      const file = fileInput.files && fileInput.files[0];
      if (!file || !pendingDocType) return;
      await uploadFile(pendingDocType, file);
      pendingDocType = null;
      fileInput.value = '';
    });

    async function uploadFile(docType, file) {
      const fd = new FormData();
      fd.append('file', file);
      try {
        toast('Uploading…');
        const res = await fetch('/hr/api/hiring/candidates/' + candidateId + '/documents/' + encodeURIComponent(docType), {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + token() },
          body: fd,
        });
        const data = await res.json().catch(function () { return null; });
        if (!res.ok || (data && data.success === false)) {
          throw new Error((data && data.error) || 'Upload failed');
        }
        toast('Document uploaded');
        if (data.candidate) render(applyCandidate(data.candidate));
        else await load();
      } catch (err) {
        toast(err.message, true);
      }
    }

    async function onDeleteCandidate() {
      const ok = await confirmDialog({
        title: 'Delete candidate',
        message: 'Delete this candidate and all uploaded documents? This cannot be undone.',
        confirmLabel: 'Delete',
        danger: true,
      });
      if (!ok) return;
      const deleteBtn = document.getElementById('hhDeleteCandidate');
      if (deleteBtn) deleteBtn.disabled = true;
      try {
        await api('/hr/api/hiring/candidates/' + candidateId, { method: 'DELETE' });
        toast('Candidate deleted');
        window.location.href = '/hr/hiring';
      } catch (err) {
        toast(err.message, true);
        if (deleteBtn) deleteBtn.disabled = false;
      }
    }

    const initialDelete = document.getElementById('hhDeleteCandidate');
    if (initialDelete) initialDelete.addEventListener('click', onDeleteCandidate);

    load();
  }

  document.addEventListener('DOMContentLoaded', function () {
    initList();
    initDetail();
  });
})();
