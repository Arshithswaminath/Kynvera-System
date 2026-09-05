(function (global) {
  var cached = null;

  function labelUser(u) {
    return (
      String(u.full_name || u.username || '') +
      (u.username ? ' (' + u.username + ')' : '')
    );
  }

  function renderChipList(chipsEl, ids, users, multi) {
    if (!chipsEl || !ids) return;
    chipsEl.innerHTML = '';
    ids.forEach(function (id) {
      var u = users.find(function (x) {
        return Number(x.id) === id;
      });
      var name = u ? labelUser(u) : 'User #' + id;
      var pill = document.createElement('span');
      pill.style.cssText =
        'display:inline-flex;align-items:center;gap:.35rem;background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;border-radius:999px;padding:.25rem .55rem;margin:.2rem;font-size:.78rem;font-weight:600;';
      pill.appendChild(document.createTextNode(name));
      var rm = document.createElement('button');
      rm.type = 'button';
      rm.setAttribute('aria-label', 'Remove colleague');
      rm.textContent = '\u00D7';
      rm.style.cssText =
        'border:none;background:rgba(15,118,110,.14);cursor:pointer;line-height:1;border-radius:50%;width:1.35rem;height:1.35rem;font-weight:bold;';
      rm.addEventListener('click', function () {
        var i = ids.indexOf(id);
        if (i >= 0) ids.splice(i, 1);
        renderChipList(chipsEl, ids, users, multi);
      });
      pill.appendChild(rm);
      chipsEl.appendChild(pill);
    });
  }

  /**
   * Re-render chips after hydration (does not bind the Add button again).
   * @param opts {{ chipsId: string, ids: number[], multi?: boolean }}
   */
  function redrawChips(opts) {
    var chipsEl = document.getElementById(opts.chipsId);
    var ids = opts.ids;
    var multi = opts.multi !== false;
    if (!chipsEl || !ids) return Promise.resolve();
    return loadUsers().then(function (users) {
      users.sort(function (a, b) {
        return labelUser(a).localeCompare(labelUser(b), undefined, {
          sensitivity: 'base',
        });
      });
      renderChipList(chipsEl, ids, users, multi);
    });
  }

  function loadUsers() {
    if (cached) return Promise.resolve(cached);
    var tok = global.localStorage ? localStorage.getItem('access_token') : '';
    return fetch('/hr/api/active-users-for-picker', {
      headers: { Authorization: 'Bearer ' + (tok || '') },
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (j) {
        cached = (j && j.users) || [];
        return cached;
      })
      .catch(function () {
        cached = [];
        return cached;
      });
  }

  /**
   * @param opts {{
   *   selectId: string,
   *   addBtnId?: string,
   *   chipsId: string,
   *   ids: number[],
   *   multi?: boolean
   * }}
   */
  function bind(opts) {
    var sel = document.getElementById(opts.selectId);
    var addBtn = document.getElementById(opts.addBtnId);
    var chipsEl = document.getElementById(opts.chipsId);
    var ids = opts.ids;
    var multi = opts.multi !== false;
    if (!sel || !chipsEl || !ids) return Promise.resolve();

    return loadUsers().then(function (users) {
      users.sort(function (a, b) {
        return labelUser(a).localeCompare(labelUser(b), undefined, {
          sensitivity: 'base',
        });
      });
      sel.innerHTML = '<option value="">Select colleague…</option>';
      users.forEach(function (u) {
        var opt = document.createElement('option');
        opt.value = String(u.id);
        opt.textContent = labelUser(u);
        sel.appendChild(opt);
      });
      renderChipList(chipsEl, ids, users, multi);
      function addFromSelect() {
        var id = parseInt(sel.value, 10);
        if (!Number.isFinite(id)) return;
        if (ids.indexOf(id) >= 0) {
          sel.value = '';
          return;
        }
        if (!multi && ids.length >= 1) ids.length = 0;
        ids.push(id);
        sel.value = '';
        renderChipList(chipsEl, ids, users, multi);
      }
      sel.addEventListener('change', addFromSelect);
      if (addBtn) {
        addBtn.addEventListener('click', addFromSelect);
      }
    });
  }

  global.HrColleagueSlotPicker = {
    loadUsers: loadUsers,
    bind: bind,
    redrawChips: redrawChips,
  };
})(window);
