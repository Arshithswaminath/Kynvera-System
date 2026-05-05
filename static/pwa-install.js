// PWA Installation and Service Worker Registration
// Injaaz App v1.0.0

let deferredPrompt;
let installButton;

// Register Service Worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/service-worker.js')
      .then((registration) => {
        console.log('✅ Service Worker registered:', registration.scope);
        
        // Check for updates every hour
        setInterval(() => {
          registration.update();
        }, 60 * 60 * 1000);
        
        // Handle updates
        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          
          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              // New service worker available
              showUpdateNotification();
            }
          });
        });
      })
      .catch((error) => {
        console.error('❌ Service Worker registration failed:', error);
      });
    
    // For iOS and browsers that don't fire beforeinstallprompt
    // Show install button after a delay if not already shown
    setTimeout(() => {
      if (!document.getElementById('pwa-install-btn') && !isStandalone()) {
        showIOSInstallButton();
      }
    }, 3000);
  });
}

// Check if app is already installed (running in standalone mode)
function isStandalone() {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  );
}

// Show update notification
function showUpdateNotification() {
  if (confirm('A new version of Injaaz is available. Reload to update?')) {
    window.location.reload();
  }
}

// Listen for beforeinstallprompt event
window.addEventListener('beforeinstallprompt', (e) => {
  console.log('💾 Install prompt available');
  
  // Prevent the default prompt
  e.preventDefault();
  
  // Store the event for later use
  deferredPrompt = e;
  
  // Show custom install button
  showInstallButton();
});

// Show install button in UI
function showInstallButton() {
  // Create install button if it doesn't exist
  if (!document.getElementById('pwa-install-btn')) {
    const installSlot = document.getElementById('pwa-install-slot');
    const useNavSlot = !!installSlot;
    
    const installBtn = document.createElement('button');
    installBtn.id = 'pwa-install-btn';
    installBtn.type = 'button';
    installBtn.title = 'Install App';
    installBtn.setAttribute('aria-label', 'Install App');
    installBtn.innerHTML = `
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="7 10 12 15 17 10"></polyline>
        <line x1="12" y1="15" x2="12" y2="3"></line>
      </svg>
    `;
    
    if (useNavSlot) {
      installBtn.classList.add('pwa-nav-icon');
      installSlot.appendChild(installBtn);
    } else {
      installBtn.innerHTML = installBtn.innerHTML + '<span>Install App</span>';
      installBtn.style.cssText = `
        position: fixed;
        top: 80px;
        right: 15px;
        background: linear-gradient(135deg, #125435 0%, #1a6b47 100%);
        color: white;
        border: 2px solid rgba(255, 255, 255, 0.2);
        padding: 12px 20px;
        border-radius: 12px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        box-shadow: 0 4px 16px rgba(18, 84, 53, 0.4), 0 2px 8px rgba(0, 0, 0, 0.1);
        z-index: 9999;
        transition: all 0.3s ease;
        animation: slideInRight 0.5s ease, pulse 2s ease-in-out infinite;
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
      `;
      installBtn.addEventListener('mouseenter', () => {
        installBtn.style.transform = 'translateX(-2px) scale(1.05)';
        installBtn.style.boxShadow = '0 6px 20px rgba(18, 84, 53, 0.5), 0 3px 10px rgba(0, 0, 0, 0.15)';
      });
      installBtn.addEventListener('mouseleave', () => {
        installBtn.style.transform = 'translateX(0) scale(1)';
        installBtn.style.boxShadow = '0 4px 16px rgba(18, 84, 53, 0.4), 0 2px 8px rgba(0, 0, 0, 0.1)';
      });
      document.body.appendChild(installBtn);
    }
    
    installBtn.addEventListener('click', installApp);
    installButton = installBtn;
    
    // Add animation keyframes
    if (!document.getElementById('pwa-animations')) {
      const style = document.createElement('style');
      style.id = 'pwa-animations';
      style.textContent = `
        @keyframes slideInRight {
          from {
            transform: translateX(100px);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
        
        @keyframes pulse {
          0%, 100% {
            box-shadow: 0 4px 16px rgba(18, 84, 53, 0.4), 0 2px 8px rgba(0, 0, 0, 0.1);
          }
          50% {
            box-shadow: 0 4px 20px rgba(18, 84, 53, 0.6), 0 2px 12px rgba(0, 0, 0, 0.15), 0 0 0 4px rgba(18, 84, 53, 0.2);
          }
        }
        
        @keyframes fadeOut {
          to {
            opacity: 0;
            transform: translateX(100px);
          }
        }
        
        #pwa-install-btn.hiding {
          animation: fadeOut 0.3s ease forwards;
        }
        
        /* Mobile optimizations - only for floating button, not nav icon */
        @media (max-width: 768px) {
          #pwa-install-btn:not(.pwa-nav-icon) {
            top: auto !important;
            bottom: max(20px, env(safe-area-inset-bottom)) !important;
            right: max(15px, env(safe-area-inset-right)) !important;
            left: auto !important;
            padding: 10px 16px !important;
            font-size: 13px !important;
            border-radius: 10px !important;
          }
          
          #pwa-install-btn:not(.pwa-nav-icon) svg {
            width: 16px !important;
            height: 16px !important;
          }
        }
        
        @media (max-width: 480px) {
          #pwa-install-btn:not(.pwa-nav-icon) {
            bottom: max(16px, env(safe-area-inset-bottom)) !important;
            right: max(12px, env(safe-area-inset-right)) !important;
            padding: 8px 14px !important;
            font-size: 12px !important;
          }
        }
      `;
      document.head.appendChild(style);
    }
  }
}

