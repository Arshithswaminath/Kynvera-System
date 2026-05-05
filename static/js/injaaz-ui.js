/**
 * Injaaz UI - Unified JavaScript Components
 * Import this single file to get all UI interactions
 * Version: 1.0.0
 * 
 * Usage in templates:
 * <script src="{{ url_for('static', filename='js/injaaz-ui.js') }}" defer></script>
 */

// Import order matters - load dependencies first
document.addEventListener('DOMContentLoaded', function() {
  'use strict';

  // ============================================
  // UTILITY FUNCTIONS
  // ============================================
  
  /**
   * Generate unique ID
   */
  function generateId(prefix = 'ui') {
    return `${prefix}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Debounce function
   */
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  /**
   * Check if element is in viewport
   */
  function isInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
      rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
  }

  // ============================================
  // RIPPLE EFFECT
  // ============================================

  function createRipple(event) {
    const button = event.currentTarget;
    const ripple = document.createElement('span');
    const rect = button.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x = event.clientX - rect.left - size / 2;
    const y = event.clientY - rect.top - size / 2;

    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;
    ripple.className = 'ripple';

    button.appendChild(ripple);

    setTimeout(() => ripple.remove(), 600);
  }

  // Add ripple to all buttons with ripple class
  document.querySelectorAll('.btn-ripple, [data-ripple]').forEach(button => {
    button.style.position = 'relative';
    button.style.overflow = 'hidden';
    button.addEventListener('click', createRipple);
  });

  // ============================================
  // SCROLL REVEAL
  // ============================================

  const scrollRevealElements = document.querySelectorAll('.scroll-reveal');
  
  if (scrollRevealElements.length > 0) {
    const revealOnScroll = () => {
      scrollRevealElements.forEach(el => {
        if (isInViewport(el)) {
          el.classList.add('visible');
        }
      });
    };

    // Initial check
    revealOnScroll();
    
    // Check on scroll (debounced)
    window.addEventListener('scroll', debounce(revealOnScroll, 50));
  }

  // ============================================
  // STAGGER ANIMATION
  // ============================================

  const staggerContainers = document.querySelectorAll('.stagger-children');
  
  if (staggerContainers.length > 0) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('animate');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });

    staggerContainers.forEach(container => observer.observe(container));
  }

  // ============================================
  // DROPDOWN TOGGLE
  // ============================================

  document.querySelectorAll('.dropdown-toggle, [data-dropdown]').forEach(toggle => {
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      const dropdown = toggle.closest('.dropdown');
      if (dropdown) {
        dropdown.classList.toggle('active');
      }
    });
  });

  // Close dropdowns when clicking outside
  document.addEventListener('click', () => {
    document.querySelectorAll('.dropdown.active').forEach(dropdown => {
      dropdown.classList.remove('active');
    });
  });

  // ============================================
  // MODAL SYSTEM
  // ============================================

  window.InjaazModal = {
    open(modalId) {
      const backdrop = document.querySelector(`.modal-backdrop[data-modal="${modalId}"]`);
      const modal = document.getElementById(modalId);
      
      if (backdrop && modal) {
        backdrop.classList.add('active');
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
      }
    },
    
    close(modalId) {
      const backdrop = document.querySelector(`.modal-backdrop[data-modal="${modalId}"]`);
      const modal = document.getElementById(modalId);
      
      if (backdrop && modal) {
        backdrop.classList.remove('active');
        modal.classList.remove('active');
        document.body.style.overflow = '';
      }
    },
    
    closeAll() {
      document.querySelectorAll('.modal-backdrop.active').forEach(backdrop => {
        backdrop.classList.remove('active');
      });
      document.querySelectorAll('.modal.active').forEach(modal => {
        modal.classList.remove('active');
      });
      document.body.style.overflow = '';
    }
  };

  // Modal triggers
  document.querySelectorAll('[data-modal-open]').forEach(trigger => {
    trigger.addEventListener('click', (e) => {
      e.preventDefault();
      const modalId = trigger.dataset.modalOpen;
      InjaazModal.open(modalId);
    });
  });

  document.querySelectorAll('[data-modal-close]').forEach(trigger => {
    trigger.addEventListener('click', (e) => {
      e.preventDefault();
      const modalId = trigger.dataset.modalClose || trigger.closest('.modal')?.id;
      if (modalId) {
        InjaazModal.close(modalId);
      }
    });
  });

  // Close modal on backdrop click
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        const modalId = backdrop.dataset.modal;
        if (modalId) {
          InjaazModal.close(modalId);
        }
      }
    });
  });

  // Close modal on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      InjaazModal.closeAll();
    }
  });

  // ============================================
  // TABS
  // ============================================

  document.querySelectorAll('[data-tabs]').forEach(tabContainer => {
    const tabs = tabContainer.querySelectorAll('[data-tab]');
    const panels = tabContainer.querySelectorAll('[data-tab-panel]');
    
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const targetId = tab.dataset.tab;
        
        // Update tabs
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        
        // Update panels
        panels.forEach(panel => {
          panel.classList.toggle('active', panel.dataset.tabPanel === targetId);
        });
      });
    });
  });

  // ============================================
  // TOOLTIP
  // ============================================

  document.querySelectorAll('[data-tooltip]').forEach(element => {
    let tooltip = null;
    
    element.addEventListener('mouseenter', () => {
      const text = element.dataset.tooltip;
      const position = element.dataset.tooltipPosition || 'top';
      
      tooltip = document.createElement('div');
      tooltip.className = `tooltip-animate tooltip-${position}`;
      tooltip.textContent = text;
      tooltip.style.position = 'absolute';
      tooltip.style.background = 'var(--color-neutral-900)';
      tooltip.style.color = 'white';
      tooltip.style.padding = '4px 8px';
      tooltip.style.borderRadius = 'var(--radius-md)';
      tooltip.style.fontSize = 'var(--text-xs)';
      tooltip.style.whiteSpace = 'nowrap';
      tooltip.style.zIndex = 'var(--z-tooltip)';
      
      document.body.appendChild(tooltip);
      
      const rect = element.getBoundingClientRect();
      const tooltipRect = tooltip.getBoundingClientRect();
      
      let top, left;
      switch (position) {
        case 'bottom':
          top = rect.bottom + 8;
          left = rect.left + (rect.width - tooltipRect.width) / 2;
          break;
        case 'left':
          top = rect.top + (rect.height - tooltipRect.height) / 2;
          left = rect.left - tooltipRect.width - 8;
          break;
        case 'right':
          top = rect.top + (rect.height - tooltipRect.height) / 2;
          left = rect.right + 8;
          break;
        default: // top
          top = rect.top - tooltipRect.height - 8;
          left = rect.left + (rect.width - tooltipRect.width) / 2;
      }
      
      tooltip.style.top = `${top + window.scrollY}px`;
      tooltip.style.left = `${left}px`;
      
      requestAnimationFrame(() => tooltip.classList.add('show'));
    });
    
    element.addEventListener('mouseleave', () => {
      if (tooltip) {
        tooltip.remove();
        tooltip = null;
      }
    });
  });

  // ============================================
  // COUNT UP ANIMATION
  // ============================================

  window.countUp = function(element, target, duration = 1000) {
    const start = 0;
    const increment = target / (duration / 16);
    let current = start;
    
    const timer = setInterval(() => {
      current += increment;
      if (current >= target) {
        element.textContent = target.toLocaleString();
        clearInterval(timer);
      } else {
        element.textContent = Math.floor(current).toLocaleString();
      }
    }, 16);
  };

  // Auto count-up for elements with data-count-up
  document.querySelectorAll('[data-count-up]').forEach(element => {
    const target = parseInt(element.dataset.countUp, 10);
    const duration = parseInt(element.dataset.countDuration, 10) || 1000;
    
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          countUp(element, target, duration);
          observer.unobserve(element);
        }
      });
    }, { threshold: 0.5 });
    
    observer.observe(element);
  });

  // ============================================
  // FORM VALIDATION FEEDBACK
  // ============================================

  document.querySelectorAll('.form-input, .form-select, .form-textarea').forEach(input => {
    input.addEventListener('invalid', (e) => {
      e.preventDefault();
      input.classList.add('form-input-error');
    });
    
    input.addEventListener('input', () => {
      if (input.validity.valid) {
        input.classList.remove('form-input-error');
      }
    });
  });

  // ============================================
  // COPY TO CLIPBOARD
  // ============================================

  window.copyToClipboard = async function(text, button) {
    try {
      await navigator.clipboard.writeText(text);
      if (button) {
        const originalText = button.textContent;
        button.textContent = 'Copied!';
        setTimeout(() => {
          button.textContent = originalText;
        }, 2000);
      }
      return true;
    } catch (err) {
      console.error('Failed to copy:', err);
      return false;
    }
  };

  document.querySelectorAll('[data-copy]').forEach(button => {
    button.addEventListener('click', () => {
      const text = button.dataset.copy;
      copyToClipboard(text, button);
    });
  });

  // ============================================
  // INITIALIZE
  // ============================================

  console.log('✅ Injaaz UI initialized');
});

// Export for external use
window.InjaazUI = {
  version: '1.0.0',
  // Methods are attached in DOMContentLoaded
};
