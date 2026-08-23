/**
 * Shared HR form ?edit=<submission_id> hydration + PUT /api/workflow/submissions/:id/update
 * (grace-period employee edits; RM / HR / GM / admin anytime — flags from backend).
 */
(function (global) {
  var stateMap = {};

  function unwrapNestedFormData(fd) {
    if (!fd || typeof fd !== 'object') return fd || {};
    var nested = fd.data;
    if (!nested || typeof nested !== 'object' || Array.isArray(nested)) return fd;
    var out = {};
    Object.keys(nested).forEach(function (k) {
      out[k] = nested[k];
    });
    Object.keys(fd).forEach(function (k) {
      if (k === 'data') return;
      var v = fd[k];
      var empty = v == null || v === '' || (Array.isArray(v) && !v.length);
      if (!empty || !(k in out)) out[k] = v;
    });
    if (out.from_date && !out.first_day_of_leave) out.first_day_of_leave = out.from_date;
    if (out.to_date && !out.last_day_of_leave) out.last_day_of_leave = out.to_date;
    if (out.number_of_days != null && out.number_of_days !== '' && (out.total_days_requested == null || out.total_days_requested === '')) {
      out.total_days_requested = out.number_of_days;
    }
    if (typeof out.leave_type === 'string' && out.leave_type.trim()) {
      var lt = out.leave_type.trim().toLowerCase().replace(/[_-]+/g, ' ');
      var leaveMap = {
        annual: 'annual',
        'annual leave': 'annual',
        sick: 'sick',
        'sick leave': 'sick',
        unpaid: 'unpaid',
        'unpaid leave': 'unpaid',
        compassionate: 'compassionate',
        study: 'study',
        examination: 'examination',
        hajj: 'hajj',
        other: 'other',
      };
      if (leaveMap[lt]) out.leave_type = leaveMap[lt];
    }
    return out;
  }

  function toDateInputOnly(v) {
    if (v == null || v === '') return '';
    var s = String(v).trim();
    return s.length >= 10 ? s.slice(0, 10) : s;
  }

  /** UTC/Z from API; display in Asia/Dubai (GST). Legacy naive HR timestamps are UAE wall (below). */
  var DISPLAY_TZ = 'Asia/Dubai';

  /**
   * Naive ``YYYY-MM-DDTHH:MM…`` from older HR form_data (UAE server clock ≈ Asia/Dubai).
   * UAE Standard Time is UTC+4 year-round (no DST since 2020).
   */
  function parseLegacyNaiveHrInstant(isoNorm) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(isoNorm)) return null;
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(isoNorm)) return null;
    var d = new Date(isoNorm + '+04:00');
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function parseDisplayInstant(iso) {
    if (iso == null || iso === '') return null;
    var s = String(iso).trim().replace(' ', 'T');
    var hasTz = /[zZ]$/.test(s) || /[+-]\d{2}:?\d{2}$/.test(s);
    if (!hasTz) {
      var legacy = parseLegacyNaiveHrInstant(s);
      if (legacy) return legacy;
      var ymdHead = s.slice(0, 10);
      if (/^\d{4}-\d{2}-\d{2}$/.test(ymdHead) && !/T\d/.test(s))
        s = ymdHead + 'T12:00:00Z';
      else s += 'Z';
    }
    var d = new Date(s);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function fmtLocalMaybeIso(iso) {
    var d = parseDisplayInstant(iso);
    if (!d) return iso == null || iso === '' ? '' : String(iso);
    return d.toLocaleString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
      timeZone: DISPLAY_TZ,
    });
  }

  /** Mirror module_hr/signature_preprocess.py — turn sheet pixels transparent so legacy grey pads read white on the form. */
  function rgbIsSignatureSheetBackground(r, g, b) {
    var mx = Math.max(r, g, b);
    var mn = Math.min(r, g, b);
    if (mx < 90) return false;
    if (mn < 62) return false;
    if (mn >= 248) return true;
    if (mn >= 222 && mx - mn <= 16) return true;
    if (b >= 225 && r >= 198 && g >= 208 && b - r >= 5 && b - g >= 4) return true;
    return false;
  }

  /** data:image/png only; HTTP(S) and other schemes returned unchanged via callback. */
  function stripSignaturePaperBackground(dataUrl, cb) {
    if (!dataUrl || dataUrl.indexOf('data:image/png') !== 0) {
      cb(dataUrl);
      return;
    }
    var im = new Image();
    im.onload = function () {
      try {
        var w = im.width;
        var h = im.height;
        if (!w || !h || w * h > 2500000) {
          cb(dataUrl);
          return;
        }
        var c = document.createElement('canvas');
        c.width = w;
        c.height = h;
        var ctx = c.getContext('2d');
        ctx.drawImage(im, 0, 0);
        var imgData = ctx.getImageData(0, 0, w, h);
        var d = imgData.data;
        var changed = false;
        for (var i = 0; i < d.length; i += 4) {
          var pr = d[i];
          var pg = d[i + 1];
          var pb = d[i + 2];
          if (rgbIsSignatureSheetBackground(pr, pg, pb)) {
            d[i + 3] = 0;
            changed = true;
          }
        }
        if (!changed) {
          cb(dataUrl);
          return;
        }
        ctx.putImageData(imgData, 0, 0);
        cb(c.toDataURL('image/png'));
      } catch (_) {
        cb(dataUrl);
      }
    };
    im.onerror = function () {
      cb(dataUrl);
    };
    im.src = dataUrl;
  }

  /** image data URL or HTTP(S) URL for <img src> */
  function signatureDataUrl(raw) {
    if (raw == null || raw === '') return '';
    if (typeof raw === 'string') {
      if (
        raw.indexOf('data:image') === 0 ||
        raw.indexOf('http://') === 0 ||
        raw.indexOf('https://') === 0 ||
        raw.indexOf('/') === 0
      )
        return raw;
      return '';
    }
    if (typeof raw === 'object' && raw !== null && raw.url) return signatureDataUrl(raw.url);
    return '';
  }

  /**
   * Teammate (_routed_signoffs) + management chain step signatures are not always bound to visible inputs.
   * Renders read-only cards under #hrRecordedSignaturesPanel when present.
   */
  function renderRecordedSignaturesPanel(form, fd) {
    var mount = document.getElementById('hrRecordedSignaturesPanel');
    var body = document.getElementById('hrRecordedSignaturesBody');
    var intro = document.getElementById('hrRecordedSignaturesIntro');
    if (!mount || !body) return;

    var entries = [];
    var seen = Object.create(null);
    function pushEntry(e) {
      if (!e || !e.url) return;
      var k = String(e.title || '') + '|' + String(e.url).slice(0, 160);
      if (seen[k]) return;
      seen[k] = true;
      entries.push(e);
    }

    if (fd && typeof fd === 'object') {
      var hasGmField = form && form.querySelector('[name="gm_signature"]');
      var hasHrField = form && form.querySelector('[name="hr_signature"]');
      var skipMgmtTrailInPanel = !!(hasGmField && hasHrField);

      var routed = fd._routed_signoffs;
      if (routed && typeof routed === 'object') {
        var slots = routed.slots;
        if (Array.isArray(slots)) {
          slots.forEach(function (grp) {
            if (!grp || typeof grp !== 'object') return;
            var label = grp.label || grp.key || 'Colleague';
            var signers = grp.signers;
            if (!Array.isArray(signers)) return;
            signers.forEach(function (s) {
              if (!s || !s.signature) return;
              var who = s.display_name || s.username || (s.user_id != null ? 'User #' + s.user_id : '');
              var title = String(label) + (who ? ' — ' + who : '');
              pushEntry({
                title: title,
                subtitle: s.signed_at ? fmtLocalMaybeIso(s.signed_at) : '',
                extra: s.comments ? String(s.comments) : '',
                url: signatureDataUrl(s.signature),
              });
            });
          });
        }
      }

      var legacyRep = fd.replacement_signers;
      if (Array.isArray(legacyRep)) {
        legacyRep.forEach(function (s) {
          if (!s || !s.signature) return;
          pushEntry({
            title: 'Coverage / replacement — ' + (s.display_name || s.username || 'Colleague'),
            subtitle: s.signed_at ? fmtLocalMaybeIso(s.signed_at) : '',
            extra: s.comments ? String(s.comments) : '',
            url: signatureDataUrl(s.signature),
          });
        });
      }

      var chain = fd.hr_mgmt_chain;
      var hasChainSigs = false;
      if (!skipMgmtTrailInPanel)
        hasChainSigs =
          chain &&
          typeof chain === 'object' &&
          Array.isArray(chain.steps) &&
          chain.steps.some(function (st) {
            return st && st.signature;
          });

      if (!skipMgmtTrailInPanel && chain && typeof chain === 'object' && Array.isArray(chain.steps)) {
        chain.steps.forEach(function (st) {
          if (!st || !st.signature) return;
          var pdfLabel = st.pdf_label || st.key || 'Management';
          var who = st.signed_by_name ? String(st.signed_by_name) : '';
          pushEntry({
            title: String(pdfLabel) + (who ? ' — ' + who : ''),
            subtitle: st.signed_at ? fmtLocalMaybeIso(st.signed_at) : '',
            extra: st.comments ? String(st.comments) : '',
            url: signatureDataUrl(st.signature),
          });
        });
      }

      if (!skipMgmtTrailInPanel && !hasChainSigs) {
        var gmu = signatureDataUrl(fd.gm_signature);
        if (gmu)
          pushEntry({
            title: 'General manager' + (fd.gm_approved_by_name ? ' — ' + String(fd.gm_approved_by_name) : ''),
            subtitle: fd.gm_approved_at ? fmtLocalMaybeIso(fd.gm_approved_at) : '',
            extra: fd.gm_comments ? String(fd.gm_comments) : '',
            url: gmu,
          });
        var hru = signatureDataUrl(fd.hr_signature);
        if (hru)
          pushEntry({
            title: 'HR (head office)' + (fd.hr_reviewed_by_name ? ' — ' + String(fd.hr_reviewed_by_name) : ''),
            subtitle: fd.hr_reviewed_at ? fmtLocalMaybeIso(fd.hr_reviewed_at) : '',
            extra: (fd.hr_comments || fd.hr_remarks || '')
              ? String(fd.hr_comments || fd.hr_remarks)
              : '',
            url: hru,
          });
      }
    }

    while (body.firstChild) body.removeChild(body.firstChild);

    if (!entries.length) {
      mount.style.display = 'none';
      if (intro) intro.style.display = 'none';
      return;
    }

    mount.style.display = 'block';
    if (intro) intro.style.display = 'block';

    entries.forEach(function (e) {
      var card = document.createElement('div');
      card.className = 'hr-recorded-sig-card';

      var h = document.createElement('div');
      h.className = 'hr-rec-title';
      h.textContent = e.title;
      card.appendChild(h);

      if (e.subtitle) {
        var st = document.createElement('div');
        st.className = 'hr-rec-sub';
        st.textContent = e.subtitle;
        card.appendChild(st);
      }

      var box = document.createElement('div');
      box.className = 'sig-box';
      var img = document.createElement('img');
      img.alt = '';
      var strip =
        window.InjaazSignatureDisplay &&
        typeof window.InjaazSignatureDisplay.stripSignaturePaperBackground === 'function'
          ? window.InjaazSignatureDisplay.stripSignaturePaperBackground
          : stripSignaturePaperBackground;
      strip(e.url, function (out) {
        img.src = out || e.url;
        if (window.InjaazSignatureDisplay && window.InjaazSignatureDisplay.applySignatureImageStyles) {
          window.InjaazSignatureDisplay.applySignatureImageStyles(img);
        } else {
          img.setAttribute('data-signature-display', '1');
        }
      });
      box.appendChild(img);
      card.appendChild(box);

      if (e.extra && String(e.extra).trim()) {
        var c = document.createElement('div');
        c.className = 'hr-rec-comment';
        c.textContent = String(e.extra).trim();
        card.appendChild(c);
      }

      body.appendChild(card);
    });
  }

  function effectiveEmployeeEditUntilIso(payload) {
    if (!payload || (payload.status || '') === 'draft') return null;
    var u = payload.employee_edit_until;
    if (u != null && String(u).trim() !== '') return String(u).trim();
    // Authoritative server value only — do not infer from created_at (mgmt sign-off clears deadline early).
    return null;
  }

  function padGraceSec(n) {
    var s = String(Math.floor(Number(n)));
    return s.length >= 2 ? s : '0' + s;
  }

  /** Format remaining milliseconds as M:SS */
  function formatRemainMs(ms) {
    ms = Math.max(0, Math.floor(ms / 1000));
    var m = Math.floor(ms / 60);
    var rs = ms % 60;
    return m + ':' + padGraceSec(rs);
  }

  function renderSignoffActivityPanel(activities, workflowLabel) {
    var sec = document.getElementById('hrSignoffActivitySec');
    var list = document.getElementById('hrSignoffActivityList');
    var empty = document.getElementById('hrSignoffActivityEmpty');
    var badge = document.getElementById('hrSignoffWorkflowBadge');
    var liveNote = document.getElementById('hrSignoffActivityLiveNote');
    if (!sec || !list) return;

    if (badge) {
      if (workflowLabel) {
        badge.style.display = 'block';
        badge.textContent = 'Current stage: ' + workflowLabel;
      } else {
        badge.style.display = 'none';
        badge.textContent = '';
      }
    }
    if (liveNote) liveNote.hidden = !(signoffPoll.iv !== null || (activities && activities.length));

    while (list.firstChild) list.removeChild(list.firstChild);

    if (!activities || !activities.length) {
      sec.style.display = 'block';
      if (empty) empty.style.display = 'block';
      return;
    }
    if (empty) empty.style.display = 'none';
    sec.style.display = 'block';

    activities.forEach(function (row) {
      var li = document.createElement('li');
      li.className = 'hr-signoff-activity-item';

      var dot = document.createElement('span');
      dot.className = 'hr-signoff-activity-dot';
      dot.setAttribute('aria-hidden', 'true');

      var stack = document.createElement('div');
      stack.className = 'hr-signoff-activity-stack';

      var title = document.createElement('div');
      title.className = 'hr-signoff-activity-title';
      var lab = (row && row.label) || '—';
      var actor = (row && row.actor) || '';
      title.textContent = lab + (actor ? ' · ' + actor : '');

      var whenEl = document.createElement('time');
      whenEl.className = 'hr-signoff-activity-time';
      var at = row && row.at;
      whenEl.textContent = at ? fmtLocalMaybeIso(at) : '—';
      if (at) whenEl.setAttribute('datetime', String(at));

      stack.appendChild(title);
      stack.appendChild(whenEl);

      var det = row && row.detail;
      if (det && String(det).trim()) {
        var d = document.createElement('div');
        d.className = 'hr-signoff-activity-detail';
        d.textContent = String(det).trim();
        stack.appendChild(d);
      }

      li.appendChild(dot);
      li.appendChild(stack);
      list.appendChild(li);
    });
  }

  var signoffPoll = { iv: null, lastFp: null, sid: null, busy: false, onFingerprintChange: null };

  function stopSignoffActivityPoll() {
    if (signoffPoll.iv !== null) {
      clearInterval(signoffPoll.iv);
      signoffPoll.iv = null;
    }
    signoffPoll.lastFp = null;
    signoffPoll.sid = null;
    signoffPoll.onFingerprintChange = null;
  }

  function pollSignoffActivityOnce() {
    if (document.visibilityState === 'hidden') return;
    var token = localStorage.getItem('access_token');
    var sid = signoffPoll.sid;
    if (!token || !sid) return;
    fetch('/hr/api/signoff-activity/' + encodeURIComponent(sid), {
      headers: { Authorization: 'Bearer ' + token },
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, j: j };
        });
      })
      .then(function (pack) {
        var j = pack.j;
        if (!pack.ok || !j || j.success === false || !j.fingerprint) return;
        var label = j.workflow_status_label || '';
        if (signoffPoll.lastFp === null) {
          signoffPoll.lastFp = j.fingerprint;
          renderSignoffActivityPanel(j.activities || [], label);
          return;
        }
        if (j.fingerprint !== signoffPoll.lastFp) {
          signoffPoll.lastFp = j.fingerprint;
          renderSignoffActivityPanel(j.activities || [], label);
          if (typeof signoffPoll.onFingerprintChange === 'function') {
            signoffPoll.onFingerprintChange(sid);
          }
        }
      })
      .catch(function () {
        /* ignore */
      });
  }

  function startSignoffActivityPoll(sid, onFingerprintChange) {
    if (!sid) return;
    stopSignoffActivityPoll();
    signoffPoll.sid = String(sid);
    signoffPoll.onFingerprintChange = onFingerprintChange || null;
    pollSignoffActivityOnce();
    signoffPoll.iv = setInterval(pollSignoffActivityOnce, 14000);
  }

  function bootSignoffActivitySidebar() {
    if (!document.getElementById('hrSignoffActivitySec')) return;
    var editSid = new URLSearchParams(location.search).get('edit');
    if (editSid) {
      startSignoffActivityPoll(editSid);
    } else {
      renderSignoffActivityPanel([], null);
    }
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && signoffPoll.iv !== null && signoffPoll.sid) {
      pollSignoffActivityOnce();
    }
  });

  function showRevisionBanner(fd) {
    var el = document.getElementById('submissionRevisionBanner');
    if (!el) return;
    var hist = fd && fd.submission_form_revision_history;
    var hasHist = Array.isArray(hist) && hist.length;
    if (!fd || (!fd.submission_form_revision_at && !hasHist)) {
      el.style.display = 'none';
      return;
    }
    el.style.display = 'block';
    el.style.whiteSpace = 'pre-line';
    if (hasHist) {
      var sorted = hist.slice().sort(function (a, b) {
        return (Number(a.save_index) || 0) - (Number(b.save_index) || 0);
      });
      var lines = sorted.map(function (e) {
        var who = e.by_name || '—';
        var when = fmtLocalMaybeIso(e.at || '');
        return 'Save #' + (e.save_index != null ? e.save_index : '—') + ': ' + who + ' · ' + when;
      });
      el.textContent =
        'Post-submit edits (' +
        hist.length +
        ' save' +
        (hist.length === 1 ? '' : 's') +
        ') — full trail is stored and appears on PDFs/emailed copies:\n' +
        lines.join('\n');
      return;
    }
    el.style.whiteSpace = '';
    var n = fd.submission_form_revision_count;
    var by = fd.submission_form_revision_by_name || '';
    var nNum = Number(n);
    el.textContent =
      'This form was updated after submission' +
      (Number.isFinite(nNum) && nNum >= 1 ? ' (save #' + nNum + ')' : '') +
      (by ? ' by ' + by : '') +
      ' — ' +
      fmtLocalMaybeIso(fd.submission_form_revision_at) +
      '.';
  }

  function fieldIsMgmtOrHr(el) {
    if (!el || !(el.closest && typeof el.closest === 'function')) return false;
    var chain = document.getElementById('hrMgmtChainSec');
    return Boolean((chain && chain.contains(el)) || el.closest('.hr-staff-zone'));
  }

  function privilegedList(opt) {
    return opt.privilegedFieldNames && opt.privilegedFieldNames.length
      ? opt.privilegedFieldNames
      : ['gm_signature', 'hr_signature'];
  }

  function isPrivilegedName(name, opt) {
    if (!name) return false;
    return privilegedList(opt).indexOf(name) >= 0;
  }

  /**
   * @returns {'employee'|'hr'|'mgmt'|'privileged'|'skip'}
   */
  function fieldBucket(el, form, opt) {
    var tag = el.tagName;
    if (!el.name || tag === 'BUTTON') return 'skip';
    if (el.type === 'file' || el.type === 'submit' || el.type === 'reset') return 'skip';
    if (isPrivilegedName(el.name, opt)) return 'privileged';
    if (fieldIsMgmtOrHr(el)) return el.closest('.hr-staff-zone') ? 'hr' : 'mgmt';
    return 'employee';
  }

  function signatureToDisplayUrl(raw) {
    if (raw == null || raw === '') return '';
    if (typeof raw === 'string') return raw;
    if (typeof raw === 'object' && raw.url) return raw.url;
    if (typeof raw === 'object' && typeof raw.saved === 'string') return ''; // uploaded ref only
    return '';
  }

  /** When RM signs via hr_mgmt_chain, legacy submissions may lack flat reporting_manager_signature. */
  function syncReportingManagerSignatureFromMgmtChain(form, fd) {
    if (!fd || typeof fd !== 'object') return;
    var inp = form.elements['reporting_manager_signature'];
    if (!inp || inp.type !== 'hidden') return;
    if (signatureToDisplayUrl(inp.value)) return;
    var fromFlat = fd.reporting_manager_signature;
    if (fromFlat != null && fromFlat !== '') {
      applySignaturePreview(form, 'reporting_manager_signature', fromFlat);
      return;
    }
    var chain = fd.hr_mgmt_chain;
    if (!chain || typeof chain !== 'object') return;
    var steps = chain.steps;
    if (!Array.isArray(steps)) return;
    for (var i = 0; i < steps.length; i++) {
      var st = steps[i];
      if (!st || !st.signature) continue;
      var k = st.key;
      if (k === 'reporting_manager' || k === 'supervisor') {
        applySignaturePreview(form, 'reporting_manager_signature', st.signature);
        return;
      }
    }
  }

  /** When GM / HR signs via hr_mgmt_chain only, flat gm_signature / hr_signature may be missing until mirror runs. */
  function syncGmHrSignaturesFromMgmtChain(form, fd) {
    if (!fd || typeof fd !== 'object') return;
    var chain = fd.hr_mgmt_chain;
    if (!chain || typeof chain !== 'object') return;
    var steps = chain.steps;
    if (!Array.isArray(steps)) return;

    var gmInp = form.elements['gm_signature'];
    if (gmInp && gmInp.type === 'hidden' && !signatureToDisplayUrl(gmInp.value)) {
      var gmPick = null;
      var gmMirror = null;
      for (var i = 0; i < steps.length; i++) {
        var st = steps[i];
        if (!st || !st.signature) continue;
        if (st.key === 'general_manager') {
          gmPick = st;
          break;
        }
        if (!gmMirror && st.also_mirrors_gm_fields) gmMirror = st;
      }
      var gmSrc = gmPick || gmMirror;
      if (gmSrc) applySignaturePreview(form, 'gm_signature', gmSrc.signature);
    }

    var hrInp = form.elements['hr_signature'];
    if (hrInp && hrInp.type === 'hidden' && !signatureToDisplayUrl(hrInp.value)) {
      for (var j = 0; j < steps.length; j++) {
        var sth = steps[j];
        if (!sth || !sth.signature) continue;
        if (sth.key === 'hr_head_office') {
          applySignaturePreview(form, 'hr_signature', sth.signature);
          break;
        }
      }
    }
  }

  function applySignaturePreview(form, fieldName, rawVal) {
    var url =
      typeof rawVal === 'string'
        ? rawVal
        : typeof rawVal === 'object' && rawVal !== null && rawVal.url
          ? String(rawVal.url)
          : '';
    var inp = form.elements[fieldName];
    if (!inp || inp.type !== 'hidden') return;
    if (url) inp.value = url;
    var wrap = inp.closest('.sig-wrap');
    if (!wrap) return;
    var img = wrap.querySelector('img');
    var ph = wrap.querySelector('.sig-ph');
    var show =
      url &&
      (url.indexOf('data:image') === 0 ||
        url.indexOf('http://') === 0 ||
        url.indexOf('https://') === 0 ||
        url.indexOf('/') === 0);
    if (show) {
      if (ph) ph.style.display = 'none';
      var rm = wrap.querySelector('.btn-rm');
      if (rm) rm.style.display = 'inline-flex';
      if (img) {
        stripSignaturePaperBackground(url, function (out) {
          if (!inp.parentNode || !wrap.parentNode) return;
          if (out) inp.value = out;
          img.src = out || url;
          img.style.display = 'block';
          try {
            form.dispatchEvent(
              new CustomEvent('hrSignaturePreviewApplied', {
                bubbles: true,
                detail: { fieldName: fieldName },
              })
            );
          } catch (_) {
            /* ignore */
          }
        });
      }
    }
  }

  function setScalarControl(form, name, val, opt) {
    var els = form.elements[name];
    if (els == null || val === undefined) return;

    var isSigField = /\bsignature\b|_signature$/i.test(name);
    if (isSigField) {
      applySignaturePreview(form, name, val);
      return;
    }

    function setOne(el, v) {
      if (!el) return;
      var tag = el.tagName;
      if (tag === 'SELECT' || tag === 'TEXTAREA')
        el.value = v == null ? '' : String(v);
      else if (el.type === 'checkbox')
        el.checked = Boolean(v);
      else if (el.type === 'radio') el.checked = String(el.value) === String(v);
      else if (el.type !== 'file' && el.type !== 'button' && el.type !== 'submit') {
        el.value = v == null ? '' : String(v);
      }
    }

    if (els.nodeName) {
      if (els.type === 'checkbox' && opt.clearanceCheckboxNames && opt.clearanceCheckboxNames.indexOf(name) >= 0) {
        els.checked = Boolean(val);
        return;
      }
      if (els.type === 'radio') {
        var want = String(val == null ? '' : val);
        var esc = name.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        form.querySelectorAll('input[type="radio"][name="' + esc + '"]').forEach(function (r) {
          r.checked = String(r.value) === want;
        });
        return;
      }
      if (els.tagName === 'INPUT' && /date/i.test(els.type) && typeof val === 'string') setOne(els, toDateInputOnly(val));
      else setOne(els, val);
      return;
    }

    try {
      if (els.length && els[0] && els[0].type === 'checkbox') {
        var wantCb = String(val == null ? '' : val);
        for (var i = 0; i < els.length; i++) {
          els[i].checked = String(els[i].value) === wantCb;
        }
        return;
      }
      if (els.length && els[0] && els[0].type === 'radio') {
        var wantRadio = String(val == null ? '' : val);
        for (var r = 0; r < els.length; r++) {
          els[r].checked = String(els[r].value) === wantRadio;
        }
        return;
      }
      if (typeof val === 'boolean' || val === true || val === false) return;
      if (typeof val !== 'number' && val != null) setOne(els[0], val);
    } catch (_) {
      /* ignore */
    }
  }

  /** Default population from submission.form_data (flat keys only). */
  function defaultPopulate(form, fd, opt) {
    if (!fd || typeof fd !== 'object') return;
    Object.keys(fd).forEach(function (k) {
      if (
        k === 'form_type' ||
        k.indexOf('submission_form_revision') === 0 ||
        k === 'replacement_signatures' ||
        k === 'reporting_officer_signer_ids' ||
        k === 'contract_evaluator_signer_ids' ||
        k === 'replacement_signer_ids' ||
        k === 'mgmt_operations_manager_signer_id'
      )
        return;
      var v = fd[k];
      if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
        if (/\bsignature\b|_signature$/i.test(k)) applySignaturePreview(form, k, v);
        return;
      }
      if (Array.isArray(v)) return;
      setScalarControl(form, k, v, opt);
    });
    if (opt.clearanceCheckboxNames) {
      opt.clearanceCheckboxNames.forEach(function (cn) {
        if (fd[cn] == null) return;
        var el = form.elements[cn];
        if (el && el.type === 'checkbox') el.checked = Boolean(fd[cn]);
      });
    }
  }

  function registerState(form, part) {
    stateMap[form.id] = part;
  }

  /** Resolve submit bar inside `form` (ids are inconsistent across HR templates). */
  function resolveSubmitBar(form, opt) {
    if (!opt || !opt.submitBarSelector) return null;
    if (opt.submitBarSelector instanceof Element) return opt.submitBarSelector;
    var sel = opt.submitBarSelector;
    try {
      var el = form.querySelector(sel);
      if (el) return el;
    } catch (_) {
      /* ignore */
    }
    try {
      return document.querySelector(sel);
    } catch (_) {
      return null;
    }
  }

  function lockForm(form, opt) {
    opt._viewLocked = true;
    var bar = resolveSubmitBar(form, opt);
    if (bar) bar.style.display = 'none';
    form.querySelectorAll('.sig-actions').forEach(function (el) {
      el.style.display = 'none';
    });
    form.querySelectorAll('button[type="submit"], button.btn-reset, .btn-reset').forEach(function (b) {
      if (bar && bar.contains(b)) return;
      b.disabled = true;
      b.style.display = 'none';
    });
    form.querySelectorAll('input:not([type="hidden"]), textarea, select').forEach(function (el) {
      if (el.type === 'radio' || el.type === 'checkbox') el.disabled = true;
      else {
        el.readOnly = true;
        if (el.tagName === 'SELECT') el.disabled = true;
      }
    });
    var mgmt = document.getElementById('hrMgmtChainSec');
    if (mgmt) {
      mgmt.querySelectorAll('button, select').forEach(function (el) {
        el.disabled = true;
      });
      mgmt.style.opacity = '0.92';
    }
  }

  function unlockHrStaffZones(form) {
    document.querySelectorAll('.hr-staff-zone').forEach(function (zone) {
      zone.classList.remove('hr-staff-zone--locked');
      zone.querySelectorAll('input, textarea, select').forEach(function (el) {
        if (el.type === 'hidden') return;
        if (el.type === 'radio' || el.type === 'checkbox') el.disabled = false;
        else {
          el.readOnly = false;
          el.removeAttribute('readonly');
          if (el.tagName === 'SELECT') el.disabled = false;
        }
      });
      zone.querySelectorAll('.sig-actions').forEach(function (el) {
        el.style.display = '';
      });
    });
  }

  function unlockEmployeePortion(form, opt, ctx) {
    form.querySelectorAll('input:not([type="hidden"]), textarea, select').forEach(function (el) {
      if (fieldIsMgmtOrHr(el)) return;
      var b = fieldBucket(el, form, opt);
      if (b === 'hr' || b === 'mgmt') return;
      if (b === 'privileged' && !(ctx.canEditHr && ctx.canEditEmployee)) return;
      if (el.type === 'radio' || el.type === 'checkbox') el.disabled = false;
      else {
        el.readOnly = false;
        el.removeAttribute('readonly');
        if (el.tagName === 'SELECT') el.disabled = false;
      }
    });
    form.querySelectorAll('.sig-wrap').forEach(function (wrap) {
      var probe = wrap.querySelector('input[name]') || wrap.querySelector('textarea[name]');
      if (!probe || fieldIsMgmtOrHr(probe)) return;
      var b = fieldBucket(probe, form, opt);
      if (b === 'privileged' && !(ctx.canEditHr && ctx.canEditEmployee)) return;
      var act = wrap.querySelector('.sig-actions');
      if (act) act.style.display = '';
    });
  }

  function collectBucket(form, opt, bucketWant, saveKind) {
    var out = {};
    var seenRadio = Object.create(null);
    form.querySelectorAll('input, textarea, select').forEach(function (el) {
      var b = fieldBucket(el, form, opt);
      if (saveKind === 'employee' && b === 'privileged') return;
      if (b !== bucketWant) return;
      if (el.type === 'hidden' && el.name && el.name.indexOf('hr_') === 0 && bucketWant === 'employee') return;
      if (el.type === 'radio') {
        if (seenRadio[el.name]) return;
        seenRadio[el.name] = true;
        var esc = el.name.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        var chk = form.querySelector('input[type="radio"][name="' + esc + '"]:checked');
        if (chk) out[chk.name] = chk.value;
        return;
      }
      if (el.type === 'checkbox') {
        out[el.name] = el.checked;
        return;
      }
      if (el.type === 'button' || el.type === 'submit' || el.type === 'reset' || el.type === 'file') return;
      out[el.name] = el.value;
    });
    if (bucketWant === 'employee' || (saveKind === 'full' && bucketWant === 'employee')) {
      if (opt.clearanceCheckboxNames) {
        opt.clearanceCheckboxNames.forEach(function (cn) {
          var el = form.elements[cn];
          if (el && el.type === 'checkbox') out[cn] = el.checked;
        });
      }
    }
    return out;
  }

  function collectUpdates(form, opt, saveKind) {
    if (typeof opt.serializeUpdates === 'function') {
      return opt.serializeUpdates(form, saveKind, opt) || {};
    }
    if (saveKind === 'hr') {
      return Object.assign(
        {},
        collectBucket(form, opt, 'hr', saveKind),
        collectBucket(form, opt, 'privileged', 'full')
      );
    }
    if (saveKind === 'employee') {
      return Object.assign({}, collectBucket(form, opt, 'employee', saveKind));
    }
    return Object.assign(
      {},
      collectBucket(form, opt, 'employee', 'full'),
      collectBucket(form, opt, 'privileged', 'full'),
      collectBucket(form, opt, 'hr', 'full'),
      collectBucket(form, opt, 'mgmt', 'full')
    );
  }

  function wireSaveSubmit(form, opt, ctx) {
    form.addEventListener(
      'submit',
      function (e) {
        if (!ctx.allowSave || !ctx.hydrateId) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        var token = localStorage.getItem('access_token');
        if (!token) {
          alert('Please sign in again.');
          return;
        }
        var bar = resolveSubmitBar(form, opt);
        var btn = bar
          ? bar.querySelector('button[type="submit"], input[type="submit"]')
          : form.querySelector('button[type="submit"], input[type="submit"]');
        var updates = collectUpdates(form, opt, ctx.saveKind);
        if (typeof opt.appendToPayload === 'function')
          Object.assign(updates, opt.appendToPayload(ctx.saveKind) || {});
        if (btn) {
          btn.disabled = true;
          btn.textContent = 'Saving…';
        }
        fetch('/api/workflow/submissions/' + encodeURIComponent(ctx.hydrateId) + '/update', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
          body: JSON.stringify({ form_data_updates: updates }),
        })
          .then(function (r) {
            return r.json().then(function (j) {
              return { ok: r.ok, j: j };
            });
          })
          .then(function (pack) {
            var r = pack.j;
            if (pack.ok && r.success !== false) {
              var frm = r.submission && r.submission.form_data;
              if (frm) showRevisionBanner(frm);
              alert(r.message || 'Saved.');
            } else alert('Error: ' + (r.error || r.message || 'Save failed'));
          })
          .catch(function (err) {
            alert('Unable to save: ' + (err && err.message ? err.message : String(err)));
          })
          .finally(function () {
            if (btn) {
              btn.disabled = false;
              btn.textContent = ctx.saveKind === 'hr' ? 'Save HR updates' : 'Save changes';
            }
          });
      },
      true
    );
  }

  /** Show live clock whenever API returns submitter grace deadline (including HR/GM on own submission). */
  function shouldShowSubmitterGraceCountdown(ctx, untilIso) {
    return !!untilIso;
  }

  var graceTicker = { iv: null, refreshing: false };

  function stopSubmitterGraceCountdown() {
    if (graceTicker.iv !== null) {
      clearInterval(graceTicker.iv);
      graceTicker.iv = null;
    }
    var row = document.getElementById('submissionEditGraceRow');
    var tickEl = document.getElementById('submissionEditGraceCountdownTick');
    if (row) row.style.display = 'none';
    if (tickEl) tickEl.textContent = '';
  }

  /** Top-of-page back link: match list hub when viewing a submitted record from ?edit=. */
  function syncBackNavToSubmittedForms() {
    var back = document.querySelector('.page-inner > a.back-btn');
    if (!back) return;
    back.setAttribute('href', '/workflow/submitted-forms');
    var svg = back.querySelector('svg');
    var label = ' Back to submitted forms';
    if (svg) {
      var clone = svg.cloneNode(true);
      back.textContent = '';
      back.appendChild(clone);
      back.appendChild(document.createTextNode(label));
    } else {
      back.textContent = label.replace(/^\s+/, '');
    }
  }

  function syncGraceExpiredHintVisibility(show) {
    var wrap = document.getElementById('submissionGraceExpiredWrap');
    if (wrap) {
      wrap.style.display = show ? 'block' : 'none';
      return;
    }
    /* Legacy markup without wrapper: hints would stay visible forever. */
    if (!show) {
      var timeEl = document.getElementById('submissionGraceExpiredHintTime');
      var mgmtEl = document.getElementById('submissionGraceExpiredHintMgmt');
      if (timeEl) timeEl.style.display = 'none';
      if (mgmtEl) mgmtEl.style.display = 'none';
    }
  }

  function syncGraceRevokedByMgmtHint(payload) {
    var timeEl = document.getElementById('submissionGraceExpiredHintTime');
    var mgmtEl = document.getElementById('submissionGraceExpiredHintMgmt');
    if (!timeEl || !mgmtEl) return;
    var byMgmt = !!(payload && payload.submitter_grace_revoked_by_management_signature);
    timeEl.style.display = byMgmt ? 'none' : 'block';
    mgmtEl.style.display = byMgmt ? 'block' : 'none';
  }

  function syncSubmissionApprovedDetail(allowSaveWhileFinalized) {
    var el = document.getElementById('submissionApprovedDetail');
    if (!el) return;
    if (allowSaveWhileFinalized) {
      el.innerHTML =
        'Finalized and approved. As <strong>administrator</strong> you may still amend stored fields when needed; for other roles this page is read-only. Use <strong>Download PDF</strong> below for the official signed record.';
    } else {
      el.innerHTML =
        'This request is finalized. Editing is closed; use <strong>Download PDF</strong> below for the official signed record.';
    }
  }

  /**
   * Update banner, locks, save bar from API payload (no form repopulation).
   * Call after initial hydrate and after grace expiry refetch.
   */
  function applyHydrationLocksAndBanner(form, opt, ctx, payload, urlEditSid) {
    ctx.canEditEmployee = !!payload.can_edit_employee_sections;
    ctx.canEditHr = !!payload.can_edit_hr_sections;
    ctx.saveKind = null;
    ctx.allowSave = false;

    var isDraft = (payload.status || '') === 'draft';
    var banner = document.getElementById('submissionViewBanner');
    var btxt = document.getElementById('submissionViewBannerText');
    var pdfA = document.getElementById('submissionViewPdf');
    if (isDraft) {
      syncGraceExpiredHintVisibility(false);
      var apr0 = document.getElementById('submissionApprovedRow');
      if (apr0) apr0.style.display = 'none';
      return effectiveEmployeeEditUntilIso(payload);
    }

    ctx.hydrateId = payload.submission_id || urlEditSid;
    var employeeEditUntilIso = effectiveEmployeeEditUntilIso(payload);
    var finalized = !!payload.hr_request_approved_completed;
    var withdrawn = !!payload.hr_request_withdrawn;

    if (banner && btxt) {
      banner.style.display = 'block';
      syncBackNavToSubmittedForms();
      var apr = document.getElementById('submissionApprovedRow');
      if (apr) apr.style.display = finalized && !withdrawn ? 'block' : 'none';
      var parts = [' Showing saved answers for ' + ctx.hydrateId + '.'];
      if (!finalized) {
        if (ctx.canEditEmployee && ctx.canEditHr) {
          parts.push(
            ' You have ongoing edit access as reporting manager / HR / GM / admin (employee and HR portions).'
          );
        } else if (ctx.canEditEmployee && employeeEditUntilIso) {
          parts.push(' You may edit employee fields until ' + fmtLocalMaybeIso(employeeEditUntilIso) + '.');
        } else if (ctx.canEditEmployee) {
          parts.push(' You can edit employee portions of this request.');
        } else if (ctx.canEditHr) {
          parts.push(' Employee sections are locked; HR Review / HR-only sections remain editable.');
        } else {
          parts.push(' This page is read-only; download the PDF for the official record.');
        }
        btxt.textContent = parts.join('');
      }
      if (withdrawn && btxt) {
        btxt.textContent =
          ' You withdrew this request (' +
          ctx.hydrateId +
          '). It is no longer in the approval workflow. This page is for reference; use Download PDF if needed.';
      }
      syncGraceExpiredHintVisibility(!!payload.submitter_employee_edit_window_closed && !finalized && !withdrawn);
      syncGraceRevokedByMgmtHint(!finalized && !withdrawn && payload ? payload : {});
      if (pdfA) {
        pdfA.href = '/hr/download-pdf/' + encodeURIComponent(ctx.hydrateId);
        pdfA.removeAttribute('target');
      }
    }

    lockForm(form, opt);
    if (ctx.canEditHr) unlockHrStaffZones(form);
    if (ctx.canEditEmployee) unlockEmployeePortion(form, opt, ctx);

    if (ctx.canEditHr && ctx.canEditEmployee) ctx.saveKind = 'full';
    else if (ctx.canEditHr) ctx.saveKind = 'hr';
    else if (ctx.canEditEmployee) ctx.saveKind = 'employee';
    ctx.allowSave = !!ctx.saveKind;

    if (finalized && btxt) {
      if (ctx.allowSave) {
        btxt.textContent =
          ' Showing saved submission ' + ctx.hydrateId + '. You may save changes while signed in as administrator.';
      } else {
        btxt.textContent = ' Showing saved submission ' + ctx.hydrateId + '.';
      }
    }
    syncSubmissionApprovedDetail(finalized && ctx.allowSave);

    registerState(form, {
      viewLocked: true,
      canEditEmployee: ctx.canEditEmployee,
      canEditHr: ctx.canEditHr,
    });

    var bar = resolveSubmitBar(form, opt);
    var submitBtn = bar
      ? bar.querySelector('button[type="submit"], input[type="submit"]')
      : form.querySelector('button[type="submit"], input[type="submit"]');
    var resetB = bar ? bar.querySelector('.btn-reset, button[type="button"].btn-reset') : null;
    if (ctx.allowSave && submitBtn) {
      submitBtn.disabled = false;
      submitBtn.style.display = '';
      submitBtn.textContent = ctx.saveKind === 'hr' ? 'Save HR updates' : 'Save changes';
      if (resetB) resetB.style.display = 'none';
      if (bar) bar.style.display = 'flex';
    } else {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.style.display = 'none';
      }
      if (resetB) resetB.style.display = 'none';
      if (bar) bar.style.display = 'none';
    }

    return employeeEditUntilIso;
  }

  function startSubmitterGraceCountdown(form, opt, ctx, untilIso) {
    stopSubmitterGraceCountdown();
    if (!shouldShowSubmitterGraceCountdown(ctx, untilIso)) return;
    var endMs = new Date(untilIso).getTime();
    if (Number.isNaN(endMs)) return;
    var row = document.getElementById('submissionEditGraceRow');
    var tickEl = document.getElementById('submissionEditGraceCountdownTick');
    if (!row || !tickEl) return;

    function expireAndRefetch() {
      if (graceTicker.iv !== null) {
        clearInterval(graceTicker.iv);
        graceTicker.iv = null;
      }
      if (graceTicker.refreshing) return;
      graceTicker.refreshing = true;
      row.style.display = 'block';
      tickEl.textContent = ' Updating edit access…';
      var token = localStorage.getItem('access_token');
      var hid = ctx.hydrateId;
      var urlSid = new URLSearchParams(location.search).get('edit') || hid;
      if (!token || !hid) {
        graceTicker.refreshing = false;
        stopSubmitterGraceCountdown();
        return;
      }
      fetch('/api/workflow/submissions/' + encodeURIComponent(hid), {
        headers: { Authorization: 'Bearer ' + token },
      })
        .then(function (r) {
          return r.json().then(function (j) {
            return { ok: r.ok, j: j };
          });
        })
        .then(function (pack) {
          var payload = pack.j;
          if (!pack.ok || !payload || payload.success === false) return;
          var mod = payload.module_type || payload.module;
          if (opt.moduleTypes.indexOf(mod) < 0) return;
          var nextUntil = applyHydrationLocksAndBanner(form, opt, ctx, payload, urlSid);
          startSubmitterGraceCountdown(form, opt, ctx, nextUntil || null);
        })
        .catch(function () {
          stopSubmitterGraceCountdown();
        })
        .finally(function () {
          graceTicker.refreshing = false;
        });
    }

    function tickRunner() {
      var rem = endMs - Date.now();
      if (rem <= 0) {
        expireAndRefetch();
        return;
      }
      row.style.display = 'block';
      tickEl.textContent =
        ' ' +
        formatRemainMs(rem) +
        ' left (ends ' +
        fmtLocalMaybeIso(untilIso) +
        '). The original submitter can no longer edit employee fields after this; reporting manager / HR / GM / admin keep access.';
    }

    graceTicker.iv = setInterval(tickRunner, 1000);
    tickRunner();
  }

  function attach(opt) {
    if (!opt || !opt.formId || !opt.moduleTypes || !opt.moduleTypes.length) return;
    var form = document.getElementById(opt.formId);
    if (!form) return;

    var ctx = {
      hydrateId: null,
      allowSave: false,
      saveKind: null,
      canEditEmployee: false,
      canEditHr: false,
    };

    registerState(form, { viewLocked: false, canEditEmployee: false, canEditHr: false });

    wireSaveSubmit(form, opt, ctx);

    function ingestSubmissionPayload(payload, urlEditSid) {
      if (!payload || payload.success === false) return;
      var mod = payload.module_type || payload.module;
      if (opt.moduleTypes.indexOf(mod) < 0) return;
      var fd = unwrapNestedFormData(payload.form_data || {});
      payload.form_data = fd;
      if (typeof opt.populateFromSubmission === 'function') opt.populateFromSubmission(payload, fd, form, opt);
      else defaultPopulate(form, fd, opt);
      syncReportingManagerSignatureFromMgmtChain(form, fd);
      syncGmHrSignaturesFromMgmtChain(form, fd);
      if (typeof opt.afterPopulate === 'function') opt.afterPopulate(payload, fd, form, opt);
      renderRecordedSignaturesPanel(form, fd);
      showRevisionBanner(fd);

      var untilIso = applyHydrationLocksAndBanner(form, opt, ctx, payload, urlEditSid);
      startSubmitterGraceCountdown(form, opt, ctx, untilIso);

      if (typeof opt.onEnterEditUi === 'function') opt.onEnterEditUi(payload, fd, form, opt);
    }

    function refetchSubmissionAfterSignoffChange(urlEditSid) {
      var token = localStorage.getItem('access_token');
      var hid = ctx.hydrateId || urlEditSid;
      if (!token || !hid || signoffPoll.busy) return;
      signoffPoll.busy = true;
      fetch('/api/workflow/submissions/' + encodeURIComponent(hid), {
        headers: { Authorization: 'Bearer ' + token },
      })
        .then(function (r) {
          return r.json().then(function (j) {
            return { ok: r.ok, j: j };
          });
        })
        .then(function (pack) {
          if (!pack.ok || !pack.j || pack.j.success === false) return;
          var payload = pack.j;
          var mod = payload.module_type || payload.module;
          if (opt.moduleTypes.indexOf(mod) < 0) return;
          ingestSubmissionPayload(payload, urlEditSid);
        })
        .catch(function () {
          /* ignore */
        })
        .finally(function () {
          signoffPoll.busy = false;
        });
    }

    function startSignoffActivityPollForAttach(urlEditSid) {
      startSignoffActivityPoll(ctx.hydrateId || urlEditSid, function () {
        refetchSubmissionAfterSignoffChange(urlEditSid);
      });
    }

    function runHydrate() {
      var sid = new URLSearchParams(location.search).get('edit');
      if (!sid) {
        renderSignoffActivityPanel([], null);
        return;
      }
      var token = localStorage.getItem('access_token');
      if (!token) return;
      fetch('/api/workflow/submissions/' + encodeURIComponent(sid), {
        headers: { Authorization: 'Bearer ' + token },
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (payload) {
          ingestSubmissionPayload(payload, sid);
          if (ctx.hydrateId) startSignoffActivityPollForAttach(sid);
        })
        .catch(function () {
          /* ignore */
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', runHydrate);
    else runHydrate();
  }

  var api = (global.HrGenericFormEdit = global.HrGenericFormEdit || {});
  api.attach = attach;
  api.showRevisionBanner = showRevisionBanner;
  api.defaultPopulate = defaultPopulate;
  api.renderRecordedSignaturesPanel = renderRecordedSignaturesPanel;
  api.renderSignoffActivityPanel = renderSignoffActivityPanel;
  api.startSignoffActivityPoll = startSignoffActivityPoll;
  api.stopSignoffActivityPoll = stopSignoffActivityPoll;
  api.bootSignoffActivitySidebar = bootSignoffActivitySidebar;
  api.canModifySig = function (formId, slotKey) {
    var f = document.getElementById(formId);
    if (!f) return true;
    var st = stateMap[f.id];
    if (!st || !st.viewLocked) return true;
    if (slotKey === 'hr') return !!st.canEditHr;
    return !!st.canEditEmployee;
  };
})(window);
