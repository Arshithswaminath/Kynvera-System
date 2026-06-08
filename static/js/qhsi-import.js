(function () {
  'use strict';

  function authHeaders() {
    var h = { 'Content-Type': 'application/json' };
    var t = localStorage.getItem('access_token');
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
  }

  function authHeadersMultipart() {
    var h = {};
    var t = localStorage.getItem('access_token');
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
  }

  function fmtRate(n) {
    return (n == null || isNaN(n)) ? '—' : (n + '%');
  }

  function renderImportSummary(container, data) {
    if (!container) return;
    var imp = data && data.import;
    if (!imp || !imp.has_import) {
      container.innerHTML = '<p class="qhse-import-empty">No Excel import yet. Upload a file to populate dashboard counts.</p>';
      return;
    }
    var batch = imp.batch || {};
    var s = imp;
    container.innerHTML =
      '<div class="qhse-import-summary">' +
      '<div class="qhse-import-summary__hd">' +
      '<strong>Latest import</strong>' +
      '<span class="qhse-import-summary__meta">' + (batch.filename || 'Excel') +
      (batch.created_at ? ' · ' + new Date(batch.created_at).toLocaleString() : '') + '</span>' +
      '</div>' +
      '<div class="qhse-import-stats">' +
      statTile('Employees', s.employees) +
      statTile('Kit lines', s.kit_lines) +
      statTile('Compliant', s.compliant, 'ok') +
      statTile('Issues', s.issues, 'warn') +
      statTile('Missing', s.missing, 'bad') +
      statTile('Compliance rate', fmtRate(s.compliance_rate), 'rate') +
      '</div>' +
      '<button type="button" class="btn-secondary qhse-import-clear" id="qhseClearImport">Clear import data</button>' +
      '</div>';
    var clearBtn = document.getElementById('qhseClearImport');
    if (clearBtn) {
      clearBtn.onclick = function () {
        if (!confirm('Clear all imported compliance data? Dashboard counts will reset until you import again.')) return;
        fetch('/qhsi/api/staff-compliance/import', { method: 'DELETE', headers: authHeaders() })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (d.success) {
              loadImportSummary(container);
              if (typeof window.qhseRefreshDashboardStats === 'function') window.qhseRefreshDashboardStats();
            } else {
              alert(d.message || d.error || 'Clear failed');
            }
          });
      };
    }
  }

  function statTile(label, value, kind) {
    var cls = 'qhse-import-stat' + (kind ? ' qhse-import-stat--' + kind : '');
    return '<div class="' + cls + '"><span class="qhse-import-stat__val">' + value + '</span><span class="qhse-import-stat__lbl">' + label + '</span></div>';
  }

  function loadImportSummary(container) {
    return fetch('/qhsi/api/staff-compliance/import/latest', { headers: authHeaders() })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && d.success) renderImportSummary(container, d);
      });
  }

  function bindImportForm(formEl, summaryEl, onSuccess) {
    if (!formEl) return;
    var input = formEl.querySelector('input[type=file]');
    var btn = formEl.querySelector('[data-import-btn]');
    var status = formEl.querySelector('[data-import-status]');

    formEl.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!input || !input.files || !input.files[0]) {
        if (status) status.textContent = 'Choose an Excel file first.';
        return;
      }
      var fd = new FormData();
      fd.append('file', input.files[0]);
      if (btn) btn.disabled = true;
      if (status) status.textContent = 'Importing…';

      fetch('/qhsi/api/staff-compliance/import', {
        method: 'POST',
        headers: authHeadersMultipart(),
        body: fd,
      })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          if (btn) btn.disabled = false;
          if (!res.ok || !res.body.success) {
            if (status) status.textContent = res.body.message || res.body.error || 'Import failed';
            return;
          }
          if (status) status.textContent = res.body.message || 'Import complete';
          input.value = '';
          loadImportSummary(summaryEl);
          if (onSuccess) onSuccess(res.body);
          if (typeof window.qhseRefreshDashboardStats === 'function') window.qhseRefreshDashboardStats();
        })
        .catch(function () {
          if (btn) btn.disabled = false;
          if (status) status.textContent = 'Import failed — check connection';
        });
    });
  }

  window.QhseImport = {
    loadImportSummary: loadImportSummary,
    bindImportForm: bindImportForm,
    renderImportSummary: renderImportSummary,
  };

  function downloadTemplate(e) {
    if (e) e.preventDefault();
    var token = localStorage.getItem('access_token');
    fetch('/qhsi/api/staff-compliance/import-template', {
      headers: token ? { 'Authorization': 'Bearer ' + token } : {},
    })
      .then(function (r) {
        if (!r.ok) throw new Error('Download failed');
        return r.blob();
      })
      .then(function (blob) {
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'QHSE_Staff_Compliance_Import_Template.xlsx';
        a.click();
        URL.revokeObjectURL(a.href);
      })
      .catch(function () { alert('Could not download template — sign in and try again.'); });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var summary = document.getElementById('qhseImportSummary');
    var form = document.getElementById('qhseImportForm');
    if (summary) loadImportSummary(summary);
    if (form) bindImportForm(form, summary);
    document.querySelectorAll('[data-qhse-template]').forEach(function (el) {
      el.addEventListener('click', downloadTemplate);
    });
  });
})();
