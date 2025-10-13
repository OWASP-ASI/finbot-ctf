/**
 * FinBot API Client
 * Common JavaScript utilities for making API calls across all apps
 */

class FinBotAPI {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
        this.defaultHeaders = {
            'Content-Type': 'application/json',
        };
    }

    /**
     * Get CSRF token from meta tag or cookie
     */
    getCSRFToken() {
        // Try to get from meta tag first
        const metaToken = document.querySelector('meta[name="csrf-token"]');
        if (metaToken) {
            return metaToken.getAttribute('content');
        }

        // Fallback to cookie
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrf_token') {
                return decodeURIComponent(value);
            }
        }

        return null;
    }

    /**
     * Make HTTP request with error handling
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;

        // Merge headers
        const headers = {
            ...this.defaultHeaders,
            ...options.headers
        };

        // Add CSRF token for non-GET requests
        if (options.method && options.method !== 'GET') {
            const csrfToken = this.getCSRFToken();
            if (csrfToken) {
                headers['X-CSRF-Token'] = csrfToken;
            }
        }

        const config = {
            credentials: 'same-origin', // Include cookies
            ...options,
            headers
        };

        try {
            const response = await fetch(url, config);

            // Handle different response types
            const contentType = response.headers.get('content-type');
            let data;

            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                data = await response.text();
            }

            if (!response.ok) {
                throw new APIError(
                    data.message || `HTTP ${response.status}: ${response.statusText}`,
                    response.status,
                    data
                );
            }

            return {
                data,
                status: response.status,
                headers: response.headers
            };
        } catch (error) {
            if (error instanceof APIError) {
                throw error;
            }

            // Network or other errors
            throw new APIError(
                error.message || 'Network error occurred',
                0,
                null
            );
        }
    }

    /**
     * GET request
     */
    async get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;

        return this.request(url, {
            method: 'GET'
        });
    }

    /**
     * POST request
     */
    async post(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    /**
     * PUT request
     */
    async put(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    /**
     * DELETE request
     */
    async delete(endpoint) {
        return this.request(endpoint, {
            method: 'DELETE'
        });
    }

    /**
     * Upload file(s)
     */
    async upload(endpoint, formData) {
        // Don't set Content-Type for FormData, let browser set it
        const headers = { ...this.defaultHeaders };
        delete headers['Content-Type'];

        return this.request(endpoint, {
            method: 'POST',
            headers,
            body: formData
        });
    }

    /**
     * Download file
     */
    async download(endpoint, filename = null) {
        const response = await this.request(endpoint, {
            method: 'GET'
        });

        // Create blob and download
        const blob = new Blob([response.data]);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || 'download';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        return response;
    }
}

/**
 * Custom API Error class
 */
class APIError extends Error {
    constructor(message, status, data) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.data = data;
    }

    /**
     * Check if error is due to authentication
     */
    isAuthError() {
        return this.status === 401 || this.status === 403;
    }

    /**
     * Check if error is due to validation
     */
    isValidationError() {
        return this.status === 422 || this.status === 400;
    }

    /**
     * Check if error is server error
     */
    isServerError() {
        return this.status >= 500;
    }
}

/**
 * Global API instance
 */
const api = new FinBotAPI();

/**
 * Form submission helper
 */
function submitForm(form, options = {}) {
    return new Promise((resolve, reject) => {
        const formData = new FormData(form);
        const method = form.method || 'POST';
        const action = form.action || window.location.pathname;

        // Convert FormData to JSON if specified
        let body;
        if (options.json) {
            const data = {};
            formData.forEach((value, key) => {
                data[key] = value;
            });
            body = JSON.stringify(data);
        } else {
            body = formData;
        }

        const headers = options.json ? { 'Content-Type': 'application/json' } : {};

        api.request(action, {
            method: method.toUpperCase(),
            headers,
            body
        })
            .then(resolve)
            .catch(reject);
    });
}

/**
 * Show loading state on element
 */
function showLoading(element, text = 'Loading...') {
    element.classList.add('loading');
    const originalText = element.textContent;
    element.textContent = text;
    element.disabled = true;

    return () => {
        element.classList.remove('loading');
        element.textContent = originalText;
        element.disabled = false;
    };
}

/**
 * Handle API errors globally
 */
function handleAPIError(error, options = {}) {
    console.error('API Error:', error);

    if (error.isAuthError()) {
        if (options.redirectOnAuth !== false) {
            window.location.href = '/login';
            return;
        }
    }

    // Show user-friendly error message
    const message = error.data?.message || error.message || 'An error occurred';

    if (options.showAlert !== false) {
        showAlert(message, 'danger');
    }

    return message;
}

/**
 * Show alert message
 */
function showAlert(message, type = 'info', duration = 5000) {
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="alert-close" onclick="this.parentElement.remove()">
            <span>&times;</span>
        </button>
    `;

    // Insert at top of main content or body
    const target = document.querySelector('.main-content') || document.body;
    target.insertBefore(alert, target.firstChild);

    // Auto-remove after duration
    if (duration > 0) {
        setTimeout(() => {
            if (alert.parentElement) {
                alert.remove();
            }
        }, duration);
    }
}

// Export for use in other modules
window.FinBotAPI = FinBotAPI;
window.APIError = APIError;
window.api = api;
window.submitForm = submitForm;
window.showLoading = showLoading;
window.handleAPIError = handleAPIError;
window.showAlert = showAlert;
