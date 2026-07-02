/**
 * HR forms — Reporting To block: load picker + pre-fill from profile reporting manager.
 *
 * Used by forms that include the standard Reporting To fields:
 *   #reportingToUserSelect, #reportingToSignerId, #reportingToName,
 *   #reportingToDesignation, #reportingToContact, #reportingToAutoHint
 *
 * Pre-fill source: GET /hr/api/mgmt-chain-context → default_reporting_to
 */
(function (global) {
  'use strict';

  var DEFAULT_IDS = {
    select: 'reportingToUserSelect',
    signerId: 'reportingToSignerId',
    name: 'reportingToName',
    designation: 'reportingToDesignation',
    contact: 'reportingToContact',
    hint: 'reportingToAutoHint',
  };

  function desigLabel(code) {
    if (!code) return '';
    return String(code).replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function designationLabel(mgr) {
    if (!mgr) return '';
    if (mgr.job_designation && String(mgr.job_designation).trim()) {
      return String(mgr.job_designation).trim();
    }
    return desigLabel(mgr.designation || '');
  }

  function fieldEdited(id) {
    var el = document.getElementById(id);
    return el && (el.dataset.userEdited === '1' || (el.value || '').trim() !== '');
  }

  function applyPrefill(mgr, ids) {
    ids = ids || DEFAULT_IDS;
    if (!mgr || !mgr.id) return false;

    var hid = document.getElementById(ids.signerId);
    if (hid && (hid.value || '').trim()) return false;

    var targetId = String(mgr.id);
    var sel = document.getElementById(ids.select);
    if (sel) {
      sel.value = targetId;
      if (hid) hid.value = (sel.value === targetId) ? targetId : '';
    }

    var nameEl = document.getElementById(ids.name);
    var desEl = document.getElementById(ids.designation);
    var ctEl = document.getElementById(ids.contact);

    if (nameEl && !fieldEdited(ids.name)) {
      nameEl.value = mgr.full_name || '';
    }
    if (desEl && !fieldEdited(ids.designation)) {
      desEl.value = designationLabel(mgr);
    }
    if (ctEl && !fieldEdited(ids.contact)) {
      ctEl.value = mgr.phone || '';
    }

    var hint = document.getElementById(ids.hint);
    if (hint && nameEl && nameEl.value) hint.style.display = 'block';
    return true;
  }

  function syncFromPicker(ids) {
    ids = ids || DEFAULT_IDS;
    var sel = document.getElementById(ids.select);
    var hid = document.getElementById(ids.signerId);
    var nameEl = document.getElementById(ids.name);
    var desEl = document.getElementById(ids.designation);
    if (!sel || !hid) return;
    var uid = sel.value;
    hid.value = uid || '';
    if (!uid) return;
    var opt = sel.selectedOptions[0];
    if (!opt) return;
    if (nameEl && !(nameEl.dataset.userEdited === '1')) {
      nameEl.value = opt.dataset.fullName || opt.textContent.split(' — ')[0] || '';
    }
    if (desEl && !(desEl.dataset.userEdited === '1')) {
      desEl.value = desigLabel(opt.dataset.designation || '');
    }
  }

  function bindFieldEditGuards(ids) {
    ids = ids || DEFAULT_IDS;
    [ids.name, ids.designation, ids.contact].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) {
        el.addEventListener('input', function () { el.dataset.userEdited = '1'; });
      }
    });
  }

  function reportingManagerFromContext(ctx) {
    if (!ctx || !ctx.success) return null;
    if (ctx.default_reporting_to && ctx.default_reporting_to.id) {
      return ctx.default_reporting_to;
    }
    if (ctx.supervisor && ctx.supervisor.id) {
      return ctx.supervisor;
    }
    return null;
  }

  async function init(opts) {
    opts = opts || {};
    var ids = Object.assign({}, DEFAULT_IDS, opts.ids || {});
    var sel = document.getElementById(ids.select);
    if (!sel) return { users: [] };

    var token = localStorage.getItem('access_token');
    var headers = token ? { Authorization: 'Bearer ' + token } : {};
    var users = [];

    try {
      var responses = await Promise.all([
        fetch('/hr/api/active-users-for-picker', { headers: headers }),
        fetch('/hr/api/mgmt-chain-context', { headers: headers }),
      ]);
      var pickerJson = await responses[0].json().catch(function () { return {}; });
      var ctxJson = await responses[1].json().catch(function () { return {}; });

      users = pickerJson.users || [];
      while (sel.children.length > 1) sel.removeChild(sel.lastChild);
      users.forEach(function (u) {
        var opt = document.createElement('option');
        opt.value = String(u.id);
        opt.textContent = (u.full_name || u.username) +
          (u.designation ? ' — ' + desigLabel(u.designation) : '');
        opt.dataset.fullName = u.full_name || u.username || '';
        opt.dataset.designation = u.designation || '';
        sel.appendChild(opt);
      });

      applyPrefill(reportingManagerFromContext(ctxJson), ids);
    } catch (_e) { /* optional until submit */ }

    return { users: users };
  }

  global.HrReportingToPrefill = {
    DEFAULT_IDS: DEFAULT_IDS,
    desigLabel: desigLabel,
    designationLabel: designationLabel,
    applyPrefill: applyPrefill,
    syncFromPicker: syncFromPicker,
    bindFieldEditGuards: bindFieldEditGuards,
    reportingManagerFromContext: reportingManagerFromContext,
    init: init,
  };
})(window);
