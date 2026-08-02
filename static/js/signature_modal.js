/**
 * InjaazSignatureModal — Draw / Type / Upload signature capture.
 * Requires SignaturePad (global) and the signature_modal.html markup.
 *
 * Usage:
 *   InjaazSignatureModal.open({
 *     title: 'Supervisor Signature',
 *     targetInputId: 'supervisorSignatureData',
 *     previewImgId: 'supervisorSigImg',
 *     hintId: 'supervisorSignatureHint',
 *     onApply: function (dataUrl) {}
 *   });
 *   InjaazSignatureModal.setSavedSignature(dataUrlOrNull);
 *   InjaazSignatureModal.applyToField(inputId, imgId, dataUrl, hintId);
 *   InjaazSignatureModal.clearField(inputId, imgId, hintId);
 */
(function (global) {
  'use strict';

  var state = {
    tab: 'draw',
    targetInputId: null,
    previewImgId: null,
    hintId: null,
    onApply: null,
    requireConfirm: false,
    pad: null,
    uploadDataUrl: null,
    savedSignature: null,
    ready: false
  };

  function $(id) {
    return document.getElementById(id);
  }

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }

  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function ensureReady() {
    if (state.ready) return true;
    var bg = $('sigmBg');
    if (!bg) return false;
    bindOnce();
    state.ready = true;
    return true;
  }

  function bindOnce() {
    qsa('[data-sigm-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        setTab(btn.getAttribute('data-sigm-tab'));
      });
    });

    $('sigmClose').addEventListener('click', close);
    $('sigmCancel').addEventListener('click', close);
    $('sigmAccept').addEventListener('click', accept);
    $('sigmClearPane').addEventListener('click', clearActivePane);
    $('sigmUseSaved').addEventListener('click', applySaved);

    var typeInput = $('sigmTypeInput');
    typeInput.addEventListener('input', function () {
      renderTypePreview(typeInput.value);
    });

    var drop = $('sigmDrop');
    var fileInput = $('sigmFileInput');
    $('sigmSelectBtn').addEventListener('click', function (e) {
      e.stopPropagation();
      fileInput.click();
    });
    drop.addEventListener('click', function (e) {
      if (e.target.id === 'sigmSelectBtn') return;
      fileInput.click();
    });
    drop.addEventListener('dragover', function (e) {
      e.preventDefault();
      drop.classList.add('is-dragover');
    });
    drop.addEventListener('dragleave', function () {
      drop.classList.remove('is-dragover');
    });
    drop.addEventListener('drop', function (e) {
      e.preventDefault();
      drop.classList.remove('is-dragover');
      var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) handleUploadFile(file);
    });
    fileInput.addEventListener('change', function () {
      var file = fileInput.files && fileInput.files[0];
      if (file) handleUploadFile(file);
    });

    bgEscClose();
  }

  function bgEscClose() {
    var bg = $('sigmBg');
    bg.addEventListener('click', function (e) {
      if (e.target === bg) close();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && bg.classList.contains('is-open')) close();
    });
  }

  function setTab(tab) {
    state.tab = tab || 'draw';
    qsa('[data-sigm-tab]').forEach(function (btn) {
      var on = btn.getAttribute('data-sigm-tab') === state.tab;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    qsa('[data-sigm-pane]').forEach(function (pane) {
      pane.classList.toggle('is-active', pane.getAttribute('data-sigm-pane') === state.tab);
    });
    if (state.tab === 'draw') {
      requestAnimationFrame(function () {
        resizePad();
      });
    }
  }

  function initPad() {
    var canvas = $('sigmDrawCanvas');
    if (!canvas || typeof SignaturePad === 'undefined') return;
    if (state.pad) {
      state.pad.clear();
      resizePad();
      return;
    }
    if (typeof enhanceTouchEvents === 'function') {
      try { enhanceTouchEvents(canvas); } catch (e) { /* ignore */ }
    }
    state.pad = new SignaturePad(canvas, {
      backgroundColor: 'rgba(0,0,0,0)',
      penColor: 'rgb(0, 0, 0)',
      minWidth: 1,
      maxWidth: 2.8,
      throttle: 16
    });
    resizePad();
    window.addEventListener('resize', resizePad);
  }

  function resizePad() {
    var canvas = $('sigmDrawCanvas');
    var pad = state.pad;
    if (!canvas || !pad) return;
    var wrap = canvas.parentElement;
    if (!wrap || wrap.offsetParent === null) return;
    var ratio = Math.max(window.devicePixelRatio || 1, 1);
    var width = wrap.clientWidth;
    var height = wrap.clientHeight;
    if (!width || !height) return;
    var data = pad.isEmpty() ? null : pad.toDataURL('image/png');
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    var ctx = canvas.getContext('2d');
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(ratio, ratio);
    pad.clear();
    if (data) pad.fromDataURL(data);
  }

  function renderTypePreview(text) {
    var preview = $('sigmTypePreview');
    var span = preview.querySelector('span');
    var t = (text || '').trim();
    if (!t) {
      preview.classList.add('is-empty');
      span.textContent = 'Preview appears here';
      return;
    }
    preview.classList.remove('is-empty');
    span.textContent = t;
  }

  function typeToDataUrl(text) {
    var t = (text || '').trim();
    if (!t) return null;
    var canvas = document.createElement('canvas');
    canvas.width = 900;
    canvas.height = 260;
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#1a1a1a';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    var fontSize = 92;
    ctx.font = '600 ' + fontSize + 'px "Caveat", "Segoe Script", cursive';
    while (fontSize > 36 && ctx.measureText(t).width > canvas.width - 56) {
      fontSize -= 2;
      ctx.font = '600 ' + fontSize + 'px "Caveat", "Segoe Script", cursive';
    }
    ctx.fillText(t, canvas.width / 2, canvas.height / 2 + 6);
    return canvas.toDataURL('image/png');
  }

  function ensureHandwritingFont() {
    if (!document.fonts || !document.fonts.load) return Promise.resolve();
    return document.fonts.load('600 92px "Caveat"').catch(function () { return null; });
  }

  function handleUploadFile(file) {
    if (!file || !file.type || file.type.indexOf('image/') !== 0) {
      alert('Please select an image file.');
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      var raw = reader.result;
      normalizeImageDataUrl(raw, function (url) {
        state.uploadDataUrl = url;
        var img = $('sigmUploadPreview');
        var drop = $('sigmDrop');
        img.src = url;
        drop.classList.add('has-file');
      });
    };
    reader.readAsDataURL(file);
  }

  function normalizeImageDataUrl(src, cb) {
    var img = new Image();
    img.onload = function () {
      var maxW = 900;
      var maxH = 360;
      var w = img.naturalWidth || img.width;
      var h = img.naturalHeight || img.height;
      var scale = Math.min(1, maxW / w, maxH / h);
      var cw = Math.max(1, Math.round(w * scale));
      var ch = Math.max(1, Math.round(h * scale));
      var canvas = document.createElement('canvas');
      canvas.width = cw;
      canvas.height = ch;
      var ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, cw, ch);
      ctx.drawImage(img, 0, 0, cw, ch);
      // Knock out flat paper / preview backgrounds so ink sits transparent
      try {
        var id = ctx.getImageData(0, 0, cw, ch);
        var d = id.data;
        for (var i = 0; i < d.length; i += 4) {
          var r = d[i], g = d[i + 1], b = d[i + 2];
          var mx = Math.max(r, g, b), mn = Math.min(r, g, b);
          if (mn >= 248 || (mn >= 222 && (mx - mn) <= 16)) {
            d[i + 3] = 0;
          }
        }
        ctx.putImageData(id, 0, 0);
      } catch (e) { /* ignore CORS / security errors */ }
      cb(canvas.toDataURL('image/png'));
    };
    img.onerror = function () {
      cb(src);
    };
    img.src = src;
  }

  function clearActivePane() {
    if (state.tab === 'draw' && state.pad) {
      state.pad.clear();
    } else if (state.tab === 'type') {
      $('sigmTypeInput').value = '';
      renderTypePreview('');
    } else if (state.tab === 'upload') {
      state.uploadDataUrl = null;
      $('sigmFileInput').value = '';
      $('sigmUploadPreview').removeAttribute('src');
      $('sigmDrop').classList.remove('has-file');
    }
  }

  function resetPanes() {
    if (state.pad) state.pad.clear();
    $('sigmTypeInput').value = '';
    renderTypePreview('');
    state.uploadDataUrl = null;
    $('sigmFileInput').value = '';
    $('sigmUploadPreview').removeAttribute('src');
    $('sigmDrop').classList.remove('has-file');
    setTab('draw');
  }

  function updateSavedButton() {
    var btn = $('sigmUseSaved');
    if (!btn) return;
    if (state.savedSignature) {
      btn.disabled = false;
      btn.title = 'Apply your saved profile signature';
    } else {
      btn.disabled = true;
      btn.title = 'No saved signature. Add one in Profile.';
    }
  }

  function applySaved() {
    if (!state.savedSignature) {
      alert('No saved signature found. Go to your Profile to save a default signature.');
      return;
    }
    resolveDataUrl(state.savedSignature).then(function (url) {
      if (!url) {
        alert('Failed to load saved signature.');
        return;
      }
      finish(url);
    });
  }

  function resolveDataUrl(src) {
    if (!src) return Promise.resolve(null);
    if (String(src).indexOf('data:image') === 0) return Promise.resolve(src);
    return fetch(src)
      .then(function (r) { return r.ok ? r.blob() : null; })
      .then(function (blob) {
        if (!blob) return null;
        return new Promise(function (resolve) {
          var reader = new FileReader();
          reader.onload = function () { resolve(reader.result); };
          reader.onerror = function () { resolve(null); };
          reader.readAsDataURL(blob);
        });
      })
      .catch(function () { return null; });
  }

  function collectDataUrl() {
    if (state.tab === 'draw') {
      if (!state.pad || state.pad.isEmpty()) return null;
      return state.pad.toDataURL('image/png');
    }
    if (state.tab === 'type') {
      return typeToDataUrl($('sigmTypeInput').value);
    }
    if (state.tab === 'upload') {
      return state.uploadDataUrl || null;
    }
    return null;
  }

  function applyToField(inputId, previewImgId, dataUrl, hintId) {
    var input = $(inputId);
    var img = previewImgId ? $(previewImgId) : null;
    var preview = img ? img.closest('.sig-field-preview') : null;
    if (input) input.value = dataUrl || '';
    if (img) {
      if (dataUrl) {
        img.src = dataUrl;
        img.style.display = 'block';
        if (preview) preview.classList.add('has-sig');
      } else {
        img.removeAttribute('src');
        img.style.display = 'none';
        if (preview) preview.classList.remove('has-sig');
      }
    }
    if (hintId) {
      var hint = $(hintId);
      if (hint) hint.style.display = dataUrl ? '' : 'none';
    }
  }

  function clearField(inputId, previewImgId, hintId) {
    applyToField(inputId, previewImgId, '', hintId);
  }

  function finish(dataUrl) {
    if (!dataUrl) {
      alert('Please provide a signature before accepting.');
      return;
    }
    if (state.requireConfirm) {
      var chk = $('sigmConfirmCheck');
      if (!chk || !chk.checked) {
        alert('Please confirm the checkbox before signing.');
        return;
      }
    }
    applyToField(state.targetInputId, state.previewImgId, dataUrl, state.hintId);
    if (typeof state.onApply === 'function') {
      try { state.onApply(dataUrl); } catch (e) { console.warn(e); }
    }
    close();
  }

  function accept() {
    if (state.tab === 'type') {
      ensureHandwritingFont().then(function () {
        finish(collectDataUrl());
      });
      return;
    }
    finish(collectDataUrl());
  }

  function open(opts) {
    opts = opts || {};
    if (!ensureReady()) {
      console.error('Signature modal markup not found');
      return;
    }
    state.targetInputId = opts.targetInputId || null;
    state.previewImgId = opts.previewImgId || null;
    state.hintId = opts.hintId || null;
    state.onApply = opts.onApply || null;
    state.requireConfirm = !!(opts.confirmLabel || opts.requireConfirm);
    $('sigmTitle').textContent = opts.title || 'Signature';
    var confirmWrap = $('sigmConfirmWrap');
    var confirmText = $('sigmConfirmText');
    var confirmChk = $('sigmConfirmCheck');
    if (confirmWrap) {
      if (state.requireConfirm) {
        confirmWrap.hidden = false;
        if (confirmText) {
          confirmText.textContent = opts.confirmLabel ||
            'I confirm the details shown on this document.';
        }
        if (confirmChk) confirmChk.checked = false;
      } else {
        confirmWrap.hidden = true;
        if (confirmChk) confirmChk.checked = false;
      }
    }
    resetPanes();
    initPad();
    updateSavedButton();
    ensureHandwritingFont();
    var bg = $('sigmBg');
    bg.classList.add('is-open');
    bg.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    requestAnimationFrame(function () {
      resizePad();
    });
  }

  function close() {
    var bg = $('sigmBg');
    if (!bg) return;
    bg.classList.remove('is-open');
    bg.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  function setSavedSignature(url) {
    state.savedSignature = url || null;
    if (state.ready) updateSavedButton();
  }

  global.InjaazSignatureModal = {
    open: open,
    close: close,
    setSavedSignature: setSavedSignature,
    applyToField: applyToField,
    clearField: clearField,
    resolveDataUrl: resolveDataUrl
  };
})(window);
