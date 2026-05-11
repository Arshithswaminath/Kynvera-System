/**
 * Persist HR forms as workflow drafts (/api/workflow/submissions/save-draft).
 */
(function (global) {
  var draftState = { id: null, storageKeyFor: {} };

  function authJsonHeaders() {
    var t = localStorage.getItem('access_token');
    return {
      Authorization: 'Bearer ' + t,
      'Content-Type': 'application/json',
    };
  }

  function applyFlatForm(form, fd) {
    if (!form || !fd || typeof fd !== 'object') return;
    Object.keys(fd).forEach(function (k) {
      if (k === '_routed_signoffs' || k === 'hr_mgmt_chain') return;
      var el = form.elements.namedItem(k);
      if (!el || !el.tagName) return;
      if (el.disabled) return;
      var v = fd[k];
      if (el.tagName === 'TEXTAREA') {
        el.value = v == null ? '' : String(v);
        return;
      }
      if (el.type === 'hidden' && /signature$/i.test(k) && typeof v === 'string' && v.indexOf('data:image') === 0) {
        el.value = v;
        var wrap = el.closest('.sig-wrap');
        if (wrap) {
          var img = wrap.querySelector('img');
          var ph = wrap.querySelector('.sig-ph');
          if (img) {
            img.src = v;
            img.style.display = 'block';
          }
          if (ph) ph.style.display = 'none';
          var rm = wrap.querySelector('.btn-rm');
          if (rm) rm.style.display = 'inline-flex';
        }
        return;
      }
      if (el.type === 'checkbox' || el.type === 'radio') return;
      if (el.tagName === 'INPUT' || el.tagName === 'SELECT')
        el.value = v == null ? '' : String(v);
    });
  }

  function attach(opt) {
    if (!opt || !opt.formId || !opt.moduleType) return;
    draftState.storageKeyFor[opt.moduleType] = 'hr_form_draft_id_' + String(opt.moduleType).replace(/[^\w\-]/g, '_');
    draftState.id = null;

    if (typeof URLSearchParams !== 'undefined') {
      if (new URLSearchParams(location.search).get('edit')) return;
    }

    var form = document.getElementById(opt.formId);
    if (!form) return;

    var key = draftState.storageKeyFor[opt.moduleType];
    var sid = typeof URLSearchParams !== 'undefined' ? new URLSearchParams(location.search).get('draft') : null;
    if (!sid && global.localStorage) sid = global.localStorage.getItem(key);
    if (sid) draftState.id = sid.trim();

    var saveBtns =
      typeof opt.saveButtonSelector === 'string' && opt.saveButtonSelector
        ? Array.prototype.slice.call(document.querySelectorAll(opt.saveButtonSelector))
        : opt.saveBtnId
          ? (function () {
              var x = document.getElementById(opt.saveBtnId);
              return x ? [x] : [];
            })()
          : [];

    function collectSlice() {
      var o = {};
      form.querySelectorAll('input, textarea, select').forEach(function (inp) {
        if (!inp.name || inp.disabled) return;
        var ty = inp.type;
        if (ty === 'file' || ty === 'button' || ty === 'submit' || ty === 'reset') return;
        if ((ty === 'checkbox' || ty === 'radio') && !inp.checked) return;
        o[inp.name] = ty === 'checkbox' ? inp.checked : inp.value;
      });
      if (typeof opt.extraCollect === 'function') Object.assign(o, opt.extraCollect() || {});
      return o;
    }

    async function persistDraft(btn) {
      var token = localStorage.getItem('access_token');
      if (!token) {
        alert('Please sign in to save progress.');
        return;
      }
      var slice = collectSlice();
      if (!slice.form_type) {
        slice.form_type = opt.formTypeSlug || opt.moduleType.replace(/^hr_/, '');
      }
      var site =
        slice.employee_name ||
        slice.site_name ||
        slice.complainant_name ||
        slice.candidate_name ||
        'HR draft';
      var visit = slice.date_of_joining || slice.today_date || slice.visit_date || new Date().toISOString().slice(0, 10);
      var body = {
        module_type: opt.moduleType,
        form_data: slice,
        site_name: typeof site === 'string' ? site.slice(0, 200) : 'HR draft',
      };
      var vd = typeof visit === 'string' ? visit.slice(0, 10) : '';
      if (vd) body.visit_date = vd;
      if (draftState.id) body.submission_id = draftState.id;

      var prev = btn && btn.textContent;
      if (btn) {
        btn.disabled = true;
        btn.textContent = 'Saving…';
      }
      try {
        var res = await fetch('/api/workflow/submissions/save-draft', {
          method: 'POST',
          headers: authJsonHeaders(),
          body: JSON.stringify(body),
        });
        var j = await res.json().catch(function () {
          return {};
        });
        if (!res.ok || j.success === false) {
          alert(j.error || j.message || 'Could not save draft');
          return;
        }
        draftState.id = j.submission_id || draftState.id;
        if (global.localStorage && draftState.id) global.localStorage.setItem(key, draftState.id);
        if (draftState.id && typeof history.replaceState === 'function') {
          var ps = new URLSearchParams(location.search);
          ps.set('draft', draftState.id);
          ps.delete('edit');
          history.replaceState(null, '', location.pathname + (ps.toString() ? '?' + ps.toString() : ''));
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = prev || 'Save progress';
        }
      }
    }

    saveBtns.forEach(function (b) {
      b.addEventListener('click', function () {
        persistDraft(b);
      });
    });

    if (sid) {
      fetch('/api/workflow/submissions/' + encodeURIComponent(sid), { headers: { Authorization: 'Bearer ' + localStorage.getItem('access_token') } })
        .then(function (r) {
          return r.json();
        })
        .then(function (payload) {
          if (!payload || payload.success === false || (payload.status || '') !== 'draft') return;
          var mod = payload.module_type || payload.module;
          if (mod !== opt.moduleType) return;
          draftState.id = payload.submission_id || sid;
          var fd = payload.form_data || {};
          applyFlatForm(form, fd);
          if (typeof opt.extraApply === 'function') opt.extraApply(fd);
        })
        .catch(function () {});
    }
  }

  global.HrFormDraft = {
    attach: attach,
    resumeDraftSubmissionId: function () {
      return draftState.id;
    },
    clearStoredId: function (moduleType) {
      var key = draftState.storageKeyFor[moduleType];
      if (key && global.localStorage) global.localStorage.removeItem(key);
      draftState.id = null;
    },
  };
})(window);