// Install the app
async function installApp() {
  if (!deferredPrompt) {
    console.log('Install prompt not available');
    return;
  }
  
  // Show the install prompt
  deferredPrompt.prompt();
  
  // Wait for user response
  const { outcome } = await deferredPrompt.userChoice;
  
  console.log(`User response: ${outcome}`);
  
  if (outcome === 'accepted') {
    console.log('✅ App installed successfully');
    hideInstallButton();
  }
  
  // Clear the prompt
  deferredPrompt = null;
}

// Hide install button
function hideInstallButton() {
  if (installButton) {
    installButton.classList.add('hiding');
    setTimeout(() => {
      installButton.remove();
    }, 300);
  }
}

// Check if already installed
window.addEventListener('appinstalled', () => {
  console.log('✅ Injaaz has been installed');
  hideInstallButton();
  
  // Track installation
  if (typeof gtag !== 'undefined') {
    gtag('event', 'pwa_install', {
      event_category: 'engagement',
      event_label: 'PWA Installation'
    });
  }
});

// Check if running as installed PWA
if (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true) {
  console.log('✅ Running as installed PWA');
  document.body.classList.add('pwa-installed');
  
  // Hide install button if shown
  hideInstallButton();
}

// Handle offline/online status
window.addEventListener('online', () => {
  console.log('🟢 Back online');
  showConnectionStatus('Online', '#10b981', 2000);
});

window.addEventListener('offline', () => {
  console.log('🔴 Offline mode - Forms require internet connection');
  showConnectionStatus('Offline - Please connect to internet', '#ef4444', 0); // 0 = stays visible
});

