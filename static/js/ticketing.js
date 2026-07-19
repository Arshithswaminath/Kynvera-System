/* =========================================================
   Ticketing / Work Order — Shared JS
   ========================================================= */

// ── Toast ────────────────────────────────────────────────
let _toastEl = null;
function tktToast(msg, type = 'info', ms = 3200) {
  if (!_toastEl) {
    _toastEl = document.createElement('div');
    _toastEl.className = 'tkt-toast';
    document.body.appendChild(_toastEl);
  }
  _toastEl.textContent = msg;
  _toastEl.className = `tkt-toast show ${type}`;
  clearTimeout(_toastEl._t);
  _toastEl._t = setTimeout(() => {
    _toastEl.classList.remove('show');
  }, ms);
}

// ── Fetch helper ─────────────────────────────────────────
async function tktFetch(url, opts = {}) {
  try {
    const isFormData = opts.body instanceof FormData;
    const headers = { ...(opts.headers || {}) };
    if (!isFormData && !Object.prototype.hasOwnProperty.call(headers, 'Content-Type')) {
      headers['Content-Type'] = 'application/json';
    }
    const token = typeof localStorage !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (token && !headers['Authorization']) {
      headers['Authorization'] = 'Bearer ' + token;
    }
    const res = await fetch(url, {
      credentials: 'include',
      ...opts,
      headers,
    });
    const json = await res.json();
    return { ok: res.ok, status: res.status, data: json };
  } catch (err) {
    return { ok: false, status: 0, data: { error: err.message } };
  }
}

