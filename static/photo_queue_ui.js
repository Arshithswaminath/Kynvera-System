/**
 * Photo Queue UI Helper - Shared UI components for all forms
 * Works with PhotoUploadQueue to provide consistent UI across forms
 */

class PhotoQueueUI {
  constructor(containerIdOrOptions, options = {}) {
    // Handle both calling patterns:
    // 1. new PhotoQueueUI('containerId', {options})
    // 2. new PhotoQueueUI({containerId: 'id', ...options}) - for backward compatibility
    let containerId;
    let finalOptions = {};
    
    if (typeof containerIdOrOptions === 'string') {
      // Pattern 1: containerId is first parameter
      containerId = containerIdOrOptions;
      finalOptions = options || {};
    } else if (containerIdOrOptions && typeof containerIdOrOptions === 'object') {
      // Pattern 2: options object with containerId property
      containerId = containerIdOrOptions.containerId;
      finalOptions = { ...containerIdOrOptions };
    } else {
      console.error('❌ PhotoQueueUI: Invalid constructor arguments:', containerIdOrOptions);
      containerId = 'photoPreviewContainer'; // Default fallback
    }
    
    // Try to find container, create if it doesn't exist
    this.container = document.getElementById(containerId);
    
    if (!this.container) {
      console.warn(`⚠️ PhotoQueueUI: Container "${containerId}" not found. Creating it...`);
      // Try to find a parent container or create one
      const formContainer = document.querySelector('form') || document.body;
      this.container = document.createElement('div');
      this.container.id = containerId;
      this.container.className = 'photo-preview-container';
      this.container.style.display = 'none';
      formContainer.appendChild(this.container);
      console.log('✅ PhotoQueueUI: Created container:', containerId);
    } else {
      console.log('✅ PhotoQueueUI: Container found:', containerId, this.container);
    }
    
    // Merge options with defaults
    this.options = {
      maxPhotos: finalOptions.maxPhotos || 100,
      showOverallProgress: finalOptions.showOverallProgress !== false,
      showRetryButton: finalOptions.showRetryButton !== false,
      onRetryAll: finalOptions.onRetryAll || finalOptions.onRetry || (() => {}),
      onRemove: finalOptions.onRemove || (() => {})
    };
    
    this.photoElements = new Map(); // photoId -> DOM element
  }

  /**
   * Create and show progress container
   */
  createProgressContainer() {
    const existing = document.getElementById('uploadQueueStatus');
    if (existing) return existing;
    
    const progressHTML = `
      <div class="upload-queue-container" id="uploadQueueStatus" style="display:none;">
        <div class="upload-progress-bar">
          <div class="upload-progress-fill" id="queueProgressFill" style="width: 0%">
            0%
          </div>
        </div>
        <div class="upload-stats" id="uploadStats">
          <strong>0</strong> completed | <strong>0</strong> uploading | <strong>0</strong> queued | <strong>0</strong> failed
        </div>
        ${this.options.showRetryButton ? '<button class="retry-all-btn" id="retryAllBtn" style="display:none;">Retry All Failed</button>' : ''}
      </div>
    `;
    
    this.container.insertAdjacentHTML('beforebegin', progressHTML);
    
    if (this.options.showRetryButton) {
      document.getElementById('retryAllBtn').addEventListener('click', () => {
        this.options.onRetryAll();
      });
    }
    
    return document.getElementById('uploadQueueStatus');
  }

  /**
   * Update overall progress bar
   */
  updateProgress(stats) {
    const progressContainer = document.getElementById('uploadQueueStatus');
    if (!progressContainer) return;
    
    if (stats.total === 0) {
      progressContainer.style.display = 'none';
      return;
    }
    
    progressContainer.style.display = 'block';
    
    const percentComplete = stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0;
    const progressFill = document.getElementById('queueProgressFill');
    
    if (progressFill) {
      progressFill.style.width = percentComplete + '%';
      progressFill.textContent = `${percentComplete}% (${stats.completed}/${stats.total})`;
    }
    
    const statsEl = document.getElementById('uploadStats');
    if (statsEl) {
      statsEl.innerHTML = `
        <strong>${stats.completed}</strong> completed | 
        <strong>${stats.uploading}</strong> uploading | 
        <strong>${stats.queued}</strong> queued | 
        <strong>${stats.failed}</strong> failed
      `;
    }
    
    const retryBtn = document.getElementById('retryAllBtn');
    if (retryBtn) {
      retryBtn.style.display = stats.failed > 0 ? 'inline-block' : 'none';
    }
    
    // Hide progress bar after completion if no failures
    if (stats.isComplete && stats.failed === 0) {
      setTimeout(() => {
        progressContainer.style.display = 'none';
      }, 3000);
    }
  }

