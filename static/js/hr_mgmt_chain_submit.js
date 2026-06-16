/**
 * HR submission — Box 2 ("who will sign by name").
 *
 * Routing is derived server-side from the submitter's lane (technician,
 * supervisor, office staff). The client only renders ctx.chain returned by
 * /hr/api/mgmt-chain-context — never sends signer IDs.
 */
(function () {
  const state = { ctx: null };

  function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
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

  function showMissingPools(pools) {
    const el = document.getElementById('hrMgmtMissingPools');
    if (!el) return;
    if (!pools || !pools.length) {
      el.style.display = 'none';
      el.innerHTML = '';
      return;
    }
    const list = pools.map(escapeHtml).join(', ');
    el.style.display = 'block';
    el.innerHTML =
      'Heads up: no active users are set up yet for: <strong>' + list + '</strong>. ' +
      'Ask an administrator to assign the right designation to the relevant staff so this form can complete.';
  }

  function appendStep(list, num, role, name, desc, modifier) {
    const li = document.createElement('li');
    li.className = 'hr-mgmt-chain-step' + (modifier ? ' ' + modifier : '');
    li.innerHTML =
      '<div class="hr-mgmt-chain-step__num">' + num + '</div>' +
      '<div class="hr-mgmt-chain-step__body">' +
      '<div class="hr-mgmt-chain-step__role">' + escapeHtml(role) + '</div>' +
      '<div class="hr-mgmt-chain-step__name">' + escapeHtml(name) + '</div>' +
      (desc ? '<div class="hr-mgmt-chain-step__desc">' + escapeHtml(desc) + '</div>' : '') +
      '</div>';
    list.appendChild(li);
  }

  function renderChain(ctx) {
    const list = document.getElementById('hrMgmtChainList');
    if (!list) return;
    list.innerHTML = '';

    if (ctx.admin_profile_bypass) {
      appendStep(
        list,
        1,
        'HR review queue',
        'Direct to HR',
        'Admin submission: the management chain is skipped.',
        '',
      );
      return;
    }

    const chain = Array.isArray(ctx.chain) ? ctx.chain : [];
    if (!chain.length) {
      // Setup error path — sidebar shows the banner; leave list empty.
      return;
    }

    let n = 1;
    chain.forEach((c) => {
      const cls = c.missing ? 'hr-mgmt-chain-step--missing' : '';
      const desc = c.missing
        ? (c.key === 'supervisor'
            ? 'Not set on your profile. Ask an administrator to assign your supervisor.'
            : 'No active users with this role yet. Ask an administrator to assign someone.')
        : c.who_detail;
      appendStep(
        list,
        n++,
        c.role_label || 'Signer',
        c.who_label || 'Assigned signer',
        desc,
        cls,
      );
    });
  }

  function applyContext(ctx) {
    state.ctx = ctx;

    const intro = document.getElementById('hrMgmtIntro');
    if (intro) {
      intro.textContent =
        ctx.lane_intro ||
        ctx.setup_error ||
        (ctx.lane ? 'Approval routing loaded.' : 'Could not determine approval routing.');
    }

    const flow = document.getElementById('hrMgmtFlow');
    if (flow) {
      if (ctx.lane_flow) {
        flow.style.display = 'block';
        flow.innerHTML = 'Order: <strong>' + escapeHtml(ctx.lane_flow) + '</strong>';
      } else {
        flow.style.display = 'none';
        flow.innerHTML = '';
      }
    }

    renderChain(normalizeCtx(ctx));
    showSetupError(ctx.setup_error || null);
    showMissingPools(ctx.missing_pools || []);

    // Expose lane after UI is painted so listeners cannot block intro/chain updates.
    try {
      window.__hrMgmtChainLane = ctx.lane || null;
      window.__hrMgmtChainSigners = (ctx.chain || []).map(function (c) {
        return {
          key: c.key,
          role: c.role_label || 'Signer',
          name: c.who_label || 'Assigned signer',
          missing: !!c.missing,
        };
      });
      window.__hrMgmtChainSupervisor = ctx.supervisor || null;
      const managerLabel = ctx.lane === 'technician'
        ? 'Supervisor signature'
        : (ctx.lane === 'supervisor' ? 'Operations manager signature' : 'General manager signature');
      window.__hrMgmtManagerSigLabel = managerLabel;
      document.dispatchEvent(new CustomEvent('hr-mgmt-chain-ready', {
        detail: {
          lane: ctx.lane,
          managerLabel,
          signers: window.__hrMgmtChainSigners,
          supervisor: ctx.supervisor || null,
        },
      }));
    } catch (_) { /* ignore */ }
  }

  /** Backward-compat: older API responses used `preview` instead of `chain`. */
  function normalizeCtx(ctx) {
    if (Array.isArray(ctx.chain) && ctx.chain.length) return ctx;
    const preview = Array.isArray(ctx.preview) ? ctx.preview : [];
    if (!preview.length) return ctx;
    return Object.assign({}, ctx, {
      chain: preview.map(function (p) {
        return {
          key: (p.designation || 'reporting_manager').replace(/\s+/g, '_'),
          role_label: p.role_label || 'Reporting manager',
          who_label: p.full_name || 'Assigned signer',
          who_detail: null,
          missing: false,
        };
      }),
    });
  }

  function boot() {
    const wrap = document.getElementById('hrMgmtChainWrap');
    if (!wrap || wrap.dataset.hrMgmtChainBooted === '1') return;
    wrap.dataset.hrMgmtChainBooted = '1';

    const token = localStorage.getItem('access_token');
    var formType = document.body.getAttribute('data-hr-form-type') || '';
    var ctxUrl = '/hr/api/mgmt-chain-context';
    if (formType) {
      ctxUrl += '?form_type=' + encodeURIComponent(formType);
    }
    fetch(ctxUrl, {
      headers: token ? { Authorization: 'Bearer ' + token } : {},
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (ctx) {
          if (!res.ok || !ctx.success) {
            applyContext({
              chain: [],
              missing_pools: [],
              setup_error: ctx.error || 'Could not load management routing.',
            });
          } else {
            applyContext(ctx);
          }
        });
      })
      .catch(function () {
        applyContext({
          chain: [],
          missing_pools: [],
          setup_error: 'Network error loading management routing.',
        });
      });
  }

  window.HrMgmtChainValidate = function () {
    if (!document.getElementById('hrMgmtChainWrap')) return null;
    const ctx = state.ctx || {};
    if (ctx.setup_error) return ctx.setup_error;
    return null;
  };

  window.HrMgmtChainGetPayload = function () {
    // Routing is fully derived server-side — never send signer IDs.
    return {};
  };

  window.HrMgmtChainReset = function () {
    /* no user-picked state to reset */
  };

  document.addEventListener('DOMContentLoaded', boot);
  if (document.readyState !== 'loading') boot();

  (function installSubmitFetchHook() {
    const origFetch = window.fetch;
    window.fetch = function (...args) {
      const resource = args[0];
      const url =
        typeof resource === 'string' ? resource : resource instanceof Request ? resource.url : '';
      if (!url.includes('/hr/api/submit') || !document.getElementById('hrMgmtChainWrap')) {
        return origFetch.apply(this, args);
      }
      const err = window.HrMgmtChainValidate?.();
      if (err) return Promise.reject(new Error(err));
      return origFetch.apply(this, args);
    };
  })();
})();
