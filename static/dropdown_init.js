// static/dropdown_init.js
// Populates item selects using server endpoint /hvac-mep/dropdowns when needed.
// It exposes window.DROPDOWN_DATA and dispatches a `dropdowns:loaded` event once ready.

(function () {
  async function fetchDropdownData() {
    if (typeof DROPDOWN_DATA !== 'undefined' && DROPDOWN_DATA) {
      return DROPDOWN_DATA;
    }
    try {
      const res = await fetch(window.location.origin + '/hvac-mep/dropdowns', { cache: 'no-store' });
      if (!res.ok) throw new Error('Failed to load dropdowns: ' + res.status);
      return await res.json();
    } catch (err) {
      console.error('Dropdown load error:', err);
      return null;
    }
  }

  function clearSelect(selectEl, placeholder = '-- Select --') {
    selectEl.innerHTML = '';
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = placeholder;
    selectEl.appendChild(opt);
    selectEl.value = '';
    selectEl.disabled = true;
  }

  function populateSelect(selectEl, items) {
    clearSelect(selectEl);
    if (!items || items.length === 0) return;
    selectEl.disabled = false;
    items.forEach(it => {
      const opt = document.createElement('option');
      opt.value = it;
      opt.textContent = it;
      selectEl.appendChild(opt);
    });
  }

  async function init() {
    const data = await fetchDropdownData();
    if (!data) {
      // nothing to init
      return;
    }

    // Expose data globally and notify listeners
    window.DROPDOWN_DATA = data;
    // Notify other code that dropdowns are ready
    try {
      window.dispatchEvent(new Event('dropdowns:loaded'));
    } catch (err) {
      // older browsers: fallback to CustomEvent
      const ev = document.createEvent('Event');
      ev.initEvent('dropdowns:loaded', true, true);
      window.dispatchEvent(ev);
    }

    // No immediate DOM population here because item rows are created dynamically
    // and will read window.DROPDOWN_DATA when they are created.
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();