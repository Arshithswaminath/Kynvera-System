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
    operations_manager: ['gm_signature', 'gmSigData'],
    general_manager: ['gm_signature', 'gmSigData'],
    hr_head_office: ['hr_signature', 'hrSigData'],
  };
  var CHAIN_CAPTURE_IMGS = {
    supervisor: ['rmSigImg', 'gmSigImg'],
    operations_manager: ['gmSigImg'],
    general_manager: ['gmSigImg'],
    hr_head_office: ['hrSigImg'],
  };

  function isDataUrl(v) {
    return typeof v === 'string' && v.trim().indexOf('data:image') === 0;
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
      if (isDataUrl(fieldValue(names[n]))) return true;
    }
    for (n = 0; n < imgs.length; n++) {
      var u = imgSrc(imgs[n]);
      if (isDataUrl(u) || u.indexOf('http://') === 0 || u.indexOf('https://') === 0 || u.indexOf('/') === 0) {
        return true;
      }
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
    return hasCapture(CHAIN_CAPTURE_FIELDS[key] || [], CHAIN_CAPTURE_IMGS[key] || []);
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
      ? 'Captured on this form'
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

    var rows = [
      renderRow('Employee signature', {
        required: true,
        signed: employeeSigned(),
      }),
    ];
    if (window.__hrShowColleagueRow) {
      rows.push(renderRow('Colleague / Replacement', {
        signed: colleagueSigned(),
        workflow: true,
      }));
    }

    var chainSigners = window.__hrMgmtChainSigners || [];
    chainSigners.forEach(function (s) {
      rows.push(renderRow(
        (s.role || 'Signer') + (s.name ? ' — ' + s.name : ''),
        {
          signed: chainStepSigned(s.key),
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
      rows.push(renderRow('HR (head office)', { signed: chainStepSigned('hr_head_office'), workflow: true }));
    }

    mount.innerHTML = rows.join('');
    try {
      document.dispatchEvent(new CustomEvent('hr-sig-summary-refreshed'));
    } catch (_) { /* ignore */ }
  }

  window.refreshHrSignatureSummary = refreshHrSignatureSummary;

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
