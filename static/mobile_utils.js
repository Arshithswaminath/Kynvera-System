/**
 * Mobile Utilities - Enhanced mobile browser support
 * Handles downloads, network detection, touch events, and mobile-specific features
 */

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
    // Create a temporary link element
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || '';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    
    // Add to DOM temporarily
    link.style.position = 'fixed';
    link.style.top = '-9999px';
    link.style.left = '-9999px';
    link.style.opacity = '0';
    link.style.pointerEvents = 'none';
    document.body.appendChild(link);
    
    // Trigger download with user gesture simulation
    try {
      // Use a small delay to ensure the link is in the DOM
      setTimeout(() => {
        link.click();
        
        // Clean up after a delay
        setTimeout(() => {
          if (link.parentNode) {
            link.parentNode.removeChild(link);
          }
        }, 1000);
      }, 100);
    } catch (e) {
      console.warn('Programmatic download failed, opening in new tab:', e);
      // Fallback: open in new tab
      if (openInNewTab) {
        window.open(url, '_blank');
      }
      if (link.parentNode) {
        link.parentNode.removeChild(link);
      }
    }
  } else {
    // Desktop: use standard download
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
  return new Promise((resolve, reject) => {
    let attempt = 0;
    
    const tryDownload = () => {
      attempt++;
      
      // For mobile, add a small delay between retries
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
    
    // Listen for online/offline events
    window.addEventListener('online', () => {
      this.isOnline = true;
      this.notifyListeners('online');
    });
    
    window.addEventListener('offline', () => {
      this.isOnline = false;
      this.notifyListeners('offline');
    });
    
    // Periodic connectivity check (for mobile networks)
    if (isMobile) {
      setInterval(() => this.checkConnectivity(), 30000); // Check every 30 seconds
    }
  }
  
  checkConnectivity() {
    // Simple fetch to check connectivity (app exposes /health)
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

// Global network monitor instance
const networkMonitor = new NetworkMonitor();

/**
 * Prevent iOS zoom on input focus
 */
function preventIOSZoom() {
  if (isIOS) {
    // Set viewport meta tag to prevent zoom
    const viewport = document.querySelector('meta[name="viewport"]');
    if (viewport) {
      viewport.setAttribute('content', 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no');
    }
    
    // Ensure inputs have font-size >= 16px to prevent zoom
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

/**
 * Enhanced touch event handling for signature pads
 */
function enhanceTouchEvents(element) {
  if (!isTouchDevice || !element) return;
  
  // Prevent default touch behaviors that interfere with drawing
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

/**
 * Mobile-friendly file input handler
 */
function setupMobileFileInput(inputElement, onFilesSelected) {
  if (!inputElement) return;
  
  // Ensure accept attribute is set for mobile
  if (!inputElement.hasAttribute('accept')) {
    inputElement.setAttribute('accept', 'image/*');
  }
  
  // Add capture attribute for mobile cameras
  if (isMobile) {
    inputElement.setAttribute('capture', 'environment'); // Use back camera
  }
  
  // Enhanced change handler
  inputElement.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files && files.length > 0 && onFilesSelected) {
      onFilesSelected(files);
    }
  });
}

/**
 * Show mobile-friendly toast notification
 */
function showMobileToast(message, type = 'info', duration = 3000) {
  const toast = document.createElement('div');
  toast.className = `mobile-toast mobile-toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: ${type === 'error' ? '#dc3545' : type === 'success' ? '#28a745' : '#125435'};
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
  
  // Add animation
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

/**
 * Initialize mobile enhancements
 */
function initMobileEnhancements() {
  // Prevent iOS zoom
  preventIOSZoom();
  
  // Setup network monitoring
  networkMonitor.onStatusChange((status) => {
    if (status === 'offline') {
      showMobileToast('No internet connection', 'error', 5000);
    } else {
      showMobileToast('Connection restored', 'success', 2000);
    }
  });
  
  // Add mobile class to body for CSS targeting
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

// Auto-initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initMobileEnhancements);
} else {
  initMobileEnhancements();
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
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
}

