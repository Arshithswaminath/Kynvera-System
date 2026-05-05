/**
 * Injaaz Toast Notification System
 * Modern, accessible toast notifications
 * Version: 1.0.0
 */

(function(window) {
  'use strict';

  // Default configuration
  const defaultConfig = {
    position: 'top-right',
    duration: 5000,
    closable: true,
    pauseOnHover: true,
    showProgress: true,
    maxToasts: 5
  };

  // Toast container reference
  let container = null;
  let toasts = [];

  // SVG Icons
  const icons = {
    success: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
      <polyline points="22 4 12 14.01 9 11.01"/>
    </svg>`,
    error: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <line x1="15" y1="9" x2="9" y2="15"/>
      <line x1="9" y1="9" x2="15" y2="15"/>
    </svg>`,
    warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>`,
    info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/>
      <line x1="12" y1="16" x2="12" y2="12"/>
      <line x1="12" y1="8" x2="12.01" y2="8"/>
    </svg>`,
    close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/>
      <line x1="6" y1="6" x2="18" y2="18"/>
    </svg>`
  };

  /**
   * Create toast container if it doesn't exist
   */
  function getContainer(position) {
    const containerId = `toast-container-${position}`;
    let existingContainer = document.getElementById(containerId);
    
    if (!existingContainer) {
      existingContainer = document.createElement('div');
      existingContainer.id = containerId;
      existingContainer.className = `toast-container toast-container-${position}`;
      existingContainer.setAttribute('role', 'region');
      existingContainer.setAttribute('aria-label', 'Notifications');
      document.body.appendChild(existingContainer);
    }
    
    return existingContainer;
  }

  /**
   * Generate unique ID
   */
  function generateId() {
    return 'toast-' + Math.random().toString(36).substr(2, 9);
  }

  /**
   * Create toast element
   */
  function createToastElement(options) {
    const toast = document.createElement('div');
    toast.id = options.id;
    toast.className = `toast toast-${options.type}`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'polite');
    
    let html = `
      <div class="toast-icon">${icons[options.type]}</div>
      <div class="toast-content">
        ${options.title ? `<div class="toast-title">${options.title}</div>` : ''}
        ${options.message ? `<div class="toast-message">${options.message}</div>` : ''}
        ${options.actions ? createActionsHTML(options.actions) : ''}
      </div>
    `;
    
    if (options.closable) {
      html += `
        <button class="toast-close" aria-label="Close notification">
          ${icons.close}
        </button>
      `;
    }
    
    if (options.showProgress && options.duration > 0) {
      html += `<div class="toast-progress" style="animation-duration: ${options.duration}ms"></div>`;
    }
    
    toast.innerHTML = html;
    
    return toast;
  }

  /**
   * Create action buttons HTML
   */
  function createActionsHTML(actions) {
    if (!actions || !actions.length) return '';
    
    const actionsHtml = actions.map(action => {
      const className = action.primary ? 'toast-action toast-action-primary' : 'toast-action toast-action-secondary';
      return `<button class="${className}" data-action="${action.id || ''}">${action.label}</button>`;
    }).join('');
    
    return `<div class="toast-actions">${actionsHtml}</div>`;
  }

  /**
   * Remove toast with animation
   */
  function removeToast(toastId) {
    const toast = document.getElementById(toastId);
    if (!toast) return;
    
    toast.classList.add('toast-exiting');
    
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
      toasts = toasts.filter(t => t.id !== toastId);
    }, 200);
  }

  /**
   * Show toast notification
   */
  function show(options) {
    // Merge with defaults
    const config = { ...defaultConfig, ...options };
    const id = config.id || generateId();
    
    // Validate type
    const validTypes = ['success', 'error', 'warning', 'info'];
    if (!validTypes.includes(config.type)) {
      config.type = 'info';
    }
    
    // Get container
    container = getContainer(config.position);
    
    // Remove oldest toast if max reached
    while (toasts.length >= config.maxToasts) {
      removeToast(toasts[0].id);
    }
    
    // Create toast element
    const toastElement = createToastElement({
      id,
      type: config.type,
      title: config.title,
      message: config.message,
      closable: config.closable,
      showProgress: config.showProgress,
      duration: config.duration,
      actions: config.actions
    });
    
    // Add to container
    container.appendChild(toastElement);
    
    // Store toast reference
    const toastRef = {
      id,
      element: toastElement,
      timeout: null,
      isPaused: false
    };
    toasts.push(toastRef);
    
    // Setup close button
    if (config.closable) {
      const closeBtn = toastElement.querySelector('.toast-close');
      if (closeBtn) {
        closeBtn.addEventListener('click', () => removeToast(id));
      }
    }
    
    // Setup action buttons
    if (config.actions) {
      config.actions.forEach(action => {
        const btn = toastElement.querySelector(`[data-action="${action.id || ''}"]`);
        if (btn && action.onClick) {
          btn.addEventListener('click', () => {
            action.onClick();
            if (action.closeOnClick !== false) {
              removeToast(id);
            }
          });
        }
      });
    }
    
    // Setup auto dismiss
    if (config.duration > 0) {
      toastRef.timeout = setTimeout(() => removeToast(id), config.duration);
      
      // Pause on hover
      if (config.pauseOnHover) {
        toastElement.addEventListener('mouseenter', () => {
          if (toastRef.timeout) {
            clearTimeout(toastRef.timeout);
            toastRef.isPaused = true;
            const progress = toastElement.querySelector('.toast-progress');
            if (progress) {
              progress.style.animationPlayState = 'paused';
            }
          }
        });
        
        toastElement.addEventListener('mouseleave', () => {
          if (toastRef.isPaused) {
            toastRef.isPaused = false;
            const progress = toastElement.querySelector('.toast-progress');
            if (progress) {
              progress.style.animationPlayState = 'running';
            }
            toastRef.timeout = setTimeout(() => removeToast(id), config.duration / 2);
          }
        });
      }
    }
    
    // Callback
    if (config.onShow) {
      config.onShow(id);
    }
    
    return id;
  }

  /**
   * Convenience methods
   */
  function success(message, title = 'Success', options = {}) {
    return show({ ...options, type: 'success', title, message });
  }

  function error(message, title = 'Error', options = {}) {
    return show({ ...options, type: 'error', title, message });
  }

  function warning(message, title = 'Warning', options = {}) {
    return show({ ...options, type: 'warning', title, message });
  }

  function info(message, title = 'Info', options = {}) {
    return show({ ...options, type: 'info', title, message });
  }

  /**
   * Dismiss toast by ID
   */
  function dismiss(toastId) {
    removeToast(toastId);
  }

  /**
   * Dismiss all toasts
   */
  function dismissAll() {
    toasts.forEach(t => removeToast(t.id));
  }

  /**
   * Update global configuration
   */
  function configure(options) {
    Object.assign(defaultConfig, options);
  }

  // Promise-based toast
  function promise(promise, options) {
    const loadingId = show({
      type: 'info',
      title: options.loading?.title || 'Loading...',
      message: options.loading?.message || '',
      duration: 0,
      closable: false,
      showProgress: false
    });

    promise
      .then((result) => {
        dismiss(loadingId);
        success(
          typeof options.success === 'function' ? options.success(result) : options.success?.message || 'Success!',
          options.success?.title || 'Success'
        );
        return result;
      })
      .catch((err) => {
        dismiss(loadingId);
        error(
          typeof options.error === 'function' ? options.error(err) : options.error?.message || 'Something went wrong',
          options.error?.title || 'Error'
        );
        throw err;
      });

    return promise;
  }

  // Export to window
  window.Toast = {
    show,
    success,
    error,
    warning,
    info,
    dismiss,
    dismissAll,
    configure,
    promise
  };

})(window);
