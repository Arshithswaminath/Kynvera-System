/**
 * PhotoUploadQueue - Optimistic UI with background upload queue
 * Handles concurrent uploads with retry logic and progress tracking
 */
class PhotoUploadQueue {
  constructor(options = {}) {
    this.maxConcurrent = options.maxConcurrent || 3;
    this.uploadEndpoint = options.uploadEndpoint || '/upload-photo';
    this.onProgress = options.onProgress || (() => {});
    this.onItemComplete = options.onItemComplete || (() => {});
    this.onQueueComplete = options.onQueueComplete || options.onComplete || (() => {}); // Support both names
    this.onError = options.onError || (() => {});
    
    this.queue = [];
    this.activeUploads = 0;
    this.completed = 0;
    this.failed = 0;
    this.total = 0;
  }

  /**
   * Add photos to the upload queue
   * @param {FileList|Array} files - Files to upload
   * @param {Object} metadata - Additional metadata for each upload
   * @returns {Array} Array of photo items with preview and status
   */
  addPhotos(files, metadata = {}) {
    const photoItems = [];
    
    Array.from(files).forEach((file, index) => {
      // Create preview immediately (optimistic UI)
      const preview = URL.createObjectURL(file);
      
      const item = {
        id: `photo_${Date.now()}_${index}`,
        file: file,
        preview: preview,
        status: 'queued', // queued, uploading, completed, failed
        progress: 0,
        url: null,
        error: null,
        metadata: metadata,
        retryCount: 0
      };
      
      this.queue.push(item);
      photoItems.push(item);
      this.total++;
    });
    
    this.processQueue();
    return photoItems;
  }

  /**
   * Process the upload queue with concurrent limit
   */
  async processQueue() {
    while (this.activeUploads < this.maxConcurrent && this.queue.length > 0) {
      const item = this.queue.find(i => i.status === 'queued');
      if (!item) break;
      
      this.activeUploads++;
      item.status = 'uploading';
      this.notifyProgress();
      
      this.uploadPhoto(item)
        .then((response) => {
          this.activeUploads--;
          this.completed++;
          item.status = 'completed';
          item.progress = 100;
          // Update URL from response if available
          if (response && response.url) {
            item.url = response.url;
          }
          // Notify item completion (for UI updates)
          this.onItemComplete(item, true);
          // Notify progress update
          this.notifyProgress();
          // Continue processing queue
          this.processQueue();
          // Check if all done
          this.checkComplete();
        })
        .catch((error) => {
          this.activeUploads--;
          this.failed++;
          item.status = 'failed';
          item.error = error.message || 'Upload failed';
          item.progress = 0;
          // Notify error callback
          if (this.onError) this.onError(error);
          // Notify item completion (for UI updates)
          this.onItemComplete(item, false);
          // Notify progress update
          this.notifyProgress();
          // Continue processing queue
          this.processQueue();
          // Check if all done
          this.checkComplete();
        });
    }
  }

