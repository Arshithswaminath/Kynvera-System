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
    if (n == null || n === '' || isNaN(n)) return '—';
    return Number(n) + '%';
  }

  function asNumber(value, fallback) {
    if (value == null || value === '') return fallback;
    var n = Number(value);
    return isNaN(n) ? fallback : n;
  }

  function pickStat(sources, keys, fallback) {
    for (var i = 0; i < sources.length; i++) {
      var src = sources[i];
      if (!src) continue;
      for (var k = 0; k < keys.length; k++) {
        if (src[keys[k]] != null && src[keys[k]] !== '') {
          return asNumber(src[keys[k]], fallback);
        }
      }
    }
    return fallback;
  }

  function renderImportSummary(container, data) {
    if (!container) return;
    var imp = data && data.import;
    if (!imp || !imp.has_import) {
      container.innerHTML = '<p class="qhse-import-empty">No Excel import yet. Upload a file to populate dashboard counts.</p>';
      return;
    }
    var batch = imp.batch || {};
    var nested = batch.stats || {};
    var sources = [imp, nested, batch];
    var employees = pickStat(sources, ['employees', 'employee_count'], 0);
    var kitLines = pickStat(sources, ['kit_lines', 'row_count'], 0);
    var compliant = pickStat(sources, ['compliant', 'ok'], 0);
    var issues = pickStat(sources, ['issues', 'issue'], 0);
    var missing = pickStat(sources, ['missing'], 0);
    var rate = pickStat(sources, ['compliance_rate'], null);
    container.innerHTML =
      '<div class="qhse-import-summary">' +
      '<div class="qhse-import-summary__hd">' +
      '<strong>Latest import</strong>' +
      '<span class="qhse-import-summary__meta">' + (batch.filename || 'Excel') +
      (batch.created_at ? ' · ' + new Date(batch.created_at).toLocaleString() : '') + '</span>' +
      '</div>' +
      '<div class="qhse-import-stats">' +
      statTile('Employees', employees) +
      statTile('Kit lines', kitLines) +
      statTile('Compliant', compliant, 'ok') +
      statTile('Issues', issues, 'warn') +
      statTile('Missing', missing, 'bad') +
      statTile('Compliance rate', fmtRate(rate), 'rate') +
      '</div>' +
      '<div class="qhse-import-summary__foot">' +
      '<button type="button" class="btn-secondary qhse-import-clear" id="qhseClearImport">Clear import data</button>' +
      '</div>' +
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

  function setImportStatus(el, text) {
    if (!el) return;
    var msg = text || '';
    el.textContent = msg;
    if (msg) el.removeAttribute('hidden');
    else el.setAttribute('hidden', '');
  }

  function bindFilePicker(formEl) {
    if (!formEl) return;
    var input = formEl.querySelector('input[type=file]');
    var nameEl = formEl.querySelector('[data-file-name]');
    if (!input || !nameEl) return;
    input.addEventListener('change', function () {
      nameEl.textContent = (input.files && input.files[0] && input.files[0].name) || 'No file chosen';
    });
  }

  function bindImportForm(formEl, summaryEl, onSuccess) {
    if (!formEl) return;
    var input = formEl.querySelector('input[type=file]');
    var btn = formEl.querySelector('[data-import-btn]');
    var status = formEl.querySelector('[data-import-status]');
    var nameEl = formEl.querySelector('[data-file-name]');
    bindFilePicker(formEl);

    formEl.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!input || !input.files || !input.files[0]) {
        setImportStatus(status, 'Choose an Excel file first.');
        return;
      }
      var fd = new FormData();
      fd.append('file', input.files[0]);
      if (btn) btn.disabled = true;
      setImportStatus(status, 'Importing…');

      fetch('/qhsi/api/staff-compliance/import', {
        method: 'POST',
        headers: authHeadersMultipart(),
        body: fd,
      })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          if (btn) btn.disabled = false;
          if (!res.ok || !res.body.success) {
            setImportStatus(status, res.body.message || res.body.error || 'Import failed');
            return;
          }
          setImportStatus(status, res.body.message || 'Import complete');
          input.value = '';
          if (nameEl) nameEl.textContent = 'No file chosen';
          loadImportSummary(summaryEl);
          if (onSuccess) onSuccess(res.body);
          if (typeof window.qhseRefreshDashboardStats === 'function') window.qhseRefreshDashboardStats();
        })
        .catch(function () {
          if (btn) btn.disabled = false;
          setImportStatus(status, 'Import failed — check connection');
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