  /**
   * Render a photo item with status overlay
   */
  renderPhotoItem(item) {
    if (!this.container) {
      console.error('❌ PhotoQueueUI: Container not found!', this.container);
      // Try to recreate container
      const containerId = this.container?.id || 'photoPreviewContainer';
      this.container = document.getElementById(containerId);
      if (!this.container) {
        console.error('❌ PhotoQueueUI: Cannot render photo - no container available');
        return null;
      }
    }
    
    if (!item.preview) {
      console.error('❌ PhotoQueueUI: Item has no preview!', item);
      return null;
    }
    
    // Ensure container is visible and responsive
    this.container.style.display = 'flex';
    this.container.style.flexWrap = 'wrap';
    this.container.style.gap = '10px';
    this.container.style.marginTop = '1rem';
    this.container.style.padding = '0.5rem';
    this.container.style.width = '100%';
    this.container.style.boxSizing = 'border-box';
    
    // Mobile-specific adjustments
    if (window.innerWidth <= 768) {
      this.container.style.gap = '8px';
      this.container.style.padding = '8px';
    }
    
    const photoDiv = document.createElement('div');
    photoDiv.className = 'photo-item';
    photoDiv.dataset.photoId = item.id;
    
    // Create image element with error handling
    const img = document.createElement('img');
    img.src = item.preview;
    img.alt = 'Photo';
    img.style.display = 'block';
    // Responsive sizing - will be overridden by CSS on mobile
    img.style.width = '120px';
    img.style.height = '120px';
    img.style.objectFit = 'cover';
    img.style.maxWidth = '100%';
    img.loading = 'lazy'; // Lazy load for better mobile performance
    img.onerror = () => {
      console.error('❌ Failed to load image preview:', item.preview);
      img.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIwIiBoZWlnaHQ9IjEyMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTIwIiBoZWlnaHQ9IjEyMCIgZmlsbD0iI2RkZCIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj5JbWFnZTwvdGV4dD48L3N2Zz4=';
    };
    img.onload = () => {
      console.log('✅ Image preview loaded:', item.id);
    };
    
    photoDiv.innerHTML = `
      <div class="photo-status-overlay status-${item.status}">
        ${this.getStatusContent(item.status, item.progress)}
      </div>
      <div class="photo-progress">
        <div class="photo-progress-fill" style="width: ${item.progress}%"></div>
      </div>
      <button class="photo-remove-btn" title="Remove photo">×</button>
    `;
    
    // Insert image as first child
    photoDiv.insertBefore(img, photoDiv.firstChild);
    
    // Add remove button handler
    const removeBtn = photoDiv.querySelector('.photo-remove-btn');
    if (removeBtn) {
      removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.options.onRemove(item.id);
      });
    }
    
    this.container.appendChild(photoDiv);
    this.photoElements.set(item.id, photoDiv);
    
    console.log('✅ PhotoQueueUI: Rendered photo item', item.id, 'in container', this.container.id);
    
    return photoDiv;
  }

  /**
   * Get status overlay content based on status
   */
  getStatusContent(status, progress = 0) {
    switch (status) {
      case 'queued':
        return `<div class="photo-status-icon">⏸</div><div>Queued</div>`;
      case 'uploading':
        return `<div class="photo-status-icon spinning">↻</div><div>Uploading ${progress}%</div>`;
      case 'completed':
        return `<div class="photo-status-icon">✓</div><div>Uploaded</div>`;
      case 'failed':
        return `<div class="photo-status-icon">✗</div><div>Failed - Click to retry</div>`;
      default:
        return '';
    }
  }

  /**
   * Update photo item status
   */
  updatePhotoStatus(item) {
    const photoDiv = this.photoElements.get(item.id);
    if (!photoDiv) {
      // If photo item doesn't exist yet, render it
      if (item.preview) {
        this.renderPhotoItem(item);
      }
      return;
    }
    
    const overlay = photoDiv.querySelector('.photo-status-overlay');
    if (overlay) {
      overlay.className = `photo-status-overlay status-${item.status}`;
      overlay.innerHTML = this.getStatusContent(item.status, item.progress);
      
      // Add retry handler for failed items
      if (item.status === 'failed') {
        overlay.style.cursor = 'pointer';
        overlay.onclick = () => {
          const event = new CustomEvent('photo-retry', { detail: { photoId: item.id } });
          document.dispatchEvent(event);
        };
      } else {
        overlay.style.cursor = 'default';
        overlay.onclick = null;
      }
    }
    
    const progressFill = photoDiv.querySelector('.photo-progress-fill');
    if (progressFill) {
      progressFill.style.width = item.progress + '%';
      // Hide progress bar when complete
      if (item.status === 'completed') {
        progressFill.style.opacity = '0';
        setTimeout(() => {
          if (progressFill) progressFill.style.display = 'none';
        }, 500);
      }
    }
    
    // Update image source if URL is available and different
    if (item.status === 'completed' && item.url) {
      const img = photoDiv.querySelector('img');
      if (img && img.src !== item.url) {
        // Only update if not already using the cloud URL
        const oldSrc = img.src;
        img.src = item.url;
        img.onerror = () => {
          // Fallback to preview if cloud URL fails
          console.warn('Failed to load cloud URL, using preview:', item.url);
          img.src = oldSrc;
        };
      }
      
      // Add "just-completed" class for animation
      photoDiv.classList.add('just-completed');
      setTimeout(() => {
        photoDiv.classList.remove('just-completed');
      }, 3000);
    }
    
    console.log(`✅ PhotoQueueUI: Updated status for ${item.id} to ${item.status} (${item.progress}%)`);
  }

  /**
   * Remove photo from UI
   */
  removePhoto(photoId) {
    const photoDiv = this.photoElements.get(photoId);
    if (photoDiv) {
      photoDiv.remove();
      this.photoElements.delete(photoId);
    }
  }

  /**
   * Clear all photos
   */
  clearAll() {
    this.photoElements.forEach((div) => div.remove());
    this.photoElements.clear();
  }

  /**
   * Get count of displayed photos
   */
  getPhotoCount() {
    return this.photoElements.size;
  }
  
  /**
   * Update container layout for mobile responsiveness
   */
  updateLayout() {
    if (!this.container) return;
    
    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
      this.container.style.gap = '8px';
      this.container.style.padding = '8px';
      // Update photo items for mobile
      this.photoElements.forEach((photoDiv) => {
        const img = photoDiv.querySelector('img');
        if (img) {
          img.style.maxWidth = '100%';
        }
      });
    } else {
      this.container.style.gap = '10px';
      this.container.style.padding = '0.5rem';
    }
  }
}

// Export for use in forms
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PhotoQueueUI;
}

// Make available globally
if (typeof window !== 'undefined') {
  window.PhotoQueueUI = PhotoQueueUI;
}