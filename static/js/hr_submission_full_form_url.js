/**
 * Resolves the same URL used by Submitted Forms → View Form for HR submissions:
 * dedicated /hr/...?edit=<id> when available, otherwise /hr/print/<id>.
 */
(function (global) {
  'use strict';

  var HR_FORM_PATHS = {
    hr_leave_application: '/hr/leave-application-form',
    hr_leave: '/hr/leave-application-form',
    hr_commencement: '/hr/commencement-form',
    hr_duty_resumption: '/hr/duty-resumption-form',
    hr_contract_renewal: '/hr/contract-renewal-form',
    hr_performance_evaluation: '/hr/performance-evaluation-form',
    hr_grievance: '/hr/grievance-form',
    hr_interview_assessment: '/hr/interview-assessment-form',
    hr_passport_release: '/hr/passport-release-form',
    hr_staff_appraisal: '/hr/staff-appraisal-form',
    hr_station_clearance: '/hr/station-clearance-form',
    hr_visa_renewal: '/hr/visa-renewal-form',
    hr_asset_handover: '/hr/asset-handover-form',
  };

  function getHrSubmissionFullFormViewUrl(moduleType, submissionId) {
    var m = String(moduleType || '').trim();
    var sid = String(submissionId || '').trim();
    if (!sid || m.indexOf('hr_') !== 0) {
      return null;
    }
    var q = '?edit=' + encodeURIComponent(sid);
    var base = HR_FORM_PATHS[m];
    if (base) {
      return base + q;
    }
    return '/hr/print/' + encodeURIComponent(sid);
  }

  /** View URL + embed=1 for iframes (no main app navbar inside the form page). */
  function getHrSubmissionFullFormEmbedUrl(moduleType, submissionId) {
    var u = getHrSubmissionFullFormViewUrl(moduleType, submissionId);
    if (!u) {
      return null;
    }
    if (u.indexOf('embed=') !== -1) {
      return u;
    }
    return u + (u.indexOf('?') !== -1 ? '&' : '?') + 'embed=1';
  }

  global.getHrSubmissionFullFormViewUrl = getHrSubmissionFullFormViewUrl;
  global.getHrSubmissionFullFormEmbedUrl = getHrSubmissionFullFormEmbedUrl;
})(typeof window !== 'undefined' ? window : globalThis);
