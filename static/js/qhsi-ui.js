/**
 * QHSI shared UI — toast, auth headers, photo zone, success modal
 */
(function (global) {
  'use strict';

  function authHeaders() {
    var t = localStorage.getItem('access_token');
    return t
      ? { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' }
      : { 'Content-Type': 'application/json' };
  }

  function toast(message, isError) {
    var el = document.createElement('div');
    el.className = 'qhsi-toast' + (isError ? ' is-error' : '');
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(function () {
      el.style.opacity = '0';
      el.style.transition = 'opacity 0.25s';
      setTimeout(function () { el.remove(); }, 280);
    }, 3200);
  }

  function showSuccess(title, message, subId, onContinue) {
    var bg = document.getElementById('qhsiSuccessBg');
    if (!bg) return;
    var h = bg.querySelector('[data-qhsi-success-title]');
    var p = bg.querySelector('[data-qhsi-success-msg]');
    var sid = bg.querySelector('[data-qhsi-success-id]');
    if (h) h.textContent = title || 'Submitted';
    if (p) p.textContent = message || '';
    if (sid) {
      sid.textContent = subId || '';
      sid.style.display = subId ? 'block' : 'none';
    }
    bg.classList.add('is-open');
    var btn = bg.querySelector('[data-qhsi-success-continue]');
    if (btn) {
      btn.onclick = function () {
        bg.classList.remove('is-open');
        if (onContinue) onContinue();
      };
    }
  }

  function bindPhotoZone(zoneEl, inputEl, previewEl) {
    if (!zoneEl || !inputEl) return;
    zoneEl.addEventListener('click', function () { inputEl.click(); });
    zoneEl.addEventListener('dragover', function (e) {
      e.preventDefault();
      zoneEl.classList.add('is-dragover');
    });
    zoneEl.addEventListener('dragleave', function () {
      zoneEl.classList.remove('is-dragover');
    });
    zoneEl.addEventListener('drop', function (e) {
      e.preventDefault();
      zoneEl.classList.remove('is-dragover');
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        inputEl.files = e.dataTransfer.files;
        renderPreviews(inputEl, previewEl);
      }
    });
    inputEl.addEventListener('change', function () {
      renderPreviews(inputEl, previewEl);
    });
  }

  function renderPreviews(inputEl, previewEl) {
    if (!previewEl || !inputEl.files) return;
    previewEl.innerHTML = '';
    Array.from(inputEl.files).forEach(function (file) {
      if (!file.type.startsWith('image/')) return;
      var img = document.createElement('img');
      img.alt = '';
      var r = new FileReader();
      r.onload = function () { img.src = r.result; };
      r.readAsDataURL(file);
      previewEl.appendChild(img);
    });
  }

  function readFilesAsDataUrls(fileList) {
    var files = Array.from(fileList || []);
    return Promise.all(
      files.map(function (file) {
        return new Promise(function (resolve, reject) {
          var fr = new FileReader();
          fr.onload = function () { resolve(fr.result); };
          fr.onerror = reject;
          fr.readAsDataURL(file);
        });
      })
    );
  }

  function loadProjectsInto(selectEl, datalistEl) {
    return fetch('/qhsi/api/projects', { headers: authHeaders() })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.projects) return;
        d.projects.forEach(function (p) {
          var label = (p.company ? p.company + ' — ' : '') + p.name;
          if (selectEl) {
            var o = document.createElement('option');
            o.value = p.name;
            o.textContent = label;
            selectEl.appendChild(o);
          }
          if (datalistEl) {
            var opt = document.createElement('option');
            opt.value = p.name;
            datalistEl.appendChild(opt);
          }
        });
      });
  }

  global.QhsiUi = {
    authHeaders: authHeaders,
    toast: toast,
    showSuccess: showSuccess,
    bindPhotoZone: bindPhotoZone,
    readFilesAsDataUrls: readFilesAsDataUrls,
    loadProjectsInto: loadProjectsInto,
  };
})(window);
