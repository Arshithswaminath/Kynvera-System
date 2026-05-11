/**
 * HR sign pages: render submitted PDF with PDF.js (scrollable pages, no browser PDF UI).
 * Expects: #rspPreviewScroll, #rspPreviewLoading, #rspPreviewPdfHost, #rspPreviewZoomWrap, #rspPreviewFrame, #rspPreviewErr
 */
(function (global) {
  'use strict';

  var PDFJS_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
  var PDFJS_WORKER = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

  var blobUrl = null;

  function revokeBlob() {
    if (blobUrl) {
      try {
        URL.revokeObjectURL(blobUrl);
      } catch (e) {}
      blobUrl = null;
    }
  }

  function clearDomPreview() {
    revokeBlob();
    var host = document.getElementById('rspPreviewPdfHost');
    if (host) {
      host.innerHTML = '';
      host.setAttribute('hidden', '');
    }
    var fr = document.getElementById('rspPreviewFrame');
    if (fr) {
      fr.removeAttribute('src');
      fr.src = 'about:blank';
      fr.style.display = 'none';
    }
    var zw = document.getElementById('rspPreviewZoomWrap');
    if (zw) {
      zw.style.display = 'none';
      zw.style.zoom = '';
    }
  }

  function ensurePdfJsLoaded() {
    if (global.pdfjsLib && typeof global.pdfjsLib.getDocument === 'function') {
      return Promise.resolve(true);
    }
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-hr-sign-pdfjs="1"]');
      if (existing) {
        existing.addEventListener('load', function () {
          resolve(!!(global.pdfjsLib && global.pdfjsLib.getDocument));
        });
        existing.addEventListener('error', function () {
          reject(new Error('pdf.js failed'));
        });
        return;
      }
      var s = document.createElement('script');
      s.src = PDFJS_CDN;
      s.crossOrigin = 'anonymous';
      s.setAttribute('data-hr-sign-pdfjs', '1');
      s.onload = function () {
        resolve(!!(global.pdfjsLib && global.pdfjsLib.getDocument));
      };
      s.onerror = function () {
        reject(new Error('pdf.js load failed'));
      };
      document.head.appendChild(s);
    });
  }

  function applyIframeFallbackZoom(zoomWrap) {
    if (!zoomWrap) return;
    if (typeof global.matchMedia === 'function' && global.matchMedia('(max-width: 960px)').matches) {
      zoomWrap.style.zoom = '1.08';
    } else {
      zoomWrap.style.zoom = '1.2';
    }
  }

  async function fetchPdfBuffer(submissionId, token) {
    var pdfPath = '/hr/download-pdf/' + encodeURIComponent(submissionId) + '?inline=1';
    var pdfRes = await fetch(pdfPath, { credentials: 'include', cache: 'no-store' });
    if (!pdfRes.ok) {
      if (!token) throw new Error('Sign in required to load preview.');
      pdfRes = await fetch(pdfPath, {
        headers: { Authorization: 'Bearer ' + token },
        cache: 'no-store',
      });
    }
    if (!pdfRes.ok) {
      var t = await pdfRes.text().catch(function () {
        return '';
      });
      throw new Error(t || 'Preview not available');
    }
    var blob = await pdfRes.blob();
    if (!blob || blob.size < 80) throw new Error('Empty PDF');
    return blob.arrayBuffer();
  }

  /**
   * @returns {Promise<boolean|null>} true = rendered pages, false = skip to iframe, null = stale (abort load)
   */
  async function tryRenderPdfJs(arrayBuffer, isStale) {
    var loaded = await ensurePdfJsLoaded();
    if (!loaded || !global.pdfjsLib || typeof global.pdfjsLib.getDocument !== 'function') {
      return false;
    }

    var scrollEl = document.getElementById('rspPreviewScroll');
    var host = document.getElementById('rspPreviewPdfHost');
    if (!host || !scrollEl) return false;

    global.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
    var pdf = await global.pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    if (isStale()) return null;

    /* Fit PDF page width to fraction of preview column (slightly roomy vs compact) */
    var FIT_FRAC = 0.9;
    var availW = Math.max(248, scrollEl.clientWidth - 16) * FIT_FRAC;
    host.innerHTML = '';
    var root = document.createElement('div');
    root.className = 'rsp-pdf-pages';

    for (var p = 1; p <= pdf.numPages; p++) {
      if (isStale()) return null;
      var page = await pdf.getPage(p);
      var base = page.getViewport({ scale: 1 });
      var scale = Math.min(3.45, availW / base.width);
      var viewport = page.getViewport({ scale: scale });
      var canvas = document.createElement('canvas');
      var ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('Canvas unsupported');
      canvas.width = viewport.width;
      canvas.height = viewport.height;

      await page.render({ canvasContext: ctx, viewport: viewport }).promise;

      var wrap = document.createElement('div');
      wrap.className = 'rsp-pdf-page';
      wrap.appendChild(canvas);
      root.appendChild(wrap);
    }

    if (isStale()) return null;
    host.appendChild(root);
    host.removeAttribute('hidden');

    var zoomWrap = document.getElementById('rspPreviewZoomWrap');
    var frame = document.getElementById('rspPreviewFrame');
    if (zoomWrap) zoomWrap.style.display = 'none';
    if (frame) frame.style.display = 'none';

    return true;
  }

  function iframeFallback(arrayBuffer, isStale) {
    var loading = document.getElementById('rspPreviewLoading');
    var zoomWrap = document.getElementById('rspPreviewZoomWrap');
    var frame = document.getElementById('rspPreviewFrame');
    var host = document.getElementById('rspPreviewPdfHost');

    revokeBlob();
    blobUrl = URL.createObjectURL(new Blob([arrayBuffer], { type: 'application/pdf' }));
    if (isStale()) {
      revokeBlob();
      return;
    }

    if (host) {
      host.innerHTML = '';
      host.setAttribute('hidden', '');
    }
    if (zoomWrap) {
      zoomWrap.style.display = 'block';
      zoomWrap.style.zoom = '';
      applyIframeFallbackZoom(zoomWrap);
    }
    if (frame) {
      frame.src = blobUrl + '#toolbar=0&navpanes=0';
      frame.style.display = 'block';
      frame.onload = function () {
        if (!isStale() && loading) loading.style.display = 'none';
      };
      setTimeout(function () {
        if (!isStale() && loading) loading.style.display = 'none';
      }, 800);
    }
  }

  global.HrSignPdfPreview = {
    revokeBlob: revokeBlob,
    clearDomPreview: clearDomPreview,
    abort: function () {
      revokeBlob();
      clearDomPreview();
    },
    /**
     * @param {{
     *   submissionId: string,
     *   token: string | null,
     *   gen: number,
     *   isStale: (gen: number) => boolean,
     *   errMessage?: string
     * }} opts
     */
    load: async function load(opts) {
      var submissionId = opts.submissionId;
      var token = opts.token;
      var gen = opts.gen;
      function isStale() {
        return opts.isStale(gen);
      }

      var loading = document.getElementById('rspPreviewLoading');
      var errEl = document.getElementById('rspPreviewErr');

      if (loading) loading.style.display = 'block';
      if (errEl) {
        errEl.style.display = 'none';
        errEl.textContent = '';
      }

      revokeBlob();
      var zw0 = document.getElementById('rspPreviewZoomWrap');
      if (zw0) zw0.style.zoom = '';
      var host0 = document.getElementById('rspPreviewPdfHost');
      if (host0) {
        host0.innerHTML = '';
        host0.setAttribute('hidden', '');
      }
      var fr0 = document.getElementById('rspPreviewFrame');
      if (fr0) {
        fr0.removeAttribute('src');
        fr0.src = 'about:blank';
        fr0.style.display = 'none';
      }
      if (zw0) zw0.style.display = 'none';

      try {
        var buf = await fetchPdfBuffer(submissionId, token);
        if (isStale()) return;

        var rendered = false;
        try {
          var r = await tryRenderPdfJs(buf, isStale);
          if (r === null) return;
          rendered = r === true;
        } catch (e) {
          console.warn('HrSignPdfPreview: PDF.js failed', e);
        }

        if (isStale()) return;

        if (rendered) {
          if (loading) loading.style.display = 'none';
          return;
        }

        iframeFallback(buf, isStale);
      } catch (e) {
        if (!isStale()) {
          if (loading) loading.style.display = 'none';
          if (errEl) {
            errEl.style.display = 'block';
            errEl.textContent =
              opts.errMessage ||
              'Could not load the submitted form as PDF.';
          }
        }
      }
    },
  };
})(typeof window !== 'undefined' ? window : this);
