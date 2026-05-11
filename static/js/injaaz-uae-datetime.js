/**
 * Server timestamps should use UTC with Z; legacy HR form_data sometimes stored naive UAE wall time.
 * Display every instant in UAE (Asia/Dubai, GST).
 * Plain calendar dates YYYY-MM-DD are treated as a fixed calendar day (midday UTC anchor).
 */
(function (global) {
  var TZ = 'Asia/Dubai';

  /** Older HR payloads: naive ``YYYY-MM-DDTHH:MM…`` from UAE host clock (Asia/Dubai, UTC+4). */
  function parseLegacyNaiveHrWall(str) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(str)) return null;
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(str)) return null;
    var d = new Date(str + '+04:00');
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function parseInstant(s) {
    if (s == null || s === '') return null;
    var str = String(s).trim().replace(' ', 'T');
    var hasTz = /[zZ]$/.test(str) || /[+-]\d{2}:?\d{2}$/.test(str);
    if (!hasTz) {
      var legacy = parseLegacyNaiveHrWall(str);
      if (legacy) return legacy;
      var ymdHead = str.slice(0, 10);
      if (/^\d{4}-\d{2}-\d{2}$/.test(ymdHead) && !/T\d/.test(str))
        str = ymdHead + 'T12:00:00Z';
      else str += 'Z';
    }
    var d = new Date(str);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  global.InjaazDateTimeUAE = {
    TZ: TZ,
    parseInstant: parseInstant,
    formatDateMed: function (iso) {
      var d = parseInstant(iso);
      if (!d) return iso == null || iso === '' ? '' : String(iso);
      return d.toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        timeZone: TZ,
      });
    },
    formatDateDMY: function (iso) {
      var d = parseInstant(iso);
      if (!d) return iso == null || iso === '' ? '' : String(iso);
      return d.toLocaleDateString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        timeZone: TZ,
      });
    },
    formatDateTime: function (iso) {
      var d = parseInstant(iso);
      if (!d) return iso == null || iso === '' ? '' : String(iso);
      return d.toLocaleString('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZone: TZ,
      });
    },
    /** Today’s calendar date in Dubai (for document footers etc.). */
    todayDMY: function () {
      return new Date().toLocaleDateString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        timeZone: TZ,
      });
    },
  };
})(typeof window !== 'undefined' ? window : this);
