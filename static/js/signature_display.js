(function (global) {
  'use strict';

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
          if (rgbIsSignatureSheetBackground(d[i], d[i + 1], d[i + 2])) {
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

  var IMG_STYLE =
    'max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;object-position:center;display:block;margin:0 auto;background:transparent;mix-blend-mode:multiply;';

  function getCanvasCssSize(canvas) {
    if (!canvas) return { width: 480, height: 160 };
    var styles = global.getComputedStyle(canvas);
    var width = parseInt(styles.width, 10);
    var height = parseInt(styles.height, 10);
    if (!width || width <= 0) width = canvas.offsetWidth || 480;
    if (!height || height <= 0) height = canvas.offsetHeight || 160;
    return { width: width, height: height };
  }

  function trimSignatureBounds(dataUrl) {
    return new Promise(function (resolve) {
      if (!dataUrl) {
        resolve(dataUrl);
        return;
      }
      var img = new Image();
      img.onload = function () {
        try {
          var w = img.width;
          var h = img.height;
          if (!w || !h) {
            resolve(dataUrl);
            return;
          }
          var c = document.createElement('canvas');
          c.width = w;
          c.height = h;
          var ctx = c.getContext('2d');
          ctx.drawImage(img, 0, 0);
          var imgData = ctx.getImageData(0, 0, w, h);
          var d = imgData.data;
          var minX = w;
          var minY = h;
          var maxX = 0;
          var maxY = 0;
          for (var y = 0; y < h; y++) {
            for (var x = 0; x < w; x++) {
              var i = (y * w + x) * 4;
              var alpha = d[i + 3];
              var r = d[i];
              var g = d[i + 1];
              var b = d[i + 2];
              if (alpha < 16) continue;
              if (rgbIsSignatureSheetBackground(r, g, b)) continue;
              if (x < minX) minX = x;
              if (y < minY) minY = y;
              if (x > maxX) maxX = x;
              if (y > maxY) maxY = y;
            }
          }
          if (maxX <= minX || maxY <= minY) {
            resolve(dataUrl);
            return;
          }
          var pad = 6;
          minX = Math.max(0, minX - pad);
          minY = Math.max(0, minY - pad);
          maxX = Math.min(w - 1, maxX + pad);
          maxY = Math.min(h - 1, maxY + pad);
          var cropW = maxX - minX + 1;
          var cropH = maxY - minY + 1;
          var out = document.createElement('canvas');
          out.width = cropW;
          out.height = cropH;
          out.getContext('2d').drawImage(c, minX, minY, cropW, cropH, 0, 0, cropW, cropH);
          resolve(out.toDataURL('image/png'));
        } catch (_) {
          resolve(dataUrl);
        }
      };
      img.onerror = function () {
        resolve(dataUrl);
      };
      img.src = dataUrl;
    });
  }

  function fitSignatureDataUrl(dataUrl, targetWidth, targetHeight, options) {
    options = options || {};
    var fillRatio = options.fillRatio != null ? options.fillRatio : 0.92;
    return new Promise(function (resolve) {
      if (!dataUrl) {
        resolve(dataUrl);
        return;
      }
      var img = new Image();
      img.onload = function () {
        try {
          var cw = Math.max(1, targetWidth);
          var ch = Math.max(1, targetHeight);
          var maxW = cw * fillRatio;
          var maxH = ch * fillRatio;
          var iw = img.naturalWidth || img.width;
          var ih = img.naturalHeight || img.height;
          if (!iw || !ih) {
            resolve(dataUrl);
            return;
          }
          var imgAspect = iw / ih;
          var drawW;
          var drawH;
          if (imgAspect >= maxW / maxH) {
            drawW = maxW;
            drawH = maxW / imgAspect;
          } else {
            drawH = maxH;
            drawW = maxH * imgAspect;
          }
          var drawX = (cw - drawW) / 2;
          var drawY = (ch - drawH) / 2;
          var tempCanvas = document.createElement('canvas');
          tempCanvas.width = Math.round(cw);
          tempCanvas.height = Math.round(ch);
          var tempCtx = tempCanvas.getContext('2d');
          tempCtx.clearRect(0, 0, cw, ch);
          tempCtx.drawImage(img, drawX, drawY, drawW, drawH);
          resolve(tempCanvas.toDataURL('image/png'));
        } catch (_) {
          resolve(dataUrl);
        }
      };
      img.onerror = function () {
        resolve(dataUrl);
      };
      img.src = dataUrl;
    });
  }

  function prepareSignatureForCanvas(dataUrl, targetWidth, targetHeight, options) {
    return new Promise(function (resolve) {
      stripSignaturePaperBackground(dataUrl, function (stripped) {
        trimSignatureBounds(stripped).then(function (trimmed) {
          fitSignatureDataUrl(trimmed, targetWidth, targetHeight, options).then(resolve);
        });
      });
    });
  }

  function applySignatureToPad(pad, canvas, dataUrl, options) {
    if (!pad || !dataUrl) return Promise.resolve(dataUrl);
    var size = getCanvasCssSize(canvas || pad.canvas);
    return prepareSignatureForCanvas(dataUrl, size.width, size.height, options).then(function (fitted) {
      pad.clear();
      pad.fromDataURL(fitted, {
        ratio: 1,
        width: Math.round(size.width),
        height: Math.round(size.height),
      });
      return fitted;
    });
  }

  function applySignatureImageStyles(img) {
    if (!img) return;
    img.setAttribute('data-signature-display', '1');
    img.style.cssText = IMG_STYLE;
  }

  function mountSignatureImage(container, signatureData, altText, onReady) {
    if (!container) return;
    container.innerHTML = '';
    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.justifyContent = 'center';

    if (!signatureData) {
      container.innerHTML = '<span style="color:#9ca3af;">Signature not available</span>';
      if (onReady) onReady(false);
      return;
    }

    var sigUrl = signatureData;
    if (typeof sigUrl === 'object' && sigUrl !== null && sigUrl.url) {
      sigUrl = sigUrl.url;
    }
    if (typeof sigUrl === 'string' && sigUrl.startsWith('/') && global.location) {
      sigUrl = global.location.origin + sigUrl;
    }

    if (
      typeof sigUrl !== 'string' ||
      !(sigUrl.startsWith('data:') || sigUrl.startsWith('http://') || sigUrl.startsWith('https://'))
    ) {
      container.innerHTML = '<span style="color:#9ca3af;">Signature not available</span>';
      if (onReady) onReady(false);
      return;
    }

    function appendImg(src) {
      var img = document.createElement('img');
      img.src = src;
      img.alt = altText || 'Signature';
      applySignatureImageStyles(img);
      img.onerror = function () {
        container.innerHTML = '<span style="color:#dc3545;">Failed to load signature</span>';
        if (onReady) onReady(false);
      };
      img.onload = function () {
        if (onReady) onReady(true);
      };
      container.appendChild(img);
    }

    stripSignaturePaperBackground(sigUrl, appendImg);
  }

  global.InjaazSignatureDisplay = {
    stripSignaturePaperBackground: stripSignaturePaperBackground,
    applySignatureImageStyles: applySignatureImageStyles,
    mountSignatureImage: mountSignatureImage,
    getCanvasCssSize: getCanvasCssSize,
    trimSignatureBounds: trimSignatureBounds,
    fitSignatureDataUrl: fitSignatureDataUrl,
    prepareSignatureForCanvas: prepareSignatureForCanvas,
    applySignatureToPad: applySignatureToPad,
  };

  function processExistingSignatureImages(root) {
    var scope = root || document;
    var imgs = scope.querySelectorAll(
      '.signoff-sig-frame img, div[id*="SignatureReadOnly"] img, #omOwnSignatureReadOnly img, .sig-box img, .signature-preview, .admin-profile-sig-preview'
    );
    imgs.forEach(function (img) {
      applySignatureImageStyles(img);
      var src = img.getAttribute('src') || '';
      if (src.indexOf('data:image/png') === 0) {
        stripSignaturePaperBackground(src, function (out) {
          if (out && out !== src) img.src = out;
        });
      }
    });
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
      processExistingSignatureImages();
    });
    global.InjaazSignatureDisplay.processExistingSignatureImages = processExistingSignatureImages;
  }
})(typeof window !== 'undefined' ? window : globalThis);
