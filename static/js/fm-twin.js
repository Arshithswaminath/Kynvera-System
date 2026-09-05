/* 2D Digital Twin — live floor-plan pins + side panel */
(function () {
  const canWrite = !!window.FM_TWIN_CAN_WRITE;
  const select = document.getElementById('planSelect');
  const stage = document.getElementById('twinStage');
  const recBtn = document.getElementById('recBtn');
  const downloadBtn = document.getElementById('downloadPlanBtn');
  const editBtn = document.getElementById('editBtn');
  const saveBtn = document.getElementById('savePinsBtn');
  const deleteBtn = document.getElementById('deletePlanBtn');
  const replaceBtn = document.getElementById('replaceImageBtn');
  const replaceInput = document.getElementById('replaceImageInput');
  const pinPanel = document.getElementById('twinPinPanel');
  const recPanel = document.getElementById('twinRecPanel');
  const sideHint = document.getElementById('twinSideHint');
  const kpis = document.getElementById('twinKpis');

  function humanLabel(value, fallback) {
    if (typeof fmHumanLabel === 'function') return fmHumanLabel(value, fallback);
    const raw = String(value == null ? '' : value).trim();
    if (!raw) return fallback == null ? '—' : fallback;
    return raw;
  }
  let plan = null;
  let pins = [];
  let selectedId = null;
  let editMode = false;
  let dirty = false;
  let pendingAsset = null;
  let buildingAssets = [];
  let draftLoc = null;
  let jumpLock = { building: '', floor: '' };
  let drag = null;
  let pan = null;
  let pinch = null;
  let skipPlaceClick = false;
  const zoomBox = document.getElementById('twinZoom');
  const zoomLabel = document.getElementById('zoomLabel');
  const editBanner = document.getElementById('twinEditBanner');
  const legend = document.getElementById('twinLegend');
  const placeCursor = document.getElementById('twinPlaceCursor');
  const twinMap = document.getElementById('twinMap');
  const pinTip = document.getElementById('twinPinTip');
  let zoom = 1;
  let severityFilter = null;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function samePlace(a, b) {
    return String(a || '').trim().toLowerCase() === String(b || '').trim().toLowerCase();
  }

  function locLabel(building, floor) {
    return [building, floor].filter(Boolean).join(' / ') || 'this floor';
  }

  function locContext() {
    return plan || draftLoc || {};
  }

  async function api(url, opts) {
    const headers = fmAuthHeaders(Object.assign({}, (opts && opts.headers) || {}));
    const res = await fetch(url, Object.assign({}, opts, { headers }));
    let data = {};
    try { data = await res.json(); } catch (_) { data = {}; }
    return { ok: res.ok, status: res.status, data };
  }

  function setDirty(on) {
    dirty = !!on;
    if (saveBtn) {
      saveBtn.hidden = !(editMode || dirty);
      saveBtn.disabled = !dirty;
      saveBtn.classList.toggle('fm-btn-primary', editMode && dirty);
      saveBtn.classList.toggle('fm-btn-outline', !(editMode && dirty));
    }
  }

  async function persistPins() {
    if (!plan) return { ok: false, error: 'No plan selected' };
    const hotspots = pins.map((p) => ({
      id: p.id,
      room: p.room,
      x_pct: p.x_pct,
      y_pct: p.y_pct,
      asset_ids: p.asset_ids || [],
      severity: p.severity || 'ok',
    }));
    const res = await api('/assets/api/floor-plans/' + plan.id, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hotspots }),
    });
    if (!res.ok || !res.data.success) {
      return { ok: false, error: (res.data && res.data.error) || 'Could not save pins' };
    }
    plan = res.data.plan;
    pins = (plan.hotspots || []).map((h, i) => Object.assign({ id: h.id || ('hs-' + (i + 1)) }, h));
    setDirty(false);
    return { ok: true };
  }

  function counts() {
    const c = { crit: 0, warn: 0, ok: 0 };
    pins.forEach((p) => { c[p.severity || 'ok'] = (c[p.severity || 'ok'] || 0) + 1; });
    return c;
  }

  function renderKpis() {
    const c = counts();
    const total = (c.crit || 0) + (c.warn || 0) + (c.ok || 0);
    document.getElementById('kpiCrit').textContent = c.crit || 0;
    document.getElementById('kpiWarn').textContent = c.warn || 0;
    document.getElementById('kpiOk').textContent = c.ok || 0;
    const totalEl = document.getElementById('kpiTotal');
    const labelEl = document.getElementById('kpiTotalLabel');
    if (totalEl) totalEl.textContent = total;
    if (labelEl) labelEl.textContent = total === 1 ? 'room on this floor' : 'rooms on this floor';
    const bar = document.getElementById('kpiBar');
    if (bar) {
      bar.innerHTML = total
        ? `<span class="twin-health-seg crit" style="flex:${c.crit || 0}"></span>`
          + `<span class="twin-health-seg warn" style="flex:${c.warn || 0}"></span>`
          + `<span class="twin-health-seg ok" style="flex:${c.ok || 0}"></span>`
        : '<span class="twin-health-empty"></span>';
    }
    if (kpis) {
      kpis.hidden = !plan;
      kpis.querySelectorAll('.twin-filter').forEach((btn) => {
        const sev = btn.dataset.sev;
        btn.classList.toggle('is-empty', !(c[sev] > 0));
        btn.classList.toggle('is-on', severityFilter === sev);
        btn.setAttribute('aria-pressed', severityFilter === sev ? 'true' : 'false');
      });
    }
  }

  function nextPinName() {
    let n = pins.length + 1;
    const used = new Set(pins.map((p) => (p.room || '').trim().toLowerCase()));
    while (used.has('pin ' + n)) n += 1;
    return 'Pin ' + n;
  }

  function hidePlaceCursor() {
    if (placeCursor) placeCursor.hidden = true;
  }

  function movePlaceCursor(e) {
    if (!placeCursor || !twinMap) return;
    if (!editMode || drag || pinch || (pan && pan.moved) || e.target.closest('.twin-hotspot')) {
      hidePlaceCursor();
      return;
    }
    const r = twinMap.getBoundingClientRect();
    placeCursor.hidden = false;
    placeCursor.style.left = (e.clientX - r.left) + 'px';
    placeCursor.style.top = (e.clientY - r.top) + 'px';
  }

  function setEditMode(on) {
    editMode = !!on;
    stage.classList.toggle('is-editing', editMode);
    document.getElementById('twinMap')?.classList.toggle('is-editing', editMode);
    if (editBanner) editBanner.hidden = !editMode;
    if (!editMode) hidePlaceCursor();
    if (editBtn) {
      editBtn.textContent = editMode ? 'Done placing' : 'Place pins';
      editBtn.classList.toggle('is-on', editMode);
      editBtn.setAttribute('aria-pressed', editMode ? 'true' : 'false');
    }
    setDirty(dirty);
  }

  function clampPct(n) {
    const v = Number(n);
    if (!Number.isFinite(v)) return 50;
    return Math.max(0, Math.min(100, v));
  }

  function pctFromEvent(ev) {
    const img = stage.querySelector('img');
    const box = (img || stage).getBoundingClientRect();
    const x = ((ev.clientX - box.left) / box.width) * 100;
    const y = ((ev.clientY - box.top) / box.height) * 100;
    return { x: clampPct(x), y: clampPct(y) };
  }

  function canvasEl() {
    return stage.querySelector('.twin-canvas') || stage;
  }

  function applyZoom() {
    const canvas = stage.querySelector('.twin-canvas');
    if (canvas) canvas.style.width = (zoom * 100) + '%';
    if (zoomLabel) zoomLabel.textContent = Math.round(zoom * 100) + '%';
  }

  function setZoom(next, pt) {
    const canvas = stage.querySelector('.twin-canvas');
    const clamped = Math.max(1, Math.min(4, Math.round(next * 20) / 20));
    if (clamped === zoom) {
      applyZoom();
      return;
    }

    let originX = 0.5;
    let originY = 0.5;
    if (canvas && pt) {
      const rect = canvas.getBoundingClientRect();
      if (rect.width) originX = (pt.x - rect.left) / rect.width;
      if (rect.height) originY = (pt.y - rect.top) / rect.height;
    }

    zoom = clamped;
    applyZoom();

    if (!canvas) return;
    if (pt) {
      const stageRect = stage.getBoundingClientRect();
      const targetX = canvas.offsetLeft + originX * canvas.offsetWidth;
      const targetY = canvas.offsetTop + originY * canvas.offsetHeight;
      stage.scrollLeft = targetX - (pt.x - stageRect.left);
      stage.scrollTop = targetY - (pt.y - stageRect.top);
    }
  }

  function pinById(id) {
    return pins.find((p) => String(p.id) === String(id));
  }

  function raiseUrl(assetId) {
    const code = encodeURIComponent(assetId || '');
    return '/tickets/new?asset_code=' + code;
  }

  function sevLabel(sev) {
    return sev === 'crit' ? 'Critical' : sev === 'warn' ? 'Warning' : 'Healthy';
  }

  function hotspotClass(h) {
    const sev = h.severity || 'ok';
    return 'twin-hotspot ' + sev
      + (String(h.id) === String(selectedId) ? ' is-selected' : '')
      + (severityFilter && sev !== severityFilter && String(h.id) !== String(selectedId) ? ' is-dimmed' : '');
  }

  function syncHotspotClasses() {
    const host = canvasEl();
    if (!host) return;
    host.querySelectorAll('.twin-hotspot').forEach((el) => {
      const h = pinById(el.dataset.id);
      if (h) el.className = hotspotClass(h);
    });
  }

  function scrollStageToEl(el) {
    if (!el || !stage) return;
    const er = el.getBoundingClientRect();
    const sr = stage.getBoundingClientRect();
    const pad = 28;
    let dx = 0;
    let dy = 0;
    if (er.left < sr.left + pad) dx = er.left - sr.left - pad;
    else if (er.right > sr.right - pad) dx = er.right - (sr.right - pad);
    if (er.top < sr.top + pad) dy = er.top - sr.top - pad;
    else if (er.bottom > sr.bottom - pad) dy = er.bottom - (sr.bottom - pad);
    if (dx) stage.scrollLeft += dx;
    if (dy) stage.scrollTop += dy;
  }

  function selectPin(id, fromList) {
    selectedId = id;
    syncHotspotClasses();
    renderSide();
    if (fromList) {
      const el = canvasEl().querySelector('.twin-hotspot[data-id="' + String(id).replace(/"/g, '') + '"]');
      scrollStageToEl(el);
    }
  }

  function addAssetHref(room) {
    const loc = locContext();
    const params = new URLSearchParams();
    const projectId = (plan && plan.project_id) || window.FM_TWIN_PROJECT_ID;
    if (projectId) params.set('project_id', projectId);
    if (loc.building) params.set('building', loc.building);
    if (loc.floor) params.set('floor', loc.floor);
    const roomName = (room || '').trim();
    if (roomName && !/^Pin\s+\d+$/i.test(roomName)) params.set('room', roomName);
    return '/assets/new' + (params.toString() ? '?' + params.toString() : '');
  }

  function floorAssetsHtml() {
    const loc = locContext();
    const pinnedCodes = new Set();
    pins.forEach((h) => (h.asset_ids || []).forEach((id) => pinnedCodes.add(String(id))));
    const locText = [loc.building, loc.floor].filter(Boolean).join(' / ');
    const n = buildingAssets.length;
    const rows = buildingAssets.map((a) => {
      const on = pinnedCodes.has(String(a.asset_id));
      const where = [a.room, humanLabel(a.asset_type, '')].filter(Boolean).join(' · ');
      const href = a.url || ('/assets/' + a.asset_id);
      return `<li>
        <a href="${esc(href)}">${esc(a.asset_id)}</a>
        <span>${esc(a.name || '')}${where ? ' · ' + esc(where) : ''}</span>
        <span class="twin-chip ${on ? 'ok' : 'warn'}">${on ? 'On drawing' : 'Not pinned'}</span>
      </li>`;
    }).join('');
    const empty = `<div class="twin-floor-empty">
        <p>No FM assets registered for ${esc(locText || 'this floor')} yet.</p>
        ${canWrite ? `<a class="fm-btn fm-btn-outline" href="${esc(addAssetHref())}">Add asset</a>` : ''}
      </div>`;
    return `
      <section class="twin-floor-assets">
        <div class="twin-pin-list-head">
          <h2>Assets on this floor</h2>
          <span>${n} fed</span>
        </div>
        ${locText ? `<p class="twin-floor-loc">${esc(locText)}</p>` : ''}
        ${rows ? `<ul class="twin-list">${rows}</ul>` : empty}
      </section>
    `;
  }

  function renderPinList() {
    if (sideHint) sideHint.hidden = true;
    pinPanel.hidden = false;
    const cards = pins.map((h) => {
      const sev = h.severity || 'ok';
      const nAssets = (h.asset_ids || []).length || (h.assets || []).length;
      const nWo = Number(h.open_ticket_count || (h.open_tickets || []).length || 0);
      const assetBit = nAssets ? (nAssets + ' asset' + (nAssets === 1 ? '' : 's')) : 'No assets';
      const woBit = nWo ? (nWo + ' open work') : 'No open work';
      return `<button type="button" class="twin-pin-card" data-pin="${esc(h.id)}">
        <span class="twin-pin-card-dot ${esc(sev)}" aria-hidden="true"></span>
        <span class="twin-pin-card-copy">
          <strong>${esc(h.room || 'Pin')}</strong>
          <span>${esc(assetBit)} · ${esc(woBit)}</span>
        </span>
        <span class="twin-chip ${esc(sev)}">${sevLabel(sev)}</span>
      </button>`;
    }).join('');
    const pinBlock = pins.length
      ? `<div class="twin-pin-list-head">
        <h2>Pins</h2>
        <span>${pins.length} on this floor</span>
      </div>
      ${editMode ? '<p class="twin-status-why">Click the drawing to drop a pin, or open a card.</p>' : ''}
      <div class="twin-pin-cards">${cards}</div>`
      : `<div class="twin-pin-list-head">
        <h2>Pins</h2>
        <span>None yet</span>
      </div>
      <p class="twin-status-why">${editMode
        ? 'Click the drawing to drop a marker, then name the room and tick the assets.'
        : (draftLoc
          ? 'Add a drawing on the left, then place pins for rooms on this floor.'
          : 'Use Place pins to mark rooms on this floor.')}</p>`;
    pinPanel.innerHTML = pinBlock + floorAssetsHtml();
    pinPanel.querySelectorAll('[data-pin]').forEach((btn) => {
      btn.addEventListener('click', () => selectPin(btn.dataset.pin, true));
    });
  }

  function renderSide(opts) {
    const pin = selectedId ? pinById(selectedId) : null;
    if (!pin) {
      if (!plan && !draftLoc) {
        pinPanel.hidden = true;
        pinPanel.innerHTML = '';
        if (sideHint) {
          sideHint.hidden = false;
          const title = sideHint.querySelector('strong');
          const copy = sideHint.querySelector('p');
          if (title) title.textContent = 'Select a pin';
          if (copy) copy.textContent = 'Click a marker on the drawing to see linked assets and open work orders.';
        }
        return;
      }
      renderPinList();
      return;
    }
    if (sideHint) sideHint.hidden = true;
    pinPanel.hidden = false;
    const sev = pin.severity || 'ok';
    const assets = pin.assets || [];
    const tickets = pin.open_tickets || [];
    const q = (opts && opts.assetQuery) || '';
    const filteredAssets = buildingAssets.filter((a) => {
      if (!q) return true;
      const hay = [a.asset_id, a.name, a.room, a.asset_type].filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q.toLowerCase());
    });
    const assetOpts = filteredAssets.map((a) => {
      const on = (pin.asset_ids || []).includes(a.asset_id);
      return `<label class="twin-asset-opt"><input type="checkbox" data-asset="${esc(a.asset_id)}" ${on ? 'checked' : ''}> ${esc(a.asset_id)} — ${esc(a.name)}</label>`;
    }).join('');
    const assetRows = assets.length
      ? assets.map((a) => `
          <li>
            <a href="${esc(a.url)}">${esc(a.asset_id)}</a>
            <span>${esc(a.name)}</span>
            <span class="twin-chip ${esc(a.severity || 'ok')}">${a.health_score != null ? esc(a.health_score) + '%' : esc(humanLabel(a.status, ''))}</span>
          </li>`).join('')
      : '<li class="fm-muted">No assets linked</li>';
    const pinAddHref = addAssetHref(pin.room);
    let ticketRows = tickets.length
      ? tickets.map((t) => `
          <li>
            <a href="${esc(t.url)}">${esc(t.ticket_id)}</a>
            <span>${esc(t.title)}</span>
            <span class="twin-chip ${esc((t.priority === 'critical' || t.priority === 'high') ? 'crit' : 'warn')}">${esc(humanLabel(t.priority))}</span>
          </li>`).join('')
      : '<li class="fm-muted">No open work orders</li>';
    if (tickets.length && (pin.open_ticket_count || 0) > tickets.length) {
      ticketRows += `<li class="fm-muted">+${esc((pin.open_ticket_count || 0) - tickets.length)} more open work orders</li>`;
    }
    const firstAsset = (pin.asset_ids && pin.asset_ids[0]) || (assets[0] && assets[0].asset_id) || '';
    const live = pin.live_severity || sev;
    const liveLabel = live === 'crit' ? 'Critical' : live === 'warn' ? 'Warning' : 'Healthy';
    let sevWhy = 'Sets the pin colour on the drawing.';
    if (canWrite && live !== sev) sevWhy = 'Live work orders suggest ' + liveLabel + '.';
    else if (!canWrite && sev === 'crit') sevWhy = 'Open high/critical work, or asset health below 40%.';
    else if (!canWrite && sev === 'warn') sevWhy = 'Open work, inactive asset, or health below 70%.';
    else if (!canWrite && !assets.length && !(pin.asset_ids || []).length) sevWhy = 'Link assets to drive this from live work orders.';
    else if (!canWrite) sevWhy = 'No open work orders on linked assets.';
    const healthPick = canWrite ? `
      <fieldset class="twin-health-pick">
        <legend>Pin health</legend>
        <div class="twin-health-opts" role="radiogroup" aria-label="Pin health">
          <label class="twin-health-opt ok${sev === 'ok' ? ' is-on' : ''}">
            <input type="radio" name="pinHealth" value="ok"${sev === 'ok' ? ' checked' : ''}> Healthy
          </label>
          <label class="twin-health-opt warn${sev === 'warn' ? ' is-on' : ''}">
            <input type="radio" name="pinHealth" value="warn"${sev === 'warn' ? ' checked' : ''}> Warning
          </label>
          <label class="twin-health-opt crit${sev === 'crit' ? ' is-on' : ''}">
            <input type="radio" name="pinHealth" value="crit"${sev === 'crit' ? ' checked' : ''}> Critical
          </label>
        </div>
      </fieldset>` : `<span class="twin-chip ${esc(sev)}" title="${esc(sevWhy)}">${sevLabel(sev)}</span>`;
    pinPanel.innerHTML = `
      <button type="button" class="twin-back-list" id="twinBackList">All pins</button>
      <div class="twin-pin-head">
        <h2>${esc(pin.room || 'Room')}</h2>
        ${canWrite ? '' : healthPick}
      </div>
      ${canWrite ? healthPick : ''}
      <p class="twin-status-why">${esc(sevWhy)}</p>
      ${pin.note && !editMode ? `<p class="twin-note">${esc(pin.note)}</p>` : ''}
      ${editMode ? `
        <label class="twin-edit-label">Room name
          <input class="fm-input" id="pinRoomName" value="${esc(pin.room || '')}" placeholder="e.g. Master Bedroom">
        </label>
        <label class="twin-edit-label">Link assets
          <input class="fm-input" id="pinAssetQ" value="${esc(q)}" placeholder="Search AST-… or name">
        </label>
        <div class="twin-asset-pick">
          ${assetOpts || '<p class="fm-muted">No assets in this building</p>'}
        </div>
      ` : `
        <h3>Assets</h3>
        <ul class="twin-list">${assetRows}</ul>
      `}
      <h3>Open work orders</h3>
      <ul class="twin-list">${ticketRows}</ul>
      <div class="twin-pin-actions">
        ${firstAsset ? `<a class="fm-btn fm-btn-primary" href="${raiseUrl(firstAsset)}">Raise work order</a>` : (editMode ? '' : `<span class="fm-muted">Link an asset to raise a work order.</span>`)}
        ${canWrite && !firstAsset ? `<a class="fm-btn fm-btn-outline" href="${esc(pinAddHref)}">Add asset</a>` : ''}
        ${editMode ? `<button type="button" class="fm-btn fm-btn-outline twin-btn-danger" id="removePinBtn">Remove pin</button>` : ''}
      </div>
    `;
    pinPanel.querySelector('#twinBackList')?.addEventListener('click', () => {
      selectedId = null;
      syncHotspotClasses();
      renderSide();
    });
    pinPanel.querySelector('#pinRoomName')?.addEventListener('input', (e) => {
      pin.room = e.target.value;
      setDirty(true);
      const lab = pinTip && !pinTip.hidden ? pinTip.querySelector('strong') : null;
      const head = pinPanel.querySelector('h2');
      if (lab) lab.textContent = pin.room || 'Pin';
      if (head) head.textContent = pin.room || 'Room';
    });
    pinPanel.querySelector('#pinAssetQ')?.addEventListener('input', (e) => {
      renderSide({ assetQuery: e.target.value, keepAssetFocus: true });
      const inp = pinPanel.querySelector('#pinAssetQ');
      if (inp) {
        inp.focus({ preventScroll: true });
        const len = inp.value.length;
        inp.setSelectionRange(len, len);
      }
    });
    pinPanel.querySelectorAll('[data-asset]').forEach((cb) => {
      cb.addEventListener('change', () => {
        pin.asset_ids = [...pinPanel.querySelectorAll('[data-asset]:checked')].map((el) => el.dataset.asset);
        setDirty(true);
      });
    });
    pinPanel.querySelectorAll('input[name="pinHealth"]').forEach((el) => {
      el.addEventListener('change', async () => {
        pin.severity = el.value;
        pinPanel.querySelectorAll('.twin-health-opt').forEach((lab) => {
          lab.classList.toggle('is-on', lab.querySelector('input')?.value === pin.severity);
        });
        syncHotspotClasses();
        renderKpis();
        if (editMode) {
          setDirty(true);
          return;
        }
        const saved = await persistPins();
        if (!saved.ok) {
          fmNotify(saved.error || 'Could not save pin health');
          return;
        }
        selectedId = pin.id;
        renderPins();
        renderKpis();
        renderSide();
      });
    });
    pinPanel.querySelector('#removePinBtn')?.addEventListener('click', async () => {
      const btn = pinPanel.querySelector('#removePinBtn');
      if (btn) btn.disabled = true;
      pins = pins.filter((p) => String(p.id) !== String(pin.id));
      selectedId = null;
      renderPins();
      renderKpis();
      const saved = await persistPins();
      if (!saved.ok) {
        setDirty(true);
        if (btn) btn.disabled = false;
        fmNotify(saved.error || 'Could not remove pin');
        renderSide();
        return;
      }
      setEditMode(false);
      renderPins();
      renderSide();
      renderKpis();
    });
    if (opts && opts.focusName) {
      requestAnimationFrame(() => {
        pinPanel.querySelector('#pinRoomName')?.focus({ preventScroll: true });
      });
    }
  }

  function renderRecs(payload) {
    recPanel.hidden = false;
    const recs = payload.recommendations || [];
    const cards = recs.length
      ? recs.map((r) => `
          <article class="twin-rec ${esc(r.severity || 'ok')}">
            <header>
              <strong>${esc(r.room || 'Area')}</strong>
              <span class="twin-chip ${esc(r.severity || 'ok')}">${esc(r.severity || '')}</span>
            </header>
            <p>${esc(r.action || '')}</p>
            <p class="fm-muted">${esc(r.reason || '')}</p>
          </article>`).join('')
      : '<p class="fm-muted">Nothing to recommend on this floor.</p>';
    recPanel.innerHTML = `
      <h2>Recommendations</h2>
      <p class="twin-note">${esc(payload.summary || '')}</p>
      <p class="twin-method">${payload.method === 'llm_estimate' ? 'Claude' : 'From live tickets'}</p>
      ${cards}
    `;
  }

  function pinBubbleHtml(h) {
    const sev = h.severity || 'ok';
    const sevLabel = sev === 'crit' ? 'Critical' : sev === 'warn' ? 'Warning' : 'Healthy';
    const names = (h.assets || []).map((a) => a.name || a.asset_id).filter(Boolean);
    let assetLine = 'No assets linked';
    if (names.length) {
      assetLine = names.slice(0, 2).join(', ');
      if (names.length > 2) assetLine += ' +' + (names.length - 2);
    } else if ((h.asset_ids || []).length) {
      assetLine = h.asset_ids.length + ' linked asset' + (h.asset_ids.length === 1 ? '' : 's');
    }
    const wo = Number(h.open_ticket_count || (h.open_tickets || []).length || 0);
    const woLine = wo
      ? (wo + ' open work order' + (wo === 1 ? '' : 's'))
      : (h.note && h.note !== 'No assets linked' ? h.note : 'No open work orders');
    return `<strong>${esc(h.room || 'Pin')}</strong>
      <span class="twin-bubble-health ${esc(sev)}">${esc(sevLabel)}</span>
      <span class="twin-bubble-line">${esc(assetLine)}</span>
      <span class="twin-bubble-line">${esc(woLine)}</span>`;
  }

  function hidePinTip() {
    if (pinTip) pinTip.hidden = true;
  }

  function showPinTip(el, h) {
    if (!pinTip || !twinMap || drag || (pan && pan.moved)) return;
    pinTip.innerHTML = pinBubbleHtml(h);
    pinTip.hidden = false;
    const mapR = twinMap.getBoundingClientRect();
    const pinR = el.getBoundingClientRect();
    pinTip.style.left = (pinR.left + pinR.width / 2 - mapR.left) + 'px';
    pinTip.style.top = (pinR.top - mapR.top) + 'px';
  }

  function renderPins() {
    hidePinTip();
    const host = canvasEl();
    host.querySelectorAll('.twin-hotspot').forEach((el) => el.remove());
    pins.forEach((h) => {
      const el = document.createElement('button');
      el.type = 'button';
      el.className = hotspotClass(h);
      el.style.left = clampPct(h.x_pct) + '%';
      el.style.top = clampPct(h.y_pct) + '%';
      el.dataset.id = h.id;
      el.setAttribute('aria-label', (h.room || 'Room') + ' — ' + (h.severity || 'ok'));
      el.addEventListener('pointerenter', () => showPinTip(el, h));
      el.addEventListener('pointerleave', hidePinTip);
      el.addEventListener('focus', (ev) => {
        if (typeof ev.preventDefault === 'function') ev.preventDefault();
        showPinTip(el, h);
      });
      el.addEventListener('blur', hidePinTip);
      el.addEventListener('mousedown', (ev) => {
        if (ev.button === 0) ev.preventDefault();
      });
      el.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        selectedId = h.id;
        syncHotspotClasses();
        renderSide();
      });
      if (canWrite) {
        el.addEventListener('pointerdown', (ev) => {
          if (!editMode || ev.button !== 0) return;
          ev.stopPropagation();
          selectedId = h.id;
          drag = { id: h.id, x: ev.clientX, y: ev.clientY, moving: false };
          try { el.setPointerCapture(ev.pointerId); } catch (_) {}
        });
        el.addEventListener('pointermove', (ev) => {
          if (!drag || String(drag.id) !== String(h.id)) return;
          if (!drag.moving) {
            if (Math.hypot(ev.clientX - drag.x, ev.clientY - drag.y) < 8) return;
            drag.moving = true;
            ev.preventDefault();
          }
          const pct = pctFromEvent(ev);
          h.x_pct = pct.x;
          h.y_pct = pct.y;
          el.style.left = pct.x + '%';
          el.style.top = pct.y + '%';
          setDirty(true);
          hidePinTip();
        });
        el.addEventListener('pointerup', (ev) => {
          if (drag && String(drag.id) === String(h.id) && !drag.moving) {
            selectedId = h.id;
            syncHotspotClasses();
            renderSide();
          }
          drag = null;
        });
        el.addEventListener('pointercancel', () => { drag = null; });
      }
      host.appendChild(el);
    });
  }

  function showEmpty() {
    stage.innerHTML = '<p class="twin-empty">Select a floor plan to see live room status.</p>';
    stage.classList.remove('is-editing');
    if (zoomBox) zoomBox.hidden = true;
    if (legend) legend.hidden = true;
    zoom = 1;
    setEditMode(false);
    severityFilter = null;
    kpis.hidden = true;
    recBtn.disabled = true;
    if (downloadBtn) downloadBtn.disabled = true;
    if (editBtn) editBtn.disabled = true;
    if (saveBtn) { saveBtn.hidden = true; saveBtn.disabled = true; }
    if (deleteBtn) deleteBtn.disabled = true;
    if (replaceBtn) replaceBtn.disabled = true;
    pinPanel.hidden = true;
    recPanel.hidden = true;
    if (sideHint) sideHint.hidden = false;
  }

  function paintPlanImage(url) {
    const canvas = document.createElement('div');
    canvas.className = 'twin-canvas';
    const img = document.createElement('img');
    img.alt = plan.name || 'Floor plan';
    img.src = url;
    canvas.appendChild(img);
    stage.replaceChildren(canvas);
    if (zoomBox) zoomBox.hidden = false;
    if (legend) legend.hidden = false;
    applyZoom();
    renderPins();
  }

  const PIN_EXPORT_COLORS = { ok: '#16a34a', warn: '#ea580c', crit: '#dc2626' };
  const KYNVERA_WORDMARK = '/static/images/kynvera/kynvera-wordmark.png';
  const KYNVERA_MARK = '/static/images/kynvera/kynvera-mark.png';

  function loadHtmlImage(src, crossOrigin) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      if (crossOrigin) img.crossOrigin = crossOrigin;
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('Could not load image'));
      img.src = src;
    });
  }

  function releaseObjectUrl(img) {
    if (img && img._objectUrl) {
      URL.revokeObjectURL(img._objectUrl);
      img._objectUrl = '';
    }
  }

  async function fetchDrawableImage(src) {
    if (!src) throw new Error('No drawing loaded');
    if (src.startsWith('data:') || src.startsWith('blob:')) {
      return loadHtmlImage(src);
    }
    if (/^https?:\/\//i.test(src)) {
      return loadHtmlImage(src, 'anonymous');
    }
    const headers = typeof fmAuthHeaders === 'function' ? fmAuthHeaders() : {};
    const res = await fetch(src, { headers: headers, credentials: 'same-origin' });
    if (!res.ok) throw new Error('Could not load drawing');
    const blob = await res.blob();
    const obj = URL.createObjectURL(blob);
    try {
      const img = await loadHtmlImage(obj);
      img._objectUrl = obj;
      return img;
    } catch (err) {
      URL.revokeObjectURL(obj);
      throw err;
    }
  }

  function exportFilename() {
    const raw = [plan && plan.name, plan && plan.building, plan && plan.floor]
      .filter(Boolean)
      .join('-');
    const slug = String(raw || 'floor-plan')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 80);
    return (slug || 'floor-plan') + '-kynvera.png';
  }

  function canvasToBlob(canvas) {
    return new Promise((resolve, reject) => {
      try {
        canvas.toBlob((blob) => {
          if (!blob) reject(new Error('Could not export drawing'));
          else resolve(blob);
        }, 'image/png');
      } catch (err) {
        reject(err);
      }
    });
  }

  function drawExportPins(ctx, width, height) {
    const pinR = Math.max(8, Math.round(width * 0.0075));
    const fontSize = Math.max(13, Math.round(width * 0.011));
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.font = '600 ' + fontSize + 'px Inter, system-ui, sans-serif';
    pins.forEach((h) => {
      const x = (clampPct(h.x_pct) / 100) * width;
      const y = (clampPct(h.y_pct) / 100) * height;
      const color = PIN_EXPORT_COLORS[h.severity] || PIN_EXPORT_COLORS.ok;
      const label = String(h.room || 'Pin');
      const padX = Math.round(fontSize * 0.45);
      const padY = Math.round(fontSize * 0.28);
      const metrics = ctx.measureText(label);
      const boxW = metrics.width + padX * 2;
      const boxH = fontSize + padY * 2;
      const boxX = Math.min(width - boxW - 4, Math.max(4, x - boxW / 2));
      const boxY = Math.max(4, y - pinR - 8 - boxH);
      ctx.fillStyle = 'rgba(25, 27, 35, 0.88)';
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(boxX, boxY, boxW, boxH, 6);
      else ctx.rect(boxX, boxY, boxW, boxH);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.fillText(label, boxX + boxW / 2, boxY + boxH - padY);
      ctx.beginPath();
      ctx.arc(x, y, pinR, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.lineWidth = Math.max(2, pinR * 0.28);
      ctx.strokeStyle = '#fff';
      ctx.stroke();
    });
  }

  async function drawKynveraFooter(ctx, width, height, footerH) {
    ctx.fillStyle = '#191b23';
    ctx.fillRect(0, height, width, footerH);
    const pad = Math.round(footerH * 0.28);
    let logo = null;
    try { logo = await fetchDrawableImage(KYNVERA_WORDMARK); }
    catch (_) {
      try { logo = await fetchDrawableImage(KYNVERA_MARK); } catch (__) { logo = null; }
    }
    let logoW = 0;
    if (logo) {
      const maxH = footerH - pad * 2;
      const scale = maxH / (logo.naturalHeight || logo.height || 1);
      const h = maxH;
      const w = (logo.naturalWidth || logo.width) * scale;
      ctx.drawImage(logo, pad, height + (footerH - h) / 2, w, h);
      logoW = w;
      releaseObjectUrl(logo);
    } else {
      ctx.fillStyle = '#ff8e68';
      ctx.font = '700 ' + Math.round(footerH * 0.38) + 'px Inter, system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText('Kynvera', pad, height + footerH / 2);
      logoW = ctx.measureText('Kynvera').width;
    }
    const loc = [plan.building, plan.floor].filter(Boolean).join(' / ');
    const title = plan.name || 'Floor plan';
    const right = width - pad;
    const textMax = Math.max(80, right - (pad + logoW + 24));
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.font = '600 ' + Math.round(footerH * 0.28) + 'px Inter, system-ui, sans-serif';
    ctx.fillText(title, right, height + footerH * 0.4, textMax);
    ctx.fillStyle = '#9498a3';
    ctx.font = '500 ' + Math.round(footerH * 0.2) + 'px Inter, system-ui, sans-serif';
    ctx.fillText(loc || 'Kynvera Digital Twin', right, height + footerH * 0.68, textMax);
  }

  async function downloadDrawing() {
    if (!plan) return;
    const shown = stage.querySelector('.twin-canvas img');
    const src = (plan.display_url || plan.image_url || (shown && (shown.currentSrc || shown.src)) || '');
    if (downloadBtn) {
      downloadBtn.disabled = true;
      downloadBtn.textContent = 'Preparing…';
    }
    let planImg = null;
    try {
      planImg = await fetchDrawableImage(src);
      const srcW = planImg.naturalWidth || planImg.width;
      const srcH = planImg.naturalHeight || planImg.height;
      if (!srcW || !srcH) throw new Error('Drawing is still loading');
      const maxW = 3200;
      const scale = srcW > maxW ? maxW / srcW : 1;
      const w = Math.max(1, Math.round(srcW * scale));
      const h = Math.max(1, Math.round(srcH * scale));
      const footerH = Math.max(64, Math.min(120, Math.round(w * 0.07)));
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h + footerH;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(planImg, 0, 0, w, h);
      drawExportPins(ctx, w, h);
      await drawKynveraFooter(ctx, w, h, footerH);
      const blob = await canvasToBlob(canvas);
      const a = document.createElement('a');
      const url = URL.createObjectURL(blob);
      a.href = url;
      a.download = exportFilename();
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
      fmNotify('Drawing downloaded', 'info');
    } catch (err) {
      const tainted = /tainted|securityerror/i.test(String(err && err.name) + ' ' + String(err && err.message));
      fmNotify(tainted
        ? 'This drawing cannot be exported. Upload the plan file in the app and try again.'
        : ((err && err.message) || 'Could not download drawing'));
    } finally {
      releaseObjectUrl(planImg);
      if (downloadBtn) {
        downloadBtn.disabled = !plan;
        downloadBtn.textContent = 'Download drawing';
      }
    }
  }

  function twinPlanList() {
    return window.FM_TWIN_PLANS || [];
  }

  function twinCatalog() {
    return window.FM_TWIN_CATALOG || [];
  }

  function pushUniquePlace(list, name) {
    if (!name) return;
    if (list.some((n) => samePlace(n, name))) return;
    list.push(name);
  }

  function fillJumpSelect(sel, names, selected) {
    if (!sel) return;
    sel.innerHTML = '';
    names.forEach((n) => {
      const opt = document.createElement('option');
      opt.value = n;
      opt.textContent = n || 'This building';
      sel.appendChild(opt);
    });
    const hit = names.find((n) => samePlace(n, selected));
    if (hit) sel.value = hit;
    else if (names.length) sel.selectedIndex = 0;
    sel.disabled = !names.length;
  }

  function buildingNames() {
    const names = [];
    twinCatalog().forEach((b) => pushUniquePlace(names, b.name));
    twinPlanList().forEach((p) => pushUniquePlace(names, p.building));
    const draft = draftLoc || window.FM_TWIN_DRAFT;
    if (draft) pushUniquePlace(names, draft.building);
    return names;
  }

  function floorsForBuilding(building) {
    const names = [];
    const cat = twinCatalog().find((b) => samePlace(b.name, building));
    ((cat && cat.floors) || []).forEach((f) => pushUniquePlace(names, f.name || f));
    twinPlanList().forEach((p) => {
      if (!samePlace(p.building, building)) return;
      pushUniquePlace(names, p.floor || '');
    });
    const draft = draftLoc || window.FM_TWIN_DRAFT;
    if (draft && samePlace(draft.building, building)) pushUniquePlace(names, draft.floor);
    return names.filter(Boolean);
  }

  function planForJump(building, floor) {
    return twinPlanList().find((p) => (
      samePlace(p.building, building) && samePlace(p.floor || '', floor || '')
    )) || null;
  }

  function draftHref(building, floor) {
    const pid = window.FM_TWIN_PROJECT_ID;
    const params = new URLSearchParams();
    if (building) params.set('building', building);
    if (floor) params.set('floor', floor);
    const qs = params.toString();
    if (pid) return '/assets/twin/project/' + pid + '/draw' + (qs ? '?' + qs : '');
    return '/assets/twin' + (qs ? '?' + qs : '');
  }

  function applyJumpLock() {
    const buildingSel = document.getElementById('jumpBuilding');
    const floorSel = document.getElementById('jumpFloor');
    if (!buildingSel || !floorSel) return;
    fillJumpSelect(buildingSel, buildingNames(), jumpLock.building);
    fillJumpSelect(floorSel, floorsForBuilding(jumpLock.building), jumpLock.floor);
  }

  function confirmMissingDrawing(missing) {
    return new Promise((resolve) => {
      let box = document.getElementById('twinConfirm');
      if (!box) {
        box = document.createElement('div');
        box.id = 'twinConfirm';
        box.className = 'twin-confirm';
        box.innerHTML = '<div class="twin-confirm-card" role="dialog" aria-modal="true">'
          + '<h2 id="twinConfirmTitle">No drawing yet</h2>'
          + '<p id="twinConfirmBody"></p>'
          + '<div class="twin-confirm-actions">'
          + '<button type="button" class="fm-btn fm-btn-outline" id="twinConfirmNo">Cancel</button>'
          + '<button type="button" class="fm-btn fm-btn-primary" id="twinConfirmYes">Open drawing</button>'
          + '</div></div>';
        document.body.appendChild(box);
      }
      const body = document.getElementById('twinConfirmBody');
      const yes = document.getElementById('twinConfirmYes');
      const no = document.getElementById('twinConfirmNo');
      if (body) {
        body.textContent = 'There is no drawing for ' + missing + ' yet. Still want to open?';
      }
      box.hidden = false;
      function finish(ok) {
        box.hidden = true;
        yes.removeEventListener('click', onYes);
        no.removeEventListener('click', onNo);
        box.removeEventListener('click', onBox);
        document.removeEventListener('keydown', onKey);
        resolve(ok);
      }
      function onYes() { finish(true); }
      function onNo() { finish(false); }
      function onBox(ev) { if (ev.target === box) finish(false); }
      function onKey(ev) { if (ev.key === 'Escape') finish(false); }
      yes.addEventListener('click', onYes);
      no.addEventListener('click', onNo);
      box.addEventListener('click', onBox);
      document.addEventListener('keydown', onKey);
      yes.focus();
    });
  }

  function syncJumpFromPlan() {
    const buildingSel = document.getElementById('jumpBuilding');
    const floorSel = document.getElementById('jumpFloor');
    if (!buildingSel || !floorSel || !plan) return;
    jumpLock = { building: plan.building || '', floor: plan.floor || '' };
    fillJumpSelect(buildingSel, buildingNames(), jumpLock.building);
    fillJumpSelect(floorSel, floorsForBuilding(jumpLock.building), jumpLock.floor);
  }

  async function goToJumpPlan() {
    const buildingSel = document.getElementById('jumpBuilding');
    const floorSel = document.getElementById('jumpFloor');
    if (!buildingSel || !floorSel) return;
    const building = buildingSel.value;
    const floor = floorSel.value;
    if (samePlace(building, jumpLock.building) && samePlace(floor, jumpLock.floor)) return;
    const match = planForJump(building, floor);
    if (match && match.id) {
      if (plan && String(plan.id) === String(match.id)) {
        jumpLock = { building, floor };
        return;
      }
      window.location.href = '/assets/twin/plan/' + match.id;
      return;
    }
    const dest = draftHref(building, floor);
    const alreadyDraft = draftLoc
      && samePlace(draftLoc.building, building)
      && samePlace(draftLoc.floor, floor);
    if (alreadyDraft) {
      jumpLock = { building, floor };
      return;
    }
    const ok = await confirmMissingDrawing(locLabel(building, floor));
    if (!ok) {
      applyJumpLock();
      return;
    }
    window.location.href = dest;
  }

  function bindDraftForm(building, floor) {
    const form = document.getElementById('twinDraftForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const file = fd.get('image');
      if (!(file && file.size)) {
        fmNotify('Choose a drawing file first');
        return;
      }
      fd.set('name', floor || building || 'Floor plan');
      fd.set('building', building);
      if (floor) fd.set('floor', floor);
      if (window.FM_TWIN_PROJECT_ID) fd.set('project_id', String(window.FM_TWIN_PROJECT_ID));
      const btn = form.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      const res = await fetch('/assets/api/floor-plans', {
        method: 'POST',
        headers: fmAuthHeaders(),
        body: fd,
      });
      let data = {};
      try { data = await res.json(); } catch (_) {}
      if (btn) btn.disabled = false;
      if (!res.ok || !data.success) {
        fmNotify((data && data.error) || 'Could not save plan');
        return;
      }
      window.location.href = '/assets/twin/plan/' + data.plan.id;
    });
    form.querySelector('input[type="file"]')?.addEventListener('change', (e) => {
      const nameEl = document.getElementById('draftImageName');
      const file = e.target.files && e.target.files[0];
      if (nameEl) nameEl.textContent = file ? file.name : 'PNG, JPG, or SVG';
    });
  }

  function showDraft(building, floor) {
    plan = null;
    pins = [];
    selectedId = null;
    draftLoc = { building: building || '', floor: floor || '' };
    jumpLock = { building: draftLoc.building, floor: draftLoc.floor };
    showEmpty();
    const loc = locLabel(building, floor);
    const title = document.querySelector('.twin-header h1');
    const copy = document.querySelector('.twin-header p');
    if (title) title.textContent = floor || building || 'Add floor plan';
    if (copy) copy.textContent = 'Add a drawing for this floor.';
    if (canWrite) {
      stage.innerHTML = '<form class="twin-empty twin-draft" id="twinDraftForm">'
        + '<strong>No drawing yet</strong>'
        + '<p>Add a floor plan for ' + esc(loc) + '.</p>'
        + '<label class="twin-file">'
        + '<span class="twin-file-row"><span class="twin-file-btn">Choose file</span>'
        + '<span class="twin-file-name" id="draftImageName">PNG, JPG, or SVG</span></span>'
        + '<input class="twin-file-input" type="file" name="image" accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml" required>'
        + '</label>'
        + '<button class="fm-btn fm-btn-primary" type="submit">Save plan</button>'
        + '</form>';
      bindDraftForm(building, floor);
    } else {
      stage.innerHTML = '<p class="twin-empty twin-draft"><strong>No drawing yet</strong>'
        + '<span>There is no floor plan for ' + esc(loc) + '.</span></p>';
    }
  }

  function initJumpBar() {
    const buildingSel = document.getElementById('jumpBuilding');
    const floorSel = document.getElementById('jumpFloor');
    if (!buildingSel || !floorSel || !window.FM_TWIN_DRAWING) return;
    const draft = window.FM_TWIN_DRAFT || {};
    const current = twinPlanList().find((p) => select && String(p.id) === String(select.value))
      || { building: draft.building || '', floor: draft.floor || '' };
    jumpLock = { building: current.building || '', floor: current.floor || '' };
    fillJumpSelect(buildingSel, buildingNames(), jumpLock.building);
    fillJumpSelect(floorSel, floorsForBuilding(jumpLock.building), jumpLock.floor);
    buildingSel.addEventListener('change', () => {
      const floors = floorsForBuilding(buildingSel.value);
      fillJumpSelect(floorSel, floors, floors[0] || '');
      goToJumpPlan();
    });
    floorSel.addEventListener('change', goToJumpPlan);
  }

  async function fetchAssets(filters) {
    const params = new URLSearchParams();
    Object.keys(filters || {}).forEach((key) => {
      const val = filters[key];
      if (val) params.set(key, String(val));
    });
    const res = await api('/assets/api/assets?' + params.toString());
    if (res.ok && res.data.success) return res.data.assets || [];
    return [];
  }

  async function loadBuildingAssets(building, floor) {
    buildingAssets = [];
    if (!building) return;
    const projectId = window.FM_TWIN_PROJECT_ID;
    let rows = await fetchAssets({
      building: building,
      floor: floor || '',
      project_id: projectId || '',
    });
    if (!rows.length) {
      const wider = await fetchAssets({ building: building });
      rows = wider.filter((a) => {
        if (!samePlace(a.building, building)) return false;
        if (!floor) return true;
        const af = (a.floor || '').trim();
        return !af || samePlace(af, floor);
      });
      if (projectId) {
        const scoped = rows.filter((a) => String(a.project_id || '') === String(projectId));
        if (scoped.length) rows = scoped;
      }
    }
    buildingAssets = rows;
  }

  async function loadPlan(id) {
    if (!id) {
      plan = null;
      pins = [];
      selectedId = null;
      editMode = false;
      showEmpty();
      return;
    }
    const res = await api('/assets/api/floor-plans/' + id);
    if (!res.ok || !res.data.success) {
      fmNotify(res.data.error || 'Could not load floor plan');
      return;
    }
    plan = res.data.plan;
    pins = (plan.hotspots || []).map((h, i) => Object.assign({ id: h.id || ('hs-' + (i + 1)) }, h));
    selectedId = null;
    draftLoc = null;
    severityFilter = null;
    recPanel.hidden = true;
    recBtn.disabled = false;
    if (downloadBtn) downloadBtn.disabled = false;
    if (editBtn) editBtn.disabled = false;
    if (deleteBtn) deleteBtn.disabled = false;
    if (replaceBtn) replaceBtn.disabled = false;
    setEditMode(false);
    setDirty(false);
    await loadBuildingAssets(plan.building, plan.floor);
    syncJumpFromPlan();
    renderKpis();
    paintPlanImage(plan.display_url || plan.image_url);
    renderSide();
  }

  stage.addEventListener('click', (ev) => {
    if (skipPlaceClick) {
      skipPlaceClick = false;
      return;
    }
    if (!editMode || !plan || ev.target.closest('.twin-hotspot')) return;
    const pct = pctFromEvent(ev);
    const pin = {
      id: 'hs-' + Date.now(),
      room: nextPinName(),
      x_pct: pct.x,
      y_pct: pct.y,
      asset_ids: pendingAsset ? [pendingAsset] : [],
      severity: 'ok',
      note: pendingAsset ? pendingAsset : 'No assets linked',
      assets: pendingAsset
        ? buildingAssets.filter((a) => String(a.asset_id) === String(pendingAsset))
        : [],
      open_tickets: [],
    };
    if (pendingAsset) pendingAsset = null;
    pins.push(pin);
    selectedId = pin.id;
    setDirty(true);
    renderPins();
    renderSide({ focusName: true });
    renderKpis();
  });

  select?.addEventListener('change', () => {
    const id = select.value;
    if (id && window.FM_TWIN_DRAWING) {
      history.replaceState({}, '', '/assets/twin/plan/' + id + location.search);
    }
    loadPlan(id);
  });

  downloadBtn?.addEventListener('click', () => {
    downloadDrawing();
  });

  recBtn?.addEventListener('click', async () => {
    if (!plan) return;
    recBtn.disabled = true;
    recBtn.textContent = 'Working…';
    const res = await api('/assets/api/floor-plans/' + plan.id + '/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    recBtn.disabled = false;
    recBtn.textContent = 'Recommendations';
    if (!res.ok || !res.data.success) {
      fmNotify(res.data.error || 'Recommendations failed');
      return;
    }
    renderRecs(res.data);
  });

  editBtn?.addEventListener('click', () => {
    if (!plan) return;
    setEditMode(!editMode);
    renderSide();
  });

  saveBtn?.addEventListener('click', async () => {
    if (!plan) return;
    saveBtn.disabled = true;
    const saved = await persistPins();
    if (!saved.ok) {
      saveBtn.disabled = false;
      fmNotify(saved.error || 'Could not save pins');
      return;
    }
    fmNotify('Pins saved', 'info');
    renderKpis();
    renderPins();
    renderSide();
  });

  replaceBtn?.addEventListener('click', () => {
    if (!plan) return;
    replaceInput?.click();
  });

  replaceInput?.addEventListener('change', async () => {
    const file = replaceInput.files && replaceInput.files[0];
    replaceInput.value = '';
    if (!file || !plan) return;
    const fd = new FormData();
    fd.set('image', file);
    if (replaceBtn) replaceBtn.disabled = true;
    const res = await fetch('/assets/api/floor-plans/' + plan.id + '/image', {
      method: 'POST',
      headers: fmAuthHeaders(),
      body: fd,
    });
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (replaceBtn) replaceBtn.disabled = false;
    if (!res.ok || !data.success) {
      fmNotify((data && data.error) || 'Could not replace drawing');
      return;
    }
    fmNotify('Drawing updated', 'info');
    await loadPlan(plan.id);
  });

  deleteBtn?.addEventListener('click', async () => {
    if (!plan) return;
    if (deleteBtn.dataset.confirm !== '1') {
      deleteBtn.dataset.confirm = '1';
      deleteBtn.textContent = 'Confirm delete';
      setTimeout(() => {
        deleteBtn.dataset.confirm = '';
        deleteBtn.textContent = 'Delete plan';
      }, 4000);
      return;
    }
    const res = await api('/assets/api/floor-plans/' + plan.id, { method: 'DELETE' });
    if (!res.ok || !res.data.success) {
      fmNotify(res.data.error || 'Could not delete plan');
      return;
    }
    fmNotify('Plan deleted', 'info');
    const projectId = window.FM_TWIN_PROJECT_ID;
    window.location.href = projectId
      ? '/assets/twin/project/' + projectId
      : '/assets/twin';
  });

  document.getElementById('planForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const fd = new FormData(form);
    const file = fd.get('image');
    const hasFile = file && file.size;
    if (!hasFile) fd.delete('image');
    const res = await fetch('/assets/api/floor-plans', {
      method: 'POST',
      headers: fmAuthHeaders(),
      body: fd,
    });
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (!res.ok || !data.success) {
      fmNotify(data.error || 'Could not save plan');
      return;
    }
    const p = data.plan;
    form.reset();
    fmNotify('Floor plan saved', 'info');
    window.location.href = '/assets/twin/plan/' + p.id;
  });

  document.getElementById('planImage')?.addEventListener('change', (e) => {
    const nameEl = document.getElementById('planImageName');
    const file = e.target.files && e.target.files[0];
    if (nameEl) nameEl.textContent = file ? file.name : 'PNG, JPG, or SVG';
  });

  kpis?.addEventListener('click', (e) => {
    const btn = e.target.closest('.twin-filter');
    if (!btn || !plan) return;
    const sev = btn.dataset.sev;
    severityFilter = severityFilter === sev ? null : sev;
    renderKpis();
    renderPins();
  });

  document.getElementById('zoomInBtn')?.addEventListener('click', () => setZoom(zoom + 0.25));
  document.getElementById('zoomOutBtn')?.addEventListener('click', () => setZoom(zoom - 0.25));
  document.getElementById('zoomFitBtn')?.addEventListener('click', () => setZoom(1));

  stage.addEventListener('wheel', (e) => {
    if (!plan || !stage.querySelector('.twin-canvas')) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const step = e.deltaMode === 1 ? 0.15 : Math.max(0.05, Math.min(0.35, Math.abs(e.deltaY) / 500));
    setZoom(zoom + (e.deltaY > 0 ? -step : step), { x: e.clientX, y: e.clientY });
  }, { passive: false });

  function endPan() {
    if (pan && pan.moved) skipPlaceClick = true;
    pan = null;
    stage.classList.remove('is-panning');
  }
  stage.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || pinch) return;
    if (!stage.querySelector('.twin-canvas')) return;
    if (e.target.closest('.twin-hotspot')) return;
    pan = { x: e.clientX, y: e.clientY, sl: stage.scrollLeft, st: stage.scrollTop, moved: false, id: e.pointerId };
  });
  stage.addEventListener('pointermove', (e) => {
    if (!pan || pan.id !== e.pointerId || drag) return;
    const dx = e.clientX - pan.x;
    const dy = e.clientY - pan.y;
    if (!pan.moved) {
      if (Math.hypot(dx, dy) < 8) return;
      pan.moved = true;
      hidePinTip();
      try { stage.setPointerCapture(e.pointerId); } catch (_) {}
      stage.classList.add('is-panning');
    }
    e.preventDefault();
    stage.scrollLeft = pan.sl - dx;
    stage.scrollTop = pan.st - dy;
  }, { passive: false });
  stage.addEventListener('pointerup', endPan);
  stage.addEventListener('pointercancel', endPan);
  stage.addEventListener('scroll', hidePinTip, { passive: true });
  stage.addEventListener('pointermove', movePlaceCursor);
  stage.addEventListener('pointerleave', hidePlaceCursor);

  function touchDist(a, b) {
    const dx = a.clientX - b.clientX;
    const dy = a.clientY - b.clientY;
    return Math.hypot(dx, dy);
  }
  stage.addEventListener('touchstart', (e) => {
    if (e.touches.length === 2 && stage.querySelector('.twin-canvas')) {
      pinch = { dist: touchDist(e.touches[0], e.touches[1]), zoom: zoom };
      drag = null;
    }
  }, { passive: true });
  stage.addEventListener('touchmove', (e) => {
    if (!pinch || e.touches.length !== 2) return;
    e.preventDefault();
    const d = touchDist(e.touches[0], e.touches[1]);
    if (!pinch.dist) return;
    const cx = (e.touches[0].clientX + e.touches[1].clientX) / 2;
    const cy = (e.touches[0].clientY + e.touches[1].clientY) / 2;
    setZoom(pinch.zoom * (d / pinch.dist), { x: cx, y: cy });
  }, { passive: false });
  stage.addEventListener('touchend', () => {
    if (!pinch) return;
    pinch = null;
  });
  stage.addEventListener('touchcancel', () => { pinch = null; });

  initJumpBar();

  const bootParams = new URLSearchParams(location.search);
  const planFromUrl = bootParams.get('plan');
  const pinFromUrl = bootParams.get('pin');
  const assetFromUrl = bootParams.get('asset');
  const placeFromUrl = bootParams.get('place') === '1';
  pendingAsset = assetFromUrl || null;
  if (select && planFromUrl && [...select.options].some((o) => o.value === String(planFromUrl))) {
    select.value = String(planFromUrl);
  } else if (select && !select.value && select.options.length > 1 && !window.FM_TWIN_DRAWING) {
    select.selectedIndex = 1;
  }
  if (select && select.value) {
    Promise.resolve(loadPlan(select.value)).then(() => {
      if (pinFromUrl && pinById(pinFromUrl)) selectedId = pinFromUrl;
      else if (assetFromUrl) {
        const hit = pins.find((p) => (p.asset_ids || []).some((id) => String(id) === String(assetFromUrl)));
        if (hit) {
          selectedId = hit.id;
          pendingAsset = null;
        }
      }
      if (selectedId) {
        renderPins();
        renderSide();
      } else if (canWrite && (placeFromUrl || pendingAsset)) {
        setEditMode(true);
        renderSide();
      }
    });
  } else if (window.FM_TWIN_DRAFT) {
    const draft = window.FM_TWIN_DRAFT;
    showDraft(draft.building || '', draft.floor || '');
    Promise.resolve(loadBuildingAssets(draft.building, draft.floor)).then(() => renderSide());
  }
})();
