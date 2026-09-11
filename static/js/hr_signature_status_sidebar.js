/**
 * HR forms — Box 1 ("Signature status") sidebar card.
 * Works on any HR form that includes #hrSigSummaryBody and hr_mgmt_chain_submit.js.
 */
(function () {
  var EMPLOYEE_FIELDS = [
    'empSigData', 'employee_signature', 'emp_signature', 'complainant_signature',
  ];
  var EMPLOYEE_IMGS = ['empSigImg', 'employeeSigImg', 'complainantSigImg'];
  var CHAIN_CAPTURE_FIELDS = {
    supervisor: ['reporting_manager_signature', 'gmSigData', 'gm_signature'],
    reporting_manager: ['reporting_manager_signature', 'gmSigData', 'gm_signature'],
    operations_manager: ['gm_signature', 'gmSigData'],
    general_manager: ['gm_signature', 'gmSigData'],
    hr_head_office: ['hr_signature', 'hrSigData'],
  };
  var CHAIN_CAPTURE_IMGS = {
    supervisor: ['rmSigImg', 'gmSigImg'],
    reporting_manager: ['rmSigImg', 'gmSigImg'],
    operations_manager: ['gmSigImg'],
    general_manager: ['gmSigImg'],
    hr_head_office: ['hrSigImg'],
  };

  function isDataUrl(v) {
    return typeof v === 'string' && v.trim().indexOf('data:image') === 0;
  }

  /** True signature asset — not an empty <img src=""> that browsers resolve to this page URL. */
  function isSignatureSrc(v) {
    if (v == null) return false;
    var s = String(v).trim();
    if (!s) return false;
    if (isDataUrl(s)) return true;
    try {
      var resolved = new URL(s, location.href).href.split('#')[0].split('?')[0];
      var page = location.href.split('#')[0].split('?')[0];
      if (resolved === page) return false;
    } catch (_e) { /* ignore */ }
    if (/^https?:\/\//i.test(s) || s.charAt(0) === '/') {
      if (/\.(png|jpe?g|gif|webp|svg|bmp)(\?|$)/i.test(s)) return true;
      if (/res\.cloudinary\.com|\/image\/upload\//i.test(s)) return true;
      return false;
    }
    return false;
  }

  function liveStepHasSignature(key) {
    var steps = window.__hrMgmtChainLiveSteps;
    if (!key || !Array.isArray(steps)) return false;
    for (var i = 0; i < steps.length; i++) {
      var st = steps[i];
      if (!st || String(st.key || '') !== String(key)) continue;
      if (isSignatureSrc(st.signature)) return true;
    }
    return false;
  }

  function fieldValue(name) {
    if (!name) return '';
    var byId = document.getElementById(name);
    if (byId && (byId.value != null || byId.getAttribute('src'))) {
      return (byId.value || byId.getAttribute('src') || '').trim();
    }
    var forms = document.querySelectorAll('form');
    for (var i = 0; i < forms.length; i++) {
      var el = forms[i].elements[name];
      if (!el) continue;
      if (el.type === 'hidden' || el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
        return (el.value || '').trim();
      }
    }
    return '';
  }

  function imgSrc(id) {
    if (!id) return '';
    var img = document.getElementById(id);
    return img ? (img.getAttribute('src') || '').trim() : '';
  }

  function hasCapture(fieldNames, imgIds) {
    var names = Array.isArray(fieldNames) ? fieldNames : [fieldNames];
    var imgs = Array.isArray(imgIds) ? imgIds : [imgIds];
    var n;
    for (n = 0; n < names.length; n++) {
      if (isSignatureSrc(fieldValue(names[n]))) return true;
    }
    for (n = 0; n < imgs.length; n++) {
      if (isSignatureSrc(imgSrc(imgs[n]))) return true;
    }
    return false;
  }

  function colleagueSigned() {
    var lists = [
      window.__leaveReplacementSigners,
      window.__hrReplacementSigners,
    ];
    for (var i = 0; i < lists.length; i++) {
      var list = lists[i];
      if (!Array.isArray(list)) continue;
      if (list.some(function (s) { return s && isDataUrl(s.signature); })) return true;
    }
    return false;
  }

  function employeeSigned() {
    return hasCapture(EMPLOYEE_FIELDS, EMPLOYEE_IMGS);
  }

  function chainStepSigned(key) {
    if (liveStepHasSignature(key)) return true;
    return hasCapture(CHAIN_CAPTURE_FIELDS[key] || [], CHAIN_CAPTURE_IMGS[key] || []);
  }

  var PATH_TO_FORM = [
    ['/hr/leave-application-form', 'leave_application'],
    ['/hr/commencement-form', 'commencement'],
    ['/hr/duty-resumption-form', 'duty_resumption'],
    ['/hr/contract-renewal-form', 'contract_renewal'],
    ['/hr/performance-evaluation-form', 'performance_evaluation'],
    ['/hr/grievance-form', 'grievance'],
    ['/hr/interview-assessment-form', 'interview_assessment'],
    ['/hr/passport-release-form', 'passport_release'],
    ['/hr/staff-appraisal-form', 'staff_appraisal'],
    ['/hr/station-clearance-form', 'station_clearance'],
    ['/hr/visa-renewal-form', 'visa_renewal'],
    ['/hr/asset-handover-form', 'asset_handover'],
    ['/hr/termination-form', 'termination'],
    ['/hr/long-vacation-form', 'long_vacation'],
    ['/hr/leave-form', 'leave'],
    ['/hr/asset-form', 'asset'],
  ];

  function detectFormType() {
    var body = document.body;
    var attr = body && body.getAttribute('data-hr-form-type');
    if (attr) return String(attr).trim();
    var path = (location.pathname || '').toLowerCase();
    var i;
    for (i = 0; i < PATH_TO_FORM.length; i++) {
      if (path.indexOf(PATH_TO_FORM[i][0]) >= 0) return PATH_TO_FORM[i][1];
    }
    return '';
  }

  function formSpec() {
    var catalog = window.__hrSigReqCatalog || {};
    var ft = detectFormType();
    if (ft && catalog[ft]) return catalog[ft];
    return {
      you_now: 'Your signature',
      you_now_count: document.getElementById('empSigData') || document.getElementById('compSigData') ? 1 : 0,
      extras: [],
    };
  }

  function updateRequiredBanner(spec, chainSigners) {
    var title = document.getElementById('hrSigRequiredTitle');
    var lede = document.getElementById('hrSigRequiredLede');
    var note = document.getElementById('hrSigStatusCountNote');
    var you = parseInt(spec.you_now_count, 10) || 0;
    var extras = Array.isArray(spec.extras) ? spec.extras : [];
    var extraReq = extras.filter(function (e) { return e && !e.optional; }).length;
    var extraOpt = extras.filter(function (e) { return e && e.optional; }).length;
    var chainN = chainSigners.length;
    var minTotal = you + extraReq + chainN;
    var parts = [];
    if (you && spec.you_now) parts.push('You now: ' + spec.you_now);
    extras.forEach(function (e) {
      if (!e || !e.label) return;
      parts.push(e.label + (e.optional ? ' (optional)' : '') + (e.note ? ' — ' + e.note : ''));
    });
    if (chainN) {
      parts.push(
        'Then ' + chainN + ' management signature' + (chainN === 1 ? '' : 's') + ': '
        + chainSigners.map(function (s) { return s.role || 'Signer'; }).join(', ')
      );
    } else {
      parts.push('Then the management chain listed below.');
    }
    var countLabel = minTotal + ' signature' + (minTotal === 1 ? '' : 's') + ' required';
    if (extraOpt) countLabel += ' (+ optional)';
    if (title) title.textContent = countLabel;
    if (lede) lede.textContent = parts.join(' ');
    if (note) note.textContent = countLabel;
    var formNotice = document.getElementById('hrSigRequiredNoticeCopy');
    if (formNotice) {
      formNotice.textContent = countLabel + '. ' + parts.join(' ');
    }
  }

  function renderRow(label, opts) {
    opts = opts || {};
    var signed = !!opts.signed;
    var required = !!opts.required;
    var workflow = !!opts.workflow;
    var missing = !!opts.missing;
    var badge = signed
      ? '<span class="duty-sig-badge duty-sig-badge--signed">Signed</span>'
      : (required || workflow || missing || !opts.optional
        ? '<span class="duty-sig-badge duty-sig-badge--pending">Pending</span>'
        : '<span class="duty-sig-badge duty-sig-badge--optional">Optional</span>');
    var signerName = (label.split(' — ')[1] || '').trim();
    var val = signed
      ? (opts.workflowSigned ? 'Signed in workflow' : 'Captured on this form')
      : (required
        ? 'Required before submit'
        : (missing
          ? 'Not assigned yet — ask an administrator'
          : (signerName
            ? 'Awaiting signature — ' + signerName
            : 'Awaiting signature in workflow')));
    return '<div class="duty-sig-summary-row"><div><span class="duty-sig-summary-label">'
      + label + '</span><div class="duty-sig-summary-value'
      + (signed ? '' : ' muted') + '">' + val + '</div></div><div>' + badge + '</div></div>';
  }

  function refreshHrSignatureSummary() {
    var mount = document.getElementById('hrSigSummaryBody');
    if (!mount) return;

    var spec = formSpec();
    var you = parseInt(spec.you_now_count, 10) || 0;
    var rows = [];
    if (you) {
      rows.push(renderRow(spec.you_now || 'Your signature', {
        required: true,
        signed: employeeSigned(),
      }));
    }

    var extras = Array.isArray(spec.extras) ? spec.extras : [];
    extras.forEach(function (e) {
      if (!e || !e.label) return;
      var isColleague = /colleague|coverage/i.test(e.label);
      rows.push(renderRow(e.label, {
        signed: isColleague ? colleagueSigned() : false,
        optional: !!e.optional,
        workflow: !e.optional,
        required: !e.optional,
      }));
    });

    if (window.__hrShowColleagueRow && !extras.some(function (e) {
      return e && /colleague|coverage/i.test(e.label || '');
    })) {
      rows.push(renderRow('Colleague / Replacement', {
        signed: colleagueSigned(),
        workflow: true,
      }));
    }

    var chainSigners = window.__hrMgmtChainSigners || [];
    chainSigners.forEach(function (s) {
      var live = liveStepHasSignature(s.key);
      var onForm = hasCapture(CHAIN_CAPTURE_FIELDS[s.key] || [], CHAIN_CAPTURE_IMGS[s.key] || []);
      rows.push(renderRow(
        (s.role || 'Signer') + (s.name ? ' — ' + s.name : ''),
        {
          signed: live || onForm,
          workflowSigned: live && !onForm,
          missing: !!s.missing,
          workflow: !s.missing,
        },
      ));
    });

    if (!chainSigners.length) {
      var lane = (window.__hrMgmtChainLane || '').toLowerCase();
      var mgrLabel = lane === 'technician'
        ? 'Supervisor signature'
        : (lane === 'supervisor' ? 'Operations manager signature' : 'General manager signature');
      rows.push(renderRow(mgrLabel, { signed: chainStepSigned('supervisor') || chainStepSigned('general_manager'), workflow: true }));
      rows.push(renderRow('HR', { signed: chainStepSigned('hr_head_office'), workflow: true }));
    }

    mount.innerHTML = rows.join('');
    updateRequiredBanner(spec, chainSigners);
    try {
      document.dispatchEvent(new CustomEvent('hr-sig-summary-refreshed'));
    } catch (_) { /* ignore */ }
  }

  window.refreshHrSignatureSummary = refreshHrSignatureSummary;
  window.setHrMgmtChainLiveSteps = function (steps) {
    window.__hrMgmtChainLiveSteps = Array.isArray(steps) ? steps : [];
    refreshHrSignatureSummary();
    try {
      document.dispatchEvent(new CustomEvent('hr-mgmt-chain-live'));
    } catch (_e) { /* ignore */ }
  };

  document.addEventListener('hr-mgmt-chain-ready', refreshHrSignatureSummary);
  document.addEventListener('DOMContentLoaded', refreshHrSignatureSummary);
  if (document.readyState !== 'loading') refreshHrSignatureSummary();

  /* Re-render when signature pads apply (common custom event on HR forms). */
  document.addEventListener('hrSignaturePreviewApplied', refreshHrSignatureSummary);

  /* Poll lightly while user is on the page — catches pad apply without events. */
  var _pollTimer = null;
  function startPollIfVisible() {
    if (_pollTimer || !document.getElementById('hrSigSummaryBody')) return;
    _pollTimer = window.setInterval(refreshHrSignatureSummary, 1200);
  }
  startPollIfVisible();
})();
