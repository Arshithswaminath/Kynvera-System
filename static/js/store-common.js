/**
 * Store Module — shared front-end helpers.
 * Used by store_dashboard, store_catalog_department, store_materials,
 * store_add_material, store_properties, store_property_detail.
 */
(function (global) {
  'use strict';

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = String(s ?? '');
    return d.innerHTML;
  }

  function formatAED(value, opts) {
    const n = parseFloat(value) || 0;
    return n.toLocaleString('en-AE', Object.assign({ minimumFractionDigits: 0, maximumFractionDigits: 0 }, opts || {}));
  }

  // Deterministic palette so a property's accent color is identical on the
  // properties grid and on its own property-detail page (both derive the
  // same index from the property name — no need to pass state via URL).
  const PROPERTY_PALETTE = [
    { accent: '#4f46e5', dark: '#312e81', icon: 'building' },
    { accent: '#db2777', dark: '#831843', icon: 'home' },
    { accent: '#d97706', dark: '#92400e', icon: 'construction' },
    { accent: '#2563eb', dark: '#1e3a8a', icon: 'factory' },
    { accent: '#7c3aed', dark: '#4c1d95', icon: 'landmark' },
    { accent: '#0d9488', dark: '#134e4a', icon: 'hotel' },
    { accent: '#e11d48', dark: '#881337', icon: 'store' },
    { accent: '#059669', dark: '#065f46', icon: 'apartment' },
  ];
  const UNASSIGNED_ACCENT = { accent: '#64748b', dark: '#334155', icon: 'box' };

  function hashName(name) {
    const str = String(name || '');
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
    }
    return hash;
  }

  function propertyAccent(name) {
    if (!name || name === 'Unassigned') return UNASSIGNED_ACCENT;
    return PROPERTY_PALETTE[hashName(name) % PROPERTY_PALETTE.length];
  }

  const ICONS = {
    building: '<svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 21h18M5 21V6.2a1.2 1.2 0 0 1 .6-1.04l5.4-3.09a1.2 1.2 0 0 1 1.2 0l5.4 3.09a1.2 1.2 0 0 1 .6 1.04V21M9 9h.01M9 12h.01M9 15h.01M15 9h.01M15 12h.01M15 15h.01"/></svg>',
    home: '<svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 11.5 12 4l9 7.5M5 10v9.5a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V10"/></svg>',
    construction: '<svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 21h18M6 21V10l6-4 6 4v11M10 21v-5h4v5"/></svg>',
    factory: '<svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 21V11l5 3.5V11l5 3.5V11l5 3.5V21H3Z"/><path stroke-linecap="round" stroke-linejoin="round" d="M7 21v-4M12 21v-4M17 21v-4"/></svg>',
    landmark: '<svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 21h18M4 21V10l8-6 8 6v11M9 21v-7h6v7"/></svg>',
    hotel: '<svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4 21V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v17M12 21v-6h5a2 2 0 0 1 2 2v4M7 6h.01M7 10h.01M7 14h.01"/></svg>',
    store: '<svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M4 9V5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v4M4 9h16M4 9l1 11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1l1-11M9 13a2 2 0 1 1 4 0v8H9v-8Z"/></svg>',
    apartment: '<svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 21V5a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v16M6 21h12M9 8h.01M9 12h.01M9 16h.01M15 8h.01M15 12h.01M15 16h.01"/></svg>',
    box: '<svg fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 7.5l-.625 10.632a2.25 2.25 0 0 1-2.247 2.118H6.622a2.25 2.25 0 0 1-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125Z"/></svg>',
  };

  function propertyIconSvg(name) {
    const a = propertyAccent(name);
    return ICONS[a.icon] || ICONS.box;
  }

  function timeAgo(isoString) {
    if (!isoString) return '';
    const then = new Date(isoString).getTime();
    if (Number.isNaN(then)) return '';
    const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (diffSec < 60) return 'just now';
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}d ago`;
    const diffMonth = Math.floor(diffDay / 30);
    if (diffMonth < 12) return `${diffMonth}mo ago`;
    return `${Math.floor(diffMonth / 12)}y ago`;
  }

  global.ProcCommon = { esc, formatAED, propertyAccent, propertyIconSvg, timeAgo };
})(window);
