/**
 * QHSA unified inspection form
 */
(function (global) {
  'use strict';

  var catalog = null;
  var lineItems = [];
  var currentSeverity = 'observation';

  function el(id) { return document.getElementById(id); }

  function loadCatalog() {
    return fetch('/qhsi/api/inspection-catalog', { headers: QhsiUi.authHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.success) catalog = d.catalog;
        return catalog;
      });
  }

  function dept() {
    return (el('department') && el('department').value) || '';
  }

  function fillSelect(select, options, placeholder) {
    if (!select) return;
    select.innerHTML = '';
    var ph = document.createElement('option');
    ph.value = '';
    ph.textContent = placeholder || 'Select…';
    select.appendChild(ph);
    (options || []).forEach(function (opt) {
      var o = document.createElement('option');
      o.value = opt;
      o.textContent = opt;
      select.appendChild(o);
    });
  }

  function syncDeptPills(val) {
    document.querySelectorAll('.qhsi-dept-pill').forEach(function (pill) {
      var inp = pill.querySelector('input');
      pill.classList.toggle('is-active', inp && inp.value === val);
    });
    if (el('department')) el('department').value = val || '';
    onDepartmentChange();
  }

  function onDepartmentChange() {
    var d = dept();
    var hint = el('deptHint');
    var hvacWrap = el('hvac-selects');
    var civilWrap = el('civil-cleaning-selects');
    if (!catalog || !d) {
      if (hint) hint.textContent = 'Select a department above to load area checklists.';
      if (hvacWrap) hvacWrap.style.display = 'none';
      if (civilWrap) civilWrap.style.display = 'none';
      return;
    }
    if (hint) {
      var labels = { hvac: 'HVAC & MEP equipment tree', civil: 'Civil works areas', cleaning: 'Cleaning facility areas' };
      hint.textContent = 'Choose area fields below, then add photos for each finding.';
    }
    if (d === 'hvac') {
      if (hvacWrap) hvacWrap.style.display = 'grid';
      if (civilWrap) civilWrap.style.display = 'none';
      fillSelect(el('sel_trade'), Object.keys(catalog.catalogs.hvac || {}), 'Trade / discipline');
      fillSelect(el('sel_system'), [], 'System');
      fillSelect(el('sel_equipment'), [], 'Equipment');
    } else {
      if (hvacWrap) hvacWrap.style.display = 'none';
      if (civilWrap) civilWrap.style.display = 'grid';
      fillSelect(el('sel_area'), Object.keys(catalog.catalogs[d] || {}), 'Area category');
      fillSelect(el('sel_zone'), [], 'Specific area');
    }
  }

  function onTradeChange() {
    var t = el('sel_trade');
    if (!t || !catalog || dept() !== 'hvac') return;
    fillSelect(el('sel_system'), Object.keys(catalog.catalogs.hvac[t.value] || {}), 'System');
    fillSelect(el('sel_equipment'), [], 'Equipment');
  }

  function onSystemChange() {
    var t = el('sel_trade');
    var s = el('sel_system');
    if (!t || !s || !catalog) return;
    fillSelect(el('sel_equipment'), (catalog.catalogs.hvac[t.value] || {})[s.value] || [], 'Equipment');
  }

  function onAreaChange() {
    var d = dept();
    var a = el('sel_area');
    if (!a || !catalog || d === 'hvac') return;
    fillSelect(el('sel_zone'), (catalog.catalogs[d] || {})[a.value] || [], 'Specific area');
  }

  function updateCount() {
    var n = el('itemCount');
    if (n) n.textContent = String(lineItems.length);
    var empty = el('findingsEmpty');
    if (empty) empty.style.display = lineItems.length ? 'none' : 'block';
  }

  function renderItems() {
    var box = el('itemsList');
    if (!box) return;
    box.querySelectorAll('.qhsi-finding-row').forEach(function (r) { r.remove(); });
    lineItems.forEach(function (item, idx) {
      var row = document.createElement('div');
      row.className = 'qhsi-finding-row';
      var label = item.area || item.system || item.trade || item.department;
      var sub = item.equipment || item.zone || '';
      var thumb = (item.photos && item.photos[0]) ? item.photos[0] : '';
      var thumbSrc = typeof thumb === 'string' ? thumb : (thumb.url || '');
      var esc = function (s) {
        var d = document.createElement('span');
        d.textContent = s || '';
        return d.innerHTML;
      };
      row.innerHTML =
        (thumbSrc ? '<img class="qhsi-finding-thumb" src="' + thumbSrc + '" alt="">' : '<div class="qhsi-finding-thumb"></div>') +
        '<div class="qhsi-finding-body" style="flex:1;min-width:0">' +
        '<strong>' + (idx + 1) + '. ' + esc(label) + (sub ? ' — ' + esc(sub) : '') +
        ' <span class="qhsi-badge qhsi-badge--' + (item.severity || 'observation') + '">' + esc(item.severity) + '</span></strong>' +
        '<p style="margin:0.35rem 0 0;font-size:0.85rem;color:#636366">' + esc(item.description || '—') + '</p>' +
        '<p style="margin:0.25rem 0 0;font-size:0.78rem;color:#8e8e93">' + (item.photos ? item.photos.length : 0) + ' photo(s)</p></div>' +
        '<button type="button" class="qhsi-btn-remove" data-idx="' + idx + '">Remove</button>';
      box.appendChild(row);
    });
    box.querySelectorAll('[data-idx]').forEach(function (btn) {
      btn.onclick = function () {
        lineItems.splice(parseInt(btn.getAttribute('data-idx'), 10), 1);
        renderItems();
        updateCount();
      };
    });
    updateCount();
  }

  function addLineItem() {
    var d = dept();
    if (!d) {
      QhsiUi.toast('Select a department first', true);
      return;
    }
    var inp = el('item_photos');
    if (!inp || !inp.files || !inp.files.length) {
      QhsiUi.toast('Add at least one photo', true);
      return;
    }
    QhsiUi.readFilesAsDataUrls(inp.files).then(function (urls) {
      var row = {
        department: d,
        description: (el('item_description') && el('item_description').value) || '',
        severity: currentSeverity,
        photos: urls,
      };
      if (d === 'hvac') {
        row.trade = el('sel_trade') && el('sel_trade').value;
        row.system = el('sel_system') && el('sel_system').value;
        row.equipment = el('sel_equipment') && el('sel_equipment').value;
        if (!row.equipment) {
          QhsiUi.toast('Select trade, system, and equipment', true);
          return;
        }
      } else {
        row.area = el('sel_area') && el('sel_area').value;
        row.zone = el('sel_zone') && el('sel_zone').value;
        if (!row.zone) {
          QhsiUi.toast('Select area category and specific area', true);
          return;
        }
      }
      lineItems.push(row);
      inp.value = '';
      var prev = el('findingPhotoPreview');
      if (prev) prev.innerHTML = '';
      if (el('item_description')) el('item_description').value = '';
      renderItems();
      QhsiUi.toast('Finding added');
    });
  }

  function submitForm(ev) {
    if (ev) ev.preventDefault();
    if (!lineItems.length) {
      QhsiUi.toast('Add at least one finding with photos', true);
      return;
    }
    var btn = el('btnSubmit');
    if (btn) btn.disabled = true;
    var payload = {
      project_name: el('project_name') && el('project_name').value,
      visit_date: el('visit_date') && el('visit_date').value,
      location: el('location') && el('location').value,
      department: dept(),
      inspector_name: el('inspector_name') && el('inspector_name').value,
      summary: el('summary') && el('summary').value,
      items: lineItems,
      tech_signature: global.getTechSignatureDataUrl ? global.getTechSignatureDataUrl() : '',
    };
    fetch('/qhsi/api/inspection/submit', {
      method: 'POST',
      headers: QhsiUi.authHeaders(),
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (res) {
        if (btn) btn.disabled = false;
        if (!res.ok) {
          QhsiUi.toast((res.body && res.body.error) || 'Submit failed', true);
          return;
        }
        var sid = res.body.submission_id;
        QhsiUi.showSuccess(
          'Inspection submitted',
          'Forwarded to the Operations Manager. Reports are generating.',
          sid,
          function () { window.location.href = '/workflow/submitted-forms?scope=inspection'; }
        );
      })
      .catch(function () {
        if (btn) btn.disabled = false;
        QhsiUi.toast('Network error', true);
      });
  }

  function init() {
    var today = new Date().toISOString().slice(0, 10);
    var vd = el('visit_date');
    if (vd) vd.max = today;

    QhsiUi.loadProjectsInto(el('project_name'), null);
    QhsiUi.bindPhotoZone(el('findingPhotoZone'), el('item_photos'), el('findingPhotoPreview'));

    document.querySelectorAll('.qhsi-dept-pill input').forEach(function (inp) {
      inp.addEventListener('change', function () {
        syncDeptPills(inp.value);
      });
    });

    document.querySelectorAll('.qhsi-sev').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.qhsi-sev').forEach(function (b) { b.classList.remove('is-active'); });
        btn.classList.add('is-active');
        currentSeverity = btn.getAttribute('data-v');
        if (el('item_severity')) el('item_severity').value = currentSeverity;
      });
    });

    loadCatalog();
    if (el('sel_trade')) el('sel_trade').addEventListener('change', onTradeChange);
    if (el('sel_system')) el('sel_system').addEventListener('change', onSystemChange);
    if (el('sel_area')) el('sel_area').addEventListener('change', onAreaChange);
    if (el('btnAddItem')) el('btnAddItem').addEventListener('click', addLineItem);
    var form = el('qhsaInspectionForm');
    if (form) form.addEventListener('submit', submitForm);

    try {
      var u = JSON.parse(localStorage.getItem('user') || '{}');
      if (el('inspector_name') && u.full_name) el('inspector_name').value = u.full_name;
    } catch (e) { /* ignore */ }

    updateCount();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  global.QhsiInspection = { lineItems: lineItems, renderItems: renderItems };
})(window);
