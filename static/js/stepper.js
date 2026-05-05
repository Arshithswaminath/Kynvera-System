/**
 * Injaaz Form Stepper Component
 * Interactive step-by-step form navigation
 * Version: 1.0.0
 */

(function(window) {
  'use strict';

  /**
   * Stepper Class
   */
  class Stepper {
    constructor(element, options = {}) {
      this.element = typeof element === 'string' ? document.querySelector(element) : element;
      
      if (!this.element) {
        console.error('Stepper: Element not found');
        return;
      }

      this.options = {
        currentStep: 0,
        clickable: false,
        animated: true,
        onStepChange: null,
        onComplete: null,
        validateStep: null,
        ...options
      };

      this.steps = [];
      this.currentStep = this.options.currentStep;
      
      this.init();
    }

    init() {
      this.parseSteps();
      this.render();
      this.bindEvents();
      this.goToStep(this.currentStep);
    }

    parseSteps() {
      // Check if steps are provided in options
      if (this.options.steps && Array.isArray(this.options.steps)) {
        this.steps = this.options.steps.map((step, index) => ({
          id: step.id || `step-${index}`,
          title: step.title || `Step ${index + 1}`,
          description: step.description || '',
          icon: step.icon || null,
          completed: step.completed || false,
          error: step.error || false
        }));
      } else {
        // Parse from existing DOM
        const stepElements = this.element.querySelectorAll('.stepper-step');
        this.steps = Array.from(stepElements).map((el, index) => ({
          id: el.dataset.stepId || `step-${index}`,
          title: el.querySelector('.step-title')?.textContent || `Step ${index + 1}`,
          description: el.querySelector('.step-description')?.textContent || '',
          icon: el.dataset.icon || null,
          completed: el.classList.contains('completed'),
          error: el.classList.contains('error')
        }));
      }
    }

    render() {
      const isVertical = this.element.classList.contains('stepper-vertical');
      const isCompact = this.element.classList.contains('stepper-compact');
      
      let html = '';
      
      this.steps.forEach((step, index) => {
        const isActive = index === this.currentStep;
        const isCompleted = step.completed || index < this.currentStep;
        const hasError = step.error;
        
        let stateClass = '';
        if (hasError) stateClass = 'error';
        else if (isActive) stateClass = 'active';
        else if (isCompleted) stateClass = 'completed';
        
        html += `
          <div class="stepper-step ${stateClass}" data-step="${index}">
            ${index > 0 ? `<div class="step-connector ${this.options.animated ? 'step-connector-animated' : ''}"></div>` : ''}
            <div class="step-indicator">
              <span class="step-number">${index + 1}</span>
              <span class="step-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </span>
            </div>
            <div class="step-content">
              <p class="step-title">${step.title}</p>
              ${step.description ? `<p class="step-description">${step.description}</p>` : ''}
            </div>
          </div>
        `;
      });
      
      this.element.innerHTML = html;
    }

    bindEvents() {
      if (this.options.clickable) {
        this.element.addEventListener('click', (e) => {
          const stepEl = e.target.closest('.stepper-step');
          if (stepEl && !stepEl.classList.contains('disabled')) {
            const stepIndex = parseInt(stepEl.dataset.step, 10);
            this.goToStep(stepIndex);
          }
        });
      }
    }

    async goToStep(index) {
      if (index < 0 || index >= this.steps.length) return;
      
      // Validate current step before moving forward
      if (index > this.currentStep && this.options.validateStep) {
        const isValid = await this.options.validateStep(this.currentStep);
        if (!isValid) {
          this.setStepError(this.currentStep, true);
          return false;
        }
        this.setStepError(this.currentStep, false);
      }
      
      // Mark previous steps as completed when moving forward
      if (index > this.currentStep) {
        for (let i = this.currentStep; i < index; i++) {
          this.steps[i].completed = true;
        }
      }
      
      const previousStep = this.currentStep;
      this.currentStep = index;
      
      this.updateUI();
      
      if (this.options.onStepChange) {
        this.options.onStepChange(index, previousStep);
      }
      
      // Check if completed
      if (index === this.steps.length - 1 && this.options.onComplete) {
        this.options.onComplete();
      }
      
      return true;
    }

    next() {
      return this.goToStep(this.currentStep + 1);
    }

    previous() {
      return this.goToStep(this.currentStep - 1);
    }

    complete() {
      this.steps.forEach(step => step.completed = true);
      this.updateUI();
      if (this.options.onComplete) {
        this.options.onComplete();
      }
    }

    reset() {
      this.steps.forEach(step => {
        step.completed = false;
        step.error = false;
      });
      this.currentStep = 0;
      this.updateUI();
    }

    setStepError(index, hasError) {
      if (index >= 0 && index < this.steps.length) {
        this.steps[index].error = hasError;
        this.updateUI();
      }
    }

    setStepCompleted(index, isCompleted) {
      if (index >= 0 && index < this.steps.length) {
        this.steps[index].completed = isCompleted;
        this.updateUI();
      }
    }

    updateUI() {
      const stepElements = this.element.querySelectorAll('.stepper-step');
      
      stepElements.forEach((el, index) => {
        const step = this.steps[index];
        const isActive = index === this.currentStep;
        const isCompleted = step.completed || index < this.currentStep;
        
        el.classList.remove('active', 'completed', 'error');
        
        if (step.error) {
          el.classList.add('error');
        } else if (isActive) {
          el.classList.add('active');
        } else if (isCompleted) {
          el.classList.add('completed');
        }
      });
    }

    getCurrentStep() {
      return this.currentStep;
    }

    getStepsCount() {
      return this.steps.length;
    }

    getProgress() {
      const completedCount = this.steps.filter(s => s.completed).length;
      return Math.round((completedCount / this.steps.length) * 100);
    }

    destroy() {
      this.element.innerHTML = '';
      this.steps = [];
    }
  }

  /**
   * Progress Bar Stepper
   */
  class ProgressStepper {
    constructor(element, options = {}) {
      this.element = typeof element === 'string' ? document.querySelector(element) : element;
      
      if (!this.element) {
        console.error('ProgressStepper: Element not found');
        return;
      }

      this.options = {
        steps: [],
        currentStep: 0,
        title: 'Progress',
        showStepLabels: true,
        ...options
      };

      this.currentStep = this.options.currentStep;
      this.init();
    }

    init() {
      this.render();
      this.updateProgress();
    }

    render() {
      const { steps, title, showStepLabels } = this.options;
      
      let stepsHtml = '';
      if (showStepLabels && steps.length > 0) {
        stepsHtml = `
          <div class="stepper-progress-steps">
            ${steps.map((step, index) => `
              <span class="stepper-progress-step ${index < this.currentStep ? 'completed' : ''} ${index === this.currentStep ? 'active' : ''}">${step}</span>
            `).join('')}
          </div>
        `;
      }

      this.element.innerHTML = `
        <div class="stepper-progress-header">
          <span class="stepper-progress-title">${title}</span>
          <span class="stepper-progress-count">${this.currentStep + 1} of ${steps.length}</span>
        </div>
        <div class="stepper-progress-bar">
          <div class="stepper-progress-fill"></div>
        </div>
        ${stepsHtml}
      `;
    }

    updateProgress() {
      const fill = this.element.querySelector('.stepper-progress-fill');
      const count = this.element.querySelector('.stepper-progress-count');
      const stepLabels = this.element.querySelectorAll('.stepper-progress-step');
      
      const progress = ((this.currentStep + 1) / this.options.steps.length) * 100;
      
      if (fill) {
        fill.style.width = `${progress}%`;
      }
      
      if (count) {
        count.textContent = `${this.currentStep + 1} of ${this.options.steps.length}`;
      }
      
      stepLabels.forEach((label, index) => {
        label.classList.remove('completed', 'active');
        if (index < this.currentStep) {
          label.classList.add('completed');
        } else if (index === this.currentStep) {
          label.classList.add('active');
        }
      });
    }

    setStep(index) {
      if (index >= 0 && index < this.options.steps.length) {
        this.currentStep = index;
        this.updateProgress();
      }
    }

    next() {
      this.setStep(this.currentStep + 1);
    }

    previous() {
      this.setStep(this.currentStep - 1);
    }

    getProgress() {
      return Math.round(((this.currentStep + 1) / this.options.steps.length) * 100);
    }
  }

  // Export to window
  window.Stepper = Stepper;
  window.ProgressStepper = ProgressStepper;

})(window);
