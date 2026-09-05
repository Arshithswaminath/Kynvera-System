/**
 * Letters of Intent register — list + add/edit + connect-to-hiring
 */
(function () {
  'use strict';

  const LINK_LABELS = {
    unlinked: 'Not linked',
    linked: 'Linked',
    manual: 'Manual hiring',
  };

  function token() {
    return localStorage.getItem('access_token') || '';
  }

  function authHeaders(extra) {
    return Object.assign({ Authorization: 'Bearer ' + token() }, extra || {});
  }

  function escapeHtml(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function toast(msg, isError) {
    let el = document.getElementById('hhToast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'hhToast';
      el.className = 'hh-toast';
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.toggle('error', !!isError);
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(function () {
      el.classList.remove('show');
    }, 2800);
  }

  async function api(url, opts) {
    const options = opts || {};
    const headers = authHeaders(options.headers || {});
    if (options.json) {
      headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(url, {
      method: options.method || 'GET',
      headers: headers,
      body: options.json ? JSON.stringify(options.json) : options.body,
    });
    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      data = null;
    }
    if (!res.ok || (data && data.success === false)) {
      const err = (data && (data.error || data.message)) || ('Request failed (' + res.status + ')');
      throw new Error(err);
    }
    return data;
  }

  async function downloadFile(url, filename) {
    const res = await fetch(url, { headers: authHeaders() });
    if (!res.ok) throw new Error('Could not download file');
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename || 'document';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1500);
  }

  function parseDubaiDate(iso) {
    if (!iso) return null;
    if (window.InjaazDateTimeUAE && typeof window.InjaazDateTimeUAE.parseInstant === 'function') {
      return window.InjaazDateTimeUAE.parseInstant(iso);
    }
    let str = String(iso).trim().replace(' ', 'T');
    if (!/[zZ]$/.test(str) && !/[+-]\d{2}:?\d{2}$/.test(str)) str += 'Z';
    const d = new Date(str);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function formatStamp(iso) {
    const d = parseDubaiDate(iso);
    if (!d) return '';
    return d.toLocaleString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'Asia/Dubai',
    });
  }

  function stampMeta(letter) {
    const created = formatStamp(letter && letter.created_at);
    const updated = formatStamp(letter && letter.updated_at);
    const createdAt = parseDubaiDate(letter && letter.created_at);
    const updatedAt = parseDubaiDate(letter && letter.updated_at);
    const same = !createdAt || !updatedAt || Math.abs(updatedAt.getTime() - createdAt.getTime()) < 2000;
    return {
      created: created,
      updated: updated,
      same: same,
      iso: (letter && (letter.updated_at || letter.created_at)) || '',
    };
  }

  function ynBadge(yes, yesLabel, noLabel) {
    if (yes) {
      return '<span class="ol-chip is-done">' + escapeHtml(yesLabel) + '</span>';
    }
    return '<span class="ol-chip is-idle">' + escapeHtml(noLabel) + '</span>';
  }

  function outcomeBadge(letter) {
    const outcome = letter.candidate_outcome || (
      letter.not_accepted ? 'not_accepted' :
      letter.signed_back ? 'signed' :
      letter.received ? 'awaiting_signature' : 'pending_hr'
    );
    if (outcome === 'signed') {
      return '<span class="ol-chip is-done">Signed</span>';
    }
    if (outcome === 'not_accepted') {
      return '<span class="ol-chip is-wait">Not accepted</span>';
    }
    if (outcome === 'awaiting_signature') {
      return '<span class="ol-chip is-progress">Awaiting signature</span>';
    }
    return '<span class="ol-chip is-idle">Awaiting HR</span>';
  }

  function linkBadge(letter) {
    const status = letter.link_status || 'unlinked';
    if (status === 'linked') {
      const name = letter.hiring_candidate && letter.hiring_candidate.full_name;
      return (
        '<a class="ol-chip is-linked" href="/hr/hiring/candidates/' +
        letter.hiring_candidate_id + '">' +
          escapeHtml(name ? ('Linked · ' + name) : 'Linked') +
        '</a>'
      );
    }
    if (status === 'manual') {
      return '<span class="ol-chip is-idle">Manual hiring</span>';
    }
    return '<span class="ol-chip is-idle">Not linked</span>';
  }

  const root = document.getElementById('olRoot');
  if (!root) return;

  const state = {
    q: '',
    received: 'all',
    signed: 'all',
    outcome: 'all',
    link_status: 'all',
    page: 1,
    perPage: document.documentElement.getAttribute('data-kynvera-snapshot') === '1' ? 50 : 20,
    pages: 1,
    count: 0,
    connectLetterId: null,
  };

  const listEl = document.getElementById('olList');
  const formModal = document.getElementById('olFormModal');
  const form = document.getElementById('olForm');
  const connectModal = document.getElementById('olConnectModal');
  const previewModal = document.getElementById('olPreviewModal');
  let formLetter = null;
  let previewUrl = null;
  let previewBlob = null;
  let previewFilename = 'document';

  function openBackdrop(el) {
    if (el) el.classList.add('open');
  }
  function closeBackdrop(el) {
    if (el) el.classList.remove('open');
  }

  function renderEmpty() {
    const filtered = !!(state.q || state.received !== 'all' || state.outcome !== 'all' ||
      state.link_status !== 'all' || state.signed !== 'all');
    if (filtered) {
      return '<div class="hh-empty ol-empty"><p>No matching letters of intent.</p></div>';
    }
    return (
      '<div class="hh-empty ol-empty">' +
        '<p>No letters of intent yet.</p>' +
        '<button type="button" class="hh-btn hh-btn-primary" data-ol-add>Add letter of intent</button>' +
      '</div>'
    );
  }

  function renderRow(letter) {
    const role = (letter.role || '').trim();
    const comment = (letter.comments || '').trim();
    const commentHtml = comment
      ? '<div class="hh-row-comment" title="' + escapeHtml(comment) + '">' +
          '<span class="hh-row-comment-label">Comment</span>' +
          '<span class="hh-row-comment-text">' + escapeHtml(comment) + '</span>' +
        '</div>'
      : '';
    const stamps = stampMeta(letter);
    let timeHtml = '';
    if (stamps.created || stamps.updated) {
      const label = stamps.same || !stamps.updated ? ('Added ' + stamps.created) : ('Updated ' + stamps.updated);
      const title = stamps.same || !stamps.updated
        ? (stamps.created + ' (Dubai)')
        : ('Added ' + stamps.created + ' · Updated ' + stamps.updated + ' (Dubai)');
      timeHtml =
        '<time class="ol-row-time" datetime="' + escapeHtml(stamps.iso) + '" title="' + escapeHtml(title) + '">' +
          escapeHtml(label) +
        '</time>';
    }
    const scanBtn = letter.has_scan_file
      ? '<button type="button" class="ol-action is-file" data-ol-view="' + letter.id + '" data-kind="scan" data-filename="' +
        escapeHtml(letter.filename || 'scan') + '">View scan</button>'
      : '<button type="button" class="ol-action" data-ol-upload="' + letter.id + '" data-kind="scan">Upload scan</button>';
    const signedBtn = letter.has_signed_file
      ? '<button type="button" class="ol-action is-file" data-ol-view="' + letter.id + '" data-kind="signed" data-filename="' +
        escapeHtml(letter.signed_filename || 'signed') + '">View signed</button>'
      : (letter.received && !letter.not_accepted
        ? '<button type="button" class="ol-action" data-ol-upload="' + letter.id + '" data-kind="signed">Upload signed</button>'
        : '');
    let connectBtn = '';
    if (letter.prompt_connect) {
      connectBtn = '<button type="button" class="ol-action is-primary" data-ol-connect="' + letter.id + '">Connect to hiring</button>';
    } else if (letter.link_status === 'linked') {
      connectBtn = '<button type="button" class="ol-action" data-ol-unlink="' + letter.id + '">Unlink</button>';
    } else if (letter.link_status === 'manual' || letter.received) {
      connectBtn = '<button type="button" class="ol-action" data-ol-connect="' + letter.id + '">Link hiring</button>';
    }

    return (
      '<article class="hh-row ol-row" data-id="' + letter.id + '" tabindex="0" aria-label="' +
        escapeHtml('View and edit letter of intent for ' + (letter.full_name || 'candidate')) + '">' +
        '<div class="hh-avatar c0" aria-hidden="true">' + escapeHtml(letter.initials || '?') + '</div>' +
        '<div class="hh-row-info">' +
          '<div class="hh-row-name">' + escapeHtml(letter.full_name) +
            (role ? '<span class="hh-row-role-inline">' + escapeHtml(role) + '</span>' : '') +
          '</div>' +
          timeHtml +
          commentHtml +
        '</div>' +
        '<div class="ol-row-aside">' +
          '<div class="hh-row-meta ol-row-flags">' +
            ynBadge(letter.received, 'From HR', 'Not from HR') +
            outcomeBadge(letter) +
            linkBadge(letter) +
          '</div>' +
          '<div class="ol-row-tools">' +
            '<button type="button" class="ol-action" data-ol-edit="' + letter.id + '">Edit</button>' +
            scanBtn +
            signedBtn +
            connectBtn +
            '<button type="button" class="ol-action is-danger" data-ol-delete="' + letter.id + '">Delete</button>' +
          '</div>' +
        '</div>' +
      '</article>'
    );
  }

  function renderPagination() {
    const el = document.getElementById('olPagination');
    if (!el) return;
    if (state.pages <= 1) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML =
      '<button type="button" class="hh-btn hh-btn-secondary hh-btn-sm" data-ol-page="prev"' +
        (state.page <= 1 ? ' disabled' : '') + '>Previous</button>' +
      '<span class="hh-page-label">Page ' + state.page + ' of ' + state.pages + '</span>' +
      '<button type="button" class="hh-btn hh-btn-secondary hh-btn-sm" data-ol-page="next"' +
        (state.page >= state.pages ? ' disabled' : '') + '>Next</button>';
  }

  async function load() {
    if (!listEl) return;
    const qs = new URLSearchParams();
    if (state.q) qs.set('q', state.q);
    if (state.received !== 'all') qs.set('received', state.received);
    if (state.outcome !== 'all') qs.set('outcome', state.outcome);
    else if (state.signed !== 'all') qs.set('signed', state.signed);
    if (state.link_status !== 'all') qs.set('link_status', state.link_status);
    qs.set('page', String(state.page));
    qs.set('per_page', String(state.perPage));
    try {
      const data = await api('/hr/api/hiring/offer-letters?' + qs.toString());
      const letters = data.letters || [];
      state.count = data.count || 0;
      state.pages = data.pages || 1;
      state.page = data.page || 1;
      if (!letters.length) {
        listEl.innerHTML = renderEmpty();
      } else {
        listEl.innerHTML = letters.map(renderRow).join('');
      }
      renderPagination();
    } catch (err) {
      listEl.innerHTML = '<div class="hh-empty">' + escapeHtml(err.message) + '</div>';
    }
  }

  function formValues() {
    const received = !!(form && form.querySelector('input[name="received"]:checked') &&
      form.querySelector('input[name="received"]:checked').value === 'yes');
    let outcome = 'awaiting_signature';
    if (received && form) {
      const checked = form.querySelector('input[name="candidate_outcome"]:checked');
      outcome = (checked && checked.value) || 'awaiting_signature';
    }
    return {
      doc_kind: 'letter_of_intent',
      full_name: (document.getElementById('olFullName') || {}).value || '',
      role: (document.getElementById('olRole') || {}).value || '',
      department: (document.getElementById('olDept') || {}).value || '',
      comments: (document.getElementById('olComments') || {}).value || '',
      received: received,
      candidate_outcome: received ? outcome : 'awaiting_signature',
      signed_back: received && outcome === 'signed',
      not_accepted: received && outcome === 'not_accepted',
    };
  }

  function setFlag(name, yes) {
    if (!form) return;
    form.querySelectorAll('input[name="' + name + '"]').forEach(function (el) {
      el.checked = yes ? el.value === 'yes' : el.value === 'no';
    });
    syncWorkflow();
  }

  function setOutcome(outcome) {
    if (!form) return;
    const value = outcome || 'awaiting_signature';
    form.querySelectorAll('input[name="candidate_outcome"]').forEach(function (el) {
      el.checked = el.value === value;
    });
    syncWorkflow();
  }

  function syncWorkflow() {
    if (!form) return;
    const receivedChecked = form.querySelector('input[name="received"]:checked');
    const received = !!(receivedChecked && receivedChecked.value === 'yes');
    const step2 = document.getElementById('olStep2Card');
    const hint = document.getElementById('olStep2Hint');
    const signedInput = document.getElementById('olSignedFile');
    const signedDrop = document.getElementById('olSignedDrop');
    const signedHint = document.getElementById('olSignedHint');

    form.querySelectorAll('input[name="candidate_outcome"]').forEach(function (el) {
      el.disabled = !received;
    });
    if (signedInput) signedInput.disabled = !received;

    if (!received) {
      setOutcomeQuiet('awaiting_signature');
    }

    const outcomeEl = form.querySelector('input[name="candidate_outcome"]:checked');
    const outcome = (outcomeEl && outcomeEl.value) || 'awaiting_signature';
    const signedSelected = received && outcome === 'signed';
    const declined = received && outcome === 'not_accepted';

    form.querySelectorAll('.ol-status-card').forEach(function (card) {
      const flag = card.getAttribute('data-flag');
      if (flag === 'received') {
        card.classList.toggle('is-yes', received);
        card.classList.remove('is-declined', 'is-locked');
      } else if (flag === 'outcome') {
        card.classList.toggle('is-locked', !received);
        card.classList.toggle('is-yes', signedSelected);
        card.classList.toggle('is-declined', declined);
      }
    });

    if (hint) {
      hint.hidden = received;
      hint.textContent = 'Complete step 1 first — receive the unsigned letter from HR.';
    }
    if (signedDrop) {
      signedDrop.classList.toggle('is-disabled', !received || declined);
      signedDrop.hidden = declined;
    }
    if (signedHint) {
      if (!received) signedHint.textContent = 'Available after the HR letter is received';
      else if (signedSelected) signedHint.textContent = 'PDF, JPG, or PNG · signed copy from the candidate';
      else signedHint.textContent = 'Choose Signed above to attach the returned copy';
    }
  }

  function setOutcomeQuiet(outcome) {
    if (!form) return;
    form.querySelectorAll('input[name="candidate_outcome"]').forEach(function (el) {
      el.checked = el.value === (outcome || 'awaiting_signature');
    });
  }

  function previewType(blob, filename) {
    const mime = ((blob && blob.type) || '').toLowerCase();
    const name = String(filename || '').toLowerCase();
    if (mime.indexOf('image/') === 0 || /\.(jpe?g|png|gif|webp)$/.test(name)) return 'image';
    if (mime.indexOf('pdf') !== -1 || /\.pdf$/.test(name)) return 'pdf';
    return 'other';
  }

  function closePreview() {
    closeBackdrop(previewModal);
    const body = document.getElementById('olPreviewBody');
    if (body) body.innerHTML = '';
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
    previewBlob = null;
    previewFilename = 'document';
  }

  function showPreview(blob, filename, titleText) {
    const title = document.getElementById('olPreviewTitle');
    const body = document.getElementById('olPreviewBody');
    if (title) title.textContent = titleText || 'File preview';
    previewFilename = filename || 'document';
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    let previewed = blob;
    const kind = previewType(blob, filename);
    if (kind === 'pdf' && ((blob && blob.type) || '').toLowerCase().indexOf('pdf') === -1) {
      previewed = new Blob([blob], { type: 'application/pdf' });
    }
    previewBlob = previewed;
    previewUrl = URL.createObjectURL(previewed);
    if (!body) return;
    if (kind === 'image') {
      body.innerHTML = '<img class="ol-preview-img" alt="" src="' + previewUrl + '">';
    } else if (kind === 'pdf') {
      body.innerHTML = '<iframe class="ol-preview-frame" title="Document preview" src="' +
        previewUrl + '#navpanes=0&pagemode=none&view=FitH"></iframe>';
    } else {
      body.innerHTML = '<p class="ol-preview-fallback">Preview isn’t available for this file type. Use Download.</p>';
    }
    openBackdrop(previewModal);
  }

  async function openPreview(id, kind, filename) {
    const body = document.getElementById('olPreviewBody');
    const title = document.getElementById('olPreviewTitle');
    if (title) title.textContent = kind === 'signed' ? 'Signed copy' : 'HR scan';
    if (body) body.innerHTML = '<div class="hh-loading"><div class="hh-spinner"></div>Loading preview…</div>';
    openBackdrop(previewModal);
    try {
      const res = await fetch(
        '/hr/api/hiring/offer-letters/' + id + '/file?kind=' + encodeURIComponent(kind || 'scan'),
        { headers: authHeaders() }
      );
      if (!res.ok) throw new Error('Could not open file');
      const blob = await res.blob();
      showPreview(blob, filename || 'document', kind === 'signed' ? 'Signed copy' : 'HR scan');
    } catch (err) {
      if (body) body.innerHTML = '<p class="ol-preview-fallback">' + escapeHtml(err.message) + '</p>';
      toast(err.message, true);
    }
  }

  function previewFromDrop(kind) {
    const inputId = kind === 'signed' ? 'olSignedFile' : 'olScanFile';
    const input = document.getElementById(inputId);
    if (input && input.files && input.files[0]) {
      showPreview(
        input.files[0],
        input.files[0].name,
        kind === 'signed' ? 'Signed copy' : 'HR scan'
      );
      return;
    }
    if (!formLetter || !formLetter.id) return;
    const has = kind === 'signed' ? formLetter.has_signed_file : formLetter.has_scan_file;
    const name = kind === 'signed'
      ? (formLetter.signed_filename || 'signed')
      : (formLetter.filename || 'scan');
    if (has) openPreview(formLetter.id, kind, name);
  }

  function syncFileDrop(opts) {
    const input = document.getElementById(opts.inputId);
    const label = document.getElementById(opts.labelId);
    const hint = document.getElementById(opts.hintId);
    const viewBtn = document.getElementById(opts.viewBtnId);
    const drop = input && input.closest('.ol-file-drop');
    const file = input && input.files && input.files[0];
    const savedName = opts.savedName || '';
    if (file) {
      if (label) label.textContent = file.name;
      if (hint) hint.textContent = 'Selected · will upload when you save';
      if (drop) drop.classList.add('has-file');
      if (viewBtn) viewBtn.hidden = false;
      return;
    }
    if (savedName) {
      if (label) label.textContent = savedName;
      if (hint) hint.textContent = 'Uploaded · click to replace';
      if (drop) drop.classList.add('has-file');
      if (viewBtn) viewBtn.hidden = false;
      return;
    }
    if (label) label.textContent = opts.emptyText;
    if (hint) hint.textContent = opts.emptyHint;
    if (drop) drop.classList.remove('has-file');
    if (viewBtn) viewBtn.hidden = true;
  }

  function syncScanDrop() {
    syncFileDrop({
      inputId: 'olScanFile',
      labelId: 'olScanName',
      hintId: 'olScanHint',
      viewBtnId: 'olScanView',
      emptyText: 'Add HR scan',
      emptyHint: 'PDF, JPG, or PNG · unsigned copy',
      savedName: formLetter && formLetter.has_scan_file ? (formLetter.filename || 'HR scan') : '',
    });
  }

  function syncSignedDrop() {
    const waitingHint = formLetter && formLetter.received
      ? 'PDF, JPG, or PNG · signed copy from the candidate'
      : 'Available after the HR letter is received';
    syncFileDrop({
      inputId: 'olSignedFile',
      labelId: 'olSignedName',
      hintId: 'olSignedHint',
      viewBtnId: 'olSignedView',
      emptyText: 'Add signed copy',
      emptyHint: waitingHint,
      savedName: formLetter && formLetter.has_signed_file ? (formLetter.signed_filename || 'Signed copy') : '',
    });
  }

  function fillForm(letter) {
    formLetter = letter && letter.id ? letter : null;
    document.getElementById('olFormId').value = letter && letter.id ? String(letter.id) : '';
    document.getElementById('olFullName').value = (letter && letter.full_name) || '';
    document.getElementById('olRole').value = (letter && letter.role) || '';
    document.getElementById('olDept').value = (letter && letter.department) || '';
    document.getElementById('olComments').value = (letter && letter.comments) || '';
    setFlag('received', !!(letter && letter.received));
    const outcome = (letter && letter.candidate_outcome) || (
      letter && letter.not_accepted ? 'not_accepted' :
      letter && letter.signed_back ? 'signed' : 'awaiting_signature'
    );
    setOutcome(outcome === 'pending_hr' ? 'awaiting_signature' : outcome);
    const scanInput = document.getElementById('olScanFile');
    const signedInput = document.getElementById('olSignedFile');
    if (scanInput) scanInput.value = '';
    if (signedInput) signedInput.value = '';
    syncScanDrop();
    syncSignedDrop();
    const title = document.getElementById('olFormTitle');
    const submit = document.getElementById('olFormSubmit');
    if (title) title.textContent = letter && letter.id ? 'Edit letter of intent' : 'Add letter of intent';
    if (submit) submit.textContent = letter && letter.id ? 'Save changes' : 'Save letter of intent';
    const sub = document.getElementById('olFormSub');
    if (sub) {
      sub.textContent = letter && letter.id
        ? 'Update step 1 (HR unsigned letter) or step 2 (signed / not accepted).'
        : 'Step 1: log the unsigned letter from HR. Step 2: mark when the candidate signs — or that it was not accepted.';
    }
    const stampsEl = document.getElementById('olFormStamps');
    if (stampsEl) {
      if (letter && letter.id) {
        const stamps = stampMeta(letter);
        const parts = [];
        if (stamps.created) parts.push('Added ' + stamps.created);
        if (stamps.updated && !stamps.same) parts.push('Updated ' + stamps.updated);
        stampsEl.textContent = parts.length ? (parts.join(' · ') + ' (Dubai)') : '';
        stampsEl.hidden = !parts.length;
      } else {
        stampsEl.textContent = '';
        stampsEl.hidden = true;
      }
    }
  }

  function openForm(letter) {
    fillForm(letter || null);
    openBackdrop(formModal);
    const first = document.getElementById('olFullName');
    if (first) first.focus();
  }

  async function openLetter(id) {
    if (!id) return;
    try {
      const data = await api('/hr/api/hiring/offer-letters/' + id);
      openForm(data.letter);
    } catch (err) {
      toast(err.message, true);
    }
  }

  function closeForm() {
    closeBackdrop(formModal);
    if (form) form.reset();
    document.getElementById('olFormId').value = '';
    formLetter = null;
    setFlag('received', false);
    setOutcome('awaiting_signature');
    syncScanDrop();
    syncSignedDrop();
  }

  async function uploadIfPicked(letterId, inputId, kind) {
    const input = document.getElementById(inputId);
    if (!input || !input.files || !input.files[0]) return;
    const fd = new FormData();
    fd.append('file', input.files[0]);
    await api('/hr/api/hiring/offer-letters/' + letterId + '/' + kind, {
      method: 'POST',
      body: fd,
    });
  }

  async function maybePromptConnect(letter) {
    if (letter && letter.prompt_connect) {
      openConnect(letter);
    }
  }

  function openConnect(letter) {
    state.connectLetterId = letter.id;
    const sub = document.getElementById('olConnectSub');
    if (sub) {
      sub.textContent = (letter.full_name || 'This letter') +
        ' is marked received. Link it to Hiring Docs, create a candidate, or keep hiring work separate.';
    }
    const picker = document.getElementById('olConnectPicker');
    if (picker) picker.hidden = true;
    const search = document.getElementById('olCandidateSearch');
    if (search) search.value = '';
    openBackdrop(connectModal);
  }

  function closeConnect() {
    closeBackdrop(connectModal);
    state.connectLetterId = null;
  }

  async function loadCandidatePicker(q) {
    const list = document.getElementById('olCandidateList');
    if (!list) return;
    list.innerHTML = '<div class="hh-loading"><div class="hh-spinner"></div>Searching…</div>';
    try {
      const qs = new URLSearchParams();
      if (q) qs.set('q', q);
      qs.set('per_page', '15');
      const data = await api('/hr/api/hiring/candidates?' + qs.toString());
      const items = data.candidates || [];
      if (!items.length) {
        list.innerHTML = '<p class="hh-import-hint">No matching candidates.</p>';
        return;
      }
      list.innerHTML = items.map(function (c) {
        return (
          '<button type="button" class="ol-candidate-item" data-candidate-id="' + c.id + '">' +
            '<strong>' + escapeHtml(c.full_name) + '</strong>' +
            '<span>' + escapeHtml(c.role || '—') + '</span>' +
          '</button>'
        );
      }).join('');
    } catch (err) {
      list.innerHTML = '<p class="hh-import-hint">' + escapeHtml(err.message) + '</p>';
    }
  }

  async function pickFile(letterId, kind) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png';
    input.setAttribute('capture', 'environment');
    input.addEventListener('change', async function () {
      if (!input.files || !input.files[0]) return;
      const fd = new FormData();
      fd.append('file', input.files[0]);
      try {
        const data = await api('/hr/api/hiring/offer-letters/' + letterId + '/' + kind, {
          method: 'POST',
          body: fd,
        });
        toast(kind === 'signed' ? 'Signed copy uploaded' : 'Scan uploaded');
        await load();
        await maybePromptConnect(data.letter);
      } catch (err) {
        toast(err.message, true);
      }
    });
    input.click();
  }

  form.addEventListener('change', function (e) {
    const t = e.target;
    if (!t) return;
    if (t.name === 'received' || t.name === 'candidate_outcome') {
      syncWorkflow();
      syncScanDrop();
      syncSignedDrop();
      return;
    }
    if (t.id === 'olScanFile') {
      if (t.files && t.files[0]) setFlag('received', true);
      syncScanDrop();
      syncSignedDrop();
      return;
    }
    if (t.id === 'olSignedFile') {
      if (t.files && t.files[0]) {
        setFlag('received', true);
        setOutcome('signed');
      }
      syncSignedDrop();
    }
  });

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    const values = formValues();
    if (!(values.full_name || '').trim()) {
      toast('Name is required', true);
      return;
    }
    const id = (document.getElementById('olFormId').value || '').trim();
    const submit = document.getElementById('olFormSubmit');
    if (submit) submit.disabled = true;
    try {
      let data;
      if (id) {
        data = await api('/hr/api/hiring/offer-letters/' + id, { method: 'PATCH', json: values });
      } else {
        data = await api('/hr/api/hiring/offer-letters', { method: 'POST', json: values });
      }
      const letterId = (data.letter && data.letter.id) || id;
      await uploadIfPicked(letterId, 'olScanFile', 'scan');
      if (values.candidate_outcome === 'signed') {
        await uploadIfPicked(letterId, 'olSignedFile', 'signed');
      }
      let latest = data.letter;
      if (letterId) {
        const refreshed = await api('/hr/api/hiring/offer-letters/' + letterId);
        latest = refreshed.letter || latest;
      }
      closeForm();
      toast(id ? 'Letter of intent saved' : 'Letter of intent added');
      await load();
      await maybePromptConnect(latest);
    } catch (err) {
      toast(err.message, true);
    } finally {
      if (submit) submit.disabled = false;
    }
  });

  formModal.addEventListener('click', function (e) {
    if (e.target === formModal || e.target.closest('[data-ol-close]')) {
      closeForm();
    }
  });

  const scanViewBtn = document.getElementById('olScanView');
  if (scanViewBtn) {
    scanViewBtn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      previewFromDrop('scan');
    });
  }
  const signedViewBtn = document.getElementById('olSignedView');
  if (signedViewBtn) {
    signedViewBtn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      previewFromDrop('signed');
    });
  }

  if (previewModal) {
    previewModal.addEventListener('click', function (e) {
      if (e.target === previewModal || e.target.closest('[data-ol-preview-close]')) {
        closePreview();
      }
    });
  }
  const previewDownload = document.getElementById('olPreviewDownload');
  if (previewDownload) {
    previewDownload.addEventListener('click', function () {
      if (!previewBlob) return;
      const a = document.createElement('a');
      const url = URL.createObjectURL(previewBlob);
      a.href = url;
      a.download = previewFilename || 'document';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (previewModal && previewModal.classList.contains('open')) {
      closePreview();
      e.preventDefault();
    }
  });

  document.getElementById('olAddBtn').addEventListener('click', function () {
    openForm(null);
  });

  listEl.addEventListener('click', async function (e) {
    const addBtn = e.target.closest('[data-ol-add]');
    if (addBtn) {
      openForm(null);
      return;
    }
    const editBtn = e.target.closest('[data-ol-edit]');
    if (editBtn) {
      openLetter(editBtn.getAttribute('data-ol-edit'));
      return;
    }
    const viewBtn = e.target.closest('[data-ol-view]');
    if (viewBtn) {
      openPreview(
        viewBtn.getAttribute('data-ol-view'),
        viewBtn.getAttribute('data-kind') || 'scan',
        viewBtn.getAttribute('data-filename') || 'document'
      );
      return;
    }
    const uploadBtn = e.target.closest('[data-ol-upload]');
    if (uploadBtn) {
      pickFile(uploadBtn.getAttribute('data-ol-upload'), uploadBtn.getAttribute('data-kind') || 'scan');
      return;
    }
    const connectBtn = e.target.closest('[data-ol-connect]');
    if (connectBtn) {
      const id = connectBtn.getAttribute('data-ol-connect');
      try {
        const data = await api('/hr/api/hiring/offer-letters/' + id);
        openConnect(data.letter);
      } catch (err) {
        toast(err.message, true);
      }
      return;
    }
    const unlinkBtn = e.target.closest('[data-ol-unlink]');
    if (unlinkBtn) {
      try {
        await api('/hr/api/hiring/offer-letters/' + unlinkBtn.getAttribute('data-ol-unlink') + '/unlink', {
          method: 'POST',
          json: {},
        });
        toast('Unlinked from hiring');
        load();
      } catch (err) {
        toast(err.message, true);
      }
      return;
    }
    const delBtn = e.target.closest('[data-ol-delete]');
    if (delBtn) {
      if (!window.confirm('Delete this letter of intent and its files? The hiring candidate is not deleted.')) return;
      try {
        await api('/hr/api/hiring/offer-letters/' + delBtn.getAttribute('data-ol-delete'), { method: 'DELETE' });
        toast('Letter of intent deleted');
        load();
      } catch (err) {
        toast(err.message, true);
      }
      return;
    }
    const row = e.target.closest('.ol-row');
    if (row && !e.target.closest('a, button, input, select, textarea, label')) {
      openLetter(row.getAttribute('data-id'));
    }
  });

  listEl.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (e.target.closest('a, button, input, select, textarea')) return;
    const row = e.target.closest('.ol-row');
    if (!row || e.target !== row) return;
    e.preventDefault();
    openLetter(row.getAttribute('data-id'));
  });

  document.getElementById('olPagination').addEventListener('click', function (e) {
    const btn = e.target.closest('[data-ol-page]');
    if (!btn || btn.disabled) return;
    if (btn.getAttribute('data-ol-page') === 'prev' && state.page > 1) state.page -= 1;
    if (btn.getAttribute('data-ol-page') === 'next' && state.page < state.pages) state.page += 1;
    load();
  });

  let searchTimer = null;
  document.getElementById('olSearch').addEventListener('input', function (e) {
    clearTimeout(searchTimer);
    const value = e.target.value || '';
    searchTimer = setTimeout(function () {
      state.q = value.trim();
      state.page = 1;
      load();
    }, 250);
  });

  document.getElementById('olReceivedFilter').addEventListener('change', function (e) {
    state.received = e.target.value || 'all';
    state.page = 1;
    load();
  });
  document.getElementById('olOutcomeFilter').addEventListener('change', function (e) {
    state.outcome = e.target.value || 'all';
    state.signed = 'all';
    state.page = 1;
    load();
  });
  document.getElementById('olLinkFilter').addEventListener('change', function (e) {
    state.link_status = e.target.value || 'all';
    state.page = 1;
    load();
  });

  document.getElementById('olConnectLater').addEventListener('click', closeConnect);
  connectModal.addEventListener('click', function (e) {
    if (e.target === connectModal) closeConnect();
  });

  document.getElementById('olConnectExisting').addEventListener('click', function () {
    const picker = document.getElementById('olConnectPicker');
    if (picker) picker.hidden = false;
    loadCandidatePicker(document.getElementById('olCandidateSearch').value || '');
    document.getElementById('olCandidateSearch').focus();
  });

  document.getElementById('olConnectCreate').addEventListener('click', async function () {
    if (!state.connectLetterId) return;
    try {
      const data = await api('/hr/api/hiring/offer-letters/' + state.connectLetterId + '/link', {
        method: 'POST',
        json: { create_candidate: true },
      });
      toast('Hiring candidate created');
      closeConnect();
      await load();
      const cid = data.candidate && data.candidate.id;
      if (cid) window.location.href = '/hr/hiring/candidates/' + cid;
    } catch (err) {
      toast(err.message, true);
    }
  });

  document.getElementById('olConnectManual').addEventListener('click', async function () {
    if (!state.connectLetterId) return;
    try {
      await api('/hr/api/hiring/offer-letters/' + state.connectLetterId + '/link', {
        method: 'POST',
        json: { manual: true },
      });
      toast('Marked for manual hiring');
      closeConnect();
      load();
    } catch (err) {
      toast(err.message, true);
    }
  });

  let candTimer = null;
  document.getElementById('olCandidateSearch').addEventListener('input', function (e) {
    clearTimeout(candTimer);
    const value = e.target.value || '';
    candTimer = setTimeout(function () {
      loadCandidatePicker(value.trim());
    }, 220);
  });

  document.getElementById('olCandidateList').addEventListener('click', async function (e) {
    const btn = e.target.closest('[data-candidate-id]');
    if (!btn || !state.connectLetterId) return;
    try {
      await api('/hr/api/hiring/offer-letters/' + state.connectLetterId + '/link', {
        method: 'POST',
        json: { candidate_id: parseInt(btn.getAttribute('data-candidate-id'), 10) },
      });
      toast('Linked to hiring candidate');
      closeConnect();
      load();
    } catch (err) {
      toast(err.message, true);
    }
  });

  load();
})();