// ── Badge helpers ─────────────────────────────────────────
function tktPriorityBadge(p) {
  const labels = { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' };
  return `<span class="tkt-badge badge-priority-${p}">${labels[p] || p}</span>`;
}
function tktStatusBadge(s) {
  const labels = {
    open: 'Open', in_progress: 'In Progress',
    pending_parts: 'Pending Parts', resolved: 'Resolved', closed: 'Closed',
  };
  return `<span class="tkt-badge badge-status-${s}">${labels[s] || s}</span>`;
}

// ── Category autocomplete (service_group → category) ─────
function tktSetupCategoryChain(sgEl, catEl, options) {
  if (!sgEl || !catEl || !options) return;
  function updateCats() {
    const sg = sgEl.value;
    const cats = (options.categories && options.categories[sg]) || [];
    const current = catEl.value;
    catEl.innerHTML = '<option value="">Select category…</option>';
    cats.forEach(c => {
      const o = document.createElement('option');
      o.value = c; o.textContent = c;
      if (c === current) o.selected = true;
      catEl.appendChild(o);
    });
  }
  sgEl.addEventListener('change', updateCats);
  updateCats();
}

// ── Procurement material autocomplete ─────────────────────
function tktSetupMaterialAutocomplete(inputEl, procMaterials, onSelect) {
  if (!inputEl) return;
  let listEl = document.getElementById('tkt-mat-ac-list');
  if (!listEl) {
    listEl = document.createElement('ul');
    listEl.id = 'tkt-mat-ac-list';
    listEl.style.cssText =
      'position:absolute;background:#fff;border:1px solid #cbd5e1;border-radius:8px;'
      + 'max-height:200px;overflow-y:auto;z-index:500;list-style:none;margin:0;padding:4px 0;'
      + 'min-width:280px;box-shadow:0 4px 16px rgba(0,0,0,.12);display:none;font-size:.875rem;';
    document.body.appendChild(listEl);
  }

  function showList(items) {
    listEl.innerHTML = '';
    if (!items.length) { listEl.style.display = 'none'; return; }
    items.forEach(m => {
      const li = document.createElement('li');
      li.style.cssText = 'padding:8px 14px;cursor:pointer;';
      li.textContent = m.name + (m.unit ? ` (${m.unit})` : '');
      li.addEventListener('mousedown', (e) => {
        e.preventDefault();
        if (onSelect) onSelect(m);
        listEl.style.display = 'none';
        inputEl.value = m.name;
      });
      li.addEventListener('mouseover', () => li.style.background = '#eff6ff');
      li.addEventListener('mouseout', () => li.style.background = '');
      listEl.appendChild(li);
    });
    const r = inputEl.getBoundingClientRect();
    listEl.style.left = (r.left + window.scrollX) + 'px';
    listEl.style.top  = (r.bottom + window.scrollY + 4) + 'px';
    listEl.style.display = 'block';
  }

  inputEl.addEventListener('input', () => {
    const q = inputEl.value.toLowerCase().trim();
    if (!q) { listEl.style.display = 'none'; return; }
    const filtered = procMaterials.filter(m => m.name.toLowerCase().includes(q)).slice(0, 12);
    showList(filtered);
  });
  inputEl.addEventListener('blur', () => {
    setTimeout(() => { listEl.style.display = 'none'; }, 150);
  });
}

// ── Signature Pad ─────────────────────────────────────────
class TktSignaturePad {
  constructor(canvas, onDrawn) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.drawing = false;
    this.isEmpty = true;
    this.onDrawn = onDrawn || (() => {});
    this._scale();
    this._bind();
  }

  _scale() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width  = rect.width  * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.scale(dpr, dpr);
    this.ctx.strokeStyle = '#1e293b';
    this.ctx.lineWidth = 2.2;
    this.ctx.lineCap = 'round';
    this.ctx.lineJoin = 'round';
  }

  _pt(e) {
    const r = this.canvas.getBoundingClientRect();
    if (e.touches) {
      return { x: e.touches[0].clientX - r.left, y: e.touches[0].clientY - r.top };
    }
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  _bind() {
    const start = (e) => { e.preventDefault(); this.drawing = true; const p = this._pt(e); this.ctx.beginPath(); this.ctx.moveTo(p.x, p.y); };
    const move  = (e) => { if (!this.drawing) return; e.preventDefault(); const p = this._pt(e); this.ctx.lineTo(p.x, p.y); this.ctx.stroke(); this.isEmpty = false; if (this.canvas.parentElement) this.canvas.parentElement.classList.add('has-sig'); this.onDrawn(); };
    const stop  = () => { this.drawing = false; };

    this.canvas.addEventListener('mousedown', start);
    this.canvas.addEventListener('mousemove', move);
    this.canvas.addEventListener('mouseup', stop);
    this.canvas.addEventListener('touchstart', start, { passive: false });
    this.canvas.addEventListener('touchmove', move, { passive: false });
    this.canvas.addEventListener('touchend', stop);
  }

  clear() {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    this.isEmpty = true;
    if (this.canvas.parentElement) this.canvas.parentElement.classList.remove('has-sig');
  }

  toDataURL() {
    return this.canvas.toDataURL('image/png');
  }
}

// ── Image upload handler ──────────────────────────────────
function tktSetupImageUpload(dropZoneEl, fileInputEl, ticketId, gallery) {
  if (!dropZoneEl || !fileInputEl) return;

  dropZoneEl.addEventListener('click', () => fileInputEl.click());

  dropZoneEl.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZoneEl.classList.add('drag-over');
  });
  dropZoneEl.addEventListener('dragleave', () => dropZoneEl.classList.remove('drag-over'));
  dropZoneEl.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZoneEl.classList.remove('drag-over');
    [...e.dataTransfer.files].forEach(f => _uploadFile(f));
  });
  fileInputEl.addEventListener('change', () => {
    [...fileInputEl.files].forEach(f => _uploadFile(f));
    fileInputEl.value = '';
  });

  async function _uploadFile(file) {
    const allowed = ['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/heic'];
    if (!allowed.includes(file.type) && !file.name.match(/\.(heic|heif)$/i)) {
      tktToast('Only image files are allowed.', 'error'); return;
    }
    const fd = new FormData();
    fd.append('image', file);
    try {
      const res = await fetch(`/tickets/api/tickets/${ticketId}/images`, { method: 'POST', body: fd });
      const json = await res.json();
      if (json.success) {
        tktToast('Image uploaded.', 'success');
        if (gallery) _appendImageThumb(json.image, gallery);
      } else {
        tktToast('Upload failed: ' + (json.error || 'Unknown error'), 'error');
      }
    } catch (e) {
      tktToast('Upload error.', 'error');
    }
  }

  function _appendImageThumb(imgData, gallery) {
    const div = document.createElement('div');
    div.className = 'tkt-image-thumb';
    div.innerHTML = `<img src="/tickets/images/${imgData.id}" alt="${imgData.filename}" loading="lazy">
      <span class="tkt-img-cap">${imgData.caption || imgData.filename}</span>`;
    div.addEventListener('click', () => tktOpenLightbox(`/tickets/images/${imgData.id}`));
    gallery.appendChild(div);
  }
}

