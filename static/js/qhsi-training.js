(function () {
  'use strict';

  function statusClass(s) {
    return 'qhsi-status qhsi-status--' + (s || 'scheduled');
  }

  function loadList() {
    var st = document.getElementById('filterStatus').value;
    var url = '/qhsi/api/trainings' + (st ? '?status=' + encodeURIComponent(st) : '');
    fetch(url, { headers: QhsiUi.authHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var box = document.getElementById('trainingList');
        box.innerHTML = '';
        if (!d || !d.trainings || !d.trainings.length) {
          box.innerHTML =
            '<div class="qhsi-empty-state">' +
            '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25"/></svg>' +
            '<p>No sessions in this view.<br>Schedule one using the form.</p></div>';
          return;
        }
        d.trainings.forEach(function (t) {
          var card = document.createElement('div');
          card.className = 'qhsi-training-card';
          var dt = t.scheduled_at ? new Date(t.scheduled_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '';
          var typeLabel = (t.training_type || 'training').replace('_', ' ');
          card.innerHTML =
            '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.5rem">' +
            '<span class="qhsi-training-card__title">' + escapeHtml(t.title) + '</span>' +
            '<span class="' + statusClass(t.status) + '">' + (t.status || '') + '</span></div>' +
            '<div class="qhsi-training-card__meta">' + escapeHtml(t.project_name) + '<br>' +
            dt + ' · ' + (t.duration_minutes || 60) + ' min · ' + typeLabel +
            (t.location ? '<br>' + escapeHtml(t.location) : '') +
            (t.facilitator_name ? '<br>Facilitator: ' + escapeHtml(t.facilitator_name) : '') +
            '</div>' +
            (t.status === 'scheduled'
              ? '<div class="qhsi-training-card__actions">' +
                '<button type="button" class="btn-secondary" data-complete="' + t.training_id + '">Complete</button>' +
                '<button type="button" class="qhsi-btn-remove" data-cancel="' + t.training_id + '">Cancel</button></div>'
              : '');
          box.appendChild(card);
        });
        box.querySelectorAll('[data-complete]').forEach(function (btn) {
          btn.onclick = function () {
            fetch('/qhsi/api/trainings/' + btn.getAttribute('data-complete'), {
              method: 'PATCH',
              headers: QhsiUi.authHeaders(),
              body: JSON.stringify({ status: 'completed' }),
            }).then(function () {
              QhsiUi.toast('Marked completed');
              loadList();
            });
          };
        });
        box.querySelectorAll('[data-cancel]').forEach(function (btn) {
          btn.onclick = function () {
            if (!confirm('Cancel this session?')) return;
            fetch('/qhsi/api/trainings/' + btn.getAttribute('data-cancel'), {
              method: 'PATCH',
              headers: QhsiUi.authHeaders(),
              body: JSON.stringify({ status: 'cancelled' }),
            }).then(function () {
              QhsiUi.toast('Session cancelled');
              loadList();
            });
          };
        });
      });
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  QhsiUi.loadProjectsInto(document.getElementById('t_project'), null);
  document.getElementById('filterStatus').onchange = loadList;

  document.getElementById('trainingForm').onsubmit = function (e) {
    e.preventDefault();
    var att = document.getElementById('t_attendees').value.split(',').map(function (s) {
      s = s.trim();
      return s ? { name: s } : null;
    }).filter(Boolean);
    fetch('/qhsi/api/trainings', {
      method: 'POST',
      headers: QhsiUi.authHeaders(),
      body: JSON.stringify({
        project_name: document.getElementById('t_project').value,
        title: document.getElementById('t_title').value,
        training_type: document.getElementById('t_type').value,
        scheduled_at: document.getElementById('t_scheduled').value,
        duration_minutes: parseInt(document.getElementById('t_duration').value, 10) || 60,
        location: document.getElementById('t_location').value,
        facilitator_name: document.getElementById('t_facilitator').value,
        attendees: att,
        notes: document.getElementById('t_notes').value,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.success) {
          document.getElementById('trainingForm').reset();
          QhsiUi.toast('Session scheduled');
          loadList();
        } else {
          QhsiUi.toast((d && d.error) || 'Could not schedule', true);
        }
      });
  };

  loadList();
})();
