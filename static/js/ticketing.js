/* =========================================================
   Ticketing / Work Order — Shared JS
   ========================================================= */

// ── Confirm + Toast ──────────────────────────────────────
let _toastEl = null;
function tktConfirm(opts) {
  const options = opts || {};
  const title = options.title || 'Are you sure?';
  const message = options.message || '';
  const okText = options.okText || 'OK';
  const cancelText = options.cancelText || 'Cancel';
  const danger = options.danger !== false;

  return new Promise((resolve) => {
    let backdrop = document.getElementById('tktConfirmModal');
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.id = 'tktConfirmModal';
      backdrop.className = 'tkt-modal-backdrop tkt-confirm-backdrop';
      backdrop.setAttribute('role', 'dialog');
      backdrop.setAttribute('aria-modal', 'true');
      backdrop.innerHTML =
        '<div class="tkt-modal tkt-confirm-modal">' +
        '<div class="tkt-modal-header">' +
        '<h3 id="tktConfirmTitle"></h3>' +
        '</div>' +
        '<div class="tkt-modal-body"><p id="tktConfirmMsg"></p></div>' +
        '<div class="tkt-modal-footer">' +
        '<button type="button" class="tkt-btn tkt-btn-outline" data-tkt-confirm-cancel></button>' +
        '<button type="button" class="tkt-btn" data-tkt-confirm-ok></button>' +
        '</div></div>';
      document.body.appendChild(backdrop);
    }

    const titleEl = backdrop.querySelector('#tktConfirmTitle');
    const msgEl = backdrop.querySelector('#tktConfirmMsg');
    const cancelBtn = backdrop.querySelector('[data-tkt-confirm-cancel]');
    const okBtn = backdrop.querySelector('[data-tkt-confirm-ok]');
    titleEl.textContent = title;
    msgEl.textContent = message;
    cancelBtn.textContent = cancelText;
    okBtn.textContent = okText;
    okBtn.style.background = danger ? '#dc2626' : '';
    okBtn.style.color = danger ? '#fff' : '';
    okBtn.style.border = danger ? 'none' : '';
    okBtn.style.fontWeight = '600';
    if (!danger) okBtn.className = 'tkt-btn tkt-btn-primary';
    else okBtn.className = 'tkt-btn';

    function cleanup(result) {
      backdrop.classList.remove('open');
      backdrop.setAttribute('aria-hidden', 'true');
      backdrop.removeEventListener('click', onBackdrop);
      cancelBtn.removeEventListener('click', onCancel);
      okBtn.removeEventListener('click', onOk);
      document.removeEventListener('keydown', onKey);
      resolve(result);
    }
    function onCancel() { cleanup(false); }
    function onOk() { cleanup(true); }
    function onBackdrop(e) { if (e.target === backdrop) cleanup(false); }
    function onKey(e) { if (e.key === 'Escape') cleanup(false); }

    cancelBtn.addEventListener('click', onCancel);
    okBtn.addEventListener('click', onOk);
    backdrop.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKey);
    backdrop.classList.add('open');
    backdrop.setAttribute('aria-hidden', 'false');
    okBtn.focus();
  });
}

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
    div.dataset.imageId = imgData.id;
    const cap = imgData.caption || imgData.filename || '';
    div.innerHTML = `<img src="/tickets/images/${imgData.id}" alt="${cap}" loading="lazy">
      <span class="tkt-img-cap">${cap}</span>
      <button type="button" class="tkt-img-remove" data-image-id="${imgData.id}" aria-label="Remove photo">Remove</button>`;
    div.addEventListener('click', (e) => {
      if (e.target.closest('.tkt-img-remove')) return;
      tktOpenLightbox(`/tickets/images/${imgData.id}`);
    });
    gallery.appendChild(div);
  }
}

async function tktDeleteTicketImage(ticketId, imageId, thumbEl) {
  if (!ticketId || !imageId) return;
  const res = await tktFetch(`/tickets/api/tickets/${ticketId}/images/${imageId}`, { method: 'DELETE' });
  if (res.ok && res.data && res.data.success) {
    tktToast('Image removed.', 'success');
    thumbEl?.remove();
  } else {
    tktToast((res.data && res.data.error) || 'Could not remove image.', 'error');
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
