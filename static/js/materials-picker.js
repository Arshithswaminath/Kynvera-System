/**
 * Materials Picker — Inspection Forms Component
 * Reusable across HVAC, Civil, and Cleaning inspection forms.
 *
 * Usage:
 *   const picker = new MaterialsPicker({
 *     containerId : 'mp-root',          // id of the wrapper div
 *     departments : ['HVAC'],           // departments to filter to (empty = all)
 *     fieldName   : 'materials_required', // hidden field name in form
 *     jwt         : getToken(),          // optional – reads from localStorage if omitted
 *   });
 *   picker.init();
 *   picker.getSelected(); // → [{id, name, brand, uom, unit_price, quantity}, ...]
 */
class MaterialsPicker {
  constructor(opts = {}) {
    this.containerId  = opts.containerId  || 'mp-root';
    this.departments  = opts.departments  || [];  // [] = show all departments
    this.fieldName    = opts.fieldName    || 'materials_required';
    this.jwt          = opts.jwt          || null;
    this._catalog     = {};   // { dept: [items] }
    this._selected    = {};   // { itemId: {item, quantity} }
    this._activeDept  = 'All';
    this._search      = '';
    this._initialised = false;
  }

  // ── Public API ────────────────────────────────────────────

  /** Bootstrap the component (fetches catalog, renders HTML). */
  async init() {
    if (this._initialised) return;
    this._initialised = true;
    this._render();
    await this._fetchCatalog();
    this._renderItems();
    this._syncHiddenField();
  }

  /** Pre-fill with previously saved selection [{id,name,brand,uom,unit_price,quantity},...]. */
  setSelected(items = []) {
    this._selected = {};
    items.forEach(it => {
      if (it.id) this._selected[it.id] = { item: it, quantity: it.quantity || 1 };
    });
    this._renderItems();
    this._renderSummary();
    this._syncHiddenField();
  }

  /** Returns the current selection as an array. */
  getSelected() {
    return Object.values(this._selected).map(({ item, quantity }) => ({
      id        : item.id,
      name      : item.name,
      brand     : item.brand,
      uom       : item.uom,
      unit_price: item.unit_price,
      quantity  : quantity,
      department: item.department,
    }));
  }

  // ── Internal helpers ──────────────────────────────────────

  _getJwt() {
    if (this.jwt) return this.jwt;
    // Try common storage keys used in this app
    return localStorage.getItem('access_token') ||
           localStorage.getItem('jwt_token') ||
           localStorage.getItem('token') || '';
  }

  async _fetchCatalog() {
    const list = this._el('-list');
    list.innerHTML = this._skeletonHTML();
    try {
      const params = new URLSearchParams();
      if (this.departments.length === 1) params.set('department', this.departments[0]);
      const res = await fetch(`/procurement/api/catalog/materials?${params}`, {
        headers: { 'Authorization': `Bearer ${this._getJwt()}` }
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this._catalog = data.materials || {};
      // Restrict to allowed departments if needed
      if (this.departments.length > 0) {
        Object.keys(this._catalog).forEach(d => {
          if (!this.departments.includes(d)) delete this._catalog[d];
        });
      }
      this._renderDeptTabs();
    } catch (e) {
      list.innerHTML = `
        <div class="mp-empty">
          <svg viewBox="0 0 24 24"><path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>
          <div class="mp-empty-title">Could not load materials catalog</div>
          <div class="mp-empty-sub">${e.message}</div>
        </div>`;
    }
  }

  _render() {
    const root = document.getElementById(this.containerId);
    if (!root) return;

    const section = root.closest('.mp-section') || root.parentElement;
    if (section) section.classList.add('mp-section');

    root.innerHTML = `
      <div class="mp-section-header" id="${this.containerId}-toggle">
        <span class="mp-section-icon">
          <svg viewBox="0 0 24 24"><path d="M20 7H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
        </span>
        <span class="mp-section-title">Materials Required</span>
        <span class="mp-section-badge" id="${this.containerId}-badge">0</span>
        <svg class="mp-chevron" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="mp-body">
        <div class="mp-toolbar">
          <div class="mp-dept-tabs" id="${this.containerId}-tabs">
            <button class="mp-dept-tab active" data-dept="All">All</button>
          </div>
          <div class="mp-search-wrap">
            <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input class="mp-search" id="${this.containerId}-search" type="text" placeholder="Search materials…" autocomplete="off">
          </div>
        </div>
        <div class="mp-list" id="${this.containerId}-list">
          ${this._skeletonHTML()}
        </div>
        <div class="mp-summary" id="${this.containerId}-summary">
          <div class="mp-summary-title">Selected Materials</div>
          <div class="mp-summary-list" id="${this.containerId}-chips"></div>
        </div>
        <input type="hidden" name="${this.fieldName}" id="${this.containerId}-field" value="[]">
      </div>`;

    // Toggle open/close
    this._el('-toggle').addEventListener('click', () => {
      const section = root.closest('.mp-section') || root.parentElement.parentElement;
      section.classList.toggle('is-open');
    });

    // Search
    this._el('-search').addEventListener('input', e => {
      this._search = e.target.value.trim().toLowerCase();
      this._renderItems();
    });
  }

  _renderDeptTabs() {
    const tabsEl = this._el('-tabs');
    const depts = Object.keys(this._catalog).sort();
    tabsEl.innerHTML = `<button class="mp-dept-tab${this._activeDept === 'All' ? ' active' : ''}" data-dept="All">All</button>`;
    depts.forEach(d => {
      const btn = document.createElement('button');
      btn.className = `mp-dept-tab${this._activeDept === d ? ' active' : ''}`;
      btn.dataset.dept = d;
      btn.textContent = d;
      tabsEl.appendChild(btn);
    });
    tabsEl.querySelectorAll('.mp-dept-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        this._activeDept = btn.dataset.dept;
        tabsEl.querySelectorAll('.mp-dept-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._renderItems();
      });
    });
  }

