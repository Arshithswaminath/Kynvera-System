/**
 * Mobile Utilities - Enhanced mobile browser support
 * Handles downloads, network detection, touch events, and mobile-specific features
 */
(function (global) {
  'use strict';

  if (global.__injaazMobileUtilsLoaded) return;
  global.__injaazMobileUtilsLoaded = true;

  // Detect mobile device
  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  const isAndroid = /Android/.test(navigator.userAgent);

  // Detect touch capability
  const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

  /**
   * Reliable mobile download handler
   * Works better on mobile browsers than programmatic clicks
   */
  function downloadFile(url, filename, options = {}) {
    const {
      forceDownload = true,
      openInNewTab = true,
      retryOnFail = true,
      maxRetries = 2
    } = options;

    // For mobile browsers, use a more reliable approach
    if (isMobile || isTouchDevice) {
      const link = document.createElement('a');
      link.href = url;
      link.download = filename || '';
      link.target = '_blank';
      link.rel = 'noopener noreferrer';

      link.style.position = 'fixed';
      link.style.top = '-9999px';
      link.style.left = '-9999px';
      link.style.opacity = '0';
      link.style.pointerEvents = 'none';
      document.body.appendChild(link);

      try {
        setTimeout(() => {
          link.click();
          setTimeout(() => {
            if (link.parentNode) {
              link.parentNode.removeChild(link);
            }
          }, 1000);
        }, 100);
      } catch (e) {
        console.warn('Programmatic download failed, opening in new tab:', e);
        if (openInNewTab) {
          window.open(url, '_blank');
        }
        if (link.parentNode) {
          link.parentNode.removeChild(link);
        }
      }
    } else {
      const link = document.createElement('a');
      link.href = url;
      link.download = filename || '';
      link.style.display = 'none';
      document.body.appendChild(link);
      link.click();
      setTimeout(() => document.body.removeChild(link), 100);
    }
  }

  /**
   * Enhanced download with retry logic for mobile
   */
  async function downloadWithRetry(url, filename, retries = 2) {
    return new Promise((resolve) => {
      let attempt = 0;

      const tryDownload = () => {
        attempt++;

        if (attempt > 1 && isMobile) {
          setTimeout(() => {
            downloadFile(url, filename, { forceDownload: true, openInNewTab: true });
            if (attempt >= retries) {
              resolve();
            } else {
              setTimeout(tryDownload, 1000);
            }
          }, 500);
        } else {
          downloadFile(url, filename, { forceDownload: true, openInNewTab: true });
          if (attempt >= retries) {
            resolve();
          } else {
            setTimeout(tryDownload, 1000);
          }
        }
      };

      tryDownload();
    });
  }

  /**
   * Network status detection and handling
   */
  class NetworkMonitor {
    constructor() {
      this.isOnline = navigator.onLine;
      this.listeners = [];

      window.addEventListener('online', () => {
        this.isOnline = true;
        this.notifyListeners('online');
      });

      window.addEventListener('offline', () => {
        this.isOnline = false;
        this.notifyListeners('offline');
      });

      if (isMobile) {
        setInterval(() => this.checkConnectivity(), 30000);
      }
    }

    checkConnectivity() {
      fetch('/health', { method: 'HEAD', cache: 'no-cache' })
        .then(() => {
          if (!this.isOnline) {
            this.isOnline = true;
            this.notifyListeners('online');
          }
        })
        .catch(() => {
          if (this.isOnline) {
            this.isOnline = false;
            this.notifyListeners('offline');
          }
        });
    }

    onStatusChange(callback) {
      this.listeners.push(callback);
    }

    notifyListeners(status) {
      this.listeners.forEach(cb => cb(status));
    }

    getStatus() {
      return this.isOnline ? 'online' : 'offline';
    }
  }

  const networkMonitor = new NetworkMonitor();

  function preventIOSZoom() {
    if (isIOS) {
      const viewport = document.querySelector('meta[name="viewport"]');
      if (viewport) {
        viewport.setAttribute('content', 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no');
      }

      const style = document.createElement('style');
      style.textContent = `
      input[type="text"],
      input[type="email"],
      input[type="tel"],
      input[type="number"],
      input[type="date"],
      input[type="password"],
      select,
      textarea {
        font-size: 16px !important;
      }
    `;
      document.head.appendChild(style);
    }
  }

  function enhanceTouchEvents(element) {
    if (!isTouchDevice || !element) return;

    element.addEventListener('touchstart', (e) => {
      e.preventDefault();
    }, { passive: false });

    element.addEventListener('touchmove', (e) => {
      e.preventDefault();
    }, { passive: false });

    element.addEventListener('touchend', (e) => {
      e.preventDefault();
    }, { passive: false });
  }

  function setupMobileFileInput(inputElement, onFilesSelected) {
    if (!inputElement) return;

    if (!inputElement.hasAttribute('accept')) {
      inputElement.setAttribute('accept', 'image/*');
    }

    if (isMobile) {
      inputElement.setAttribute('capture', 'environment');
    }

    inputElement.addEventListener('change', (e) => {
      const files = e.target.files;
      if (files && files.length > 0 && onFilesSelected) {
        onFilesSelected(files);
      }
    });
  }

  function showMobileToast(message, type = 'info', duration = 3000) {
    const toast = document.createElement('div');
    toast.className = `mobile-toast mobile-toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: ${type === 'error' ? '#dc3545' : type === 'success' ? '#28a745' : '#ff8e68'};
    color: white;
    padding: 12px 24px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    z-index: 10000;
    font-size: 14px;
    max-width: 90%;
    text-align: center;
    animation: slideUp 0.3s ease;
  `;

    const style = document.createElement('style');
    style.textContent = `
    @keyframes slideUp {
      from {
        transform: translateX(-50%) translateY(100px);
        opacity: 0;
      }
      to {
        transform: translateX(-50%) translateY(0);
        opacity: 1;
      }
    }
  `;
    if (!document.querySelector('#mobile-toast-style')) {
      style.id = 'mobile-toast-style';
      document.head.appendChild(style);
    }

    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideUp 0.3s ease reverse';
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, duration);
  }

  function initMobileEnhancements() {
    preventIOSZoom();

    networkMonitor.onStatusChange((status) => {
      if (status === 'offline') {
        showMobileToast('No internet connection', 'error', 5000);
      } else {
        showMobileToast('Connection restored', 'success', 2000);
      }
    });

    if (isMobile) {
      document.body.classList.add('is-mobile');
    }
    if (isIOS) {
      document.body.classList.add('is-ios');
    }
    if (isAndroid) {
      document.body.classList.add('is-android');
    }
    if (isTouchDevice) {
      document.body.classList.add('is-touch');
    }

    console.log('Mobile enhancements initialized', {
      isMobile,
      isIOS,
      isAndroid,
      isTouchDevice
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMobileEnhancements);
  } else {
    initMobileEnhancements();
  }

  const api = {
    isMobile,
    isIOS,
    isAndroid,
    isTouchDevice,
    downloadFile,
    downloadWithRetry,
    networkMonitor,
    preventIOSZoom,
    enhanceTouchEvents,
    setupMobileFileInput,
    showMobileToast,
    initMobileEnhancements
  };

  global.MobileUtils = api;
  global.downloadFile = downloadFile;
  global.downloadWithRetry = downloadWithRetry;
  global.showMobileToast = showMobileToast;
  global.networkMonitor = networkMonitor;
  global.initMobileEnhancements = initMobileEnhancements;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
