/**
 * CineFlow Productions Web App Main JavaScript
 * Handles web-specific functionality for the public website
 */

document.addEventListener('DOMContentLoaded', () => {
    initializeNavigation();
    initializeForms();
    initializeAnimations();
    initializeAccessibility();
    initializeScrollEffects();
    initializeCTFHeader();
});

/**
 * Initialize navigation functionality
 */
function initializeNavigation() {
    // Mobile menu toggle
    const mobileMenuButton = document.getElementById('mobile-menu-button');
    const mobileMenu = document.getElementById('mobile-menu');

    if (mobileMenuButton && mobileMenu) {
        mobileMenuButton.addEventListener('click', () => {
            const isHidden = mobileMenu.classList.contains('hidden');

            if (isHidden) {
                mobileMenu.classList.remove('hidden');
                mobileMenuButton.setAttribute('aria-expanded', 'true');
            } else {
                mobileMenu.classList.add('hidden');
                mobileMenuButton.setAttribute('aria-expanded', 'false');
            }
        });

        // Close mobile menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!mobileMenuButton.contains(e.target) && !mobileMenu.contains(e.target)) {
                mobileMenu.classList.add('hidden');
                mobileMenuButton.setAttribute('aria-expanded', 'false');
            }
        });

        // Close mobile menu on window resize
        window.addEventListener('resize', () => {
            if (window.innerWidth >= 768) {
                mobileMenu.classList.add('hidden');
                mobileMenuButton.setAttribute('aria-expanded', 'false');
            }
        });
    }
}

/**
 * Initialize scroll effects
 */
function initializeScrollEffects() {
    // Header scroll effect
    const header = document.querySelector('header');
    if (header) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 100) {
                header.classList.add('bg-cine-dark');
                header.classList.remove('bg-cine-dark/95');
            } else {
                header.classList.remove('bg-cine-dark');
                header.classList.add('bg-cine-dark/95');
            }
        });
    }

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href === '#') return;

            const target = document.querySelector(href);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

/**
 * Initialize form functionality
 */
function initializeForms() {
    // Auth forms
    const authForms = document.querySelectorAll('.auth-form');
    authForms.forEach(form => {
        form.addEventListener('submit', handleAuthSubmit);
    });

    // Real-time validation
    const formInputs = document.querySelectorAll('.form-control');
    formInputs.forEach(input => {
        input.addEventListener('blur', validateField);
        input.addEventListener('input', debounce(validateField, 500));
    });
}

/**
 * Handle auth form submission
 */
async function handleAuthSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');

    // Validate form
    const validation = validateForm(form);
    if (!validation.isValid) {
        displayFormErrors(form, validation.errors);
        return;
    }

    const hideLoading = showLoading(submitBtn);

    try {
        const response = await submitForm(form, { json: true });

        // Handle successful auth
        if (response.data.redirect) {
            window.location.href = response.data.redirect;
        } else {
            window.location.reload();
        }
    } catch (error) {
        if (error.isValidationError() && error.data?.errors) {
            displayFormErrors(form, error.data.errors);
        } else {
            handleAPIError(error, { redirectOnAuth: false });
        }
    } finally {
        hideLoading();
    }
}

/**
 * Validate individual form field
 */
function validateField(e) {
    const field = e.target;
    const value = field.value.trim();
    const fieldGroup = field.closest('.form-group');

    if (!fieldGroup) return;

    // Clear previous errors
    const existingError = fieldGroup.querySelector('.form-error');
    if (existingError) {
        existingError.remove();
    }
    fieldGroup.classList.remove('has-error');

    // Skip validation if field is empty and not required
    if (!value && !field.hasAttribute('required')) {
        return;
    }

    let errorMessage = '';

    // Required validation
    if (field.hasAttribute('required') && !value) {
        errorMessage = 'This field is required';
    }
    // Password validation
    else if (field.type === 'password' && value) {
        const passwordValidation = validatePassword(value);
        if (!passwordValidation.isValid) {
            errorMessage = passwordValidation.feedback[0];
        }
    }
    // Confirm password validation
    else if (field.name === 'confirm_password' && value) {
        const passwordField = document.querySelector('input[name="password"]');
        if (passwordField && value !== passwordField.value) {
            errorMessage = 'Passwords do not match';
        }
    }

    if (errorMessage) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'form-error';
        errorDiv.textContent = errorMessage;
        fieldGroup.appendChild(errorDiv);
        fieldGroup.classList.add('has-error');
    }
}

/**
 * Display form validation errors
 */
function displayFormErrors(form, errors) {
    clearFormErrors(form);

    Object.entries(errors).forEach(([fieldName, fieldErrors]) => {
        const field = form.querySelector(`[name="${fieldName}"]`);
        if (!field) return;

        const fieldGroup = field.closest('.form-group');
        if (!fieldGroup) return;

        const errorDiv = document.createElement('div');
        errorDiv.className = 'form-error';
        errorDiv.textContent = Array.isArray(fieldErrors) ? fieldErrors[0] : fieldErrors;

        fieldGroup.appendChild(errorDiv);
        fieldGroup.classList.add('has-error');
    });
}

/**
 * Clear form validation errors
 */
function clearFormErrors(form) {
    const errorElements = form.querySelectorAll('.form-error');
    errorElements.forEach(error => error.remove());

    const errorGroups = form.querySelectorAll('.has-error');
    errorGroups.forEach(group => group.classList.remove('has-error'));
}

/**
 * Initialize scroll animations
 */
function initializeAnimations() {
    // Fade in elements on scroll
    const animatedElements = document.querySelectorAll('[data-animate]');

    if (animatedElements.length === 0) return;

    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const element = entry.target;
                const animation = element.dataset.animate || 'fadeIn';

                element.classList.add('animate', animation);
                observer.unobserve(element);
            }
        });
    }, observerOptions);

    animatedElements.forEach(element => {
        observer.observe(element);
    });
}

/**
 * Initialize accessibility features
 */
function initializeAccessibility() {
    // Skip link functionality
    const skipLink = document.querySelector('.skip-link');
    if (skipLink) {
        skipLink.addEventListener('click', (e) => {
            e.preventDefault();
            const target = document.querySelector(skipLink.getAttribute('href'));
            if (target) {
                target.focus();
                target.scrollIntoView();
            }
        });
    }

    // Keyboard navigation for dropdowns
    const dropdownToggles = document.querySelectorAll('[data-toggle="dropdown"]');
    dropdownToggles.forEach(toggle => {
        toggle.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggle.click();
            }
        });
    });

    // Focus management for modals
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        modal.addEventListener('shown', () => {
            const firstFocusable = modal.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
            if (firstFocusable) {
                firstFocusable.focus();
            }
        });
    });
}

/**
 * Smooth scroll for anchor links
 */
document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href^="#"]');
    if (!link) return;

    const href = link.getAttribute('href');
    if (href === '#') return;

    const target = document.querySelector(href);
    if (target) {
        e.preventDefault();
        scrollToElement(target, 80); // Account for fixed header
    }
});

/**
 * Initialize live chat (if available)
 */
function openChat() {
    // This would integrate with your chat service (e.g., Intercom, Zendesk)
    if (window.Intercom) {
        window.Intercom('show');
    } else if (window.zE) {
        window.zE('webWidget', 'open');
    } else {
        // Fallback method
        window.location.href = '/contact';
    }
}

// Make web-specific functions available globally
window.openChat = openChat;