// Show connection status message
function showConnectionStatus(message, color, duration) {
  // Remove existing status
  const existing = document.getElementById('connection-status');
  if (existing) {
    existing.remove();
  }
  
  const status = document.createElement('div');
  status.id = 'connection-status';
  status.textContent = message;
  status.style.cssText = `
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%) translateY(-20px);
    background: ${color};
    color: white;
    padding: 12px 24px;
    border-radius: 8px;
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    font-weight: 500;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    z-index: 10000;
    animation: slideDown 0.3s ease forwards;
  `;
  
  // Add slide animation
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideDown {
      to { transform: translateX(-50%) translateY(0); }
    }
  `;
  document.head.appendChild(style);
  
  document.body.appendChild(status);
  
  setTimeout(() => {
    status.style.animation = 'slideDown 0.3s ease reverse';
    setTimeout(() => status.remove(), 300);
  }, duration);
}

// Expose API for manual cache management
window.InjaazPWA = {
  update: () => {
    navigator.serviceWorker.ready.then((registration) => {
      registration.update();
    });
  },
  
  unregister: () => {
    navigator.serviceWorker.ready.then((registration) => {
      registration.unregister();
    });
  },
  
  getInstallStatus: () => {
    return window.matchMedia('(display-mode: standalone)').matches;
  },
  
  clearCache: async () => {
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames.map(name => caches.delete(name)));
    console.log('✅ Cache cleared');
  }
};

// Show iOS install instructions button
function showIOSInstallButton() {
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
  
  if (isIOS || isSafari || /Mobile/.test(navigator.userAgent)) {
    const installSlot = document.getElementById('pwa-install-slot');
    const useNavSlot = !!installSlot;
    
    const installBtn = document.createElement('button');
    installBtn.id = 'pwa-install-btn';
    installBtn.type = 'button';
    installBtn.title = 'Install App';
    installBtn.setAttribute('aria-label', 'Install App');
    installBtn.innerHTML = `
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="7 10 12 15 17 10"></polyline>
        <line x1="12" y1="15" x2="12" y2="3"></line>
      </svg>
    `;
    
    if (useNavSlot) {
      installBtn.classList.add('pwa-nav-icon');
      installSlot.appendChild(installBtn);
    } else {
      installBtn.innerHTML = installBtn.innerHTML + '<span>Install App</span>';
      installBtn.style.cssText = `
        position: fixed;
        top: 80px;
        right: 15px;
        background: linear-gradient(135deg, #125435 0%, #1a6b47 100%);
        color: white;
        border: 2px solid rgba(255, 255, 255, 0.2);
        padding: 12px 20px;
        border-radius: 12px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 8px;
        box-shadow: 0 4px 16px rgba(18, 84, 53, 0.4), 0 2px 8px rgba(0, 0, 0, 0.1);
        z-index: 9999;
        transition: all 0.3s ease;
        animation: slideInRight 0.5s ease, pulse 2s ease-in-out infinite;
      `;
      document.body.appendChild(installBtn);
    }
    
    installBtn.addEventListener('click', () => {
      if (isIOS) {
        showIOSInstructions();
      } else {
        showAndroidInstructions();
      }
    });
    installButton = installBtn;
  }
}

// Show iOS installation instructions
function showIOSInstructions() {
  const modal = document.createElement('div');
  modal.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    padding: 20px;
  `;
  
  modal.innerHTML = `
    <div style="
      background: white;
      border-radius: 16px;
      padding: 30px;
      max-width: 400px;
      text-align: center;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    ">
      <h2 style="color: #125435; margin: 0 0 20px 0; font-size: 22px;">Install Injaaz App</h2>
      <div style="color: #333; line-height: 1.6; text-align: left; margin-bottom: 20px;">
        <p style="margin: 10px 0;"><strong>1.</strong> Tap the <strong>Share</strong> button 
        <svg width="16" height="16" viewBox="0 0 24 24" fill="#007AFF" style="vertical-align: middle; margin: 0 4px;">
          <path d="M8 4H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2v-2M12 4v12m0-12l-4 4m4-4l4 4"/>
        </svg> at the bottom</p>
        <p style="margin: 10px 0;"><strong>2.</strong> Scroll and tap <strong>"Add to Home Screen"</strong> 
        <svg width="16" height="16" viewBox="0 0 24 24" fill="#007AFF" style="vertical-align: middle; margin: 0 4px;">
          <rect x="4" y="4" width="16" height="16" rx="2" fill="none" stroke="#007AFF" stroke-width="2"/>
          <path d="M12 8v8m-4-4h8" stroke="#007AFF" stroke-width="2"/>
        </svg></p>
        <p style="margin: 10px 0;"><strong>3.</strong> Tap <strong>"Add"</strong> to confirm</p>
      </div>
      <button onclick="this.parentElement.parentElement.remove()" style="
        background: #125435;
        color: white;
        border: none;
        padding: 12px 32px;
        border-radius: 8px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
      ">Got it!</button>
    </div>
  `;
  
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.remove();
  });
  
  document.body.appendChild(modal);
}

// Show Android installation instructions
function showAndroidInstructions() {
  const modal = document.createElement('div');
  modal.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    padding: 20px;
  `;
  
  modal.innerHTML = `
    <div style="
      background: white;
      border-radius: 16px;
      padding: 30px;
      max-width: 400px;
      text-align: center;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    ">
      <h2 style="color: #125435; margin: 0 0 20px 0; font-size: 22px;">Install Injaaz App</h2>
      <div style="color: #333; line-height: 1.6; text-align: left; margin-bottom: 20px;">
        <p style="margin: 10px 0;"><strong>1.</strong> Tap the <strong>Menu</strong> button (⋮) in the browser</p>
        <p style="margin: 10px 0;"><strong>2.</strong> Select <strong>"Install app"</strong> or <strong>"Add to Home screen"</strong></p>
        <p style="margin: 10px 0;"><strong>3.</strong> Tap <strong>"Install"</strong> to confirm</p>
      </div>
      <button onclick="this.parentElement.parentElement.remove()" style="
        background: #125435;
        color: white;
        border: none;
        padding: 12px 32px;
        border-radius: 8px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
      ">Got it!</button>
    </div>
  `;
  
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.remove();
  });
  
  document.body.appendChild(modal);
}

console.log('✅ PWA install script loaded');
