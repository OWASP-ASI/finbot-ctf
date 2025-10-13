/**
 * FinBot Common Utilities
 * Shared JavaScript utilities across all apps
 */

/**
 * DOM Ready utility
 */
function ready(fn) {
    if (document.readyState !== 'loading') {
        fn();
    } else {
        document.addEventListener('DOMContentLoaded', fn);
    }
}

/**
 * Debounce function calls
 */
function debounce(func, wait, immediate = false) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            timeout = null;
            if (!immediate) func.apply(this, args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(this, args);
    };
}

/**
 * Throttle function calls
 */
function throttle(func, limit) {
    let inThrottle;
    return function (...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Format currency
 */
function formatCurrency(amount, currency = 'USD', locale = 'en-US') {
    return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}

/**
 * Format number with commas
 */
function formatNumber(number, decimals = 0) {
    return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(number);
}

/**
 * Format date
 */
function formatDate(date, options = {}) {
    const defaultOptions = {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    };

    const formatOptions = { ...defaultOptions, ...options };
    return new Intl.DateTimeFormat('en-US', formatOptions).format(new Date(date));
}

/**
 * Format relative time (e.g., "2 hours ago")
 */
function formatRelativeTime(date) {
    const now = new Date();
    const diffInSeconds = Math.floor((now - new Date(date)) / 1000);

    const intervals = {
        year: 31536000,
        month: 2592000,
        week: 604800,
        day: 86400,
        hour: 3600,
        minute: 60
    };

    for (const [unit, seconds] of Object.entries(intervals)) {
        const interval = Math.floor(diffInSeconds / seconds);
        if (interval >= 1) {
            return `${interval} ${unit}${interval > 1 ? 's' : ''} ago`;
        }
    }

    return 'Just now';
}

/**
 * Validate email address
 */
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * Validate password strength
 */
function validatePassword(password) {
    const result = {
        isValid: false,
        score: 0,
        feedback: []
    };

    if (password.length < 8) {
        result.feedback.push('Password must be at least 8 characters long');
    } else {
        result.score += 1;
    }

    if (!/[a-z]/.test(password)) {
        result.feedback.push('Password must contain at least one lowercase letter');
    } else {
        result.score += 1;
    }

    if (!/[A-Z]/.test(password)) {
        result.feedback.push('Password must contain at least one uppercase letter');
    } else {
        result.score += 1;
    }

    if (!/\d/.test(password)) {
        result.feedback.push('Password must contain at least one number');
    } else {
        result.score += 1;
    }

    if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
        result.feedback.push('Password should contain at least one special character');
    } else {
        result.score += 1;
    }

    result.isValid = result.score >= 4;
    return result;
}

/**
 * Generate random ID
 */
function generateId(prefix = 'id', length = 8) {
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let result = prefix + '-';
    for (let i = 0; i < length; i++) {
        result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
}

/**
 * Copy text to clipboard
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (err) {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();

        try {
            document.execCommand('copy');
            textArea.remove();
            return true;
        } catch (err) {
            textArea.remove();
            return false;
        }
    }
}

/**
 * Smooth scroll to element
 */
function scrollToElement(element, offset = 0) {
    const targetElement = typeof element === 'string'
        ? document.querySelector(element)
        : element;

    if (!targetElement) return;

    const elementPosition = targetElement.getBoundingClientRect().top;
    const offsetPosition = elementPosition + window.pageYOffset - offset;

    window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth'
    });
}

/**
 * Check if element is in viewport
 */
function isInViewport(element, threshold = 0) {
    const rect = element.getBoundingClientRect();
    const windowHeight = window.innerHeight || document.documentElement.clientHeight;
    const windowWidth = window.innerWidth || document.documentElement.clientWidth;

    return (
        rect.top >= -threshold &&
        rect.left >= -threshold &&
        rect.bottom <= windowHeight + threshold &&
        rect.right <= windowWidth + threshold
    );
}

/**
 * Local storage helpers with JSON support
 */
const storage = {
    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
            return true;
        } catch (e) {
            console.error('Failed to save to localStorage:', e);
            return false;
        }
    },

    get(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (e) {
            console.error('Failed to read from localStorage:', e);
            return defaultValue;
        }
    },

    remove(key) {
        try {
            localStorage.removeItem(key);
            return true;
        } catch (e) {
            console.error('Failed to remove from localStorage:', e);
            return false;
        }
    },

    clear() {
        try {
            localStorage.clear();
            return true;
        } catch (e) {
            console.error('Failed to clear localStorage:', e);
            return false;
        }
    }
};

/**
 * URL helpers
 */
const url = {
    getParam(name) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(name);
    },

    setParam(name, value) {
        const urlParams = new URLSearchParams(window.location.search);
        urlParams.set(name, value);
        const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
        window.history.replaceState({}, '', newUrl);
    },

    removeParam(name) {
        const urlParams = new URLSearchParams(window.location.search);
        urlParams.delete(name);
        const newUrl = urlParams.toString()
            ? `${window.location.pathname}?${urlParams.toString()}`
            : window.location.pathname;
        window.history.replaceState({}, '', newUrl);
    }
};

/**
 * Device detection
 */
const device = {
    isMobile() {
        return window.innerWidth <= 768;
    },

    isTablet() {
        return window.innerWidth > 768 && window.innerWidth <= 1024;
    },

    isDesktop() {
        return window.innerWidth > 1024;
    },

    isTouchDevice() {
        return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    }
};

/**
 * Form validation helpers
 */
function validateForm(form) {
    const errors = {};
    const formData = new FormData(form);

    // Get all form fields
    const fields = form.querySelectorAll('input, select, textarea');

    fields.forEach(field => {
        const value = formData.get(field.name);
        const fieldErrors = [];

        // Required validation
        if (field.hasAttribute('required') && (!value || value.trim() === '')) {
            fieldErrors.push(`${field.name} is required`);
        }

        // Email validation
        if (field.type === 'email' && value && !isValidEmail(value)) {
            fieldErrors.push('Please enter a valid email address');
        }

        // Password validation
        if (field.type === 'password' && value) {
            const passwordValidation = validatePassword(value);
            if (!passwordValidation.isValid) {
                fieldErrors.push(...passwordValidation.feedback);
            }
        }

        // Min/Max length validation
        if (field.minLength && value && value.length < field.minLength) {
            fieldErrors.push(`${field.name} must be at least ${field.minLength} characters`);
        }

        if (field.maxLength && value && value.length > field.maxLength) {
            fieldErrors.push(`${field.name} must be no more than ${field.maxLength} characters`);
        }

        if (fieldErrors.length > 0) {
            errors[field.name] = fieldErrors;
        }
    });

    return {
        isValid: Object.keys(errors).length === 0,
        errors
    };
}

// Export utilities to global scope
window.ready = ready;
window.debounce = debounce;
window.throttle = throttle;
window.formatCurrency = formatCurrency;
window.formatNumber = formatNumber;
window.formatDate = formatDate;
window.formatRelativeTime = formatRelativeTime;
window.isValidEmail = isValidEmail;
window.validatePassword = validatePassword;
window.generateId = generateId;
window.copyToClipboard = copyToClipboard;
window.scrollToElement = scrollToElement;
window.isInViewport = isInViewport;
window.storage = storage;
window.url = url;
window.device = device;
window.validateForm = validateForm;
