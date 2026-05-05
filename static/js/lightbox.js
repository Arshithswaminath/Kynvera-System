/**
 * Injaaz Photo Lightbox
 * Full-screen image viewer with navigation and gestures
 * Version: 1.0.0
 */

(function(window) {
  'use strict';

  // SVG Icons
  const icons = {
    close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"></line>
      <line x1="6" y1="6" x2="18" y2="18"></line>
    </svg>`,
    prev: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="15 18 9 12 15 6"></polyline>
    </svg>`,
    next: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="9 18 15 12 9 6"></polyline>
    </svg>`,
    download: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
      <polyline points="7 10 12 15 17 10"></polyline>
      <line x1="12" y1="15" x2="12" y2="3"></line>
    </svg>`,
    zoomIn: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="8"></circle>
      <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      <line x1="11" y1="8" x2="11" y2="14"></line>
      <line x1="8" y1="11" x2="14" y2="11"></line>
    </svg>`,
    zoomOut: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="8"></circle>
      <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
      <line x1="8" y1="11" x2="14" y2="11"></line>
    </svg>`
  };

  /**
   * Lightbox Class
   */
  class Lightbox {
    constructor(options = {}) {
      this.options = {
        showThumbnails: true,
        showCounter: true,
        showCaption: true,
        showDownload: true,
        enableZoom: true,
        enableKeyboard: true,
        enableSwipe: true,
        loop: true,
        ...options
      };

      this.images = [];
      this.currentIndex = 0;
      this.isOpen = false;
      this.isZoomed = false;
      this.overlay = null;

      this.init();
    }

    init() {
      this.createOverlay();
      this.bindEvents();
    }

    createOverlay() {
      this.overlay = document.createElement('div');
      this.overlay.className = 'lightbox-overlay';
      this.overlay.setAttribute('role', 'dialog');
      this.overlay.setAttribute('aria-modal', 'true');
      this.overlay.setAttribute('aria-label', 'Image viewer');

      this.overlay.innerHTML = `
        <button class="lightbox-close" aria-label="Close">${icons.close}</button>
        
        ${this.options.showDownload || this.options.enableZoom ? `
          <div class="lightbox-actions">
            ${this.options.enableZoom ? `<button class="lightbox-action lightbox-zoom" aria-label="Zoom">${icons.zoomIn}</button>` : ''}
            ${this.options.showDownload ? `<button class="lightbox-action lightbox-download" aria-label="Download">${icons.download}</button>` : ''}
          </div>
        ` : ''}
        
        <button class="lightbox-nav lightbox-prev" aria-label="Previous image">${icons.prev}</button>
        <button class="lightbox-nav lightbox-next" aria-label="Next image">${icons.next}</button>
        
        <div class="lightbox-content">
          <div class="lightbox-loading"></div>
          <img class="lightbox-image" src="" alt="">
        </div>
        
        <div class="lightbox-footer">
          <div class="lightbox-caption"></div>
          <div class="lightbox-counter"></div>
        </div>
        
        <div class="lightbox-thumbnails"></div>
        
        <div class="lightbox-zoom-hint">Click to zoom</div>
      `;

      document.body.appendChild(this.overlay);

      // Cache elements
      this.elements = {
        close: this.overlay.querySelector('.lightbox-close'),
        prev: this.overlay.querySelector('.lightbox-prev'),
        next: this.overlay.querySelector('.lightbox-next'),
        image: this.overlay.querySelector('.lightbox-image'),
        loading: this.overlay.querySelector('.lightbox-loading'),
        caption: this.overlay.querySelector('.lightbox-caption'),
        counter: this.overlay.querySelector('.lightbox-counter'),
        thumbnails: this.overlay.querySelector('.lightbox-thumbnails'),
        content: this.overlay.querySelector('.lightbox-content'),
        zoom: this.overlay.querySelector('.lightbox-zoom'),
        download: this.overlay.querySelector('.lightbox-download')
      };
    }

    bindEvents() {
      // Close button
      this.elements.close.addEventListener('click', () => this.close());

      // Navigation
      this.elements.prev.addEventListener('click', () => this.prev());
      this.elements.next.addEventListener('click', () => this.next());

      // Zoom
      if (this.options.enableZoom) {
        this.elements.image.addEventListener('click', () => this.toggleZoom());
        if (this.elements.zoom) {
          this.elements.zoom.addEventListener('click', () => this.toggleZoom());
        }
      }

      // Download
      if (this.elements.download) {
        this.elements.download.addEventListener('click', () => this.download());
      }

      // Close on overlay click
      this.overlay.addEventListener('click', (e) => {
        if (e.target === this.overlay || e.target === this.elements.content) {
          this.close();
        }
      });

      // Keyboard navigation
      if (this.options.enableKeyboard) {
        document.addEventListener('keydown', (e) => {
          if (!this.isOpen) return;

          switch (e.key) {
            case 'Escape':
              this.close();
              break;
            case 'ArrowLeft':
              this.prev();
              break;
            case 'ArrowRight':
              this.next();
              break;
            case ' ':
              e.preventDefault();
              this.toggleZoom();
              break;
          }
        });
      }

      // Touch/swipe support
      if (this.options.enableSwipe) {
        this.setupSwipe();
      }
    }

    setupSwipe() {
      let startX = 0;
      let startY = 0;
      let distX = 0;
      let distY = 0;
      const threshold = 50;

      this.elements.content.addEventListener('touchstart', (e) => {
        if (this.isZoomed) return;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
      }, { passive: true });

      this.elements.content.addEventListener('touchmove', (e) => {
        if (this.isZoomed) return;
        distX = e.touches[0].clientX - startX;
        distY = e.touches[0].clientY - startY;
      }, { passive: true });

      this.elements.content.addEventListener('touchend', () => {
        if (this.isZoomed) return;
        
        if (Math.abs(distX) > Math.abs(distY) && Math.abs(distX) > threshold) {
          if (distX > 0) {
            this.prev();
          } else {
            this.next();
          }
        }
        
        distX = 0;
        distY = 0;
      });
    }

    open(images, startIndex = 0) {
      this.images = Array.isArray(images) ? images : [images];
      this.currentIndex = startIndex;
      this.isOpen = true;

      // Prevent body scroll
      document.body.style.overflow = 'hidden';

      // Show overlay
      this.overlay.classList.add('active');

      // Load image
      this.loadImage();

      // Update thumbnails
      this.updateThumbnails();

      // Focus close button for accessibility
      this.elements.close.focus();
    }

    close() {
      this.isOpen = false;
      this.isZoomed = false;
      this.elements.content.classList.remove('zoomed');

      // Restore body scroll
      document.body.style.overflow = '';

      // Hide overlay
      this.overlay.classList.remove('active');
    }

    loadImage() {
      const image = this.images[this.currentIndex];
      const src = typeof image === 'string' ? image : image.src || image.url;
      const caption = typeof image === 'string' ? '' : image.caption || image.title || '';

      // Show loading
      this.elements.loading.style.display = 'block';
      this.elements.image.style.opacity = '0';

      // Load image
      const img = new Image();
      img.onload = () => {
        this.elements.image.src = src;
        this.elements.loading.style.display = 'none';
        this.elements.image.style.opacity = '1';
      };
      img.onerror = () => {
        this.elements.loading.style.display = 'none';
        console.error('Failed to load image:', src);
      };
      img.src = src;

      // Update caption
      if (this.options.showCaption) {
        this.elements.caption.textContent = caption;
        this.elements.caption.style.display = caption ? 'block' : 'none';
      }

      // Update counter
      if (this.options.showCounter) {
        this.elements.counter.textContent = `${this.currentIndex + 1} / ${this.images.length}`;
      }

      // Update navigation buttons
      this.updateNavigation();
    }

    updateNavigation() {
      const hasPrev = this.options.loop || this.currentIndex > 0;
      const hasNext = this.options.loop || this.currentIndex < this.images.length - 1;

      this.elements.prev.disabled = !hasPrev;
      this.elements.next.disabled = !hasNext;

      // Hide nav buttons if single image
      if (this.images.length <= 1) {
        this.elements.prev.style.display = 'none';
        this.elements.next.style.display = 'none';
      } else {
        this.elements.prev.style.display = '';
        this.elements.next.style.display = '';
      }
    }

    updateThumbnails() {
      if (!this.options.showThumbnails || this.images.length <= 1) {
        this.elements.thumbnails.classList.add('single');
        return;
      }

      this.elements.thumbnails.classList.remove('single');
      this.elements.thumbnails.innerHTML = this.images.map((image, index) => {
        const src = typeof image === 'string' ? image : image.src || image.url || image.thumbnail;
        const isActive = index === this.currentIndex;
        return `<img class="lightbox-thumbnail ${isActive ? 'active' : ''}" src="${src}" data-index="${index}" alt="">`;
      }).join('');

      // Bind thumbnail clicks
      this.elements.thumbnails.querySelectorAll('.lightbox-thumbnail').forEach(thumb => {
        thumb.addEventListener('click', () => {
          const index = parseInt(thumb.dataset.index, 10);
          this.goTo(index);
        });
      });
    }

    updateActiveThumbnail() {
      this.elements.thumbnails.querySelectorAll('.lightbox-thumbnail').forEach((thumb, index) => {
        thumb.classList.toggle('active', index === this.currentIndex);
      });
    }

    prev() {
      if (this.currentIndex > 0) {
        this.currentIndex--;
      } else if (this.options.loop) {
        this.currentIndex = this.images.length - 1;
      } else {
        return;
      }
      this.loadImage();
      this.updateActiveThumbnail();
    }

    next() {
      if (this.currentIndex < this.images.length - 1) {
        this.currentIndex++;
      } else if (this.options.loop) {
        this.currentIndex = 0;
      } else {
        return;
      }
      this.loadImage();
      this.updateActiveThumbnail();
    }

    goTo(index) {
      if (index >= 0 && index < this.images.length) {
        this.currentIndex = index;
        this.loadImage();
        this.updateActiveThumbnail();
      }
    }

    toggleZoom() {
      if (!this.options.enableZoom) return;
      
      this.isZoomed = !this.isZoomed;
      this.elements.content.classList.toggle('zoomed', this.isZoomed);
      
      if (this.elements.zoom) {
        this.elements.zoom.innerHTML = this.isZoomed ? icons.zoomOut : icons.zoomIn;
      }
    }

    download() {
      const image = this.images[this.currentIndex];
      const src = typeof image === 'string' ? image : image.src || image.url;
      const filename = src.split('/').pop() || 'image.jpg';

      const link = document.createElement('a');
      link.href = src;
      link.download = filename;
      link.target = '_blank';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }

    destroy() {
      if (this.overlay) {
        this.overlay.remove();
      }
      this.images = [];
      this.isOpen = false;
    }
  }

  /**
   * Auto-init for data attributes
   */
  function initLightboxGalleries() {
    // Find all lightbox triggers
    const triggers = document.querySelectorAll('[data-lightbox]');
    const galleries = {};

    triggers.forEach(trigger => {
      const galleryId = trigger.dataset.lightbox || 'default';
      
      if (!galleries[galleryId]) {
        galleries[galleryId] = {
          lightbox: new Lightbox(),
          images: []
        };
      }

      const src = trigger.dataset.src || trigger.href || trigger.src;
      const caption = trigger.dataset.caption || trigger.title || '';
      
      galleries[galleryId].images.push({ src, caption });
      const imageIndex = galleries[galleryId].images.length - 1;

      trigger.addEventListener('click', (e) => {
        e.preventDefault();
        galleries[galleryId].lightbox.open(galleries[galleryId].images, imageIndex);
      });
    });
  }

  // Auto-init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLightboxGalleries);
  } else {
    initLightboxGalleries();
  }

  // Export to window
  window.Lightbox = Lightbox;
  window.initLightboxGalleries = initLightboxGalleries;

})(window);
