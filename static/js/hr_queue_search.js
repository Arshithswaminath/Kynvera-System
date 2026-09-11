/**
 * Client-side filter for HR queue lists (pending / completed / GM / my requests).
 * Matches employee name, form reference (HR · 3F9A6A1C), and form type.
 */
(function (global) {
  'use strict';

  function formTypeLabel(type) {
    if (global.hrDisplay && typeof global.hrDisplay.formTypeLabel === 'function') {
      return global.hrDisplay.formTypeLabel(type);
    }
    return String(type || '').replace(/^hr_/, '').replace(/_/g, ' ');
  }

  function submissionRef(id) {
    if (global.hrDisplay && typeof global.hrDisplay.submissionRef === 'function') {
      return global.hrDisplay.submissionRef(id);
    }
    return String(id || '');
  }

  function haystack(s) {
    if (!s || typeof s !== 'object') return '';
    var fd = s.form_data && typeof s.form_data === 'object' ? s.form_data : {};
    var parts = [
      fd.employee_name,
      fd.employee_full_name,
      fd.employee_id,
      fd.submitted_by_name,
      s.submitter_name,
      s.submitter_display,
      s.site_name,
      s.submission_id,
      submissionRef(s.submission_id),
      formTypeLabel(s.module_type),
      s.module_type,
      String(s.module_type || '').replace(/^hr_/, '').replace(/_/g, ' '),
      fd.leave_type,
    ];
    return parts.filter(Boolean).join(' ').toLowerCase();
  }

  function matches(s, q) {
    q = String(q || '').trim().toLowerCase();
    if (!q) return true;
    var hay = haystack(s);
    return q.split(/\s+/).every(function (tok) {
      return hay.indexOf(tok) !== -1;
    });
  }

  function filter(items, q) {
    return (items || []).filter(function (s) {
      return matches(s, q);
    });
  }

  function queryFrom(el) {
    return el ? String(el.value || '') : '';
  }

  function bind(inputId, onChange) {
    var el = document.getElementById(inputId);
    if (!el || el.dataset.hrQueueSearchBound === '1' || typeof onChange !== 'function') return;
    el.dataset.hrQueueSearchBound = '1';
    var timer = null;
    function fire() {
      onChange(el.value);
    }
    el.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(fire, 120);
    });
    el.addEventListener('search', fire);
  }

  global.HrQueueSearch = {
    haystack: haystack,
    matches: matches,
    filter: filter,
    queryFrom: queryFrom,
    bind: bind,
  };
})(typeof window !== 'undefined' ? window : this);
