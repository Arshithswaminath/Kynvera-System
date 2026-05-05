/**
 * Injaaz API Client
 * Shared module for making authenticated API requests with automatic token refresh
 */

(function(window) {
  'use strict';

  const ApiClient = {
    /**
     * Get the current access token from localStorage
     * @returns {string|null} The access token or null
     */
    getAccessToken: function() {
      return localStorage.getItem('access_token');
    },

    /**
     * Get the current refresh token from localStorage
     * @returns {string|null} The refresh token or null
     */
    getRefreshToken: function() {
      return localStorage.getItem('refresh_token');
    },

    /**
     * Clear all authentication tokens and user data
     */
    clearAuth: function() {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
    },

    /**
     * Redirect to login page
     * @param {string} message - Optional message to show
     */
    redirectToLogin: function(message) {
      if (message) {
        console.warn('Auth redirect:', message);
      }
      this.clearAuth();
      window.location.href = '/login';
    },

    /**
     * Refresh the access token using the refresh token
     * @returns {Promise<string|null>} New access token or null if refresh failed
     */
    refreshAccessToken: async function() {
      try {
        const headers = { 'Content-Type': 'application/json' };
        const refreshToken = this.getRefreshToken();
        /* Prefer Bearer refresh from localStorage; if missing, rely on httpOnly refresh_token_cookie
           (same-origin + credentials). Previous code returned null here → upload 401 on prod. */
        if (refreshToken) {
          headers['Authorization'] = 'Bearer ' + refreshToken;
        }

        const response = await fetch('/api/auth/refresh', {
          method: 'POST',
          headers: headers,
          credentials: 'include'
        });

        if (!response.ok) {
          if (response.status === 401 || response.status === 422) {
            console.warn('Refresh token expired or invalid');
            this.clearAuth();
          }
          return null;
        }

        const data = await response.json();
        if (data.access_token) {
          localStorage.setItem('access_token', data.access_token);
          if (data.refresh_token) {
            localStorage.setItem('refresh_token', data.refresh_token);
          }
          console.log('Access token refreshed successfully');
          return data.access_token;
        }
        return null;
      } catch (error) {
        console.error('Token refresh failed:', error);
        return null;
      }
    },

    /**
     * Make an authenticated fetch request with automatic token refresh on 401
     * @param {string} url - The URL to fetch
     * @param {Object} options - Fetch options (method, body, headers, etc.)
     * @param {boolean} autoRedirect - Whether to redirect to login on auth failure (default: true)
     * @returns {Promise<Response>} The fetch response
     */
    fetch: async function(url, options = {}, autoRedirect = true) {
      let token = this.getAccessToken();
      
      if (!token) {
        console.warn('No access token available');
        if (autoRedirect) {
          this.redirectToLogin('No access token');
        }
        return { ok: false, status: 401, json: async () => ({ error: 'No access token' }) };
      }

      const isFormData =
        typeof FormData !== 'undefined' && options.body instanceof FormData;
      let formDataEntries = null;
      if (isFormData && options.body instanceof FormData) {
        formDataEntries = Array.from(options.body.entries());
      }

      // Merge headers with authorization (omit Content-Type for multipart — browser sets boundary)
      const headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
      };
      if (isFormData) {
        delete headers['Content-Type'];
        delete headers['content-type'];
      }

      // Make initial request
      let response;
      try {
        response = await fetch(url, {
          ...options,
          headers,
          credentials: 'include'
        });
      } catch (error) {
        console.error('Fetch error:', error);
        throw error;
      }

      // If 401, try to refresh token and retry once
      if (response.status === 401) {
        console.log('Received 401, attempting token refresh...');
        const newToken = await this.refreshAccessToken();

        if (newToken) {
          console.log('Retrying request with new token');
          const retryHeaders = {
            ...options.headers,
            'Authorization': `Bearer ${newToken}`
          };
          if (isFormData) {
            delete retryHeaders['Content-Type'];
            delete retryHeaders['content-type'];
          }
          let retryBody = options.body;
          if (formDataEntries) {
            retryBody = new FormData();
            formDataEntries.forEach(function (pair) {
              retryBody.append(pair[0], pair[1]);
            });
          }
          response = await fetch(url, {
            ...options,
            body: retryBody,
            headers: retryHeaders,
            credentials: 'include'
          });
          // Stale/corrupt localStorage Bearer can still 401 while httpOnly access cookie is valid
          if (response.status !== 401) {
            return response;
          }
          localStorage.removeItem('access_token');
          const cookieHeaders = { ...options.headers };
          delete cookieHeaders['Authorization'];
          delete cookieHeaders['authorization'];
          if (isFormData) {
            delete cookieHeaders['Content-Type'];
            delete cookieHeaders['content-type'];
          }
          return fetch(url, {
            ...options,
            body: retryBody,
            headers: cookieHeaders,
            credentials: 'include'
          });
        }
        console.warn('Token refresh failed');
        if (autoRedirect) {
          this.redirectToLogin('Session expired');
        }
        return { ok: false, status: 401, json: async () => ({ error: 'Session expired' }) };
      }

      return response;
    },

    /**
     * Convenience method for GET requests
     * @param {string} url - The URL to fetch
     * @param {boolean} autoRedirect - Whether to redirect to login on auth failure
     * @returns {Promise<Response>}
     */
    get: async function(url, autoRedirect = true) {
      return this.fetch(url, { method: 'GET' }, autoRedirect);
    },

    /**
     * Convenience method for POST requests with JSON body
     * @param {string} url - The URL to post to
     * @param {Object} data - The data to send as JSON
     * @param {boolean} autoRedirect - Whether to redirect to login on auth failure
     * @returns {Promise<Response>}
     */
    post: async function(url, data = {}, autoRedirect = true) {
      return this.fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      }, autoRedirect);
    },

    /**
     * Convenience method for PUT requests with JSON body
     * @param {string} url - The URL to put to
     * @param {Object} data - The data to send as JSON
     * @param {boolean} autoRedirect - Whether to redirect to login on auth failure
     * @returns {Promise<Response>}
     */
    put: async function(url, data = {}, autoRedirect = true) {
      return this.fetch(url, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      }, autoRedirect);
    },

    /**
     * Convenience method for DELETE requests
     * @param {string} url - The URL to delete
     * @param {boolean} autoRedirect - Whether to redirect to login on auth failure
     * @returns {Promise<Response>}
     */
    delete: async function(url, autoRedirect = true) {
      return this.fetch(url, { method: 'DELETE' }, autoRedirect);
    },

    /**
     * Check if user is authenticated (has valid token)
     * @returns {boolean}
     */
    isAuthenticated: function() {
      return !!this.getAccessToken();
    },

    /**
     * Get current user from localStorage
     * @returns {Object|null}
     */
    getCurrentUser: function() {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        try {
          return JSON.parse(userStr);
        } catch (e) {
          return null;
        }
      }
      return null;
    }
  };

  // Export to window for global access
  window.ApiClient = ApiClient;

  // Also export convenience functions for backward compatibility
  window.authenticatedFetch = function(url, options, autoRedirect) {
    return ApiClient.fetch(url, options, autoRedirect);
  };

  window.refreshAccessToken = function() {
    return ApiClient.refreshAccessToken();
  };

})(window);
