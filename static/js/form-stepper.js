/**
 * Injaaz Form Stepper Component
 * Interactive progress indicator for multi-step forms
 * Version: 1.0.0
 */

(function(window) {
  'use strict';

  class FormStepper {
    /**
     * Create a new FormStepper instance
     * @param {Object} options - Configuration options
     */
    constructor(options = {}) {
      this.options = {
        container: options.container || null,
        steps: options.steps || [],
        currentStep: options.currentStep || 0,
        variant: options.variant || 'default', // default, compact, dots, progress
        orientation: options.orientation || 'horizontal', // horizontal, vertical
        clickable: options.clickable !== false,
        allowSkip: options.allowSkip || false,
        onStepChange: options.onStepChange || null,
        onComplete: options.onComplete || null
      };
      
      this.currentStep = this.options.currentStep;
      this.element = null;
      
      if (this.options.container) {
        this.render();
      }
    }

    /**
     * Render the stepper
     */
    render() {
      const container = typeof this.options.container === 'string' 
        ? document.querySelector(this.options.container)
        : this.options.container;
        
      if (!container) {
        console.error('FormStepper: Container not found');
        return;
      }
      
      // Clear existing content
      container.innerHTML = '';
      
      // Create stepper based on variant
      if (this.options.variant === 'progress') {
        this.element = this.createProgressVariant();
      } else {
        this.element = this.createStepperVariant();
      }
      
      container.appendChild(this.element);
      this.bindEvents();
    }

    /**
     * Create default/compact/dots stepper variant
     */
    createStepperVariant() {
      const stepper = document.createElement('div');
      stepper.className = this.getStepperClasses();
      stepper.setAttribute('role', 'navigation');
      stepper.setAttribute('aria-label', 'Form progress');
      
      this.options.steps.forEach((step, index) => {
        const stepEl = this.createStepElement(step, index);
        stepper.appendChild(stepEl);
      });
      
      return stepper;
    }

    /**
     * Create progress bar variant
     */
    createProgressVariant() {
      const wrapper = document.createElement('div');
      wrapper.className = 'stepper stepper-progress';
      
      const progress = (this.currentStep / (this.options.steps.length - 1)) * 100;
      const currentStepData = this.options.steps[this.currentStep];
      
      wrapper.innerHTML = `
        <div class="stepper-progress-bar">
          <div class="stepper-progress-fill" style="width: ${progress}%"></div>
        </div>
        <div class="stepper-progress-labels">
          <span class="stepper-progress-current">
            Step ${this.currentStep + 1}: ${currentStepData?.title || ''}
          </span>
          <span class="stepper-progress-total">
            ${this.currentStep + 1} of ${this.options.steps.length}
          </span>
        </div>
      `;
      
      return wrapper;
    }

    /**
     * Get stepper CSS classes
     */
    getStepperClasses() {
      const classes = ['stepper'];
      
      if (this.options.variant === 'compact') {
        classes.push('stepper-compact');
      } else if (this.options.variant === 'dots') {
        classes.push('stepper-dots');
      }
      
      if (this.options.orientation === 'vertical') {
        classes.push('stepper-vertical');
      }
      
      if (this.options.clickable) {
        classes.push('stepper-clickable');
      }
      
      return classes.join(' ');
    }

    /**
     * Create individual step element
     */
    createStepElement(step, index) {
      const stepEl = document.createElement('div');
      stepEl.className = 'stepper-step';
      stepEl.dataset.step = index;
      
      // Set state class
      if (index < this.currentStep) {
        stepEl.classList.add('completed');
      } else if (index === this.currentStep) {
        stepEl.classList.add('active');
      }
      
      if (step.error) {
        stepEl.classList.add('error');
      }
      
      if (!this.options.allowSkip && index > this.currentStep + 1) {
        stepEl.classList.add('disabled');
      }
      
      // Create indicator
      const indicator = document.createElement('div');
      indicator.className = 'stepper-indicator';
      indicator.innerHTML = `<span>${index + 1}</span>`;
      stepEl.appendChild(indicator);
      
      // Create content
      if (this.options.variant !== 'dots') {
        const content = document.createElement('div');
        content.className = 'stepper-content';
        
        const title = document.createElement('div');
        title.className = 'stepper-title';
        title.textContent = step.title || `Step ${index + 1}`;
        content.appendChild(title);
        
        if (step.description) {
          const desc = document.createElement('div');
          desc.className = 'stepper-description';
          desc.textContent = step.description;
          content.appendChild(desc);
        }
        
        stepEl.appendChild(content);
      }
      
      // Create connector (except for last step)
      if (index < this.options.steps.length - 1) {
        const connector = document.createElement('div');
        connector.className = 'stepper-connector';
        stepEl.appendChild(connector);
      }
      
      return stepEl;
    }

    /**
     * Bind event listeners
     */
    bindEvents() {
      if (!this.options.clickable || !this.element) return;
      
      const steps = this.element.querySelectorAll('.stepper-step');
      steps.forEach((step, index) => {
        step.addEventListener('click', () => {
          if (step.classList.contains('disabled')) return;
          
          // Only allow going back or forward by one if allowSkip is false
          if (!this.options.allowSkip && index > this.currentStep + 1) return;
          
          this.goTo(index);
        });
      });
    }

    /**
     * Go to specific step
     */
    goTo(stepIndex) {
      if (stepIndex < 0 || stepIndex >= this.options.steps.length) return;
      if (stepIndex === this.currentStep) return;
      
      const previousStep = this.currentStep;
      this.currentStep = stepIndex;
      
      // Re-render
      this.render();
      
      // Callback
      if (this.options.onStepChange) {
        this.options.onStepChange({
          previous: previousStep,
          current: this.currentStep,
          step: this.options.steps[this.currentStep]
        });
      }
      
      // Check completion
      if (this.currentStep === this.options.steps.length - 1 && this.options.onComplete) {
        this.options.onComplete();
      }
    }

    /**
     * Go to next step
     */
    next() {
      this.goTo(this.currentStep + 1);
    }

    /**
     * Go to previous step
     */
    prev() {
      this.goTo(this.currentStep - 1);
    }

    /**
     * Mark current step as completed and go to next
     */
    complete() {
      if (this.currentStep < this.options.steps.length - 1) {
        this.next();
      }
    }

    /**
     * Mark step as error
     */
    setError(stepIndex, hasError = true) {
      if (stepIndex >= 0 && stepIndex < this.options.steps.length) {
        this.options.steps[stepIndex].error = hasError;
        this.render();
      }
    }

    /**
     * Get current step index
     */
    getCurrentStep() {
      return this.currentStep;
    }

    /**
     * Get current step data
     */
    getCurrentStepData() {
      return this.options.steps[this.currentStep];
    }

    /**
     * Check if at first step
     */
    isFirst() {
      return this.currentStep === 0;
    }

    /**
     * Check if at last step
     */
    isLast() {
      return this.currentStep === this.options.steps.length - 1;
    }

    /**
     * Get progress percentage
     */
    getProgress() {
      return Math.round((this.currentStep / (this.options.steps.length - 1)) * 100);
    }

    /**
     * Update steps configuration
     */
    setSteps(steps) {
      this.options.steps = steps;
      if (this.currentStep >= steps.length) {
        this.currentStep = steps.length - 1;
      }
      this.render();
    }

    /**
     * Destroy the stepper
     */
    destroy() {
      if (this.element && this.element.parentNode) {
        this.element.parentNode.removeChild(this.element);
      }
      this.element = null;
    }
  }

  /**
   * Create stepper from existing Bootstrap tabs
   */
  function createFromTabs(tabContainer, stepperContainer, options = {}) {
    const tabs = tabContainer.querySelectorAll('[data-bs-toggle="tab"], .nav-link');
    const steps = Array.from(tabs).map((tab, index) => ({
      title: tab.textContent.trim(),
      id: tab.getAttribute('href') || tab.dataset.bsTarget
    }));
    
    const stepper = new FormStepper({
      container: stepperContainer,
      steps,
      currentStep: 0,
      ...options,
      onStepChange: (event) => {
        // Sync with Bootstrap tabs
        const targetTab = tabs[event.current];
        if (targetTab) {
          const bsTab = new bootstrap.Tab(targetTab);
          bsTab.show();
        }
        if (options.onStepChange) {
          options.onStepChange(event);
        }
      }
    });
    
    // Sync stepper when tabs change
    tabs.forEach((tab, index) => {
      tab.addEventListener('shown.bs.tab', () => {
        if (stepper.getCurrentStep() !== index) {
          stepper.currentStep = index;
          stepper.render();
        }
      });
    });
    
    return stepper;
  }

  // Export
  window.FormStepper = FormStepper;
  window.FormStepper.createFromTabs = createFromTabs;

})(window);