  _renderItems() {
    const listEl = this._el('-list');
    const items = this._filteredItems();
    if (items.length === 0) {
      listEl.innerHTML = `
        <div class="mp-empty">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <div class="mp-empty-title">No materials found</div>
          <div class="mp-empty-sub">Try a different search or department filter.</div>
        </div>`;
      return;
    }

    listEl.innerHTML = items.map(item => this._itemHTML(item)).join('');

    listEl.querySelectorAll('.mp-item').forEach(card => {
      // Toggle selection on card click (but not on qty input)
      card.addEventListener('click', e => {
        if (e.target.closest('.mp-item-qty input')) return;
        const id = card.dataset.id;
        if (this._selected[id]) {
          delete this._selected[id];
          card.classList.remove('selected');
        } else {
          const item = this._findItem(id);
          if (item) {
            this._selected[id] = { item, quantity: 1 };
            card.classList.add('selected');
          }
        }
        this._afterChange();
      });

      // Quantity input
      const qtyInput = card.querySelector('.mp-item-qty input');
      if (qtyInput) {
        qtyInput.addEventListener('click', e => e.stopPropagation());
        qtyInput.addEventListener('input', e => {
          const id = card.dataset.id;
          const val = parseFloat(e.target.value) || 1;
          if (this._selected[id]) {
            this._selected[id].quantity = val;
            this._afterChange();
          }
        });
      }
    });
  }

  _itemHTML(item) {
    const sel = !!this._selected[item.id];
    const qty = this._selected[item.id]?.quantity ?? 1;
    return `
      <div class="mp-item${sel ? ' selected' : ''}" data-id="${item.id}">
        <div class="mp-item-check">
          <svg class="mp-item-check-mark" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
        </div>
        <div class="mp-item-info">
          <div class="mp-item-name">${this._esc(item.name)}</div>
          <div class="mp-item-meta">
            ${item.brand ? `<span class="mp-item-tag brand">${this._esc(item.brand)}</span>` : ''}
            ${item.uom   ? `<span class="mp-item-tag uom">${this._esc(item.uom)}</span>` : ''}
          </div>
        </div>
        <div class="mp-item-qty">
          <label>Qty</label>
          <input type="number" min="0.01" step="any" value="${qty}" onclick="event.stopPropagation()">
        </div>
      </div>`;
  }

  _renderSummary() {
    const chips = this._el('-chips');
    const sel = Object.values(this._selected);
    const section = document.getElementById(this.containerId)
      ?.closest('.mp-section') || document.getElementById(this.containerId)?.parentElement?.parentElement;

    if (sel.length === 0) {
      if (section) section.classList.remove('has-selection');
      return;
    }
    if (section) section.classList.add('has-selection');

    chips.innerHTML = sel.map(({ item, quantity }) => `
      <div class="mp-summary-chip" data-id="${item.id}">
        ${this._esc(item.name)}
        <span class="mp-chip-qty">${quantity} ${item.uom || ''}</span>
        <svg class="mp-chip-remove" viewBox="0 0 24 24" data-id="${item.id}">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </div>`).join('');

    chips.querySelectorAll('.mp-chip-remove').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const id = btn.dataset.id;
        delete this._selected[id];
        this._afterChange(true);
      });
    });
  }

  _afterChange(rerenderItems = false) {
    if (rerenderItems) this._renderItems();
    this._renderSummary();
    this._updateBadge();
    this._syncHiddenField();
  }

  _updateBadge() {
    const badge = this._el('-badge');
    const count = Object.keys(this._selected).length;
    badge.textContent = count;
    badge.classList.toggle('has-items', count > 0);
  }

  _syncHiddenField() {
    const field = this._el('-field');
    field.value = JSON.stringify(this.getSelected());
    // Fire a native change event so frameworks / form collectors pick it up
    field.dispatchEvent(new Event('change', { bubbles: true }));
  }

  _filteredItems() {
    const items = [];
    Object.entries(this._catalog).forEach(([dept, list]) => {
      if (this._activeDept !== 'All' && dept !== this._activeDept) return;
      list.forEach(item => {
        if (this._search &&
            !item.name.toLowerCase().includes(this._search) &&
            !item.brand.toLowerCase().includes(this._search)) return;
        items.push({ ...item, department: dept });
      });
    });
    return items;
  }

  _findItem(id) {
    for (const list of Object.values(this._catalog)) {
      const found = list.find(i => i.id === id);
      if (found) return { ...found };
    }
    return null;
  }

  _el(suffix) {
    return document.getElementById(this.containerId + suffix);
  }

  _esc(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  _skeletonHTML() {
    return `<div class="mp-loading">
      ${[...Array(4)].map(() => '<div class="mp-skeleton"></div>').join('')}
    </div>`;
  }
}
