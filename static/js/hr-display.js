/** Shared HR list labels — hide snake_case IDs like HR-VISA_RENEWAL-8861C8D4. */
(function (w) {
  function formTypeLabel(type) {
    var key = String(type || '').replace(/^hr_/, '');
    var labels = {
      leave_application: 'Leave Application',
      commencement: 'Commencement',
      duty_resumption: 'Duty Resumption',
      contract_renewal: 'Contract Renewal',
      performance_evaluation: 'Performance Evaluation',
      grievance: 'Grievance',
      interview_assessment: 'Interview Assessment',
      passport_release: 'Passport Release',
      staff_appraisal: 'Staff Appraisal',
      station_clearance: 'Station Clearance',
      visa_renewal: 'Visa Renewal',
      asset_handover: 'Asset Handover',
      termination: 'Termination',
      long_vacation: 'Long Vacation',
      asset: 'Asset',
    };
    if (labels[key]) return labels[key];
    return key.replace(/_/g, ' ').replace(/\b\w/g, function (c) {
      return c.toUpperCase();
    });
  }

  function submissionRef(id) {
    var raw = String(id || '');
    var m = raw.match(/^HR-(?:[A-Z0-9_]+-)?([A-F0-9]{6,})$/i);
    if (m) return 'HR · ' + m[1].toUpperCase();
    return raw;
  }

  function chainStepRole(step) {
    if (!step || typeof step !== 'object') return '';
    if (step.key === 'hr_head_office') return 'HR';
    var raw = String(step.pdf_label || step.who_label || '').trim();
    var lowered = raw.toLowerCase();
    if (lowered.indexOf('head office') !== -1 || lowered === 'hr (ho)' || lowered === 'hr (h.o.)') {
      return 'HR';
    }
    if (lowered === 'general manager') return 'GM';
    if (lowered === 'operations manager') return 'operations manager';
    if (lowered === 'reporting manager') return 'reporting manager';
    if (lowered === 'immediate supervisor') return 'supervisor';
    return raw;
  }

  var WORKFLOW_STAGE_LABELS = {
    replacement_signoff: 'With colleagues',
    hr_review: 'With HR',
    hr_mgmt_hr_head_office: 'With HR',
    gm_review: 'With GM',
    hr_mgmt_gm: 'With GM',
    hr_mgmt_reporting_manager: 'With reporting manager',
    hr_mgmt_operations_manager: 'With operations manager',
    hr_mgmt_supervisor: 'With supervisor',
    hr_mgmt_routing_approver: 'With next approver',
    approved: 'Approved',
    completed: 'Approved',
    rejected: 'Rejected',
    withdrawn: 'Withdrawn',
  };

  function stageLabel(workflowStatus, formData) {
    var fd = formData && typeof formData === 'object' ? formData : {};
    var chain = fd.hr_mgmt_chain;
    if (chain && Array.isArray(chain.steps) && chain.steps.length) {
      var idx = Number(chain.current_index);
      if (!isFinite(idx) || idx < 0) idx = 0;
      if (idx >= chain.steps.length) return 'Approved';
      var step = chain.steps[idx];
      if (step && !step.signature) {
        var role = chainStepRole(step);
        if (role) return 'With ' + role;
      }
    }
    var w = String(workflowStatus || '').trim();
    if (WORKFLOW_STAGE_LABELS[w]) return WORKFLOW_STAGE_LABELS[w];
    if (!w) return 'In progress';
    return w.replace(/_/g, ' ').replace(/\b\w/g, function (c) {
      return c.toUpperCase();
    });
  }

  w.hrDisplay = {
    formTypeLabel: formTypeLabel,
    submissionRef: submissionRef,
    stageLabel: stageLabel,
  };
})(window);
