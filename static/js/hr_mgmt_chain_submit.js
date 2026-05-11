/** HR submit: management chain from Admin reporting line; technicians pick Operations manager only. */
(function () {
  const state = {
    omId: [],
    omUsers: [],
    allUsers: [],
    ctx: null,
  };

  function laneFromDom() {
    const w = document.getElementById('hrMgmtChainWrap');
    return (w && w.getAttribute('data-lane')) || 'employee';
  }

  function chip(html) {
    const s = document.createElement('span');
    s.style.cssText =
      'display:inline-flex;align-items:center;gap:.25rem;font-size:.92rem;font-weight:600;padding:.18rem .55rem;border-radius:999px;background:#e2e8f0;color:#0f172a;';
    s.innerHTML = html;
    return s;
  }

  function fillSelect(sel, users) {
    if (!sel) return;
    sel.innerHTML = '<option value="">Select…</option>';
    users.forEach((u) => {
      const o = document.createElement('option');
      o.value = String(u.id);
      o.textContent = u.full_name || u.username || '#' + u.id;
      sel.appendChild(o);
    });
  }

  function showSetupError(msg) {
    const el = document.getElementById('hrMgmtSetupErr');
    if (!el) return;
    if (!msg) {
      el.style.display = 'none';
      el.textContent = '';
      return;
    }
    el.style.display = 'block';
    el.textContent = msg;
  }

  function applyContext(ctx) {
    state.ctx = ctx;
    const lane = ctx.lane || laneFromDom();
    const intro = document.getElementById('hrMgmtIntro');
    const omRow = document.getElementById('hrMgmtOmRow');
    const assignedLbl = document.getElementById('hrMgmtAssignedLbl');
    const chips = document.getElementById('hrMgmtAssignedChips');
    const empty = document.getElementById('hrMgmtAssignedEmpty');
    const gmHint = document.getElementById('hrMgmtRmGmHint');

    if (ctx.admin_profile_bypass) {
      if (intro)
        intro.innerHTML =
          'As an <strong>administrator</strong> with no reporting manager on your profile, this submission ' +
          'skips the PDF management chain and goes straight to the <strong>HR review</strong> queue.';
      if (assignedLbl) assignedLbl.textContent = 'Management chain';
      if (omRow) omRow.style.display = 'none';
      if (gmHint) gmHint.style.display = 'none';
      if (chips) {
        chips.innerHTML = '';
        chips.appendChild(
          chip('Admin — HR review queue (management chain skipped for this submit)')
        );
      }
      if (empty) empty.style.display = 'none';
      showSetupError(null);
      return;
    }

    if (intro) {
      if (lane === 'technician') {
        intro.innerHTML =
          'You are a <strong>technician</strong>. Your <strong>reporting supervisor</strong> is the person set as <em>Reporting manager</em> on your profile (must be a Supervisor account). ' +
          'Select the <strong>operations manager</strong> below. The trail is: reporting supervisor → operations manager → general manager (skipped if your supervisor is the GM) → HR (head office).';
      } else {
        intro.innerHTML =
          'Your <strong>reporting manager</strong> is assigned on your profile by an administrator. This form routes: reporting manager → general manager (skipped if your reporting manager is already the GM) → HR (head office). ' +
          '<strong>No operations manager</strong> step for your role.';
      }
    }

    if (assignedLbl) {
      assignedLbl.textContent = lane === 'technician' ? 'Reporting supervisor' : 'Reporting manager';
    }

    if (omRow) omRow.style.display = ctx.needs_operations_manager ? 'block' : 'none';

    if (gmHint)
      gmHint.style.display = ctx.reporting_contact_is_general_manager ? 'block' : 'none';

    if (chips) chips.innerHTML = '';
    const rc = ctx.reporting_contact;
    if (rc && chips) {
      chips.appendChild(chip(escapeHtml(rc.full_name || '#' + rc.id)));
      if (empty) empty.style.display = 'none';
    } else if (empty) {
      empty.style.display = 'block';
    }

    showSetupError(ctx.setup_error || null);
  }

  function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  function bindOmPick() {
    const sel = document.getElementById('hrMgmtOmSel');
    const add = document.getElementById('hrMgmtOmAdd');
    const chipHost = document.getElementById('hrMgmtOmChips');
    if (!sel || !add || !chipHost) return;
    function nameFor(uid) {
      const u = state.omUsers.find((x) => String(x.id) === String(uid));
      return u ? u.full_name || u.username : null;
    }
    function renderOm() {
      chipHost.innerHTML = '';
      state.omId.forEach((id, i) => {
        const nm = nameFor(id) || 'User #' + id;
        const c = chip(
          nm +
            ' <button type="button" data-i="' +
            i +
            '" style="border:none;background:transparent;cursor:pointer;font-weight:bold">×</button>'
        );
        c.querySelector('button').onclick = () => {
          state.omId.splice(i, 1);
          renderOm();
        };
        chipHost.appendChild(c);
      });
    }
    add.onclick = () => {
      const v = sel.value;
      if (!v) return;
      const uid = parseInt(v, 10);
      if (!uid) return;
      state.omId.length = 0;
      state.omId.push(uid);
      renderOm();
      sel.value = '';
    };
  }

  window.HrMgmtChainValidate = function () {
    if (!document.getElementById('hrMgmtChainWrap')) return null;
    const ctx = state.ctx || {};
    if (ctx.setup_error) return ctx.setup_error;
    if (ctx.admin_profile_bypass) return null;
    if (!ctx.has_reporting_contact) {
      return 'Reporting manager must be set on your profile by an administrator before you can submit.';
    }
    const lane = ctx.lane || laneFromDom();
    if (lane === 'technician') {
      if (!state.omId.length) return 'Select the operations manager.';
    }
    return null;
  };

  window.HrMgmtChainGetPayload = function () {
    if (!document.getElementById('hrMgmtChainWrap')) return {};
    const ctx = state.ctx || {};
    const lane = ctx.lane || laneFromDom();
    const out = {};
    if (lane === 'technician' && state.omId[0]) {
      out.mgmt_operations_manager_signer_id = state.omId[0];
    }
    return out;
  };

  window.HrMgmtChainReset = function () {
    state.omId.length = 0;
    const chipHost = document.getElementById('hrMgmtOmChips');
    if (chipHost) chipHost.innerHTML = '';
  };

  document.addEventListener('DOMContentLoaded', async () => {
    const wrap = document.getElementById('hrMgmtChainWrap');
    if (!wrap) return;

    const token = localStorage.getItem('access_token');
    try {
      const res = await fetch('/hr/api/mgmt-chain-context', {
        headers: token ? { Authorization: 'Bearer ' + token } : {},
      });
      const ctx = await res.json().catch(() => ({}));
      if (!res.ok || !ctx.success) {
        showSetupError(ctx.error || 'Could not load management routing.');
        applyContext({
          lane: laneFromDom(),
          needs_operations_manager: laneFromDom() === 'technician',
          has_reporting_contact: false,
          reporting_contact_is_general_manager: false,
          reporting_contact: null,
          technician_supervisor_valid: false,
          setup_error: ctx.error || 'Could not load management routing.',
        });
      } else {
        applyContext(ctx);
      }
    } catch (_) {
      showSetupError('Network error loading management routing.');
      applyContext({
        lane: laneFromDom(),
        needs_operations_manager: laneFromDom() === 'technician',
        has_reporting_contact: false,
        reporting_contact_is_general_manager: false,
        reporting_contact: null,
        technician_supervisor_valid: false,
        setup_error: 'Network error loading management routing.',
      });
    }

    try {
      if (token) {
        const res = await fetch('/hr/api/active-users-for-picker', {
          headers: { Authorization: 'Bearer ' + token },
        });
        const j = await res.json().catch(() => ({}));
        if (res.ok && j.success && Array.isArray(j.users)) {
          state.allUsers = j.users;
          state.omUsers = j.users.filter((u) => (u.designation || '').toLowerCase() === 'operations_manager');
          fillSelect(document.getElementById('hrMgmtOmSel'), state.omUsers);
        }
      }
    } catch (_) {
      /* ignore */
    }

    bindOmPick();

    const origFetch = window.fetch;
    window.fetch = function (...args) {
      const resource = args[0];
      let config = args[1];
      const url =
        typeof resource === 'string' ? resource : resource instanceof Request ? resource.url : '';
      if (!url.includes('/hr/api/submit') || !document.getElementById('hrMgmtChainWrap')) {
        return origFetch.apply(this, args);
      }
      const err = window.HrMgmtChainValidate?.();
      if (err) {
        return Promise.reject(new Error(err));
      }
      if (config && typeof config.body === 'string') {
        try {
          const data = JSON.parse(config.body);
          Object.assign(data, window.HrMgmtChainGetPayload?.() || {});
          config = Object.assign({}, config, { body: JSON.stringify(data) });
        } catch (_e) {
          /* noop */
        }
      }
      const nextArgs = config !== undefined ? [resource, config] : [resource];
      return origFetch.apply(this, nextArgs);
    };
  });
})();