// ── Lightbox ──────────────────────────────────────────────
function tktOpenLightbox(src) {
  let lb = document.getElementById('tkt-lightbox');
  if (!lb) {
    lb = document.createElement('div');
    lb.id = 'tkt-lightbox';
    lb.className = 'tkt-lightbox';
    lb.innerHTML = '<img id="tkt-lb-img" src="" alt=""><button class="tkt-lightbox-close" id="tkt-lb-close">✕</button>';
    lb.addEventListener('click', (e) => { if (e.target === lb) lb.classList.remove('open'); });
    document.getElementById('tkt-lb-close')?.addEventListener('click', () => lb.classList.remove('open'));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') lb.classList.remove('open'); });
    document.body.appendChild(lb);
  }
  lb.querySelector('#tkt-lb-img').src = src;
  lb.classList.add('open');
}

// ── Format hours label ────────────────────────────────────
function tktFmtHours(h) {
  const n = parseFloat(h);
  if (n === 0.25) return '15 min';
  if (n === 0.5)  return '30 min';
  if (n === 0.75) return '45 min';
  if (n === Math.floor(n)) return `${n}h`;
  return `${n}h`;
}

// ── Excel-style table column filters ──────────────────────
function tktInitExcelFilters(tableId, opts = {}) {
  const table = document.getElementById(tableId);
  if (!table) return;

  const tbody = table.tBodies[0];
  if (!tbody) return;

  const state = {
    filters: {},   // colKey -> Set of allowed values (null/absent = all)
    sortKey: null,
    sortDir: null, // 'asc' | 'desc'
    openKey: null,
  };

  const countEl = opts.countEl ? document.querySelector(opts.countEl) : null;
  const clearAllBtn = opts.clearAllBtn ? document.querySelector(opts.clearAllBtn) : null;

  let panel = document.getElementById('tkt-excel-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'tkt-excel-panel';
    panel.className = 'tkt-excel-panel';
    panel.hidden = true;
    panel.innerHTML = `
      <div class="tkt-excel-sort">
        <button type="button" data-sort="asc">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M3 4h13M3 8h9m-9 4h6m4 0 3-3m0 0 3 3m-3-3v12"/></svg>
          Sort A → Z
        </button>
        <button type="button" data-sort="desc">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M3 4h13M3 8h9m-9 4h9m5-4v12m0 0 3-3m-3 3-3-3"/></svg>
          Sort Z → A
        </button>
      </div>
      <div class="tkt-excel-search">
        <input type="search" placeholder="Search values…" autocomplete="off">
      </div>
      <div class="tkt-excel-actions">
        <button type="button" data-act="select-all">Select all</button>
        <button type="button" data-act="clear">Clear</button>
      </div>
      <div class="tkt-excel-list" role="listbox" aria-multiselectable="true"></div>
      <div class="tkt-excel-footer">
        <button type="button" class="tkt-excel-btn-cancel" data-act="cancel">Cancel</button>
        <button type="button" class="tkt-excel-btn-ok" data-act="ok">OK</button>
      </div>
    `;
    document.body.appendChild(panel);
  }

  const searchInput = panel.querySelector('.tkt-excel-search input');
  const listEl = panel.querySelector('.tkt-excel-list');
  let draftSelected = new Set();
  let draftValues = [];
  let allUniqueForCol = [];

  function rowVal(row, key) {
    return (row.dataset[key] || '').trim();
  }

  function getVisibleRows(ignoreKey) {
    return Array.from(tbody.rows).filter((row) => {
      for (const [k, set] of Object.entries(state.filters)) {
        if (ignoreKey && k === ignoreKey) continue;
        if (!set) continue;
        if (!set.has(rowVal(row, k))) return false;
      }
      return true;
    });
  }

  function uniqueValues(key) {
    const rows = getVisibleRows(key);
    const map = new Map();
    rows.forEach((row) => {
      const v = rowVal(row, key);
      const label = v || '(Blank)';
      if (!map.has(v)) map.set(v, label);
    });
    return Array.from(map.entries())
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base', numeric: true }));
  }

  function applyFiltersAndSort() {
    const rows = Array.from(tbody.rows);
    rows.forEach((row) => {
      let show = true;
      for (const [k, set] of Object.entries(state.filters)) {
        if (!set) continue;
        if (!set.has(rowVal(row, k))) { show = false; break; }
      }
      row.classList.toggle('tkt-row-hidden', !show);
    });

    if (state.sortKey && state.sortDir) {
      const visible = rows.filter((r) => !r.classList.contains('tkt-row-hidden'));
      const hidden = rows.filter((r) => r.classList.contains('tkt-row-hidden'));
      const key = state.sortKey;
      const dir = state.sortDir === 'asc' ? 1 : -1;
      visible.sort((a, b) => {
        const av = rowVal(a, key);
        const bv = rowVal(b, key);
        if (key === 'created') {
          const ad = a.dataset.createdSort || av;
          const bd = b.dataset.createdSort || bv;
          return ad.localeCompare(bd, undefined, { numeric: true }) * dir;
        }
        return av.localeCompare(bv, undefined, { sensitivity: 'base', numeric: true }) * dir;
      });
      [...visible, ...hidden].forEach((r) => tbody.appendChild(r));
    }

    updateHeaderMarks();
    updateMeta();
  }

  function activeFilterCount() {
    return Object.values(state.filters).filter(Boolean).length;
  }

  function updateMeta() {
    const total = tbody.rows.length;
    const shown = Array.from(tbody.rows).filter((r) => !r.classList.contains('tkt-row-hidden')).length;
    if (countEl) {
      const n = activeFilterCount();
      countEl.textContent = n
        ? `Showing ${shown} of ${total} ticket${total === 1 ? '' : 's'} (${n} column filter${n === 1 ? '' : 's'})`
        : `${total} ticket${total === 1 ? '' : 's'}`;
    }
    if (clearAllBtn) {
      clearAllBtn.hidden = !(activeFilterCount() || state.sortKey);
    }
  }

  function updateHeaderMarks() {
    table.querySelectorAll('.tkt-col-filter-btn').forEach((btn) => {
      const key = btn.dataset.col;
      btn.classList.toggle('active', !!state.filters[key]);
      btn.classList.toggle('open', state.openKey === key);
      const mark = btn.parentElement?.querySelector('.tkt-col-sort-mark');
      if (mark) {
        if (state.sortKey === key) {
          mark.textContent = state.sortDir === 'asc' ? '▲' : '▼';
          mark.hidden = false;
        } else {
          mark.textContent = '';
          mark.hidden = true;
        }
      }
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderList(filterText) {
    const q = (filterText || '').trim().toLowerCase();
    const items = q
      ? allUniqueForCol.filter((x) => x.label.toLowerCase().includes(q))
      : allUniqueForCol;
    draftValues = items;
    if (!items.length) {
      listEl.innerHTML = '<div class="tkt-excel-empty">No matching values</div>';
      return;
    }
    listEl.innerHTML = items.map((item, i) => {
      const checked = draftSelected.has(item.value) ? 'checked' : '';
      const safeLabel = escapeHtml(item.label);
      return `<label class="tkt-excel-item"><input type="checkbox" data-idx="${i}" ${checked}><span title="${safeLabel}">${safeLabel}</span></label>`;
    }).join('');
  }

  function positionPanel(anchor) {
    panel.hidden = false;
    const rect = anchor.getBoundingClientRect();
    const pw = panel.offsetWidth;
    const ph = panel.offsetHeight;
    let left = rect.left;
    let top = rect.bottom + 4;
    if (left + pw > window.innerWidth - 8) left = Math.max(8, window.innerWidth - pw - 8);
    if (top + ph > window.innerHeight - 8) top = Math.max(8, rect.top - ph - 4);
    panel.style.left = `${Math.max(8, left)}px`;
    panel.style.top = `${top}px`;
  }

  function closePanel() {
    panel.hidden = true;
    state.openKey = null;
    updateHeaderMarks();
  }

  function openPanel(key, btn) {
    state.openKey = key;
    allUniqueForCol = uniqueValues(key);
    const current = state.filters[key];
    draftSelected = current
      ? new Set(current)
      : new Set(allUniqueForCol.map((x) => x.value));

    panel.querySelectorAll('[data-sort]').forEach((b) => {
      b.classList.toggle('active', state.sortKey === key && state.sortDir === b.dataset.sort);
    });
    searchInput.value = '';
    renderList('');
    positionPanel(btn);
    updateHeaderMarks();
    searchInput.focus();
  }

  function commitDraft() {
    const key = state.openKey;
    if (!key) return;
    const allVals = new Set(allUniqueForCol.map((x) => x.value));
    if (draftSelected.size === 0) {
      state.filters[key] = new Set();
    } else if (draftSelected.size >= allVals.size && [...allVals].every((v) => draftSelected.has(v))) {
      delete state.filters[key];
    } else {
      state.filters[key] = new Set(draftSelected);
    }
    closePanel();
    applyFiltersAndSort();
  }

  table.querySelectorAll('.tkt-col-filter-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const key = btn.dataset.col;
      if (state.openKey === key && !panel.hidden) closePanel();
      else openPanel(key, btn);
    });
  });

  panel.addEventListener('click', (e) => e.stopPropagation());

  panel.querySelectorAll('[data-sort]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = state.openKey;
      if (!key) return;
      const dir = btn.dataset.sort;
      if (state.sortKey === key && state.sortDir === dir) {
        state.sortKey = null;
        state.sortDir = null;
      } else {
        state.sortKey = key;
        state.sortDir = dir;
      }
      panel.querySelectorAll('[data-sort]').forEach((b) => {
        b.classList.toggle('active', state.sortKey === key && state.sortDir === b.dataset.sort);
      });
      applyFiltersAndSort();
    });
  });

  searchInput.addEventListener('input', () => renderList(searchInput.value));

  panel.querySelector('[data-act="select-all"]').addEventListener('click', () => {
    draftValues.forEach((x) => draftSelected.add(x.value));
    renderList(searchInput.value);
  });

  panel.querySelector('[data-act="clear"]').addEventListener('click', () => {
    draftValues.forEach((x) => draftSelected.delete(x.value));
    renderList(searchInput.value);
  });

  listEl.addEventListener('change', (e) => {
    const cb = e.target.closest('input[type="checkbox"]');
    if (!cb) return;
    const idx = Number(cb.dataset.idx);
    const item = draftValues[idx];
    if (!item) return;
    if (cb.checked) draftSelected.add(item.value);
    else draftSelected.delete(item.value);
  });

  panel.querySelector('[data-act="ok"]').addEventListener('click', commitDraft);
  panel.querySelector('[data-act="cancel"]').addEventListener('click', closePanel);

  document.addEventListener('click', (e) => {
    if (panel.hidden) return;
    if (panel.contains(e.target)) return;
    if (e.target.closest('.tkt-col-filter-btn')) return;
    closePanel();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !panel.hidden) closePanel();
  });

  window.addEventListener('resize', () => { if (!panel.hidden) closePanel(); });
  // Close when the page/table scrolls, but not when scrolling inside the filter panel list
  window.addEventListener('scroll', (e) => {
    if (panel.hidden) return;
    const t = e.target;
    if (t && (t === panel || (t.nodeType === 1 && panel.contains(t)))) return;
    closePanel();
  }, true);

  if (clearAllBtn) {
    clearAllBtn.addEventListener('click', () => {
      state.filters = {};
      state.sortKey = null;
      state.sortDir = null;
      closePanel();
      applyFiltersAndSort();
    });
  }

  applyFiltersAndSort();
}
