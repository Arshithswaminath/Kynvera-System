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

  w.hrDisplay = { formTypeLabel: formTypeLabel, submissionRef: submissionRef };
})(window);