  /**
   * Upload a single photo
   * @param {Object} item - Photo item to upload
   * @returns {Promise}
   */
  async uploadPhoto(item) {
    const formData = new FormData();
    formData.append('photo', item.file);
    
    // Add any metadata
    if (item.metadata) {
      Object.keys(item.metadata).forEach(key => {
        formData.append(key, item.metadata[key]);
      });
    }

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      
      // Track upload progress
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          item.progress = Math.round((e.loaded / e.total) * 100);
          this.notifyProgress();
        }
      });
      
      xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
          try {
            const response = JSON.parse(xhr.responseText);
            if (response.success && response.url) {
              item.url = response.url;
              item.progress = 100;
              resolve(response);
            } else {
              reject(new Error(response.error || 'Upload failed'));
            }
          } catch (e) {
            reject(new Error('Invalid response from server'));
          }
        } else {
          reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
        }
      });
      
      xhr.addEventListener('error', () => {
        reject(new Error('Network error'));
      });
      
      xhr.addEventListener('timeout', () => {
        reject(new Error('Upload timeout'));
      });
      
      xhr.open('POST', this.uploadEndpoint);
      xhr.timeout = 60000; // 60 second timeout
      xhr.send(formData);
    });
  }

  /**
   * Retry a failed upload
   * @param {String} itemId - ID of the item to retry
   */
  retryUpload(itemId) {
    const item = this.queue.find(i => i.id === itemId);
    if (!item || item.status !== 'failed') return;
    
    item.status = 'queued';
    item.progress = 0;
    item.error = null;
    item.retryCount++;
    this.failed--;
    
    this.notifyProgress();
    this.processQueue();
  }

  /**
   * Retry all failed uploads
   */
  retryAllFailed() {
    const failedItems = this.queue.filter(i => i.status === 'failed');
    failedItems.forEach(item => {
      item.status = 'queued';
      item.progress = 0;
      item.error = null;
      item.retryCount++;
    });
    
    this.failed = 0;
    this.notifyProgress();
    this.processQueue();
  }

  /**
   * Remove a photo from the queue
   * @param {String} itemId - ID of the item to remove
   */
  removePhoto(itemId) {
    const index = this.queue.findIndex(i => i.id === itemId);
    if (index === -1) return;
    
    const item = this.queue[index];
    
    // Revoke blob URL to free memory
    if (item.preview && item.preview.startsWith('blob:')) {
      URL.revokeObjectURL(item.preview);
    }
    
    // Update counters
    if (item.status === 'completed') this.completed--;
    else if (item.status === 'failed') this.failed--;
    this.total--;
    
    this.queue.splice(index, 1);
    this.notifyProgress();
  }

  /**
   * Get all uploaded photo URLs
   * @returns {Array} Array of successfully uploaded URLs
   */
  getUploadedUrls() {
    return this.queue
      .filter(item => item.status === 'completed' && item.url)
      .map(item => ({ url: item.url, id: item.id }));
  }

  /**
   * Get queue statistics
   * @returns {Object} Statistics about the queue
   */
  getStats() {
    return {
      total: this.total,
      completed: this.completed,
      failed: this.failed,
      uploading: this.queue.filter(i => i.status === 'uploading').length,
      queued: this.queue.filter(i => i.status === 'queued').length,
      isComplete: this.isComplete()
    };
  }

  /**
   * Check if all uploads are complete
   * @returns {Boolean}
   */
  isComplete() {
    return this.total > 0 && 
           (this.completed + this.failed) === this.total &&
           this.activeUploads === 0;
  }

  /**
   * Notify progress callback
   */
  notifyProgress() {
    this.onProgress(this.getStats());
  }

  /**
   * Check if queue is complete and notify
   */
  checkComplete() {
    if (this.isComplete()) {
      this.onQueueComplete(this.getStats());
    }
  }

  /**
   * Clear all completed items
   */
  clearCompleted() {
    const completed = this.queue.filter(i => i.status === 'completed');
    completed.forEach(item => {
      if (item.preview && item.preview.startsWith('blob:')) {
        URL.revokeObjectURL(item.preview);
      }
    });
    
    this.queue = this.queue.filter(i => i.status !== 'completed');
    this.completed = 0;
    this.total = this.queue.length;
    this.notifyProgress();
  }

  /**
   * Reset the entire queue
   */
  reset() {
    // Revoke all blob URLs
    this.queue.forEach(item => {
      if (item.preview && item.preview.startsWith('blob:')) {
        URL.revokeObjectURL(item.preview);
      }
    });
    
    this.queue = [];
    this.activeUploads = 0;
    this.completed = 0;
    this.failed = 0;
    this.total = 0;
    this.notifyProgress();
  }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PhotoUploadQueue;
}

// Make available globally
if (typeof window !== 'undefined') {
  window.PhotoUploadQueue = PhotoUploadQueue;
}