// static/dropdown_init.js
// Populates inspection item selects from /inspection/dropdowns.
// Exposes window.DROPDOWN_DATA and dispatches `dropdowns:loaded` once ready.

(function () {
  function authHeaders() {
    var h = { Accept: 'application/json' };
    try {
      var token =
        localStorage.getItem('access_token') || localStorage.getItem('token');
      if (token) h.Authorization = 'Bearer ' + token;
    } catch (_) {}
    return h;
  }

  async function fetchDropdownData() {
    if (typeof window.DROPDOWN_DATA === 'object' && window.DROPDOWN_DATA && Object.keys(window.DROPDOWN_DATA).length) {
      return window.DROPDOWN_DATA;
    }
    try {
      var res = await fetch(window.location.origin + '/inspection/dropdowns', {
        cache: 'no-store',
        credentials: 'same-origin',
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error('Failed to load dropdowns: ' + res.status);
      return await res.json();
    } catch (err) {
      console.error('Dropdown load error:', err);
      return null;
    }
  }

  async function init() {
    var data = await fetchDropdownData();
    if (!data || typeof data !== 'object' || !Object.keys(data).length) {
      return;
    }

    window.DROPDOWN_DATA = data;
    try {
      window.dispatchEvent(new Event('dropdowns:loaded'));
    } catch (err) {
      var ev = document.createEvent('Event');
      ev.initEvent('dropdowns:loaded', true, true);
      window.dispatchEvent(ev);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
