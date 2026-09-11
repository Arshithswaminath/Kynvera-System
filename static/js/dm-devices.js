(function (global) {
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function authHeaders(extra) {
    if (typeof fmAuthHeaders === 'function') return fmAuthHeaders(extra);
    const h = Object.assign({}, extra || {});
    const t = localStorage.getItem('access_token');
    if (t) h.Authorization = 'Bearer ' + t;
    return h;
  }
  function notify(msg, type) {
    if (typeof fmNotify === 'function') fmNotify(msg, type || 'info');
  }
  function statusLabel(status) {
    if (typeof fmHumanLabel === 'function') return fmHumanLabel(status, 'Idle');
    return status || 'Idle';
  }
  function deviceRowsHtml(devices) {
    if (!devices.length) {
      return '<tr><td colspan="7">No devices found</td></tr>';
    }
    return devices.map(function (d) {
      const assignee = d.assigned_user_name || d.assigned_user || '—';
      return (
        '<tr data-href="/admin/devices/' + encodeURIComponent(d.id) + '">' +
        '<td data-label="ID">' + esc(d.device_id) + '</td>' +
        '<td data-label="Name">' + esc(d.name) + '</td>' +
        '<td data-label="Type">' + esc(d.device_type || '—') + '</td>' +
        '<td data-label="Building">' + esc(d.building || '—') + '</td>' +
        '<td data-label="Status"><span class="fm-status fm-status-' + esc(d.status || 'idle') + '">' + esc(statusLabel(d.status)) + '</span></td>' +
        '<td data-label="Health">' + (d.health != null ? esc(d.health) : '—') + '</td>' +
        '<td data-label="Assigned">' + esc(assignee) + '</td>' +
        '</tr>'
      );
    }).join('');
  }
  async function fetchDevices(params) {
    const qs = params ? ('?' + new URLSearchParams(params).toString()) : '';
    const res = await fetch('/api/admin/devices' + qs, { headers: authHeaders() });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok || data.success === false) {
      throw new Error(data.error || data.message || 'Failed to load devices');
    }
    return data.devices || (data.data && data.data.devices) || [];
  }
  function bindTableNav(tbody) {
    if (!tbody) return;
    tbody.addEventListener('click', function (e) {
      const tr = e.target.closest('tr[data-href]');
      if (!tr) return;
      if (e.target.closest('a,button')) return;
      location.href = tr.getAttribute('data-href');
    });
  }
  function confirmDialog(opts) {
    return new Promise(function (resolve) {
      const overlay = document.createElement('div');
      overlay.className = 'dm-modal open';
      overlay.setAttribute('role', 'dialog');
      overlay.innerHTML =
        '<div class="dm-modal-card">' +
        '<h2>' + esc(opts.title || 'Confirm') + '</h2>' +
        '<div class="dm-modal-body"><p>' + esc(opts.body || '') + '</p></div>' +
        '<div class="dm-modal-actions">' +
        '<button type="button" class="fm-btn fm-btn-outline" data-dm-cancel>Cancel</button>' +
        '<button type="button" class="fm-btn fm-btn-primary" data-dm-ok>' + esc(opts.ok || 'Remove') + '</button>' +
        '</div></div>';
      document.body.appendChild(overlay);
      function close(ok) {
        overlay.remove();
        resolve(!!ok);
      }
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) close(false);
      });
      overlay.querySelector('[data-dm-cancel]').addEventListener('click', function () { close(false); });
      overlay.querySelector('[data-dm-ok]').addEventListener('click', function () { close(true); });
    });
  }
  async function removeDevice(id, name) {
    const ok = await confirmDialog({
      title: 'Remove this device?',
      body: (name || 'This device') + ' will be removed from the inventory.',
      ok: 'Remove',
    });
    if (!ok) return false;
    const res = await fetch('/api/admin/devices/' + id, { method: 'DELETE', headers: authHeaders() });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) {
      notify(data.error || data.message || 'Failed to remove device', 'error');
      return false;
    }
    notify('Device removed', 'info');
    return true;
  }
  async function enrollFromForm(form) {
    const payload = {};
    new FormData(form).forEach(function (value, key) {
      payload[key] = typeof value === 'string' ? value.trim() : value;
    });
    if (!payload.name) throw new Error('Device name is required');
    const res = await fetch('/api/admin/devices', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(data.error || data.message || 'Failed to enroll device');
    return data.device || (data.data && data.data.device) || data;
  }
  async function importExcel(file) {
    const formData = new FormData();
    formData.append('file', file);
    const headers = authHeaders();
    delete headers['Content-Type'];
    const res = await fetch('/api/admin/devices/import-excel', {
      method: 'POST',
      headers: headers,
      body: formData,
    });
    const json = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(json.error || json.message || 'Failed to import devices');
    const data = json.data || json;
    const imported = Number(data.imported || 0);
    const dup = Number(data.skipped_duplicates || 0);
    const empty = Number(data.skipped_empty || 0);
    let msg = 'Imported ' + imported + ' device(s)';
    if (dup || empty) msg += ' · skipped ' + (dup + empty);
    notify(msg, 'info');
    return data;
  }
  async function downloadSample() {
    const res = await fetch('/api/admin/devices/sample-excel', { headers: authHeaders() });
    if (!res.ok) throw new Error('Failed to download sample Excel');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'device_import_sample.xlsx';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    notify('Sample Excel downloaded', 'info');
  }
  function exportCSV(devices) {
    const rows = [['ID', 'Name', 'Status', 'Type', 'OS', 'Building', 'User']];
    (devices || []).forEach(function (d) {
      rows.push([
        d.device_id, d.name, d.status, d.device_type, d.os, d.building || '',
        d.assigned_user_email || d.assigned_user || '',
      ]);
    });
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(rows.map(function (r) { return r.join(','); }).join('\n'));
    a.download = 'devices_export.csv';
    a.click();
    notify('CSV exported', 'info');
  }
  function sparkHtml(values, max) {
    max = max || 1;
    return (values || []).map(function (n) {
      const h = 6 + Math.round((Number(n) / max) * 16);
      return '<span style="height:' + h + 'px"></span>';
    }).join('');
  }
  function heatHtml(overview) {
    const labels = overview.day_labels || [];
    let html = '';
    (overview.heat_rows || []).forEach(function (row) {
      html += '<div class="dm-ov-heat-row"><span class="dm-ov-heat-label">' + esc(row.label) + '</span>';
      (row.cells || []).forEach(function (cell, i) {
        const n = Number(cell.count || 0);
        const phrase = n === 1 ? '1 device last seen.' : n + ' devices last seen.';
        const text = (row.label || '') + ' of ' + (labels[i] || '') + ' — ' + phrase;
        html += '<span class="dm-ov-heat-cell lv-' + (cell.level || 0) + '" data-dm-tip="' + esc(text) + '"></span>';
      });
      html += '</div>';
    });
    html += '<div class="dm-ov-heat-days"><span></span>';
    labels.forEach(function (label) {
      html += '<span>' + esc(label) + '</span>';
    });
    html += '</div>';
    return html;
  }
  function timelineHtml(overview) {
    return (overview.timeline || []).map(function (mark) {
      const n = Number(mark.count || 0);
      const phrase = n === 1 ? '1 device enrolled.' : n + ' devices enrolled.';
      const tip = esc((mark.label || '') + ' — ' + phrase);
      return (
        '<div class="dm-ov-track-col' + (mark.is_today ? ' is-today' : '') + '">' +
        '<span class="dm-ov-track-dot' + (mark.count ? ' is-on' : '') + '" data-dm-tip="' + tip + '"></span>' +
        (mark.is_peak ? '<span class="dm-ov-pill">' + esc(mark.pill) + '</span>' : '') +
        '<span class="dm-ov-track-day">' + esc(mark.label) + '</span>' +
        '</div>'
      );
    }).join('');
  }
  function setLive(name, fn) {
    document.querySelectorAll('[data-dm-live="' + name + '"]').forEach(fn);
  }
  function syncRangeControls(period, nav) {
    document.querySelectorAll('[data-dm-range]').forEach(function (sel) { sel.value = period; });
    document.querySelectorAll('[data-dm-range-link]').forEach(function (a) {
      a.classList.toggle('is-on', a.getAttribute('data-dm-range-link') === period);
    });
    document.querySelectorAll('[data-dm-live-root]').forEach(function (root) {
      root.setAttribute('data-dm-period', period);
      if (nav) {
        if (nav.year) root.setAttribute('data-dm-year', String(nav.year));
        if (nav.month) root.setAttribute('data-dm-month', String(nav.month));
      }
    });
  }
  function navFromEl(el) {
    if (!el) return null;
    return {
      mode: el.getAttribute('data-mode') || 'month',
      label: (el.querySelector('[data-dm-live="heat-cursor"]') || {}).textContent || '',
      year: Number(el.getAttribute('data-year')) || 0,
      month: Number(el.getAttribute('data-month')) || 0,
      prev_year: Number(el.getAttribute('data-prev-year')) || 0,
      prev_month: Number(el.getAttribute('data-prev-month')) || 0,
      next_year: Number(el.getAttribute('data-next-year')) || 0,
      next_month: Number(el.getAttribute('data-next-month')) || 0,
      can_prev: el.getAttribute('data-can-prev') === '1',
      can_next: el.getAttribute('data-can-next') === '1',
    };
  }
  function writeNavEl(nav) {
    document.querySelectorAll('[data-dm-heat-nav]').forEach(function (el) {
      el.setAttribute('data-mode', nav.mode || 'month');
      el.setAttribute('data-year', String(nav.year || ''));
      el.setAttribute('data-month', String(nav.month || ''));
      el.setAttribute('data-prev-year', String(nav.prev_year || ''));
      el.setAttribute('data-prev-month', String(nav.prev_month || ''));
      el.setAttribute('data-next-year', String(nav.next_year || ''));
      el.setAttribute('data-next-month', String(nav.next_month || ''));
      el.setAttribute('data-can-prev', nav.can_prev ? '1' : '0');
      el.setAttribute('data-can-next', nav.can_next ? '1' : '0');
    });
  }
  function syncHeatNav(nav) {
    nav = nav || {};
    lastNav = nav;
    currentYear = Number(nav.year) || currentYear;
    currentMonth = Number(nav.month) || currentMonth;
    writeNavEl(nav);
    setLive('heat-cursor', function (el) { el.textContent = nav.label || ''; });
    document.querySelectorAll('[data-dm-heat-step]').forEach(function (btn) {
      const dir = Number(btn.getAttribute('data-dm-heat-step'));
      btn.disabled = dir < 0 ? !nav.can_prev : !nav.can_next;
    });
  }
  function renderOverview(overview) {
    if (!overview) return;
    const cols = String(overview.bucket_count || 7);
    setLive('caption', function (el) {
      el.textContent = (overview.period_label || '') + ' · ' + (overview.range_caption || '');
    });
    setLive('report-lead', function (el) {
      const label = String(overview.period_label || '').toLowerCase();
      el.textContent = 'Fleet reporting for ' + label + ' · ' + (overview.range_caption || '');
    });
    setLive('enroll-kicker', function (el) { el.textContent = overview.enroll_kicker || 'Enrolled'; });
    setLive('enroll-value', function (el) {
      el.textContent = overview.enrolled_in_range != null ? String(overview.enrolled_in_range) : '0';
    });
    setLive('enroll-delta', function (el) {
      const chip = overview.enroll_delta || {};
      el.textContent = chip.label || '—';
      el.className = 'dm-ov-delta ' + (chip.css || 'is-flat');
    });
    setLive('enroll-hint', function (el) {
      const chip = overview.enroll_delta || {};
      el.textContent = (chip.label || '—') + ' vs prior period';
    });
    setLive('enroll-spark', function (el) {
      el.innerHTML = sparkHtml(overview.enrolled_spark, overview.spark_max);
    });
    setLive('health-delta', function (el) {
      const chip = overview.health_delta || {};
      el.textContent = chip.label || '—';
      el.className = 'dm-ov-delta ' + (chip.css || 'is-flat');
    });
    setLive('health-spark', function (el) {
      el.innerHTML = sparkHtml(overview.health_spark, overview.health_spark_max);
    });
    setLive('seen-range', function (el) {
      el.textContent = overview.seen_in_range != null ? String(overview.seen_in_range) : '0';
    });
    setLive('period-label', function (el) { el.textContent = overview.period_label || ''; });
    setLive('heat', function (el) {
      el.style.setProperty('--dm-cols', cols);
      el.setAttribute('data-dm-cols', cols);
      el.setAttribute('data-dm-period', overview.period || 'week');
      el.setAttribute('aria-label', 'Last-seen activity ' + (overview.period_label || ''));
      el.innerHTML = heatHtml(overview);
    });
    setLive('heat-hint', function (el) {
      el.textContent = overview.heat_empty_hint || '';
      el.hidden = !overview.heat_empty;
    });
    setLive('timeline', function (el) {
      el.style.setProperty('--dm-cols', cols);
      el.innerHTML = timelineHtml(overview);
    });
    syncRangeControls(overview.period || 'week', overview.heat_nav);
    syncHeatNav(overview.heat_nav);
  }
  async function fetchOverview(range, year, month) {
    const u = new URL('/api/admin/devices/overview', location.origin);
    u.searchParams.set('range', range || 'week');
    if (year) u.searchParams.set('year', String(year));
    if (month) u.searchParams.set('month', String(month));
    const res = await fetch(u.toString(), { headers: authHeaders() });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok || data.success === false) {
      throw new Error(data.error || data.message || 'Failed to load overview');
    }
    return data.overview || (data.data && data.data.overview) || data;
  }
  let rangeToken = 0;
  let currentRange = '';
  let currentYear = 0;
  let currentMonth = 0;
  let lastNav = null;
  function wait(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }
  function fadeMs() {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return 0;
    return 180;
  }
  function pushCursor(range, nav) {
    const u = new URL(location.href);
    u.searchParams.set('range', range);
    if (nav && nav.year) u.searchParams.set('year', String(nav.year));
    else u.searchParams.delete('year');
    if (nav && nav.mode === 'month' && nav.month) {
      u.searchParams.set('month', String(nav.month));
    } else {
      u.searchParams.delete('month');
    }
    history.pushState({ range: range, year: nav && nav.year, month: nav && nav.month }, '', u);
  }
  async function applyRange(range, opts) {
    opts = opts || {};
    range = String(range || 'week').toLowerCase();
    if (range !== 'week' && range !== 'month' && range !== 'all') range = 'week';
    const year = opts.year != null ? opts.year : currentYear;
    const month = opts.month != null ? opts.month : currentMonth;
    if (!opts.force && range === currentRange && year === currentYear && month === currentMonth) return;
    const prev = { range: currentRange, year: currentYear, month: currentMonth };
    currentRange = range;
    if (year) currentYear = Number(year);
    if (month) currentMonth = Number(month);
    syncRangeControls(range, { year: currentYear, month: currentMonth });
    const roots = document.querySelectorAll('[data-dm-live-root]');
    roots.forEach(function (root) { root.classList.add('is-switching'); });
    const token = ++rangeToken;
    try {
      const overview = (await Promise.all([fetchOverview(range, currentYear, currentMonth), wait(fadeMs())]))[0];
      if (token !== rangeToken) return;
      renderOverview(overview);
      if (opts.push !== false) pushCursor(range, overview.heat_nav);
    } catch (err) {
      if (token === rangeToken) {
        currentRange = prev.range;
        currentYear = prev.year;
        currentMonth = prev.month;
        syncRangeControls(prev.range, { year: prev.year, month: prev.month });
        notify(err.message || err, 'error');
      }
    } finally {
      if (token === rangeToken) {
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            roots.forEach(function (root) { root.classList.remove('is-switching'); });
          });
        });
      }
    }
  }
  function stepHeat(dir) {
    if (!lastNav) return;
    if (dir < 0 && !lastNav.can_prev) return;
    if (dir > 0 && !lastNav.can_next) return;
    applyRange(currentRange || 'week', {
      year: dir < 0 ? lastNav.prev_year : lastNav.next_year,
      month: dir < 0 ? lastNav.prev_month : lastNav.next_month,
      force: true,
    });
  }
  function bindLiveRange() {
    if (!document.querySelector('[data-dm-range], [data-dm-range-link], [data-dm-heat-step]')) return;
    const selected = document.querySelector('[data-dm-range-link].is-on, [data-dm-range]');
    const root = document.querySelector('[data-dm-live-root]');
    currentRange = (selected && (selected.getAttribute('data-dm-range-link') || selected.value)) || 'week';
    currentYear = Number(root && root.getAttribute('data-dm-year')) || 0;
    currentMonth = Number(root && root.getAttribute('data-dm-month')) || 0;
    lastNav = navFromEl(document.querySelector('[data-dm-heat-nav]'));
    document.querySelectorAll('[data-dm-range-form]').forEach(function (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        const sel = form.querySelector('[data-dm-range]');
        applyRange(sel ? sel.value : 'week');
      });
    });
    document.querySelectorAll('[data-dm-range]').forEach(function (sel) {
      sel.addEventListener('change', function () { applyRange(sel.value); });
    });
    document.querySelectorAll('[data-dm-range-link]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        applyRange(a.getAttribute('data-dm-range-link'));
      });
    });
    document.querySelectorAll('[data-dm-heat-step]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        stepHeat(Number(btn.getAttribute('data-dm-heat-step')));
      });
    });
    window.addEventListener('popstate', function (e) {
      const u = new URL(location.href);
      const fromState = e.state || {};
      applyRange(fromState.range || u.searchParams.get('range') || 'week', {
        year: fromState.year || u.searchParams.get('year'),
        month: fromState.month || u.searchParams.get('month'),
        push: false,
        force: true,
      });
    });
  }
  function bindTips() {
    let tip = document.getElementById('dmFloatTip');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'dmFloatTip';
      tip.className = 'dm-float-tip';
      tip.setAttribute('role', 'tooltip');
      tip.hidden = true;
      document.body.appendChild(tip);
    }
    function place(e) {
      const pad = 14;
      let x = e.clientX + pad;
      let y = e.clientY + 18;
      const w = tip.offsetWidth || 240;
      const h = tip.offsetHeight || 48;
      if (x + w > window.innerWidth - 8) x = e.clientX - w - 10;
      if (y + h > window.innerHeight - 8) y = e.clientY - h - 12;
      tip.style.left = Math.max(8, x) + 'px';
      tip.style.top = Math.max(8, y) + 'px';
    }
    document.addEventListener('pointerover', function (e) {
      const el = e.target.closest('[data-dm-tip]');
      if (!el) return;
      const text = (el.getAttribute('data-dm-tip') || '').trim();
      if (!text) return;
      tip.textContent = text;
      tip.hidden = false;
      place(e);
    });
    document.addEventListener('pointermove', function (e) {
      if (tip.hidden) return;
      if (!e.target.closest('[data-dm-tip]')) return;
      place(e);
    });
    document.addEventListener('pointerout', function (e) {
      const next = e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('[data-dm-tip]');
      if (next) return;
      tip.hidden = true;
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      bindLiveRange();
      bindTips();
    });
  } else {
    bindLiveRange();
    bindTips();
  }
  global.DM = {
    esc: esc,
    authHeaders: authHeaders,
    notify: notify,
    deviceRowsHtml: deviceRowsHtml,
    fetchDevices: fetchDevices,
    bindTableNav: bindTableNav,
    confirmDialog: confirmDialog,
    removeDevice: removeDevice,
    enrollFromForm: enrollFromForm,
    importExcel: importExcel,
    downloadSample: downloadSample,
    exportCSV: exportCSV,
    fetchOverview: fetchOverview,
    applyRange: applyRange,
  };
})(window);
