/**
 * Inspection Sidebar — live workflow timeline + signature status + recorded signatures.
 * Mirrors the HR leave/duty form sidebar visually (hr-signoff-activity-list +
 * duty-sig-summary-rows). Hydrates from window.preloadedSubmissionData /
 * window.submissionData and polls GET /api/workflow/submissions/<id> every 15s
 * in edit mode.
 */
(function () {
  'use strict';

  var POLL_MS = 15000;

  var SIG_INPUT_TO_KEY = {
    supervisorSignatureData: 'supervisor',
    opManSignatureData: 'opMan',
    businessDevSignatureData: 'businessDev',
    procurementSignatureData: 'procurement',
    generalManagerSignatureData: 'generalManager',
    techSignatureData: 'submitter',
    submitterSignatureData: 'submitter'
  };

  /* tech_signature / techSignatureData belong to the SUBMITTER (technician),
     not the supervisor. Keep them in their own slot so the same image never
     gets double-attributed to two different roles in the sidebar. */
  var SIG_FIELD_TO_KEY = [
    ['tech_signature', 'submitter'],
    ['techSignatureData', 'submitter'],
    ['submitter_signature', 'submitter'],
    ['supervisor_signature', 'supervisor'],
    ['supervisorSignatureData', 'supervisor'],
    ['opMan_signature', 'opMan'],
    ['operations_manager_signature', 'opMan'],
    ['businessDev_signature', 'businessDev'],
    ['business_dev_signature', 'businessDev'],
    ['businessDevSignature', 'businessDev'],
    ['procurement_signature', 'procurement'],
    ['procurementSignature', 'procurement'],
    ['generalManager_signature', 'generalManager'],
    ['general_manager_signature', 'generalManager'],
    ['generalManagerSignature', 'generalManager']
  ];

  var SIG_LABELS = {
    submitter: 'Submitter',
    supervisor: 'Supervisor',
    opMan: 'Operations Manager',
    businessDev: 'Business Development',
    procurement: 'Procurement',
    generalManager: 'General Manager'
  };

  var SIG_ROW_ORDER = [
    { key: 'submitter',      label: 'Submitter',            required: true,  hint: 'Awaiting submission' },
    { key: 'supervisor',     label: 'Supervisor',           required: true,  hint: 'Site sign-off' },
    { key: 'opMan',          label: 'Operations Manager',   required: true,  hint: 'Stage 1 approval' },
    { key: 'businessDev',    label: 'Business Development', required: true,  hint: 'Stage 2 approval' },
    { key: 'procurement',    label: 'Procurement',          required: true,  hint: 'Stage 2 approval' },
    { key: 'generalManager', label: 'General Manager',      required: true,  hint: 'Final approval' }
  ];

  var pollTimer = null;
  var lastSubmissionId = null;
  var lastFingerprint = null;

  function $(id) { return document.getElementById(id); }

  function fmtDate(iso) {
    if (!iso) return '';
    try {
      var d = new Date(iso);
      if (isNaN(d)) return '';
      return d.toLocaleString(undefined, {
        month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit'
      });
    } catch (_) { return ''; }
  }

  function userName(u) {
    if (!u) return null;
    return u.full_name || u.username ||
      (u.first_name && u.last_name ? u.first_name + ' ' + u.last_name : null);
  }

  function getSubmissionId() {
    if (window.preloadedSubmissionData && window.preloadedSubmissionData.submission_id) {
      return window.preloadedSubmissionData.submission_id;
    }
    if (window.submissionData && window.submissionData.submission_id) {
      return window.submissionData.submission_id;
    }
    var p = new URLSearchParams(window.location.search);
    return p.get('edit') || null;
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  /* ─── Workflow timeline ──────────────────────────────────────── */
  function buildSteps(data) {
    var status = (data && data.workflow_status) || null;
    var rejected = status === 'rejected';
    var rejectionStage = ((data && data.rejection_stage) || '').toLowerCase();
    var rejStageMap = {
      supervisor: 'supervisor', sup: 'supervisor',
      operations_manager: 'om', om: 'om',
      business_dev: 'bd_proc', bd: 'bd_proc', procurement: 'bd_proc', bd_procurement: 'bd_proc',
      general_manager: 'gm', gm: 'gm'
    };
    var rejTarget = rejStageMap[rejectionStage] || null;

    var steps = [];

    /* Submitted */
    var submittedAt = data && data.created_at;
    var submitter = data && userName(data.user);
    steps.push({
      id: 'submitted',
      state: data ? 'done' : 'current',
      title: data ? 'Submitted' : 'Submit form',
      time: submittedAt ? fmtDate(submittedAt) : '',
      detail: data
        ? (submitter ? 'By ' + submitter : 'Submission created')
        : 'Fill in and submit to start the chain'
    });

    /* Supervisor — only "done" after formal supervisor review, not on submitter sig */
    var supAt = data && data.supervisor_reviewed_at;
    var supNm = data && userName(data.supervisor);
    var pastSupervisor = [
      'operations_manager_review', 'operations_manager_approved',
      'bd_procurement_review', 'general_manager_review', 'completed'
    ].indexOf(status) >= 0;
    var supDone = !!(supAt || pastSupervisor);
    var supIsCurrent = !!data && !supDone && (
      status === 'supervisor_review' ||
      status === 'supervisor_notified' ||
      status === 'submitted'
    );
    steps.push({
      id: 'supervisor',
      state: rejected && rejTarget === 'supervisor'
        ? 'rejected'
        : supDone ? 'done' : (supIsCurrent ? 'current' : 'pending'),
      title: 'Supervisor',
      time: supAt ? fmtDate(supAt) : '',
      detail: supDone
        ? (supNm ? 'Reviewed by ' + supNm : 'Supervisor signed off')
        : (supIsCurrent ? 'Awaiting supervisor review' : 'Pending review')
    });

    /* OM */
    var omAt = data && data.operations_manager_approved_at;
    var omNm = data && userName(data.operations_manager);
    var omIsCurrent = !!data && status === 'operations_manager_review';
    steps.push({
      id: 'om',
      state: rejected && rejTarget === 'om'
        ? 'rejected'
        : omAt ? 'done' : (omIsCurrent ? 'current' : 'pending'),
      title: 'Operations Manager',
      time: omAt ? fmtDate(omAt) : '',
      detail: omAt
        ? (omNm ? 'Approved by ' + omNm : 'Approved')
        : (omIsCurrent ? 'Awaiting review' : 'Pending review')
    });

    /* BD + Procurement */
    var bdAt = data && data.business_dev_approved_at;
    var procAt = data && data.procurement_approved_at;
    var bdNm = data && userName(data.business_dev);
    var procNm = data && userName(data.procurement);
    var bdProcCurrent = !!data &&
      (status === 'bd_procurement_review' || status === 'operations_manager_approved');
    var bdProcDone = bdAt && procAt;
    var bdProcDetail;
    if (bdProcDone) {
      bdProcDetail = 'BD: ' + (bdNm || 'signed') + ' · Procurement: ' + (procNm || 'signed');
    } else if (bdAt) {
      bdProcDetail = 'BD signed' + (bdNm ? ' (' + bdNm + ')' : '') + ' · awaiting Procurement';
    } else if (procAt) {
      bdProcDetail = 'Procurement signed' + (procNm ? ' (' + procNm + ')' : '') + ' · awaiting BD';
    } else if (bdProcCurrent) {
      bdProcDetail = 'Awaiting BD & Procurement';
    } else {
      bdProcDetail = 'Pending review';
    }
    steps.push({
      id: 'bd_proc',
      state: rejected && rejTarget === 'bd_proc'
        ? 'rejected'
        : bdProcDone ? 'done' : (bdProcCurrent ? 'current' : 'pending'),
      title: 'BD & Procurement',
      time: bdProcDone ? fmtDate(procAt || bdAt) : (bdAt || procAt ? fmtDate(bdAt || procAt) : ''),
      detail: bdProcDetail
    });

    /* GM */
    var gmAt = data && data.general_manager_approved_at;
    var gmNm = data && userName(data.general_manager);
    var gmIsCurrent = !!data && status === 'general_manager_review';
    steps.push({
      id: 'gm',
      state: rejected && rejTarget === 'gm'
        ? 'rejected'
        : gmAt ? 'done' : (gmIsCurrent ? 'current' : 'pending'),
      title: 'General Manager',
      time: gmAt ? fmtDate(gmAt) : '',
      detail: gmAt
        ? (gmNm ? 'Approved by ' + gmNm : 'Approved')
        : (gmIsCurrent ? 'Awaiting review' : 'Pending review')
    });

    /* Completed */
    var done = !!data && status === 'completed';
    steps.push({
      id: 'completed',
      state: done ? 'done' : (rejected ? 'pending' : 'pending'),
      title: 'Completed',
      time: '',
      detail: done ? 'Trail complete' : (rejected ? 'Halted by rejection' : 'Trail complete')
    });

    /* Replace rejected stage detail with reason. */
    if (rejected && data && data.rejection_reason && rejTarget) {
      for (var i = 0; i < steps.length; i++) {
        if (steps[i].id === rejTarget) {
          steps[i].detail = 'Rejected: ' + data.rejection_reason;
          break;
        }
      }
    }

    return steps;
  }

  function workflowBadgePersonLine(data) {
    if (!data) return '';
    var status = data.workflow_status || '';
    var submitter = userName(data.user) || userName(data.supervisor);
    var sup = userName(data.supervisor);
    var om = userName(data.operations_manager);
    var gm = userName(data.general_manager);
    var bd = userName(data.business_dev);
    var proc = userName(data.procurement);

    if (status === 'supervisor_review' || status === 'supervisor_notified') {
      return submitter ? 'By ' + submitter : (sup ? 'Assigned to ' + sup : '');
    }
    if (status === 'submitted' || status === 'operations_manager_review') {
      return submitter ? 'By ' + submitter : '';
    }
    if (status === 'operations_manager_approved') {
      return om ? 'Approved by ' + om : (submitter ? 'By ' + submitter : '');
    }
    if (status === 'bd_procurement_review') {
      if (bd && proc) return 'BD: ' + bd + ' · Procurement: ' + proc;
      if (bd) return 'BD signed (' + bd + ') · awaiting Procurement';
      if (proc) return 'Procurement signed (' + proc + ') · awaiting BD';
      return submitter ? 'By ' + submitter : '';
    }
    if (status === 'general_manager_review') {
      return gm ? 'Awaiting ' + gm : (submitter ? 'By ' + submitter : '');
    }
    if (status === 'completed') {
      return gm ? 'Approved by ' + gm : (submitter ? 'By ' + submitter : '');
    }
    return submitter ? 'By ' + submitter : '';
  }

  function workflowBadgeMainLabel(data) {
    if (!data) return '';
    var status = data.workflow_status || '';
    return ({
      submitted: 'Submitted — awaiting Supervisor',
      supervisor_review: 'Awaiting Supervisor review',
      supervisor_notified: 'Awaiting Supervisor review',
      operations_manager_review: 'Stage 1 — Operations Manager review',
      operations_manager_approved: 'Stage 1 approved — moving to BD & Procurement',
      bd_procurement_review: 'Stage 2 — BD & Procurement review',
      general_manager_review: 'Stage 3 — General Manager review',
      completed: 'Completed — trail closed',
      rejected: 'Rejected' + (data.rejection_reason ? ': ' + data.rejection_reason : ''),
      closed_by_admin: 'Closed by Admin'
    })[status] || ('Status: ' + status);
  }

  function renderWorkflow(data) {
    var ul = $('ifWorkflowTimeline');
    if (!ul) return;
    var steps = buildSteps(data);
    var html = steps.map(function (s) {
      var stateCls = ' is-' + s.state;
      var time = s.time ? '<span class="hr-signoff-activity-time">' + escapeHtml(s.time) + '</span>' : '';
      var detail = s.detail ? '<div class="hr-signoff-activity-detail">' + escapeHtml(s.detail) + '</div>' : '';
      return '<li class="hr-signoff-activity-item' + stateCls + '" data-step="' + s.id + '">' +
             '<span class="hr-signoff-activity-dot" aria-hidden="true"></span>' +
             '<div class="hr-signoff-activity-stack">' +
               '<div class="hr-signoff-activity-title">' + escapeHtml(s.title) + '</div>' +
               time + detail +
             '</div>' +
             '</li>';
    }).join('');
    ul.innerHTML = html;

    /* Live note + workflow badge. */
    var liveNote = $('ifWfLiveNote');
    var badge = $('ifWfBadge');
    if (data) {
      if (liveNote) liveNote.hidden = false;
      if (badge) {
        var main = workflowBadgeMainLabel(data);
        var person = workflowBadgePersonLine(data);
        if (person) {
          badge.innerHTML =
            '<span class="if-wf-badge-main">' + escapeHtml(main) + '</span>' +
            '<span class="if-wf-badge-person">' + escapeHtml(person) + '</span>';
        } else {
          badge.textContent = main;
        }
        badge.style.display = 'block';
      }
    } else {
      if (liveNote) liveNote.hidden = true;
      if (badge) badge.style.display = 'none';
    }
  }

  /* ─── Signature status (form pads + persisted data) ──────────── */
  function parseFormData(raw) {
    if (raw == null) return {};
    if (typeof raw === 'string') {
      try { return JSON.parse(raw); } catch (_) { return {}; }
    }
    return typeof raw === 'object' ? raw : {};
  }

  /** Top-level form_data fields plus nested form_data.data (legacy shape). */
  function flattenFormDataForLookup(data) {
    var fd = parseFormData(data && data.form_data != null ? data.form_data : null);
    var out = {};
    var nested = fd.data;
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      Object.keys(nested).forEach(function (k) { out[k] = nested[k]; });
    }
    Object.keys(fd).forEach(function (k) {
      if (k !== 'data') out[k] = fd[k];
    });
    return out;
  }

  function readPadValue(domId) {
    var el = $(domId);
    if (!el) return '';
    var v = el.value || '';
    return v && v.length > 80 ? v : '';
  }

  function getSignatureKeysFromForm(data) {
    data = data || window.preloadedSubmissionData || window.submissionData || null;
    var signed = {};
    Object.keys(SIG_INPUT_TO_KEY).forEach(function (id) {
      if (readPadValue(id)) signed[SIG_INPUT_TO_KEY[id]] = true;
    });
    /* Legacy: submitter capture reused supervisorSignatureData before supervisor review */
    if (readPadValue('supervisorSignatureData') && !supervisorActuallySigned(data)) {
      signed.submitter = true;
      delete signed.supervisor;
    }
    /* Hidden inputs may still hold the submitter's legacy signature in
       supervisorSignatureData — do not count that as supervisor signed. */
    if (signed.supervisor && !supervisorActuallySigned(data)) {
      delete signed.supervisor;
    }
    return signed;
  }

  function sigValuePresent(v) {
    if (!v) return false;
    if (typeof v === 'string') return v.length > 80;
    /* Cloudinary / object form: {url, is_cloud, ...} */
    if (typeof v === 'object') {
      var url = v.url || v.saved || v.path || v.data || '';
      return typeof url === 'string' && url.length > 10;
    }
    return false;
  }

  /* True only when the assigned supervisor has formally reviewed — not when
     a technician's initial signature was (legacy) stored in supervisor_signature. */
  function supervisorActuallySigned(data) {
    if (!data) return false;
    if (data.supervisor_reviewed_at) return true;
    var st = String(data.workflow_status || '');
    return [
      'operations_manager_review', 'operations_manager_approved',
      'bd_procurement_review', 'general_manager_review', 'completed'
    ].indexOf(st) >= 0;
  }

  function getSignatureKeysFromData(data) {
    var signed = {};
    if (!data) return signed;
    var flatFd = flattenFormDataForLookup(data);
    SIG_FIELD_TO_KEY.forEach(function (pair) {
      var k = pair[0], key = pair[1];
      var v = flatFd[k];
      if (!sigValuePresent(v) && data[k] != null) v = data[k];
      if (sigValuePresent(v)) signed[key] = true;
    });

    /* Legacy submissions: technician signed on submit but signature landed in
       supervisor_signature because the old form reused that field. Re-attribute
       to submitter until the real supervisor has reviewed. */
    if (signed.supervisor && !supervisorActuallySigned(data)) {
      signed.submitter = true;
      delete signed.supervisor;
    } else if (!signed.submitter) {
      var legacySig = flatFd.supervisor_signature || data.supervisor_signature;
      if (sigValuePresent(legacySig) && !supervisorActuallySigned(data)) {
        signed.submitter = true;
      }
    }

    /* Supervisor row only counts after formal supervisor review */
    if (signed.supervisor && !supervisorActuallySigned(data)) {
      delete signed.supervisor;
    }

    if (submitterSignatureDetected(data, flatFd, signed)) {
      signed.submitter = true;
    }

    return signed;
  }

  function submitterSignatureDetected(data, flatFd, signedFromFields) {
    if (signedFromFields && signedFromFields.submitter) return true;
    if (getSigFieldPresent(flatFd, data, 'tech_signature')) return true;
    if (getSigFieldPresent(flatFd, data, 'submitter_signature')) return true;
    if (getSigFieldPresent(flatFd, data, 'techSignatureData')) return true;
    if (!supervisorActuallySigned(data) && getSigFieldPresent(flatFd, data, 'supervisor_signature')) {
      return true;
    }
    if (readPadValue('techSignatureData')) return true;
    if (readPadValue('supervisorSignatureData') && !supervisorActuallySigned(data)) return true;
    var frame = document.getElementById('submitterSignoffSigFrame');
    if (frame && !frame.classList.contains('is-empty')) {
      var img = frame.querySelector('img[src]');
      if (img && String(img.getAttribute('src') || '').length > 10) return true;
    }
    if (data && data.submission_id && data.workflow_status && String(data.workflow_status) !== 'draft') {
      return true;
    }
    if (data && data.created_at && data.status && String(data.status) !== 'draft') {
      return true;
    }
    return false;
  }

  function getSigFieldPresent(flatFd, data, fieldKey) {
    if (sigValuePresent(flatFd[fieldKey])) return true;
    if (data && sigValuePresent(data[fieldKey])) return true;
    return false;
  }

  function mergePersistedFormData(apiData) {
    if (!apiData) return apiData;
    var preload = window.preloadedSubmissionData || window.submissionData;
    if (!preload) return apiData;
    var merged = Object.assign({}, apiData);
    var apiFlat = flattenFormDataForLookup(apiData);
    var preFlat = flattenFormDataForLookup(preload);
    var outFd = Object.assign({}, parseFormData(apiData.form_data));
    SIG_FIELD_TO_KEY.forEach(function (pair) {
      var k = pair[0];
      if (!sigValuePresent(outFd[k]) && !sigValuePresent(apiFlat[k]) && sigValuePresent(preFlat[k])) {
        outFd[k] = preFlat[k];
      } else if (!sigValuePresent(outFd[k]) && sigValuePresent(apiFlat[k])) {
        outFd[k] = apiFlat[k];
      }
    });
    merged.form_data = outFd;
    if (!merged.user && preload.user) merged.user = preload.user;
    return merged;
  }

  function formatDesignation(u) {
    if (!u) return '';
    var d = String(u.designation || u.job_designation || u.role || '').trim().toLowerCase();
    var labels = {
      technician: 'Technician',
      supervisor: 'Supervisor',
      manager: 'Manager',
      operations_manager: 'Operations Manager',
      business_development: 'Business Development',
      procurement: 'Procurement',
      general_manager: 'General Manager',
      admin: 'Admin',
      user: 'Staff'
    };
    return labels[d] || d.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function resolveSigner(key, data) {
    if (!data) return null;
    var u;
    if (key === 'submitter') u = data.user;
    else if (key === 'opMan') u = data.operations_manager;
    else if (key === 'businessDev') u = data.business_dev;
    else if (key === 'procurement') u = data.procurement;
    else if (key === 'generalManager') u = data.general_manager;
    else if (key === 'supervisor') {
      /* The supervisor row is only "signed" when the assigned supervisor has
         actually reviewed (supervisor_reviewed_at is set). Until then we leave
         it empty so the technician's submitter signature isn't mis-attributed
         to the supervisor. */
      u = data.supervisor || null;
    }
    if (!u) return null;
    return {
      name: userName(u),
      role: formatDesignation(u)
    };
  }

  function getSignerName(key, data) {
    var s = resolveSigner(key, data);
    return s ? s.name : null;
  }

  function renderSignatureRows(persisted, data) {
    var mount = $('ifSignatureRows');
    if (!mount) return;
    data = data || window.preloadedSubmissionData || window.submissionData || null;
    if (!persisted) persisted = getSignatureKeysFromData(data);
    var fromForm = getSignatureKeysFromForm(data);
    var html = SIG_ROW_ORDER.map(function (r) {
      var signed = !!(fromForm[r.key] || (persisted && persisted[r.key]));
      /* Supervisor is only signed after formal review — never from stale form data */
      if (r.key === 'supervisor' && !supervisorActuallySigned(data)) {
        signed = false;
      }
      if (r.key === 'submitter' && !signed) {
        signed = submitterSignatureDetected(data, flattenFormDataForLookup(data), persisted || {});
      }
      var signer = signed ? resolveSigner(r.key, data) : null;
      var rowLabel = signed && signer && signer.role ? signer.role : r.label;
      var value;
      if (signed) {
        if (signer && signer.name) {
          value = escapeHtml(signer.name + ' signed');
        } else if (r.key === 'submitter') {
          value = 'Submitted';
        } else {
          value = 'Signed';
        }
      } else {
        value = escapeHtml(r.hint || 'Pending');
      }
      var badge = signed
        ? '<span class="duty-sig-badge duty-sig-badge--signed">' + (r.key === 'submitter' ? 'Submitted' : 'Signed') + '</span>'
        : '<span class="duty-sig-badge duty-sig-badge--pending">Pending</span>';
      return '<div class="duty-sig-summary-row" data-sig="' + r.key + '">' +
               '<div>' +
                 '<span class="duty-sig-summary-label">' + escapeHtml(rowLabel) + '</span>' +
                 '<div class="duty-sig-summary-value' + (signed ? '' : ' muted') + '">' + value + '</div>' +
               '</div>' +
               '<div>' + badge + '</div>' +
             '</div>';
    }).join('');
    if (window.__ifSigRowsFp === html) return;
    window.__ifSigRowsFp = html;
    mount.innerHTML = html;
  }

  /* ─── Inspection summary (live form fields) ──────────────────── */
  /* Ordered list of [field id, label]. First match wins per row, so we can
     support all three inspection forms without per-form config. */
  var SUMMARY_FIELDS = [
    [['project_name', 'site_name'], 'Project / Site'],
    [['date', 'visit_date', 'date_of_visit'], 'Date'],
    [['area', 'area_other'], 'Area'],
    [['description_of_work'], 'Scope of work'],
    [['general_comments'], 'General comments'],
    [['supervisorComments'], 'Supervisor comments'],
    [['operationsManagerComments'], 'Operations Manager'],
    [['businessDevComments'], 'Business Development'],
    [['procurementComments'], 'Procurement'],
    [['generalManagerComments'], 'General Manager']
  ];

  function readField(ids) {
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (!el) continue;
      var v = '';
      if (el.tagName === 'SELECT') {
        var opt = el.options[el.selectedIndex];
        v = opt ? (opt.text || opt.value || '') : '';
        if (v === '-- Select --' || v === 'Select...') v = '';
      } else {
        v = el.value || '';
      }
      v = String(v).trim();
      if (v) return v;
    }
    return '';
  }

  function fmtSummaryDate(s) {
    if (!s || !/^\d{4}-\d{2}-\d{2}/.test(s)) return s;
    try {
      var d = new Date(s);
      if (isNaN(d.getTime())) return s;
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
    } catch (_) { return s; }
  }

  function truncate(s, n) {
    if (!s) return '';
    s = String(s);
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }

  /* Pull a short, human-readable label out of an items container.
     Supports all three inspection forms:
       • HVAC-MEP   → #itemsList children with .meta lines (Asset/System/Description)
       • Civil      → #workItemsContainer .work-item-block (work_desc[] / material[])
     Returns { count, descriptions: [..short labels..] } */
  function collectItems() {
    var out = { count: 0, descriptions: [] };

    /* HVAC items */
    var hvacList = document.getElementById('itemsList');
    if (hvacList) {
      var hvacCards = hvacList.querySelectorAll('.item-card, .hvac-item-card');
      hvacCards.forEach(function (card) {
        var asset = '';
        var system = '';
        var description = '';
        card.querySelectorAll('.meta').forEach(function (m) {
          var t = (m.textContent || '').trim();
          var assetM = t.match(/Asset:\s*([^\n]+?)(?:\s+System:|$)/i);
          var sysM = t.match(/System:\s*([^\n]+)/i);
          var descM = t.match(/Description:\s*([^\n]+)/i);
          if (assetM) asset = assetM[1].trim();
          if (sysM) system = sysM[1].trim();
          if (descM) description = descM[1].trim();
        });
        var label = description || [asset, system].filter(Boolean).join(' · ');
        if (label) out.descriptions.push(label);
      });
      out.count += hvacCards.length;
    }

    /* Civil work items */
    var civilContainer = document.getElementById('workItemsContainer');
    if (civilContainer) {
      var blocks = civilContainer.querySelectorAll('.work-item-block');
      blocks.forEach(function (block) {
        var desc = (block.querySelector('input[name="work_desc[]"]') || {}).value || '';
        var mat = (block.querySelector('input[name="material[]"]') || {}).value || '';
        var qty = (block.querySelector('input[name="work_qty[]"]') || {}).value || '';
        desc = String(desc).trim();
        mat = String(mat).trim();
        qty = String(qty).trim();
        if (!desc && !mat && !qty) return; /* skip blank rows */
        var bits = [];
        if (desc) bits.push(desc);
        else if (mat) bits.push(mat);
        if (qty) bits.push('×' + qty);
        out.count += 1;
        if (bits.length) out.descriptions.push(bits.join(' '));
      });
    }

    return out;
  }

  /* Pull selected materials from any of the three pickers. */
  function collectMaterials() {
    var picker = window.hvacMaterialsPicker || window.civilMaterialsPicker || window.cleaningMaterialsPicker;
    if (!picker || typeof picker.getSelected !== 'function') return { count: 0, names: [] };
    var sel = [];
    try { sel = picker.getSelected() || []; } catch (_) { sel = []; }
    if (!Array.isArray(sel)) sel = [];
    var names = sel.map(function (m) {
      if (!m) return '';
      var name = m.name || m.material_name || m.label || m.title || m.code || '';
      var qty = m.quantity || m.qty || '';
      var unit = m.unit || '';
      var s = String(name).trim();
      if (!s) return '';
      if (qty) s += ' ×' + qty + (unit ? ' ' + unit : '');
      return s;
    }).filter(Boolean);
    return { count: sel.length, names: names };
  }

  function summariseItems(items) {
    if (!items.count) return '';
    var n = items.count;
    var head = n + ' item' + (n === 1 ? '' : 's') + ' added';
    if (!items.descriptions.length) return head;
    var preview = items.descriptions.slice(0, 3).map(function (d) { return truncate(d, 60); });
    var extra = items.descriptions.length > 3 ? ' +' + (items.descriptions.length - 3) + ' more' : '';
    return head + ': ' + preview.join('; ') + extra;
  }

  function summariseMaterials(mats) {
    if (!mats.count) return '';
    var head = mats.count + ' material' + (mats.count === 1 ? '' : 's') + ' selected';
    if (!mats.names.length) return head;
    var preview = mats.names.slice(0, 4).map(function (n) { return truncate(n, 50); });
    var extra = mats.names.length > 4 ? ' +' + (mats.names.length - 4) + ' more' : '';
    return head + ': ' + preview.join(', ') + extra;
  }

  function renderSummary() {
    var list = $('ifSummaryList');
    var empty = $('ifSummaryEmpty');
    if (!list || !empty) return;

    var rows = [];
    SUMMARY_FIELDS.forEach(function (cfg) {
      var ids = cfg[0], label = cfg[1];
      var v = readField(ids);
      if (!v) return;
      if (ids.indexOf('date') !== -1 || ids.indexOf('visit_date') !== -1 || ids.indexOf('date_of_visit') !== -1) {
        v = fmtSummaryDate(v);
      }
      rows.push({ label: label, value: truncate(v, 220) });
    });

    var items = collectItems();
    var itemsLine = summariseItems(items);
    if (itemsLine) rows.push({ label: 'Inspection items', value: itemsLine });

    var mats = collectMaterials();
    var matsLine = summariseMaterials(mats);
    if (matsLine) rows.push({ label: 'Materials', value: matsLine });

    if (!rows.length) {
      if (!list.hidden || list.innerHTML) {
        list.hidden = true;
        list.innerHTML = '';
      }
      empty.hidden = false;
      window.__ifSummaryFp = '';
      return;
    }

    var html = rows.map(function (r) {
      return '<div class="if-summary-row">' +
               '<span class="if-summary-label">' + escapeHtml(r.label) + '</span>' +
               '<div class="if-summary-value">' + escapeHtml(r.value) + '</div>' +
             '</div>';
    }).join('');

    /* Avoid rewriting identical markup — prevents the load/flicker jump */
    if (window.__ifSummaryFp === html) return;
    window.__ifSummaryFp = html;

    empty.hidden = true;
    list.hidden = false;
    list.innerHTML = html;
  }

  function bindSummaryListeners() {
    if (window.__ifSummaryBound) return;
    window.__ifSummaryBound = true;

    var allIds = [];
    SUMMARY_FIELDS.forEach(function (cfg) { cfg[0].forEach(function (id) { allIds.push(id); }); });
    allIds.forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      ['input', 'change'].forEach(function (ev) {
        el.addEventListener(ev, renderSummary);
      });
    });

    /* Watch items containers for add/remove + nested edits */
    if (window.MutationObserver) {
      ['itemsList', 'workItemsContainer'].forEach(function (id) {
        var el = document.getElementById(id);
        if (!el) return;
        var obs = new MutationObserver(function () { renderSummary(); });
        obs.observe(el, { childList: true, subtree: true, characterData: true });
        el.addEventListener('input', renderSummary);
        el.addEventListener('change', renderSummary);
      });
    }

    /* Light poll keeps materials picker (which doesn't dispatch global events)
       in sync without flooding the form with listeners. */
    if (!window.__ifSummaryPoll) {
      window.__ifSummaryPoll = setInterval(renderSummary, 1500);
    }
  }

  /* ─── Polling ────────────────────────────────────────────────── */
  function fingerprint(d) {
    if (!d) return '';
    return [
      d.workflow_status,
      d.supervisor_reviewed_at,
      d.operations_manager_approved_at, d.business_dev_approved_at,
      d.procurement_approved_at, d.general_manager_approved_at,
      d.rejected_at, d.rejection_reason
    ].join('|');
  }

  function authHeaders() {
    var t = null;
    try { t = localStorage.getItem('access_token'); } catch (_) {}
    return t ? { Authorization: 'Bearer ' + t } : {};
  }

  function pollOnce() {
    var sid = lastSubmissionId;
    if (!sid) return Promise.resolve();
    return fetch('/api/workflow/submissions/' + encodeURIComponent(sid), {
      headers: authHeaders(),
      credentials: 'same-origin'
    }).then(function (r) {
      if (!r.ok) return null;
      return r.json();
    }).then(function (j) {
      if (!j) return;
      var data = mergePersistedFormData((j && j.data) ? j.data : j);
      var fp = fingerprint(data);
      if (fp !== lastFingerprint) {
        lastFingerprint = fp;
        renderWorkflow(data);
        renderSignatureRows(getSignatureKeysFromData(data), data);
        renderSummary();
      }
    }).catch(function () { /* ignore network errors */ });
  }

  function startPolling() {
    if (pollTimer || !lastSubmissionId) return;
    pollTimer = setInterval(function () {
      if (document.hidden) return;
      pollOnce();
    }, POLL_MS);
  }

  /* ─── Signature pad live binding ─────────────────────────────── */
  function bindPadListeners() {
    Object.keys(SIG_INPUT_TO_KEY).forEach(function (id) {
      var el = $(id);
      if (!el || el.__ifSidebarBound) return;
      el.__ifSidebarBound = true;
      ['change', 'input'].forEach(function (ev) {
        el.addEventListener(ev, function () { renderSignatureRows(); });
      });
    });
    if (window.MutationObserver) {
      Object.keys(SIG_INPUT_TO_KEY).forEach(function (id) {
        var el = $(id);
        if (!el || el.__ifSidebarObs) return;
        var obs = new MutationObserver(function () { renderSignatureRows(); });
        obs.observe(el, { attributes: true, attributeFilter: ['value'] });
        el.__ifSidebarObs = obs;
      });
    }
    if (!window.__ifSidebarSigPoll) {
      window.__ifSidebarSigPoll = setInterval(function () { renderSignatureRows(); }, 2500);
    }
  }

  /* ─── Watermark hide on first stroke ─────────────────────────── */
  /* Look up the SignaturePad instance on a canvas (set by sig pad library or
     any of the form scripts that store them on `window.pads`). */
  function findPadInstance(canvas) {
    if (!canvas) return null;
    if (canvas._signaturePad) return canvas._signaturePad;
    var byId = window.pads || {};
    var keys = Object.keys(byId);
    for (var i = 0; i < keys.length; i++) {
      var p = byId[keys[i]];
      if (p && p.canvas === canvas) return p;
    }
    return null;
  }

  function isCanvasBlank(canvas) {
    try {
      var ctx = canvas.getContext('2d');
      var data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      for (var i = 3; i < data.length; i += 4) {
        if (data[i] !== 0) return false;
      }
      return true;
    } catch (_) { return false; }
  }

  function syncWatermark(container) {
    var canvas = container.__ifCanvas;
    if (!canvas) return;
    var pad = findPadInstance(canvas);
    var hidden = container.__ifHidden;
    var hasSig = false;
    if (pad && typeof pad.isEmpty === 'function') hasSig = !pad.isEmpty();
    else if (hidden && hidden.value && hidden.value.trim()) hasSig = true;
    else hasSig = !isCanvasBlank(canvas);
    container.classList.toggle('has-signature', hasSig);
  }

  function bindWatermarkHide() {
    document.querySelectorAll('.signature-container').forEach(function (container) {
      var canvas = container.querySelector('canvas.signature-pad');
      if (!canvas) return;
      container.__ifCanvas = canvas;
      container.__ifHidden = container.querySelector('input[type="hidden"]') ||
        (canvas.id ? document.getElementById(canvas.id.replace('Pad', 'Data')) : null);

      if (!container.__ifWatermarkBound) {
        container.__ifWatermarkBound = true;

        ['pointerdown', 'mousedown', 'touchstart'].forEach(function (ev) {
          canvas.addEventListener(ev, function () {
            container.classList.add('has-signature');
          }, { passive: true });
        });

        /* clear buttons inside the same container */
        container.querySelectorAll('button').forEach(function (btn) {
          var id = (btn.id || '').toLowerCase();
          if (id.indexOf('clear') !== -1) {
            btn.addEventListener('click', function () {
              setTimeout(function () { syncWatermark(container); }, 30);
            });
          }
        });

        if (container.__ifHidden) {
          container.__ifHidden.addEventListener('change', function () { syncWatermark(container); });
        }
      }

      syncWatermark(container);
    });

    if (!window.__ifWatermarkPoll) {
      window.__ifWatermarkPoll = setInterval(function () {
        document.querySelectorAll('.signature-container').forEach(syncWatermark);
      }, 600);
    }
  }

  /* ─── Public API ─────────────────────────────────────────────── */
  function init() {
    if (!$('ifWorkflowTimeline')) return;
    lastSubmissionId = getSubmissionId();

    var preload = window.preloadedSubmissionData || window.submissionData || null;
    renderWorkflow(preload);
    renderSignatureRows(getSignatureKeysFromData(preload), preload);
    renderSummary();

    bindPadListeners();
    bindWatermarkHide();
    bindSummaryListeners();

    if (lastSubmissionId) {
      pollOnce();
      startPolling();
    }

    /* Re-check signature rows once DOM sign-off cards are fully painted */
    setTimeout(function () { renderSignatureRows(); }, 150);
  }

  window.InspectionSidebar = {
    init: init,
    refresh: function (data) {
      bindPadListeners();
      bindWatermarkHide();
      bindSummaryListeners();
      renderSummary();
      if (data) {
        data = mergePersistedFormData(data) || data;
        renderWorkflow(data);
        renderSignatureRows(getSignatureKeysFromData(data), data);
      } else {
        var preload = mergePersistedFormData(window.preloadedSubmissionData || window.submissionData || null)
          || window.preloadedSubmissionData || window.submissionData || null;
        renderSignatureRows(getSignatureKeysFromData(preload), preload);
        if (lastSubmissionId) pollOnce();
      }
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
