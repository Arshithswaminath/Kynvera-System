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
    preparing_offer_letter: 'Preparing offer letter',
    offer_letter_prepared: 'Offer letter prepared',
    offer_letter_signed: 'Offer letter signed',
    md_signed_offer_received: 'Signed offer letter from MD received',
    gathering_documents_for_visa: 'Gathering documents for visa process',
    visa_process_started: 'Visa process started',
    candidate_employee: 'Candidate employed',
    on_hold: 'On hold',
  };

  // Linear stages only — on_hold is a process-wide pause, not a step.
  const PIPELINE_STEPS = [
    'interview_completed',
    'gathering_documents',
    'preparing_offer_letter',
    'offer_letter_prepared',
    'offer_letter_signed',
    'md_signed_offer_received',
    'gathering_documents_for_visa',
    'visa_process_started',
    'candidate_employee',
  ];

  const PIPELINE_SHORT = {
    interview_completed: 'Interview',
    gathering_documents: 'Documents',
    preparing_offer_letter: 'Prep offer',
    offer_letter_prepared: 'Offer ready',
    offer_letter_signed: 'Offer signed',
    md_signed_offer_received: 'MD signed',
    gathering_documents_for_visa: 'Visa docs',
    visa_process_started: 'Visa',
    candidate_employee: 'Employee',
    on_hold: 'On hold',
  };

  const PIPELINE_META = {
    interview_completed: {
      focus: 'Interview done — start collecting identity papers',
      next: 'Move to Gathering documents when HR begins the checklist',
      hint: 'Passport, Emirates ID, photo, PCC, and education certificate come next.',
    },
    gathering_documents: {
      focus: 'Collecting identity & clearance documents',
      next: 'Advance to Preparing offer letter when docs are in hand',
      hint: 'Track passport, Emirates ID, photograph, PCC (attested), and education certificate.',
    },
    preparing_offer_letter: {
      focus: 'Offer letter is being prepared',
      next: 'Advance when the department offer letter is ready',
      hint: 'Draft and route the offer letter for department signature.',
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
      next: 'Gather documents needed for the visa process',
      hint: 'Collect visa paperwork next. Insurance, e-visa, and contract stay locked until Visa process started.',
    },
    gathering_documents_for_visa: {
      focus: 'Collecting documents for the visa process',
      next: 'Advance to Visa process started when papers are ready',
      hint: 'Visa pack (insurance, e-visa, contract) stays locked until you mark Visa process started.',
    },
    visa_process_started: {
      focus: 'Visa process open — upload remaining pack',
      next: 'Advance to Candidate employed when the file is ready to close',
      hint: 'Insurance, e-visa, and contract uploads are unlocked at this stage.',
    },
    on_hold: {
      focus: 'Whole process paused — not a hiring stage',
      next: 'Jump to a stage to resume the process',
      hint: 'On hold freezes progress at any point. Resume by choosing a stage.',
    },
    candidate_employee: {
      focus: 'File closed — candidate is now an employee',
      next: 'Hiring file is closed',
      hint: 'Final stage. The hiring file is closed; reopen only if something needs correction.',
    },
  };

  function visaDocsUnlockedForStatus(status) {
    if (!status || status === 'on_hold') return false;
    const visaIdx = PIPELINE_STEPS.indexOf('visa_process_started');
    const idx = PIPELINE_STEPS.indexOf(status);
    return visaIdx >= 0 && idx >= visaIdx;
  }

  function nextPipelineStatus(current) {
    const idx = PIPELINE_STEPS.indexOf(current);
    if (idx < 0) return PIPELINE_STEPS[0] || null;
    if (idx + 1 < PIPELINE_STEPS.length) return PIPELINE_STEPS[idx + 1];
    return null;
  }

  const VISA_GATED = { insurance: true, e_visa: true, contract: true };
  const IDENTITY_DOC_TYPES = ['passport', 'emirates_id', 'photograph', 'pcc', 'education_certificate'];
  const OFFER_DOC_TYPES = ['offer_letter'];
  const VISA_DOC_TYPES = ['insurance', 'e_visa', 'contract'];

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

  function packProgress(docs, types) {
    const byType = {};
    (docs || []).forEach(function (d) { byType[d.doc_type] = d; });
    let done = 0;
    const missing = [];
    types.forEach(function (t) {
      const d = byType[t];
      if (d && d.is_complete) {
        done += 1;
      } else {
        missing.push({
          type: t,
          label: (d && d.label) || t.replace(/_/g, ' '),
        });
      }
    });
    const total = types.length;
    return {
      done: done,
      total: total,
      missing: missing,
      pct: total ? Math.round((done / total) * 100) : 0,
      ready: total > 0 && done >= total,
    };
  }

  function collectCandidateDocs(c) {
    // Last write wins so the authoritative `documents` list overrides any stale phase slice.
    const byType = {};
    [].concat(c.phase1_documents || [], c.phase2_documents || [], c.documents || []).forEach(function (d) {
      if (!d || !d.doc_type) return;
      byType[d.doc_type] = d;
    });
    return Object.keys(byType).map(function (k) { return byType[k]; });
  }

  function shortDocLabel(label) {
    const s = String(label || '').replace(/\s*\(.*?\)\s*/g, '').trim();
    if (s.length <= 18) return s;
    return s.slice(0, 16) + '…';
  }

  function coachDocLabel(label) {
    return String(label || '').replace(/\s*\(.*?\)\s*/g, '').trim();
  }

  function buildPackChip(label, pack, locked) {
    let cls = 'hh-pipe-chip';
    let state = '';
    if (locked) {
      cls += ' is-locked';
      state = 'Unlocks at Visa';
    } else if (pack.ready) {
      cls += ' is-ready';
      state = 'Complete';
    } else if (pack.done > 0) {
      cls += ' is-progress';
      state = pack.missing.length === 1
        ? ('Need ' + shortDocLabel(pack.missing[0].label))
        : (pack.missing.length + ' still needed');
    } else {
      cls += ' is-progress';
      state = 'Not started';
    }
    const count = locked ? '—' : (pack.done + '/' + pack.total);
    const width = locked ? 0 : pack.pct;
    return (
      '<div class="' + cls + '">' +
        '<div class="hh-pipe-chip-top">' +
          '<span class="hh-pipe-chip-label">' + escapeHtml(label) + '</span>' +
          '<span class="hh-pipe-chip-count">' + escapeHtml(count) + '</span>' +
        '</div>' +
        '<div class="hh-pipe-chip-track" aria-hidden="true">' +
          '<div class="hh-pipe-chip-fill" style="width:' + width + '%"></div>' +
        '</div>' +
        '<div class="hh-pipe-chip-state">' + escapeHtml(state) + '</div>' +
      '</div>'
    );
  }

  function buildStageCoach(c, pipeKey, daysInStage, nextKey, visaUnlocked) {
    const merged = collectCandidateDocs(c);
    const identity = packProgress(merged, IDENTITY_DOC_TYPES);
    const offer = packProgress(merged, OFFER_DOC_TYPES);
    const visa = packProgress(merged, VISA_DOC_TYPES);
    const meta = PIPELINE_META[pipeKey] || PIPELINE_META.interview_completed;
    const nextLabel = nextKey ? (PIPELINE_SHORT[nextKey] || PIPELINE_LABELS[nextKey]) : null;

    let title = meta.next || meta.focus;
    let hint = meta.hint || '';
    let tone = 'neutral';
    let actions = [];

    if (pipeKey === 'on_hold') {
      title = 'Process is paused — pick a stage to resume';
      hint = 'On hold freezes progress. Jump to the stage where work should continue.';
      tone = 'hold';
    } else if (pipeKey === 'candidate_employee') {
      title = 'File closed — candidate is employed';
      hint = identity.ready && offer.ready && visa.ready
        ? 'All document packs are complete.'
        : 'File is closed. Reopen a stage only if something needs correction.';
      tone = 'ready';
    } else if (pipeKey === 'gathering_documents' || pipeKey === 'interview_completed') {
      if (identity.ready) {
        title = 'Identity pack complete — ready for offer prep';
        tone = 'ready';
        hint = nextLabel ? ('Advance to ' + nextLabel + ' when HR starts the offer.') : hint;
      } else {
        title = identity.done === 0
          ? 'Start the identity checklist'
          : (identity.missing.length + ' identity doc' + (identity.missing.length === 1 ? '' : 's') + ' still open');
        tone = 'progress';
        actions = identity.missing.slice(0, 3);
        hint = 'Tap a missing item below to jump to it in the checklist.';
      }
    } else if (
      pipeKey === 'preparing_offer_letter' ||
      pipeKey === 'offer_letter_prepared' ||
      pipeKey === 'offer_letter_signed' ||
      pipeKey === 'md_signed_offer_received'
    ) {
      if (!offer.ready) {
        title = 'Upload the department-signed offer letter';
        tone = 'progress';
        actions = offer.missing.slice(0, 1);
        hint = 'Offer letter can be uploaded at any stage — it is never locked.';
      } else if (pipeKey === 'md_signed_offer_received') {
        title = 'MD signed — gather visa paperwork next';
        tone = 'ready';
        hint = nextLabel ? ('Advance to ' + nextLabel + ' when visa papers are being collected.') : hint;
      } else {
        title = meta.next;
        tone = 'ready';
      }
    } else if (pipeKey === 'gathering_documents_for_visa') {
      title = 'Collect visa paperwork, then open the visa pack';
      tone = 'progress';
      hint = 'Insurance, e-visa, and contract unlock when you mark Visa process started.';
    } else if (pipeKey === 'visa_process_started') {
      if (visa.ready && offer.ready) {
        title = 'Visa pack complete — clear to mark employed';
        tone = 'ready';
        hint = nextLabel ? ('Advance to ' + nextLabel + ' to close the hiring file.') : hint;
      } else {
        const open = visa.missing.length;
        title = open === 0
          ? 'Finish remaining offer paperwork'
          : (open + ' visa pack item' + (open === 1 ? '' : 's') + ' still needed');
        tone = 'progress';
        actions = visa.missing.slice(0, 3);
        if (!offer.ready) actions = offer.missing.concat(actions).slice(0, 3);
        hint = 'Upload from section 2 below — or tap a gap to jump there.';
      }
    }

    if (daysInStage != null && daysInStage >= 7 && pipeKey !== 'candidate_employee' && pipeKey !== 'on_hold') {
      hint = (hint ? hint + ' · ' : '') + 'Parked here ' + daysInStage + 'd — worth a nudge?';
      if (tone === 'neutral') tone = 'progress';
    }

    const actionHtml = actions.length
      ? ('<div class="hh-pipe-coach-actions">' +
          actions.map(function (a) {
            return (
              '<button type="button" class="hh-pipe-coach-chip" data-jump-doc="' +
              escapeHtml(a.type) + '">' +
              escapeHtml(coachDocLabel(a.label)) +
              '</button>'
            );
          }).join('') +
        '</div>')
      : '';

    const chipsHtml =
      '<div class="hh-pipe-chips" aria-label="Document pack progress">' +
        buildPackChip('Identity', identity, false) +
        buildPackChip('Offer', offer, false) +
        buildPackChip('Visa pack', visa, !visaUnlocked) +
      '</div>';

    return (
      '<div class="hh-pipe-insight is-' + tone + '">' +
        '<div class="hh-pipe-insight-main">' +
          '<div class="hh-pipe-insight-label">Next move</div>' +
          '<p class="hh-pipe-insight-text">' + escapeHtml(title) + '</p>' +
          (hint ? '<p class="hh-pipe-insight-hint">' + escapeHtml(hint) + '</p>' : '') +
          actionHtml +
        '</div>' +
        chipsHtml +
      '</div>'
    );
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

  function vacancyAssignmentChip(c) {
    const vac = c && c.vacancy;
    if (vac) {
      const label = (vac.label || '').trim() ||
        [vac.trade_name, vac.project_name].filter(Boolean).join(' - ');
      if (label) {
        return (
          '<span class="hh-vacancy-chip is-assigned" title="Assigned vacancy">' +
            escapeHtml(label) +
          '</span>'
        );
      }
    }
    return '<span class="hh-vacancy-chip is-unassigned">Unassigned</span>';
  }

  async function loadVacancyPicker(selectEl, opts) {
    const options = opts || {};
    if (!selectEl) return [];
    const roleHint = (options.roleHint || '').trim();
    const selectedId = options.selectedId ? String(options.selectedId) : '';
    const includeCurrent = options.includeCurrent || null;
    selectEl.innerHTML = '<option value="">Loading vacancies…</option>';
    try {
      const qs = new URLSearchParams();
      if (roleHint) qs.set('trade', roleHint);
      const data = await api('/hr/api/staffing/open-vacancies?' + qs.toString());
      let items = data.vacancies || [];
      if (includeCurrent && includeCurrent.id) {
        const exists = items.some(function (v) { return String(v.id) === String(includeCurrent.id); });
        if (!exists) {
          items = [includeCurrent].concat(items);
        }
      }
      let html = '<option value="">Not assigned — pick an open vacancy…</option>';
      items.forEach(function (v) {
        const label = v.label || (
          [v.trade_name, v.project_name].filter(Boolean).join(' · ') || ('Vacancy #' + v.id)
        );
        html += '<option value="' + escapeHtml(String(v.id)) + '"' +
          (selectedId && String(v.id) === selectedId ? ' selected' : '') + '>' +
          escapeHtml(label) + '</option>';
      });
      selectEl.innerHTML = html;
      return items;
    } catch (e) {
      selectEl.innerHTML = '<option value="">Could not load vacancies</option>';
      return [];
    }
  }

  function bindVacancyPickerFill(selectEl, formEl) {
    if (!selectEl || !formEl || selectEl._hhVacBound) return;
    selectEl._hhVacBound = true;
    selectEl.addEventListener('change', function () {
      const opt = selectEl.options[selectEl.selectedIndex];
      if (!opt || !opt.value) return;
      // Prefill replacement from option dataset if we stored it; otherwise leave.
      const items = selectEl._hhItems || [];
      const vac = items.find(function (v) { return String(v.id) === String(opt.value); });
      if (!vac) return;
      const replName = formEl.querySelector('[name="replacement_name"]');
      const replId = formEl.querySelector('[name="replacement_employee_id"]');
      const roleEl = formEl.querySelector('[name="role"]');
      if (replName && !(replName.value || '').trim() && vac.replacement_name) {
        replName.value = vac.replacement_name;
      }
      if (replId && !(replId.value || '').trim() && vac.replacement_employee_id) {
        replId.value = vac.replacement_employee_id;
      }
      if (roleEl && !(roleEl.value || '').trim() && vac.trade_name) {
        roleEl.value = vac.trade_name;
      }
      const hint = document.getElementById('hhVacancyHint');
      if (hint) {
        const bits = [vac.trade_name, vac.project_name].filter(Boolean);
        if (vac.requirement_type === 'replacement' && vac.replacement_name) {
          bits.push('replacing ' + vac.replacement_name);
        }
        hint.textContent = bits.length
          ? ('Will assign: ' + bits.join(' · '))
          : 'Fills trade, project, and replacement from Manpower Tracker.';
      }
    });
  }

  async function assignCandidateVacancy(candidateId, vacancyId) {
    if (!candidateId || !vacancyId) return null;
    return api('/hr/api/staffing/assign', {
      method: 'POST',
      json: { candidate_id: candidateId, vacancy_id: parseInt(vacancyId, 10) },
    });
  }

  async function unassignCandidateVacancy(candidateId) {
    if (!candidateId) return null;
    return api('/hr/api/staffing/unassign', {
      method: 'POST',
      json: { candidate_id: candidateId },
    });
  }

  function avatarClass(name) {
    let n = 0;
    const s = String(name || '');
    for (let i = 0; i < s.length; i++) n = ((n << 5) - n) + s.charCodeAt(i);
    return 'c' + (Math.abs(n) % 12);
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

  /** Last-updated label in Asia/Dubai (GST), 24-hour clock. */
  function formatUpdatedAtDubai(iso) {
    if (!iso) return '';
    var d = null;
    if (window.InjaazDateTimeUAE && typeof window.InjaazDateTimeUAE.parseInstant === 'function') {
      d = window.InjaazDateTimeUAE.parseInstant(iso);
    } else {
      var str = String(iso).trim().replace(' ', 'T');
      if (!/[zZ]$/.test(str) && !/[+-]\d{2}:?\d{2}$/.test(str)) str += 'Z';
      d = new Date(str);
      if (Number.isNaN(d.getTime())) d = null;
    }
    if (!d) return '';
    return d.toLocaleString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'Asia/Dubai',
    });
  }

  /** Compact Dubai timestamp for pipeline stat tiles. */
  function formatStatTimestampDubai(iso) {
    if (!iso) return { value: '—', title: '' };
    var d = null;
    if (window.InjaazDateTimeUAE && typeof window.InjaazDateTimeUAE.parseInstant === 'function') {
      d = window.InjaazDateTimeUAE.parseInstant(iso);
    } else {
      var str = String(iso).trim().replace(' ', 'T');
      if (!/[zZ]$/.test(str) && !/[+-]\d{2}:?\d{2}$/.test(str)) str += 'Z';
      d = new Date(str);
      if (Number.isNaN(d.getTime())) d = null;
    }
    if (!d) return { value: '—', title: '' };
    var opts = { timeZone: 'Asia/Dubai', hour12: false };
    var day = d.toLocaleString('en-GB', Object.assign({ day: 'numeric', month: 'short' }, opts));
    var time = d.toLocaleString('en-GB', Object.assign({ hour: '2-digit', minute: '2-digit' }, opts));
    var full = formatUpdatedAtDubai(iso);
    return { value: day + ' · ' + time, title: full ? (full + ' (Dubai)') : '' };
  }

  /* ── List filter persistence (survives detail → Back to list) ── */
  const LIST_FILTERS_KEY = 'hhHiringListFilters';

  function readStoredListFilters() {
    try {
      const raw = sessionStorage.getItem(LIST_FILTERS_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (e) {
      return null;
    }
  }

  function writeStoredListFilters(filters) {
    try {
      sessionStorage.setItem(LIST_FILTERS_KEY, JSON.stringify({
        q: filters.q || '',
        status: filters.status || 'all',
        pipeline: filters.pipeline || 'all',
        assignment: filters.assignment || 'all',
        trade_id: filters.trade_id || 'all',
        project_id: filters.project_id || 'all',
        page: filters.page || 1,
      }));
    } catch (e) { /* ignore quota / private mode */ }
  }

  function listFiltersQuery(filters) {
    const qs = new URLSearchParams();
    if (filters.q) qs.set('q', filters.q);
    if (filters.status && filters.status !== 'all') qs.set('status', filters.status);
    if (filters.pipeline && filters.pipeline !== 'all') qs.set('pipeline', filters.pipeline);
    if (filters.assignment && filters.assignment !== 'all') qs.set('assignment', filters.assignment);
    if (filters.trade_id && filters.trade_id !== 'all') qs.set('trade_id', String(filters.trade_id));
    if (filters.project_id && filters.project_id !== 'all') qs.set('project_id', String(filters.project_id));
    if (filters.page && Number(filters.page) > 1) qs.set('page', String(filters.page));
    return qs;
  }

  function hiringListHref(filters) {
    const src = filters || readStoredListFilters() || {};
    const s = listFiltersQuery(src).toString();
    return '/hr/hiring' + (s ? '?' + s : '');
  }

  function parseListFiltersFromLocation() {
    const params = new URLSearchParams(window.location.search || '');
    const out = {};
    if (params.has('q')) out.q = params.get('q') || '';
    if (params.has('status')) out.status = params.get('status') || 'all';
    if (params.has('pipeline')) out.pipeline = params.get('pipeline') || 'all';
    if (params.has('assignment')) out.assignment = params.get('assignment') || 'all';
    if (params.has('trade_id')) out.trade_id = params.get('trade_id') || 'all';
    if (params.has('project_id')) out.project_id = params.get('project_id') || 'all';
    if (params.has('page')) {
      const p = parseInt(params.get('page'), 10);
      if (p > 0) out.page = p;
    }
    return out;
  }

  /* ── List page ─────────────────────────────────────────── */
  function initList() {
    const root = document.getElementById('hhListRoot');
    if (!root) return;

    const fromUrl = parseListFiltersFromLocation();
    const fromStore = readStoredListFilters() || {};
    const initial = Object.assign({
      q: '',
      status: 'all',
      pipeline: 'all',
      assignment: 'all',
      trade_id: 'all',
      project_id: 'all',
      page: 1,
    }, fromStore, fromUrl);

    if (initial.assignment === 'unassigned') {
      initial.trade_id = 'all';
      initial.project_id = 'all';
    }

    const state = {
      q: initial.q || '',
      status: initial.status || 'all',
      pipeline: initial.pipeline || 'all',
      assignment: initial.assignment || 'all',
      trade_id: initial.trade_id ? String(initial.trade_id) : 'all',
      project_id: initial.project_id ? String(initial.project_id) : 'all',
      page: initial.page || 1,
      perPage: 10,
      pages: 1,
      count: 0,
    };

    const listEl = document.getElementById('hhCandidateList');
    const searchEl = document.getElementById('hhSearch');
    const filterBtns = document.querySelectorAll('.hh-filter-btn');
    const pipelineFilter = document.getElementById('hhPipelineFilter');
    const assignmentFilter = document.getElementById('hhAssignmentFilter');
    const tradeFilter = document.getElementById('hhTradeFilter');
    const projectFilter = document.getElementById('hhProjectFilter');
    const pagEl = document.getElementById('hhPagination');
    const modal = document.getElementById('hhAddModal');
    const form = document.getElementById('hhAddForm');
    const interviewPick = document.getElementById('hhInterviewPick');
    const interviewApply = document.getElementById('hhInterviewApply');

    let searchTimer = null;
    let assessmentsCache = [];

    function persistFilters() {
      writeStoredListFilters(state);
      const qs = listFiltersQuery(state).toString();
      const next = window.location.pathname + (qs ? '?' + qs : '');
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, '', next);
      }
    }

    function syncVacancyFacetControls() {
      const unassigned = state.assignment === 'unassigned';
      if (tradeFilter) {
        tradeFilter.disabled = unassigned;
        if (unassigned) state.trade_id = 'all';
      }
      if (projectFilter) {
        projectFilter.disabled = unassigned;
        if (unassigned) state.project_id = 'all';
      }
    }

    function fillFacetSelect(selectEl, items, selectedId, allLabel) {
      if (!selectEl) return selectedId || 'all';
      const selected = selectedId && selectedId !== 'all' ? String(selectedId) : 'all';
      let html = '<option value="all">' + escapeHtml(allLabel) + '</option>';
      (items || []).forEach(function (item) {
        if (!item || item.id == null || item.id === '') return;
        const name = (item.name || '').toString().trim();
        if (!name) return;
        html += '<option value="' + escapeHtml(String(item.id)) + '">' +
          escapeHtml(name) +
          '</option>';
      });
      selectEl.innerHTML = html;
      const opt = selectEl.querySelector('option[value="' + selected + '"]');
      selectEl.value = opt ? selected : 'all';
      return opt ? selected : 'all';
    }

    function facetsFromCandidateItems(items) {
      const trades = {};
      const projects = {};
      (items || []).forEach(function (c) {
        const v = c && c.vacancy;
        if (!v) return;
        if (v.trade_id != null && v.trade_name) {
          trades[String(v.trade_id)] = String(v.trade_name);
        }
        if (v.project_id != null && v.project_name) {
          projects[String(v.project_id)] = String(v.project_name);
        }
      });
      function toList(map) {
        return Object.keys(map).map(function (id) {
          return { id: id, name: map[id] };
        }).sort(function (a, b) {
          return a.name.localeCompare(b.name);
        });
      }
      return { trades: toList(trades), projects: toList(projects) };
    }

    function mergeFacetLists(a, b) {
      const map = {};
      [].concat(a || [], b || []).forEach(function (item) {
        if (!item || item.id == null || item.id === '') return;
        const name = (item.name || '').toString().trim();
        if (!name) return;
        map[String(item.id)] = { id: item.id, name: name };
      });
      return Object.keys(map).map(function (k) { return map[k]; }).sort(function (x, y) {
        return String(x.name).localeCompare(String(y.name));
      });
    }

    function syncFilterControls() {
      if (searchEl) searchEl.value = state.q || '';
      filterBtns.forEach(function (btn) {
        const active = (btn.getAttribute('data-status') || 'all') === state.status;
        btn.classList.toggle('active', active);
      });
      if (pipelineFilter) {
        const opt = pipelineFilter.querySelector('option[value="' + state.pipeline + '"]');
        pipelineFilter.value = opt ? state.pipeline : 'all';
        if (!opt) state.pipeline = 'all';
      }
      if (assignmentFilter) {
        const opt = assignmentFilter.querySelector('option[value="' + state.assignment + '"]');
        assignmentFilter.value = opt ? state.assignment : 'all';
        if (!opt) state.assignment = 'all';
      }
      syncVacancyFacetControls();
      if (tradeFilter && tradeFilter.querySelector('option[value="' + state.trade_id + '"]')) {
        tradeFilter.value = state.trade_id;
      } else if (tradeFilter) {
        tradeFilter.value = 'all';
        state.trade_id = 'all';
      }
      if (projectFilter && projectFilter.querySelector('option[value="' + state.project_id + '"]')) {
        projectFilter.value = state.project_id;
      } else if (projectFilter) {
        projectFilter.value = 'all';
        state.project_id = 'all';
      }
    }

    syncFilterControls();

    async function load() {
      persistFilters();
      listEl.innerHTML = '<div class="hh-loading"><div class="hh-spinner"></div>Loading candidates…</div>';
      try {
        const qs = new URLSearchParams({
          q: state.q,
          status: state.status,
          pipeline: state.pipeline,
          assignment: state.assignment || 'all',
          page: String(state.page),
          per_page: String(state.perPage),
        });
        if (state.assignment !== 'unassigned') {
          if (state.trade_id && state.trade_id !== 'all') qs.set('trade_id', String(state.trade_id));
          if (state.project_id && state.project_id !== 'all') qs.set('project_id', String(state.project_id));
        }
        const data = await api('/hr/api/hiring/candidates?' + qs.toString());
        const items = data.candidates || [];
        state.count = data.count || 0;
        state.pages = data.pages || 1;
        const fromItems = facetsFromCandidateItems(items);
        const trades = mergeFacetLists(data.vacancy_trades, fromItems.trades);
        const projects = mergeFacetLists(data.vacancy_projects, fromItems.projects);
        state.trade_id = fillFacetSelect(tradeFilter, trades, state.trade_id, 'All trades');
        state.project_id = fillFacetSelect(projectFilter, projects, state.project_id, 'All projects');
        syncVacancyFacetControls();
        renderList(items);
        renderPagination();
      } catch (e) {
        listEl.innerHTML = '<div class="hh-empty">' + escapeHtml(e.message) + '</div>';
        pagEl.innerHTML = '';
      }
    }

    function renderList(items) {
      if (!items.length) {
        const filtered = !!(
          (state.q && state.q.trim()) ||
          (state.status && state.status !== 'all') ||
          (state.pipeline && state.pipeline !== 'all') ||
          (state.assignment && state.assignment !== 'all') ||
          (state.trade_id && state.trade_id !== 'all') ||
          (state.project_id && state.project_id !== 'all')
        );
        listEl.innerHTML =
          '<div class="hh-empty">' +
            '<p class="hh-empty-title">' + (filtered ? 'No matching candidates' : 'No candidates yet') + '</p>' +
            '<p class="hh-empty-sub">' +
              (filtered
                ? 'Try clearing the vacancy, trade, project, or stage filters.'
                : 'Add a candidate with their details to start tracking onboarding documents.') +
            '</p>' +
            (filtered
              ? ''
              : ('<button type="button" class="hh-btn hh-btn-primary" data-hh-add>' +
                  '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/></svg>' +
                  'Add Candidate' +
                '</button>')) +
          '</div>';
        return;
      }
      listEl.innerHTML = items.map(function (c) {
        const pct = c.total ? Math.round((c.completed / c.total) * 100) : 0;
        const pipeKey = c.pipeline_status || 'interview_completed';
        const pipeLabel = PIPELINE_LABELS[pipeKey] || c.pipeline_label || pipeKey;
        const comment = (c.comments || '').trim();
        const commentHtml = comment
          ? '<div class="hh-row-comment" title="' + escapeHtml(comment) + '">' +
              '<span class="hh-row-comment-label">Comment</span>' +
              '<span class="hh-row-comment-text">' + escapeHtml(comment) + '</span>' +
            '</div>'
          : '';
        const roleLine = [c.role, c.department].filter(Boolean).join(' · ') || '—';
        const updatedLabel = formatUpdatedAtDubai(c.updated_at);
        const updatedHtml = updatedLabel
          ? '<time class="hh-row-updated" datetime="' + escapeHtml(c.updated_at || '') + '" title="Last updated (Dubai time)">' +
              escapeHtml(updatedLabel) +
            '</time>'
          : '<span class="hh-row-updated hh-row-updated-empty" aria-hidden="true"></span>';
        return (
          '<a class="hh-row" href="/hr/hiring/candidates/' + c.id + '">' +
            '<div class="hh-avatar ' + avatarClass(c.full_name) + '">' + escapeHtml(c.initials || '?') + '</div>' +
            '<div class="hh-row-info">' +
              '<div class="hh-row-name">' + escapeHtml(c.full_name) +
                '<span class="hh-row-role-inline">' + escapeHtml(roleLine) + '</span>' +
              '</div>' +
              vacancyAssignmentChip(c) +
            '</div>' +
            '<div class="hh-row-progress">' +
              '<span class="hh-progress-count">' + escapeHtml(c.progress_label) + '</span>' +
              '<div class="hh-progress-track" title="Documents ' + escapeHtml(c.progress_label) + '">' +
                '<div class="hh-progress-fill" style="width:' + pct + '%"></div>' +
              '</div>' +
            '</div>' +
            '<div class="hh-row-meta">' +
              '<span class="hh-status pipeline ' + escapeHtml(pipeKey) + '">' +
                escapeHtml(pipeLabel) +
              '</span>' +
              commentHtml +
            '</div>' +
            updatedHtml +
            '<button type="button" class="hh-row-delete" data-hh-delete="' + c.id + '" aria-label="Delete ' + escapeHtml(c.full_name) + '" title="Delete candidate">' +
              '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.25" stroke="currentColor" aria-hidden="true">' +
                '<path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>' +
              '</svg>' +
            '</button>' +
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

    if (assignmentFilter) {
      assignmentFilter.addEventListener('change', function () {
        state.assignment = assignmentFilter.value || 'all';
        if (state.assignment === 'unassigned') {
          state.trade_id = 'all';
          state.project_id = 'all';
        }
        syncVacancyFacetControls();
        state.page = 1;
        load();
      });
    }

    if (tradeFilter) {
      tradeFilter.addEventListener('change', function () {
        if (state.assignment === 'unassigned') return;
        state.trade_id = tradeFilter.value || 'all';
        state.page = 1;
        load();
      });
    }

    if (projectFilter) {
      projectFilter.addEventListener('change', function () {
        if (state.assignment === 'unassigned') return;
        state.project_id = projectFilter.value || 'all';
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
      const title = document.getElementById('hhAddTitle');
      const sub = document.getElementById('hhAddSub');
      const submit = document.getElementById('hhAddSubmit');
      if (title) title.textContent = 'Add Candidate';
      if (sub) {
        sub.textContent = 'Enter candidate details, or import name and role from an Interview Assessment already in the system.';
      }
      if (submit) submit.textContent = 'Create checklist';
      modal.classList.add('open');
      loadAssessments();
      const vacPick = document.getElementById('hhVacancyPick');
      const roleEl = form && form.querySelector('[name="role"]');
      loadVacancyPicker(vacPick, { roleHint: roleEl ? roleEl.value : '' }).then(function (items) {
        if (vacPick) vacPick._hhItems = items;
      });
      bindVacancyPickerFill(vacPick, form);
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
      const addBtn = e.target.closest('[data-hh-add]');
      if (addBtn) {
        openModal();
        return;
      }
      const delBtn = e.target.closest('[data-hh-delete]');
      if (!delBtn) return;
      e.preventDefault();
      e.stopPropagation();
      const id = parseInt(delBtn.getAttribute('data-hh-delete'), 10);
      if (!id) return;
      (async function () {
        const ok = await confirmDialog({
          title: 'Delete candidate',
          message: 'Delete this candidate and all uploaded documents? This cannot be undone.',
          confirmLabel: 'Delete',
          danger: true,
        });
        if (!ok) return;
        delBtn.disabled = true;
        try {
          await api('/hr/api/hiring/candidates/' + id, { method: 'DELETE' });
          toast('Candidate deleted');
          load();
        } catch (err) {
          toast(err.message, true);
          delBtn.disabled = false;
        }
      })();
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

    function hideImportResult() {
      const el = document.getElementById('hhImportResult');
      if (!el) return;
      clearTimeout(el._dismissTimer);
      el._dismissTimer = null;
      el.classList.remove('is-fading');
      el.hidden = true;
      el.innerHTML = '';
    }

    function showImportResult(result, message) {
      const el = document.getElementById('hhImportResult');
      if (!el) return;
      clearTimeout(el._dismissTimer);
      el._dismissTimer = null;
      el.classList.remove('is-fading');
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
      // Success banners auto-fade after 10s; error lists stay until dismissed.
      if (!errs.length) {
        el._dismissTimer = setTimeout(function () {
          el.classList.add('is-fading');
          setTimeout(hideImportResult, 400);
        }, 10000);
      }
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
          hideImportResult();
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
          const vacancyId = (fd.get('vacancy_id') || '').toString().trim();
          if (data.candidate && data.candidate.id && vacancyId) {
            try {
              await assignCandidateVacancy(data.candidate.id, vacancyId);
            } catch (assignErr) {
              toast('Candidate created, but vacancy assign failed: ' + assignErr.message, true);
              closeModal();
              window.location.href = '/hr/hiring/candidates/' + data.candidate.id;
              return;
            }
          }
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

    // Back from candidate detail often restores this page from bfcache
    // (history.back), so DOMContentLoaded does not re-run — refetch then.
    window.addEventListener('pageshow', function (ev) {
      if (ev.persisted) load();
    });

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
      if (next.pipeline_status && PIPELINE_LABELS[next.pipeline_status]) {
        next.pipeline_label = PIPELINE_LABELS[next.pipeline_status];
      } else if (!next.pipeline_label) {
        next.pipeline_label = next.pipeline_status || '';
      }
      if (typeof next.visa_docs_unlocked !== 'boolean') {
        next.visa_docs_unlocked = visaDocsUnlockedForStatus(next.pipeline_status);
      }
      if (typeof next.is_on_hold !== 'boolean') {
        next.is_on_hold = next.pipeline_status === 'on_hold';
      }
      if (typeof next.file_closed !== 'boolean') {
        next.file_closed = !next.is_on_hold && next.pipeline_status === 'candidate_employee';
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

    /** After any document mutation: refresh checklist + Next Move + packs + stats together. */
    async function syncAfterDocChange(data) {
      const c = data && data.candidate;
      if (c && (Array.isArray(c.documents) || Array.isArray(c.phase1_documents))) {
        render(applyCandidate(c));
        return;
      }
      await load();
    }

    function renderDocRow(d) {
      const locked = !!d.upload_locked;
      const accept = (d.allowed_extensions || []).map(function (x) { return '.' + x; }).join(',');
      const status = d.status || 'missing';
      const hasFile = !!d.has_file;
      const isReceived = !hasFile && (status === 'uploaded' || status === 'attested' || status === 'verified');
      let statusHtml = '';
      let toolsHtml = '';

      const isOfferLetter = d.doc_type === 'offer_letter';

      if (!isOfferLetter) {
        if (locked) {
          statusHtml = '<span class="hh-doc-badge is-locked">Locked</span>';
        } else if (hasFile) {
          if (d.doc_type === 'pcc' && status === 'uploaded') {
            statusHtml = '<span class="hh-doc-badge is-wait">Awaiting attest</span>';
          } else if (d.doc_type === 'pcc' && (status === 'attested' || status === 'verified')) {
            statusHtml = '<span class="hh-doc-badge is-done">Attested</span>';
          } else {
            statusHtml = '<span class="hh-doc-badge is-done">On file</span>';
          }
        } else if (status === 'attested') {
          statusHtml = '<span class="hh-doc-badge is-received">Attested</span>';
        } else if (status === 'verified') {
          statusHtml = '<span class="hh-doc-badge is-received">Verified</span>';
        } else if (status === 'uploaded') {
          statusHtml = '<span class="hh-doc-badge is-received">File uploaded</span>';
        } else {
          statusHtml = '<span class="hh-doc-badge is-idle">Needed</span>';
        }

        if (!locked) {
          if (hasFile && d.id) {
            toolsHtml += '<button type="button" class="hh-doc-tool" data-view="' + d.id + '" data-filename="' + escapeHtml(d.filename || 'document') + '">View</button>';
          }
          if (d.doc_type === 'pcc' && hasFile && status === 'uploaded') {
            toolsHtml += '<button type="button" class="hh-doc-tool is-primary" data-attest="pcc">Mark attested</button>';
          }
          toolsHtml +=
            '<button type="button" class="hh-doc-tool' + (hasFile || isReceived ? '' : ' is-primary') + '" data-upload="' + escapeHtml(d.doc_type) + '" data-accept="' + escapeHtml(accept) + '">' +
              (hasFile ? 'Re-upload' : (isReceived ? 'Attach file' : 'Upload')) +
            '</button>';
          if (!hasFile && !isReceived) {
            toolsHtml +=
              '<button type="button" class="hh-doc-tool" data-mark-received="' + escapeHtml(d.doc_type) + '">Mark received</button>';
          }
          if ((hasFile || isReceived) && d.id) {
            toolsHtml +=
              '<button type="button" class="hh-doc-tool is-danger" data-clear="' + d.id + '" data-clear-mode="' +
                (isReceived ? 'received' : 'file') + '">' +
                (isReceived ? 'Clear mark' : 'Clear') +
              '</button>';
          }
        }
      }

      let sub = '';
      if (isOfferLetter) {
        sub = '';
      } else if (locked) {
        sub = 'Available after Visa process started';
      } else if (hasFile && d.filename) {
        sub = escapeHtml(d.filename);
        if (d.uploaded_at) sub += ' · ' + escapeHtml(String(d.uploaded_at).slice(0, 10));
      } else if (isReceived) {
        sub = 'Handed over in person — no file copy in system';
      } else {
        const exts = (d.allowed_extensions || []).join(', ').toUpperCase();
        sub = 'Accepted: ' + escapeHtml(exts || '—');
      }

      const docSvg =
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" aria-hidden="true">' +
          '<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>' +
        '</svg>';

      let iconHtml;
      if (locked || hasFile) {
        iconHtml =
          '<div class="hh-doc-icon' + (hasFile ? ' is-on-file' : '') + '" aria-hidden="true">' +
            docSvg +
          '</div>';
      } else {
        iconHtml =
          '<label class="hh-doc-icon hh-doc-icon-check' + (isReceived ? ' is-checked' : '') + '"' +
            ' title="' + (isReceived ? 'Clear in-person upload mark' : 'Mark as handed over in person') + '">' +
            '<input type="checkbox" class="hh-visually-hidden" data-inperson-check="' + escapeHtml(d.doc_type) + '"' +
              (isReceived ? ' checked' : '') +
              (d.id ? ' data-doc-id="' + d.id + '"' : '') +
              ' aria-label="' + (isReceived ? 'Clear file uploaded mark for ' : 'Mark file uploaded for ') +
              escapeHtml(d.label || d.doc_type) + '">' +
            docSvg +
            '<span class="hh-doc-icon-tick" aria-hidden="true">' +
              '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor">' +
                '<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5"/>' +
              '</svg>' +
            '</span>' +
          '</label>';
      }

      return (
        '<div class="hh-doc-row' + (locked ? ' is-locked' : '') +
          (isOfferLetter ? ' has-offer-comment' : '') +
          '" data-doc-type="' + escapeHtml(d.doc_type) + '">' +
          iconHtml +
          '<div class="hh-doc-info">' +
            '<div class="hh-doc-label">' + escapeHtml(d.label || d.doc_type) + '</div>' +
            (isOfferLetter
              ? '<div class="hh-doc-sub">Offer letter note</div>'
              : (sub ? '<div class="hh-doc-sub">' + sub + '</div>' : '')) +
          '</div>' +
          (isOfferLetter
            ? '<div class="hh-doc-offer-comment' + ((d.notes || '').trim() ? ' has-note' : '') + '">' +
                '<input type="text" id="hhOfferLetterComment" class="hh-doc-offer-comment-input" maxlength="2000" ' +
                  'placeholder="Add a note…" aria-label="Offer letter comment" ' +
                  'value="' + escapeHtml(d.notes || '') + '">' +
              '</div>'
            : '<div class="hh-doc-actions">' +
                '<div class="hh-doc-actions-top">' + statusHtml + '</div>' +
                (toolsHtml ? '<div class="hh-doc-tools">' + toolsHtml + '</div>' : '') +
              '</div>') +
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
        is_on_hold: value === 'on_hold',
        file_closed: value === 'candidate_employee',
        visa_docs_unlocked: visaDocsUnlockedForStatus(value),
        updated_at: new Date().toISOString(),
      });
      render(optimistic);

      try {
        const data = await api('/hr/api/hiring/candidates/' + candidateId, {
          method: 'PATCH',
          json: { pipeline_status: value },
        });
        const toastMsg = value === 'on_hold'
          ? 'Process put on hold'
          : (value === 'candidate_employee' ? 'File closed' : 'Status updated');
        toast(toastMsg);
        render(applyCandidate(data.candidate || candidateState, {
          pipeline_status: value,
          pipeline_label: PIPELINE_LABELS[value],
          is_on_hold: value === 'on_hold',
          file_closed: value === 'candidate_employee',
          visa_docs_unlocked: visaDocsUnlockedForStatus(value),
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
        const jump = e.target.closest('[data-jump-doc]');
        if (jump) {
          const docType = jump.getAttribute('data-jump-doc');
          const row = document.querySelector('.hh-doc-row[data-doc-type="' + docType + '"]');
          if (row) {
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('is-flash');
            setTimeout(function () { row.classList.remove('is-flash'); }, 1400);
          }
          return;
        }
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
      const pipeLabel = PIPELINE_LABELS[pipeKey] || c.pipeline_label || pipeKey;
      const meta = PIPELINE_META[pipeKey] || PIPELINE_META.interview_completed;
      const steps = PIPELINE_STEPS;
      const stepIdx = steps.indexOf(pipeKey);
      const currentIdx = stepIdx >= 0 ? stepIdx : -1;
      const isOnHold = pipeKey === 'on_hold' || !!c.is_on_hold;
      const isFileClosed = !isOnHold && (pipeKey === 'candidate_employee' || !!c.file_closed);
      // On hold pauses the whole process — resume via Jump to / stepper, no advance.
      const nextKey = isOnHold ? null : nextPipelineStatus(pipeKey);
      const nextLabel = nextKey ? (PIPELINE_LABELS[nextKey] || nextKey) : null;
      const visaUnlocked = !!c.visa_docs_unlocked;

      const daysInStage = (function () {
        const raw = c.updated_at || c.created_at;
        if (!raw) return null;
        const t = Date.parse(raw);
        if (Number.isNaN(t)) return null;
        return Math.max(0, Math.floor((Date.now() - t) / 86400000));
      })();

      const lastTouch = formatStatTimestampDubai(c.updated_at || c.created_at);

      const onFileStat = (function () {
        const raw = c.created_at;
        if (!raw) return { value: '—', title: '', warn: false };
        const t = Date.parse(raw);
        if (Number.isNaN(t)) return { value: '—', title: '', warn: false };
        const days = Math.max(0, Math.floor((Date.now() - t) / 86400000));
        const opened = formatStatTimestampDubai(raw);
        return {
          value: days === 0 ? 'Today' : (days === 1 ? '1 day' : (days + ' days')),
          title: opened.title ? ('Opened ' + opened.title) : ('Opened ' + opened.value),
          warn: days >= 14,
        };
      })();

      const hireTypeStat = (function () {
        const vac = c.vacancy;
        const replName = (c.replacement_name || (vac && vac.replacement_name) || '').trim();
        const isReplacement = (vac && vac.requirement_type === 'replacement') || !!replName;
        if (isReplacement) {
          return {
            value: 'Replacement',
            title: replName ? ('Replacing ' + replName) : 'Replacement hire',
            highlight: true,
          };
        }
        return {
          value: 'New hire',
          title: 'Not linked as a replacement',
          highlight: false,
        };
      })();

      const contactStat = (function () {
        const phone = (c.phone || '').trim();
        const email = (c.email || '').trim();
        if (phone) {
          return {
            value: phone,
            title: email ? (phone + ' · ' + email) : phone,
            empty: false,
          };
        }
        if (email) {
          return {
            value: email,
            title: email,
            empty: false,
          };
        }
        return {
          value: '—',
          title: 'No phone or email on file',
          empty: true,
        };
      })();

      const selectOptions =
        '<optgroup label="Stages">' +
          steps.map(function (key) {
            return '<option value="' + escapeHtml(key) + '"' +
              (key === pipeKey ? ' selected' : '') + '>' +
              escapeHtml(PIPELINE_LABELS[key]) + '</option>';
          }).join('') +
        '</optgroup>' +
        '<optgroup label="Process">' +
          '<option value="on_hold"' + (isOnHold ? ' selected' : '') + '>' +
            'On hold — pause process' +
          '</option>' +
        '</optgroup>';

      const stepsHtml = steps.map(function (key, i) {
        const label = PIPELINE_LABELS[key] || key;
        const short = PIPELINE_SHORT[key] || label;
        const current = !isOnHold && key === pipeKey;
        const done = !isOnHold && currentIdx > i;
        return (
          '<li class="hh-pipe-step' + (current ? ' is-current' : '') + (done ? ' is-done' : '') +
            (isOnHold ? ' is-frozen' : '') +
            (current && isFileClosed ? ' is-closed' : '') + '">' +
            '<button type="button" class="hh-pipe-btn" data-pipeline="' + escapeHtml(key) + '"' +
              ' title="' + escapeHtml(label) +
                (current && isFileClosed ? ' (file closed)' : '') +
                (isOnHold ? ' — tap to resume here' : '') + '"' +
              ' aria-current="' + (current ? 'step' : 'false') + '"' +
              ' aria-label="' + (isOnHold ? 'Resume at: ' : 'Set stage: ') + escapeHtml(label) + '">' +
              '<span class="hh-pipe-dot" aria-hidden="true">' +
                (done || (current && isFileClosed) ? '✓' : String(i + 1)) +
              '</span>' +
              '<span class="hh-pipe-label">' + escapeHtml(short) + '</span>' +
            '</button>' +
          '</li>'
        );
      }).join('');

      const stageKicker = isOnHold
        ? 'Process on hold'
        : (isFileClosed
            ? 'File closed'
            : ('Stage ' + (currentIdx + 1) + ' of ' + steps.length));
      const holdBtn = isOnHold
        ? ''
        : '<button type="button" class="hh-btn hh-btn-ghost hh-btn-sm hh-pipeline-hold-btn" data-pipeline="on_hold" title="Pause the whole hiring process">' +
            'Put on hold' +
          '</button>';
      const advanceHtml = nextKey
        ? '<button type="button" class="hh-btn hh-btn-primary hh-btn-sm" data-pipeline="' + escapeHtml(nextKey) + '">' +
            'Advance to ' + escapeHtml(PIPELINE_SHORT[nextKey] || nextLabel) +
          '</button>'
        : (isOnHold
            ? '<span class="hh-pipeline-final hh-pipeline-final-hold">Jump to a stage to resume</span>'
            : (isFileClosed
                ? '<span class="hh-pipeline-final hh-pipeline-final-closed">File closed</span>'
                : '<span class="hh-pipeline-final">Final stage</span>'));

      body.innerHTML =
        '<div class="hh-pipeline-top' + (isOnHold ? ' is-on-hold' : '') + '">' +
          '<div class="hh-pipeline-stage">' +
            '<div class="hh-pipeline-kicker' + (isOnHold ? ' is-hold' : '') + '">' + escapeHtml(stageKicker) + '</div>' +
            '<h2 class="hh-pipeline-title">' + escapeHtml(isOnHold ? 'On hold' : pipeLabel) + '</h2>' +
            '<p class="hh-pipeline-focus">' + escapeHtml(meta.focus) + '</p>' +
          '</div>' +
          '<div class="hh-pipeline-note">' +
            renderCommentsBlock(c) +
          '</div>' +
          '<div class="hh-pipeline-controls">' +
            '<label class="hh-pipeline-select-wrap">' +
              '<span class="hh-pipeline-select-label">Jump to</span>' +
              '<select id="hhPipelineSelectInline" class="hh-select hh-pipeline-select" aria-label="Update pipeline status">' +
                selectOptions +
              '</select>' +
            '</label>' +
            holdBtn +
            advanceHtml +
          '</div>' +
        '</div>' +

        '<div class="hh-pipeline-segments' + (isOnHold ? ' is-on-hold' : '') + '" role="img" aria-label="' + escapeHtml(stageKicker) + '">' +
          steps.map(function (key, i) {
            let cls = '';
            if (isOnHold) {
              cls = 'is-frozen';
            } else if (i < currentIdx) {
              cls = 'is-done';
            } else if (i === currentIdx) {
              cls = isFileClosed ? 'is-current is-closed' : 'is-current';
            }
            return '<span class="hh-pipeline-seg ' + cls + '" title="' + escapeHtml(PIPELINE_LABELS[key] || key) + '"></span>';
          }).join('') +
          '<span class="hh-pipeline-seg-caption' + (isOnHold ? ' is-hold' : '') + '">' + escapeHtml(stageKicker) + '</span>' +
        '</div>' +

        '<ol class="hh-pipeline-stepper' + (isOnHold ? ' is-on-hold' : '') + '">' + stepsHtml + '</ol>' +

        '<div class="hh-pipeline-intel">' +
          buildStageCoach(c, pipeKey, daysInStage, nextKey, visaUnlocked) +
          '<div class="hh-pipe-stats">' +
            '<div class="hh-pipe-stat is-timestamp" title="' + escapeHtml(lastTouch.title) + '">' +
              '<span class="hh-pipe-stat-val">' + escapeHtml(lastTouch.value) + '</span>' +
              '<span class="hh-pipe-stat-lbl">Last updated</span>' +
            '</div>' +
            '<div class="hh-pipe-stat"' +
              (onFileStat.title ? ' title="' + escapeHtml(onFileStat.title) + '"' : '') + '>' +
              '<span class="hh-pipe-stat-val">' + escapeHtml(onFileStat.value) + '</span>' +
              '<span class="hh-pipe-stat-lbl">On file</span>' +
            '</div>' +
            '<div class="hh-pipe-stat"' +
              (hireTypeStat.title ? ' title="' + escapeHtml(hireTypeStat.title) + '"' : '') + '>' +
              '<span class="hh-pipe-stat-val">' + escapeHtml(hireTypeStat.value) + '</span>' +
              '<span class="hh-pipe-stat-lbl">Hire type</span>' +
            '</div>' +
            '<div class="hh-pipe-stat"' +
              (contactStat.title ? ' title="' + escapeHtml(contactStat.title) + '"' : '') + '>' +
              '<span class="hh-pipe-stat-val">' + escapeHtml(contactStat.value) + '</span>' +
              '<span class="hh-pipe-stat-lbl">Contact</span>' +
            '</div>' +
          '</div>' +
        '</div>';

      body.classList.remove('is-busy');
      body.classList.toggle('is-on-hold', isOnHold);
      bindPipelineBody(body);
      bindCommentsEditors();

      if (select) {
        select.value = pipeKey;
        select.disabled = false;
      }
    }

    function renderVacancyBlock(c) {
      const vac = c.vacancy;
      if (vac && vac.id) {
        const bits = [vac.trade_name, vac.project_name].filter(Boolean).join(' · ') || ('Vacancy #' + vac.id);
        const repl = vac.requirement_type === 'replacement' && vac.replacement_name
          ? (' · Replacing ' + vac.replacement_name)
          : '';
        return (
          '<div class="hh-vacancy-card is-assigned is-clickable" id="hhVacancyCard" ' +
            'role="link" tabindex="0" data-tracker-href="/hr/manpower-tracker" ' +
            'title="Open Manpower Tracker" aria-label="Open Manpower Tracker for this vacancy">' +
            '<div class="hh-vacancy-card-head">' +
              '<span class="hh-vacancy-kicker">Project vacancy</span>' +
              '<div class="hh-vacancy-card-actions">' +
                '<button type="button" class="hh-replacement-edit" id="hhVacancyUnassign">Unassign</button>' +
              '</div>' +
            '</div>' +
            '<div class="hh-vacancy-card-label">' + escapeHtml(bits) + escapeHtml(repl) + '</div>' +
            '<div class="hh-vacancy-card-meta">#' + escapeHtml(String(vac.id)) +
              (vac.status_label ? ' · ' + escapeHtml(vac.status_label) : '') +
            '</div>' +
          '</div>'
        );
      }
      return (
        '<div class="hh-vacancy-card is-unassigned" id="hhVacancyCard">' +
          '<div class="hh-vacancy-card-head">' +
            '<span class="hh-vacancy-kicker">Project vacancy</span>' +
            '<button type="button" class="hh-replacement-edit" id="hhVacancyAssignOpen">Assign</button>' +
          '</div>' +
          '<div class="hh-vacancy-card-label">Not assigned</div>' +
          '<div class="hh-vacancy-card-meta">Link an open Manpower vacancy for this hire</div>' +
        '</div>'
      );
    }

    function bindVacancyCard() {
      const card = document.getElementById('hhVacancyCard');
      if (card && card.classList.contains('is-clickable')) {
        const goTracker = function () {
          const href = card.getAttribute('data-tracker-href') || '/hr/manpower-tracker';
          window.location.href = href;
        };
        card.addEventListener('click', function (e) {
          if (e.target.closest('button, a, input, select, textarea')) return;
          goTracker();
        });
        card.addEventListener('keydown', function (e) {
          if (e.key !== 'Enter' && e.key !== ' ') return;
          if (e.target.closest('button, a, input, select, textarea')) return;
          e.preventDefault();
          goTracker();
        });
      }
      const unassignBtn = document.getElementById('hhVacancyUnassign');
      if (unassignBtn) {
        unassignBtn.addEventListener('click', async function (e) {
          e.preventDefault();
          e.stopPropagation();
          const ok = await confirmDialog({
            title: 'Unassign vacancy',
            message: 'Remove this candidate from the project vacancy? The vacancy stays open in Manpower Tracker.',
            confirmLabel: 'Unassign',
          });
          if (!ok) return;
          try {
            const data = await unassignCandidateVacancy(candidateId);
            toast('Vacancy unassigned');
            if (data && data.candidate) {
              render(applyCandidate(data.candidate));
            } else {
              await load();
            }
          } catch (err) {
            toast(err.message, true);
          }
        });
      }
      const assignOpen = document.getElementById('hhVacancyAssignOpen');
      if (assignOpen) {
        assignOpen.addEventListener('click', openEditModal);
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
        const padY = (parseFloat(styles.paddingTop) || 0) + (parseFloat(styles.paddingBottom) || 0);
        const noteSlot = block.closest('.hh-pipeline-note');
        const hostW = (noteSlot || block.parentElement || block).clientWidth || 0;

        // In the pipeline note slot, fill available width and grow with content.
        // Elsewhere, keep a compact text-sized width.
        if (noteSlot) {
          input.style.width = '100%';
        } else {
          const padX = (parseFloat(styles.paddingLeft) || 0) + (parseFloat(styles.paddingRight) || 0);
          const maxW = Math.min(420, Math.max(160, hostW || 420));
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
          input.style.width = Math.max(minW, Math.min(maxW, textW)) + 'px';
        }

        input.style.height = 'auto';
        const maxH = (lineHeight * 4) + padY;
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

      if (typeof ResizeObserver !== 'undefined') {
        const noteSlot = block.closest('.hh-pipeline-note') || block;
        const ro = new ResizeObserver(function () { fitSize(); });
        ro.observe(noteSlot);
      } else {
        window.addEventListener('resize', fitSize);
      }

      fitSize();
    }

    const editModal = document.getElementById('hhAddModal');
    const editForm = document.getElementById('hhAddForm');
    const editTitle = document.getElementById('hhAddTitle');
    const editSub = document.getElementById('hhAddSub');
    const editSubmit = document.getElementById('hhAddSubmit');
    const editInterviewPick = document.getElementById('hhInterviewPick');
    const editInterviewApply = document.getElementById('hhInterviewApply');
    let editAssessmentsCache = [];
    let editModalBound = false;

    function fillEditForm(c) {
      if (!editForm || !c) return;
      const set = function (name, value) {
        const el = editForm.querySelector('[name="' + name + '"]');
        if (el) el.value = value || '';
      };
      set('full_name', c.full_name);
      set('role', c.role);
      set('department', c.department);
      set('phone', c.phone);
      set('email', c.email);
      set('replacement_name', c.replacement_name);
      set('replacement_employee_id', c.replacement_employee_id);
      set('comments', c.comments);
      const vacPick = document.getElementById('hhVacancyPick');
      const includeCurrent = c.vacancy ? {
        id: c.vacancy.id,
        label: c.vacancy.label || [c.vacancy.trade_name, c.vacancy.project_name].filter(Boolean).join(' · '),
        trade_name: c.vacancy.trade_name,
        project_name: c.vacancy.project_name,
        replacement_name: c.vacancy.replacement_name,
        replacement_employee_id: c.vacancy.replacement_employee_id,
        requirement_type: c.vacancy.requirement_type,
      } : null;
      loadVacancyPicker(vacPick, {
        roleHint: c.role || '',
        selectedId: c.vacancy_id || (c.vacancy && c.vacancy.id) || '',
        includeCurrent: includeCurrent,
      }).then(function (items) {
        if (vacPick) vacPick._hhItems = items;
      });
      bindVacancyPickerFill(vacPick, editForm);
    }

    async function loadEditAssessments() {
      if (!editInterviewPick) return;
      editInterviewPick.innerHTML = '<option value="">Loading assessments…</option>';
      if (editInterviewApply) editInterviewApply.disabled = true;
      try {
        const data = await api('/hr/api/hiring/interview-assessments?limit=40');
        editAssessmentsCache = data.assessments || [];
        if (!editAssessmentsCache.length) {
          editInterviewPick.innerHTML = '<option value="">No interview assessments found</option>';
          return;
        }
        editInterviewPick.innerHTML =
          '<option value="">Select an interview assessment…</option>' +
          editAssessmentsCache.map(function (a, i) {
            const label = a.full_name + (a.role ? ' — ' + a.role : '') +
              (a.interview_date ? ' (' + a.interview_date + ')' : '');
            return '<option value="' + i + '">' + escapeHtml(label) + '</option>';
          }).join('');
      } catch (e) {
        editInterviewPick.innerHTML = '<option value="">Could not load assessments</option>';
      }
    }

    function openEditModal() {
      const c = candidateState;
      if (!editModal || !editForm || !c) return;
      if (editTitle) editTitle.textContent = 'Edit Candidate';
      if (editSub) {
        editSub.textContent = 'Update candidate details. You can also refill name and role from an Interview Assessment.';
      }
      if (editSubmit) editSubmit.textContent = 'Save changes';
      fillEditForm(c);
      editModal.classList.add('open');
      loadEditAssessments();
      const first = editForm.querySelector('input[name="full_name"]');
      if (first) first.focus();
    }

    function closeEditModal() {
      if (!editModal) return;
      editModal.classList.remove('open');
      if (editForm) editForm.reset();
      if (editInterviewPick) {
        editInterviewPick.innerHTML = '<option value="">Select an interview assessment…</option>';
      }
      if (editInterviewApply) editInterviewApply.disabled = true;
    }

    function bindEditModal() {
      if (editModalBound || !editModal || !editForm) return;
      editModalBound = true;

      editModal.addEventListener('click', function (e) {
        if (e.target === editModal) closeEditModal();
      });
      const cancel = editModal.querySelector('[data-close]');
      if (cancel) cancel.addEventListener('click', closeEditModal);

      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && editModal.classList.contains('open')) {
          closeEditModal();
        }
      });

      if (editInterviewPick) {
        editInterviewPick.addEventListener('change', function () {
          if (editInterviewApply) editInterviewApply.disabled = editInterviewPick.value === '';
        });
      }
      if (editInterviewApply) {
        editInterviewApply.addEventListener('click', function () {
          const idx = parseInt(editInterviewPick && editInterviewPick.value, 10);
          if (Number.isNaN(idx) || !editAssessmentsCache[idx]) {
            toast('Select an interview assessment first', true);
            return;
          }
          const a = editAssessmentsCache[idx];
          const nameEl = editForm.querySelector('[name="full_name"]');
          const roleEl = editForm.querySelector('[name="role"]');
          if (nameEl) nameEl.value = a.full_name || '';
          if (roleEl) roleEl.value = a.role || '';
          toast('Filled from interview assessment');
        });
      }

      editForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        const fd = new FormData(editForm);
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
        if (editSubmit) editSubmit.disabled = true;
        try {
          const data = await api('/hr/api/hiring/candidates/' + candidateId, {
            method: 'PATCH',
            json: payload,
          });
          const vacancyId = (fd.get('vacancy_id') || '').toString().trim();
          const prevVacancyId = candidateState && (candidateState.vacancy_id || (candidateState.vacancy && candidateState.vacancy.id));
          let linked = data.candidate;
          if (vacancyId && String(vacancyId) !== String(prevVacancyId || '')) {
            const assignData = await assignCandidateVacancy(candidateId, vacancyId);
            linked = (assignData && assignData.candidate) || linked;
          } else if (!vacancyId && prevVacancyId) {
            const unData = await unassignCandidateVacancy(candidateId);
            linked = (unData && unData.candidate) || linked;
          }
          toast('Details updated');
          closeEditModal();
          if (linked) {
            render(applyCandidate(linked));
          } else {
            await load();
          }
        } catch (err) {
          toast(err.message, true);
        } finally {
          if (editSubmit) editSubmit.disabled = false;
        }
      });
    }

    function bindProfileEditors() {
      const editBtn = document.getElementById('hhEditCandidate');
      if (!editBtn) return;
      bindEditModal();
      editBtn.addEventListener('click', openEditModal);
    }

    function render(c) {
      if (!c) return;
      if (c.full_name) {
        document.title = c.full_name + ' — Hiring Documents · Injaaz';
      }
      const contacts = [];
      if (c.email) contacts.push(escapeHtml(c.email));
      if (c.phone) contacts.push(escapeHtml(c.phone));
      const pencilSvg =
        '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor" width="15" height="15" aria-hidden="true">' +
          '<path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13L2 21l1.05-2.935a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Z"/>' +
        '</svg>';
      headerEl.innerHTML =
        '<div class="hh-profile-main" id="hhProfileMain">' +
          '<div class="hh-avatar ' + avatarClass(c.full_name) + '" id="hhProfileAvatar">' + escapeHtml(c.initials || '?') + '</div>' +
          '<div class="hh-detail-meta" id="hhDetailMetaView">' +
            '<div class="hh-detail-meta-head">' +
              '<h1 id="hhProfileName">' + escapeHtml(c.full_name) + '</h1>' +
              '<button type="button" class="hh-profile-edit-btn" id="hhEditCandidate" title="Edit details" aria-label="Edit candidate details">' +
                pencilSvg +
              '</button>' +
            '</div>' +
            '<p id="hhProfileRoleLine">' + escapeHtml([c.role, c.department].filter(Boolean).join(' · ') || '—') + '</p>' +
            (contacts.length
              ? '<div class="hh-detail-contacts" id="hhProfileContacts">' + contacts.join('<span aria-hidden="true"> · </span>') + '</div>'
              : '<div class="hh-detail-contacts" id="hhProfileContacts" hidden></div>') +
          '</div>' +
        '</div>' +
        renderReplacementBlock(c) +
        renderVacancyBlock(c) +
        '<div class="hh-profile-aside">' +
          '<button type="button" class="hh-btn hh-btn-sm hh-btn-on-brand-ghost" id="hhMarkAllSubmitted">Mark all submitted</button>' +
          '<button type="button" class="hh-btn hh-btn-sm hh-btn-on-brand-danger" id="hhDeleteCandidate">Delete</button>' +
        '</div>';

      const markAllBtn = document.getElementById('hhMarkAllSubmitted');
      if (markAllBtn) {
        markAllBtn.addEventListener('click', onMarkAllSubmitted);
      }
      const deleteBtn = document.getElementById('hhDeleteCandidate');
      if (deleteBtn) {
        deleteBtn.addEventListener('click', onDeleteCandidate);
      }
      bindReplacementEditors();
      bindVacancyCard();
      bindProfileEditors();

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
        bindOfferLetterCommentEditor();
      }
    }

    function bindOfferLetterCommentEditor() {
      const input = document.getElementById('hhOfferLetterComment');
      const wrap = input && input.closest('.hh-doc-offer-comment');
      if (!input || !wrap) return;

      let lastSaved = (input.value || '').trim();
      let saving = false;

      async function saveIfChanged() {
        const value = (input.value || '').trim();
        if (value === lastSaved || saving) return;
        saving = true;
        input.disabled = true;
        try {
          const data = await api(
            '/hr/api/hiring/candidates/' + candidateId + '/documents/offer_letter/notes',
            { method: 'PATCH', json: { notes: value } }
          );
          lastSaved = value;
          wrap.classList.toggle('has-note', !!value);
          if (data.candidate) applyCandidate(data.candidate);
          toast(value ? 'Offer letter comment saved' : 'Offer letter comment cleared');
        } catch (err) {
          toast(err.message, true);
          input.value = lastSaved;
        } finally {
          saving = false;
          input.disabled = false;
        }
      }

      input.addEventListener('blur', saveIfChanged);
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          input.blur();
        }
      });
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

      const markReceivedBtn = e.target.closest('[data-mark-received]');
      if (markReceivedBtn) {
        const docType = markReceivedBtn.getAttribute('data-mark-received');
        markReceivedBtn.disabled = true;
        try {
          const data = await api(
            '/hr/api/hiring/candidates/' + candidateId + '/documents/' + encodeURIComponent(docType) + '/mark-received',
            { method: 'POST', json: {} }
          );
          toast('Marked as file uploaded (handed over in person)');
          await syncAfterDocChange(data);
        } catch (err) {
          toast(err.message, true);
        } finally {
          markReceivedBtn.disabled = false;
        }
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
          const data = await api('/hr/api/hiring/candidates/' + candidateId + '/documents/pcc/attest', { method: 'POST', json: {} });
          toast('PCC marked attested');
          await syncAfterDocChange(data);
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
        const clearMode = clearBtn.getAttribute('data-clear-mode') || 'file';
        const ok = await confirmDialog({
          title: clearMode === 'received' ? 'Clear upload mark' : 'Clear document',
          message: clearMode === 'received'
            ? 'Clear the in-person file uploaded mark for this document?'
            : 'Clear this document? The uploaded file will be removed.',
          confirmLabel: 'Clear',
          danger: true,
        });
        if (!ok) return;
        clearBtn.disabled = true;
        try {
          const data = await api('/hr/api/hiring/documents/' + id, { method: 'DELETE' });
          toast(clearMode === 'received' ? 'Upload mark cleared' : 'Document cleared');
          await syncAfterDocChange(data);
        } catch (err) {
          toast(err.message, true);
        } finally {
          clearBtn.disabled = false;
        }
      }
    }

    async function handleInPersonCheck(e) {
      const input = e.target.closest('[data-inperson-check]');
      if (!input || input.tagName !== 'INPUT') return;
      const docType = input.getAttribute('data-inperson-check');
      const checked = !!input.checked;
      const label = input.closest('.hh-doc-icon-check');
      input.disabled = true;
      try {
        if (checked) {
          const data = await api(
            '/hr/api/hiring/candidates/' + candidateId + '/documents/' + encodeURIComponent(docType) + '/mark-received',
            { method: 'POST', json: {} }
          );
          toast('Marked as file uploaded (handed over in person)');
          await syncAfterDocChange(data);
        } else {
          const docId = input.getAttribute('data-doc-id');
          if (!docId) {
            input.checked = true;
            toast('Could not clear — reload and try again', true);
            return;
          }
          const ok = await confirmDialog({
            title: 'Clear upload mark',
            message: 'Clear the in-person file uploaded mark for this document?',
            confirmLabel: 'Clear',
            danger: true,
          });
          if (!ok) {
            input.checked = true;
            return;
          }
          const data = await api('/hr/api/hiring/documents/' + docId, { method: 'DELETE' });
          toast('Upload mark cleared');
          await syncAfterDocChange(data);
        }
      } catch (err) {
        input.checked = !checked;
        if (label) label.classList.toggle('is-checked', !checked);
        toast(err.message, true);
      } finally {
        input.disabled = false;
      }
    }

    function bindChecklistDnD(el) {
      if (!el) return;
      el.addEventListener('click', handleDocClick);
      el.addEventListener('change', handleInPersonCheck);
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
        await syncAfterDocChange(data);
      } catch (err) {
        toast(err.message, true);
      }
    }

    async function onMarkAllSubmitted() {
      const ok = await confirmDialog({
        title: 'Mark all submitted',
        message: 'Mark every document as submitted? Existing uploaded files are kept. PCC will be marked attested.',
        confirmLabel: 'Mark all submitted',
      });
      if (!ok) return;
      const markAllBtn = document.getElementById('hhMarkAllSubmitted');
      if (markAllBtn) markAllBtn.disabled = true;
      try {
        const data = await api(
          '/hr/api/hiring/candidates/' + candidateId + '/mark-all-documents-submitted',
          { method: 'POST', json: {} }
        );
        toast('All documents marked as submitted');
        await syncAfterDocChange(data);
      } catch (err) {
        toast(err.message, true);
        if (markAllBtn) markAllBtn.disabled = false;
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
        window.location.href = hiringListHref();
      } catch (err) {
        toast(err.message, true);
        if (deleteBtn) deleteBtn.disabled = false;
      }
    }

    const backLink = document.querySelector('a.hh-back');
    if (backLink) {
      backLink.setAttribute('href', hiringListHref());
      // Prefer a real navigation to the list so rows refetch; history.back()
      // can restore a stale cached dashboard.
      backLink.setAttribute('data-no-history-back', '1');
    }

    const initialMarkAll = document.getElementById('hhMarkAllSubmitted');
    if (initialMarkAll) initialMarkAll.addEventListener('click', onMarkAllSubmitted);
    const initialDelete = document.getElementById('hhDeleteCandidate');
    if (initialDelete) initialDelete.addEventListener('click', onDeleteCandidate);

    load();
  }

  document.addEventListener('DOMContentLoaded', function () {
    initList();
    initDetail();
  });
})();
