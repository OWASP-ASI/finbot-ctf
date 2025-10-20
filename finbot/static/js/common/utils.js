/**
 * FinBot Common Utilities
 * Shared JavaScript utilities across all apps
 * Contains reusable utility functions for DOM manipulation, formatting, validation, etc.
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
 * Validate TIN/EIN (Tax Identification Number/Employer Identification Number)
 * Supports both formats: XX-XXXXXXX and XXXXXXXXX
 */
function validateTIN(tin) {
    if (!tin) return { isValid: false, message: 'TIN/EIN is required' };

    // Remove all non-digits for validation
    const cleanTIN = tin.replace(/\D/g, '');

    // Check if it's 9 digits
    if (cleanTIN.length !== 9) {
        return {
            isValid: false,
            message: 'TIN/EIN must be 9 digits'
        };
    }

    // Check format: either XXXXXXXXX or XX-XXXXXXX
    const tinRegex = /^\d{2}-?\d{7}$/;
    if (!tinRegex.test(tin)) {
        return {
            isValid: false,
            message: 'Please enter a valid TIN/EIN format (XX-XXXXXXX or XXXXXXXXX)'
        };
    }

    return { isValid: true, message: '' };
}

/**
 * Validate US Bank Account Number
 * Typically 8-17 digits, but can vary by bank
 */
function validateBankAccount(accountNumber) {
    if (!accountNumber) return { isValid: false, message: 'Bank account number is required' };

    // Remove all non-digits
    const cleanAccount = accountNumber.replace(/\D/g, '');

    // Check length (most US bank accounts are 8-17 digits)
    if (cleanAccount.length < 8 || cleanAccount.length > 17) {
        return {
            isValid: false,
            message: 'Bank account number should be 8-17 digits'
        };
    }

    // Basic format check - should be all digits
    if (!/^\d+$/.test(cleanAccount)) {
        return {
            isValid: false,
            message: 'Bank account number should contain only digits'
        };
    }

    return { isValid: true, message: '' };
}

/**
 * Validate US Bank Routing Number
 * Must be exactly 9 digits and pass checksum validation
 */
function validateRoutingNumber(routingNumber) {
    if (!routingNumber) return { isValid: false, message: 'Routing number is required' };

    // Remove all non-digits
    const cleanRouting = routingNumber.replace(/\D/g, '');

    // Must be exactly 9 digits
    if (cleanRouting.length !== 9) {
        return {
            isValid: false,
            message: 'Routing number must be exactly 9 digits'
        };
    }

    return { isValid: true, message: '' };
}

/**
 * Format TIN/EIN with standard formatting (XX-XXXXXXX)
 */
function formatTIN(tin) {
    const cleanTIN = tin.replace(/\D/g, '');
    if (cleanTIN.length === 9) {
        return `${cleanTIN.slice(0, 2)}-${cleanTIN.slice(2)}`;
    }
    return tin;
}

/**
 * Format routing number (adds spaces for readability: XXX XXX XXX)
 */
function formatRoutingNumber(routingNumber) {
    const cleanRouting = routingNumber.replace(/\D/g, '');
    if (cleanRouting.length === 9) {
        return `${cleanRouting.slice(0, 3)} ${cleanRouting.slice(3, 6)} ${cleanRouting.slice(6)}`;
    }
    return routingNumber;
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
        if (field.minLength && field.minLength > 0 && value && value.length < field.minLength) {
            fieldErrors.push(`${field.name} must be at least ${field.minLength} characters`);
        }

        if (field.maxLength && field.maxLength > 0 && value && value.length > field.maxLength) {
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

/**
 * Show form field errors
 */
function showFieldError(field, message) {
    clearFieldError(field);

    const errorDiv = document.createElement('div');
    errorDiv.className = 'field-error text-red-400 text-sm mt-1';
    errorDiv.textContent = message;

    field.classList.add('border-red-400');
    field.parentNode.appendChild(errorDiv);
}


/**
 * Clear form field errors
 */
function clearFieldError(field) {
    field.classList.remove('border-red-400');
    const existingError = field.parentNode.querySelector('.field-error');
    if (existingError) {
        existingError.remove();
    }
}

/**
 * Clear all form field errors
 */
function clearAllFieldErrors(form) {
    const errorElements = form.querySelectorAll('.field-error');
    errorElements.forEach(error => error.remove());

    const errorFields = form.querySelectorAll('.border-red-400');
    errorFields.forEach(field => field.classList.remove('border-red-400'));
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
 * Show Notification
 */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;

    // Style the notification with vendor theme
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 16px 24px;
        background: linear-gradient(135deg, var(--portal-surface), var(--portal-glass));
        border: 1px solid rgba(0, 212, 255, 0.2);
        border-radius: 12px;
        color: var(--text-primary);
        backdrop-filter: blur(20px);
        box-shadow: var(--glow-primary);
        z-index: 1000;
        transform: translateX(100%);
        transition: transform 0.3s ease;
    `;

    document.body.appendChild(notification);

    // Animate in
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 100);

    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentElement) {
                document.body.removeChild(notification);
            }
        }, 300);
    }, 3000);
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
window.validateTIN = validateTIN;
window.validateBankAccount = validateBankAccount;
window.validateRoutingNumber = validateRoutingNumber;
window.formatTIN = formatTIN;
window.formatRoutingNumber = formatRoutingNumber;
window.generateId = generateId;
window.copyToClipboard = copyToClipboard;
window.scrollToElement = scrollToElement;
window.isInViewport = isInViewport;
window.storage = storage;
window.url = url;
window.device = device;
window.validateForm = validateForm;
window.showFieldError = showFieldError;
window.clearFieldError = clearFieldError;
window.clearAllFieldErrors = clearAllFieldErrors;
window.showLoading = showLoading;
window.showNotification = showNotification;
