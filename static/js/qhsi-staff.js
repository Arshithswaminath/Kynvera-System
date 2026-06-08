(function () {
  'use strict';
  var kitRows = [];
  var kitIndex = 0;

  function updateKitSummary() {
    var totalEl = document.querySelector('[data-kit-total]');
    var issuesEl = document.querySelector('[data-kit-issues]');
    if (totalEl) totalEl.textContent = String(kitRows.length);
    if (issuesEl) {
      var issues = kitRows.filter(function (row) {
        var sel = row.querySelector('.kit-condition');
        return sel && sel.value !== 'ok';
      }).length;
      issuesEl.textContent = String(issues);
    }
  }

  function addKitRow() {
    var id = 'kit-' + (++kitIndex);
    var wrap = document.createElement('div');
    wrap.className = 'qhsi-item-card';
    wrap.dataset.kitId = id;
    var opts = (window.KIT_TYPES || []).map(function (k) {
      return '<option value="' + k.id + '">' + k.label + '</option>';
    }).join('');
    wrap.innerHTML =
      '<div class="qhsi-item-card__hd">' +
      '<span class="qhsi-item-card__title">Kit item</span>' +
      '<button type="button" class="qhsi-btn-remove" data-remove-kit>Remove</button></div>' +
      '<div class="grid-2">' +
      '<div class="fld"><label class="fld-lbl">Item</label><select class="fld-inp kit-type">' + opts + '</select></div>' +
      '<div class="fld"><label class="fld-lbl">Condition</label><select class="fld-inp kit-condition">' +
      '<option value="ok">OK — compliant</option>' +
      '<option value="issue">Issue — replacement needed</option>' +
      '<option value="missing">Missing</option></select></div>' +
      '<div class="fld fw"><label class="fld-lbl">Comments</label><input class="fld-inp kit-comments" placeholder="Size, serial, remarks…"></div>' +
      '</div>' +
      '<div class="fld" style="margin-top:0.75rem">' +
      '<label class="fld-lbl">Photos</label>' +
      '<div class="qhsi-photo-zone" data-zone><span class="qhsi-photo-zone-label">Tap to add photos</span>' +
      '<p class="qhsi-photo-zone-hint">Uniform, PPE, or ID badge — multiple images allowed</p>' +
      '<input type="file" class="kit-photos" accept="image/*" multiple capture="environment"></div>' +
      '<div class="qhsi-photo-previews" data-preview></div></div>';
    document.getElementById('kitItems').appendChild(wrap);
    var zone = wrap.querySelector('[data-zone]');
    var inp = wrap.querySelector('.kit-photos');
    var prev = wrap.querySelector('[data-preview]');
    QhsiUi.bindPhotoZone(zone, inp, prev);
    wrap.querySelector('[data-remove-kit]').onclick = function () {
      wrap.remove();
      kitRows = kitRows.filter(function (r) { return r !== wrap; });
      updateKitSummary();
    };
    var condSel = wrap.querySelector('.kit-condition');
    if (condSel) condSel.addEventListener('change', updateKitSummary);
    kitRows.push(wrap);
    updateKitSummary();
  }

  document.getElementById('btnAddKit').onclick = addKitRow;
  addKitRow();

  var rd = document.querySelector('[name=record_date]');
  if (rd) rd.max = new Date().toISOString().slice(0, 10);

  QhsiUi.loadProjectsInto(null, document.getElementById('projectList'));

  document.getElementById('staffForm').onsubmit = function (e) {
    e.preventDefault();
    var btn = document.getElementById('btnSubmitStaff');
    if (btn) btn.disabled = true;
    var promises = kitRows.map(function (row) {
      var inp = row.querySelector('.kit-photos');
      return QhsiUi.readFilesAsDataUrls(inp.files).then(function (photos) {
        return {
          type: row.querySelector('.kit-type').value,
          condition: row.querySelector('.kit-condition').value,
          comments: row.querySelector('.kit-comments').value,
          photos: photos,
        };
      });
    });
    Promise.all(promises).then(function (items) {
      var f = document.getElementById('staffForm');
      return fetch('/qhsi/api/staff-compliance/submit', {
        method: 'POST',
        headers: QhsiUi.authHeaders(),
        body: JSON.stringify({
          employee_name: f.employee_name.value,
          employee_id: f.employee_id.value,
          project_name: f.project_name.value,
          record_date: f.record_date.value,
          department: f.department.value,
          supervisor_name: f.supervisor_name.value,
          notes: f.notes.value,
          kit_items: items,
        }),
      });
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
          'Record submitted',
          'Forwarded to the Operations Manager for review.',
          sid,
          function () { window.location.href = '/workflow/submitted-forms?scope=inspection'; }
        );
      })
      .catch(function () {
        if (btn) btn.disabled = false;
        QhsiUi.toast('Network error', true);
      });
  };
})();
