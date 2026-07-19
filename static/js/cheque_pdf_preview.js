/**
 * ChequePdfPreview — pop-up preview of the Cheque Preparation / Request Form.
 *
 * Preview is an HTML paper form filled from the JSON API (always visible in
 * browsers / PWA / Capacitor). Download still generates the branded PDF.
 *
 * Usage:
 *   ChequePdfPreview.open('CHQ-ABC12345');
 *   ChequePdfPreview.refreshIfOpen('CHQ-ABC12345');
 *   ChequePdfPreview.close();
 */
(function (global) {
  'use strict';

  var LABELS = {
    requested: 'Requested', verified: 'Verified', approved: 'Approved',
    prepared: 'Prepared', submitted: 'Submitted', cleared: 'Cleared',
    rejected: 'Rejected', cancelled: 'Cancelled',
  };

  var state = {
    ref: null,
    ready: false,
    gen: 0,
    loading: false,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function esc(s) {
    return (s == null ? '' : String(s)).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function fmtAED(n) {
    return 'AED ' + (Number(n) || 0).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function fmtDate(d) {
    if (!d) return '—';
    var dt = new Date(d.length <= 10 ? d + 'T00:00:00' : d);
    if (isNaN(dt.getTime())) return String(d);
    return dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function ensureReady() {
    if (state.ready) return true;
    var bg = $('cpmBg');
    if (!bg) return false;
    $('cpmClose').addEventListener('click', close);
    $('cpmRefresh').addEventListener('click', function () {
      if (state.ref && !state.loading) load(state.ref);
    });
    $('cpmDownload').addEventListener('click', download);
    bg.addEventListener('click', function (e) {
      if (e.target === bg) close();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && bg.classList.contains('is-open')) close();
    });
    state.ready = true;
    return true;
  }

  function setLoading(on) {
    state.loading = !!on;
    var loading = $('cpmLoading');
    if (loading) loading.hidden = !on;
    var btn = $('cpmDownload');
    if (btn && on === false) btn.disabled = false;
    var refresh = $('cpmRefresh');
    if (refresh) refresh.disabled = !!on;
  }

  function setError(msg) {
    var errEl = $('cpmError');
    if (!errEl) return;
    if (msg) {
      errEl.hidden = false;
      errEl.textContent = msg;
    } else {
      errEl.hidden = true;
      errEl.textContent = '';
    }
  }

  function renderPaper(c) {
    var paper = $('cpmPaper');
    if (!paper) return;

    var items = c.items || [];
    var rows = items.length
      ? items.map(function (it) {
          return (
            '<tr>' +
              '<td class="num">' + esc(it.sn) + '</td>' +
              '<td><strong>' + esc(it.supplier) + '</strong></td>' +
              '<td class="num">' + esc(fmtAED(it.amount)) + '</td>' +
              '<td>' + esc(fmtDate(it.cheque_date)) + '</td>' +
              '<td class="remarks-cell">' + esc(it.remarks || '—') + '</td>' +
            '</tr>'
          );
        }).join('')
      : '<tr><td colspan="5" class="cpm-empty">No supplier lines</td></tr>';

    var docs = String(c.attached_documents || '')
      .split('\n')
      .map(function (s) { return s.trim(); })
      .filter(Boolean);

    function sig(role, name, date, signature) {
      var pending = !name;
      var ink = signature
        ? '<img class="cpm-sig-ink" src="' + esc(signature) + '" alt="Signature">'
        : '<div class="cpm-sig-rule"></div>';
      return (
        '<div class="cpm-sig">' +
          '<div class="cpm-sig-role">' + esc(role) + '</div>' +
          '<div class="cpm-sig-body">' +
            '<div class="cpm-sig-label">Name</div>' +
            '<div class="cpm-sig-name' + (pending ? ' pending' : '') + '">' +
              esc(pending ? 'Pending' : name) +
            '</div>' +
            '<div class="cpm-sig-label">Signature</div>' +
            ink +
            '<div class="cpm-sig-label">Date</div>' +
            '<div>' + esc(fmtDate(date)) + '</div>' +
          '</div>' +
        '</div>'
      );
    }

    var statusLabel = LABELS[c.status] || c.status || '—';

    paper.innerHTML =
      '<div class="cpm-paper-stripe"></div>' +
      '<div class="cpm-paper-head">' +
        '<div>' +
          '<h2 class="cpm-paper-title">Cheque Preparation / Request Form</h2>' +
          '<p class="cpm-paper-co">AMAAN SYSTEMS LLC</p>' +
        '</div>' +
        '<img class="cpm-paper-logo" src="/static/icons/Amaan-mark.png" alt="Amaan" onerror="this.style.display=\'none\'">' +
      '</div>' +
      '<div class="cpm-meta">' +
        '<div class="cpm-meta-row"><span class="cpm-meta-label">Reference No</span><span class="cpm-meta-value">' + esc(c.reference_no) + '</span></div>' +
        '<div class="cpm-meta-row"><span class="cpm-meta-label">Office</span><span class="cpm-meta-value">' + esc(c.office || '—') + '</span></div>' +
        '<div class="cpm-meta-row"><span class="cpm-meta-label">Status</span><span class="cpm-meta-value status">' + esc(String(statusLabel).toUpperCase()) + '</span></div>' +
        '<div class="cpm-meta-row"><span class="cpm-meta-label">Department</span><span class="cpm-meta-value">' + esc(c.department || 'Finance') + '</span></div>' +
        '<div class="cpm-meta-row"><span class="cpm-meta-label">Request Date</span><span class="cpm-meta-value">' + esc(fmtDate(c.requested_date)) + '</span></div>' +
      '</div>' +
      '<div class="cpm-section">Supplier Lines</div>' +
      '<table class="cpm-table">' +
        '<thead><tr><th style="width:48px">SN</th><th>Supplier</th><th style="width:130px">Amount (AED)</th><th style="width:110px">Date</th><th>Remarks</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
      '</table>' +
      '<div class="cpm-total"><span>TOTAL</span><span>' + esc(fmtAED(c.total_amount)) + '</span></div>' +
      '<div class="cpm-section">Approval Signatories</div>' +
      '<div class="cpm-sigs">' +
        sig('Requested by', c.requested_by_name, c.requested_date, c.requested_signature) +
        sig('Verified by', c.verified_by_name, c.verified_date, c.verified_signature) +
        sig('Approved by', c.approved_by_name, c.approved_date, c.approved_signature) +
      '</div>' +
      '<div class="cpm-section">Attached Documents</div>' +
      '<div class="cpm-box cpm-box-lg cpm-docs">' +
        (docs.length
          ? '<ol>' + docs.map(function (d) { return '<li>' + esc(d) + '</li>'; }).join('') + '</ol>'
          : '<span class="cpm-empty">—</span>') +
      '</div>';
  }

  async function apiFetch(url, options) {
    var fetcher = (global.ApiClient && global.ApiClient.fetch)
      ? global.ApiClient.fetch.bind(global.ApiClient)
      : global.fetch;
    return fetcher(url, options || {});
  }

  async function load(ref) {
    var gen = ++state.gen;
    setError('');
    setLoading(true);

    try {
      var res = await apiFetch('/operations/api/cheques/' + encodeURIComponent(ref), {
        method: 'GET',
        cache: 'no-store',
      });
      if (state.gen !== gen || state.ref !== ref) return;

      var data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error((data && data.error) || 'Could not load cheque request');
      }
      if (!data.cheque) throw new Error('Cheque request not found');

      renderPaper(data.cheque);
      setLoading(false);
    } catch (e) {
      if (state.gen !== gen || state.ref !== ref) return;
      setLoading(false);
      setError((e && e.message) || 'Could not load the preview.');
    }
  }

  async function download() {
    if (!state.ref || state.loading) return;
    var btn = $('cpmDownload');
    if (btn) btn.disabled = true;
    try {
      var res = await apiFetch(
        '/operations/cheques/' + encodeURIComponent(state.ref) + '/pdf?download=1&_=' + Date.now(),
        { method: 'GET', cache: 'no-store' }
      );
      if (!res.ok) {
        var msg = 'Could not download the PDF.';
        try {
          var err = await res.json();
          if (err && err.error) msg = err.error;
        } catch (e) { /* ignore */ }
        throw new Error(msg);
      }
      var blob = await res.blob();
      var pdfBlob = blob.type === 'application/pdf'
        ? blob
        : new Blob([blob], { type: 'application/pdf' });
      var url = URL.createObjectURL(pdfBlob);
      var a = document.createElement('a');
      a.href = url;
      a.download = state.ref + '.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
    } catch (e) {
      alert((e && e.message) || 'Download failed');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function open(ref) {
    if (!ref) return;
    if (!ensureReady()) {
      console.error('Cheque PDF preview markup not found');
      return;
    }
    // Prevent re-entrant open storms from double-clicks
    if (state.ref === ref && $('cpmBg').classList.contains('is-open') && state.loading) {
      return;
    }
    state.ref = ref;
    $('cpmSub').textContent = ref;
    var bg = $('cpmBg');
    bg.classList.add('is-open');
    bg.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    load(ref);
  }

  function refreshIfOpen(ref) {
    if (!state.ready) return;
    var bg = $('cpmBg');
    if (bg && bg.classList.contains('is-open') && state.ref === ref) {
      load(ref);
    }
  }

  function closeIfOpen(ref) {
    if (!state.ready) return;
    var bg = $('cpmBg');
    if (bg && bg.classList.contains('is-open') && state.ref === ref) {
      close();
    }
  }

  function close() {
    var bg = $('cpmBg');
    if (!bg) return;
    state.gen += 1;
    bg.classList.remove('is-open');
    bg.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    var paper = $('cpmPaper');
    if (paper) paper.innerHTML = '';
    setError('');
    setLoading(false);
    state.ref = null;
  }

  global.ChequePdfPreview = {
    open: open,
    refreshIfOpen: refreshIfOpen,
    closeIfOpen: closeIfOpen,
    close: close,
  };
})(window);
