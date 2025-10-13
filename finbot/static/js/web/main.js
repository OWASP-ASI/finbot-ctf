/**
 * CineFlow Productions Web App Main JavaScript
 * Handles common functionality for the public website
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
    // Forms removed - no longer handling newsletter or contact submissions

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

// Make openChat available globally
window.openChat = openChat;

/**
 * Initialize CTF header functionality
 */
function initializeCTFHeader() {
    // CTF Details & Policy button functionality
    const ctfDetailsButton = document.querySelector('[data-ctf-details]');

    if (ctfDetailsButton) {
        ctfDetailsButton.addEventListener('click', () => {
            showCTFDetailsModal();
        });
    }
}

/**
 * Show CTF Details & Policy modal
 */
function showCTFDetailsModal() {
    // Create modal content
    const modalContent = `
        <div class="fixed inset-0 bg-black bg-opacity-50 z-70 flex items-center justify-center p-4">
            <div class="bg-gray-900 border border-green-400 rounded-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto">
                <div class="p-6">
                    <div class="flex items-center justify-between mb-6">
                        <div class="flex items-center space-x-3">
                            <div class="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-500 rounded-full flex items-center justify-center">
                                <svg class="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                                </svg>
                            </div>
                            <h2 class="text-xl font-bold text-green-400">OWASP Agentic AI CTF Details & Policy</h2>
                        </div>
                        <button class="text-gray-400 hover:text-white" onclick="closeCTFModal()">
                            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                            </svg>
                        </button>
                    </div>

                    <div class="space-y-4 text-gray-300">
                        <div class="bg-green-900/20 border border-green-400/30 rounded-lg p-4">
                            <h3 class="text-green-400 font-semibold mb-2">🎯 CTF Objective</h3>
                            <p class="text-sm">This is an educational Capture The Flag (CTF) environment designed to demonstrate AI security vulnerabilities and defensive techniques in a controlled setting.</p>
                        </div>

                        <div class="bg-blue-900/20 border border-blue-400/30 rounded-lg p-4">
                            <h3 class="text-blue-400 font-semibold mb-2">📋 OWASP Guidelines</h3>
                            <ul class="text-sm space-y-1">
                                <li>• Follow responsible disclosure practices</li>
                                <li>• Respect system boundaries and limitations</li>
                                <li>• Use findings for educational purposes only</li>
                                <li>• Report vulnerabilities through proper channels</li>
                            </ul>
                        </div>

                        <div class="bg-yellow-900/20 border border-yellow-400/30 rounded-lg p-4">
                            <h3 class="text-yellow-400 font-semibold mb-2">⚠️ Important Notices</h3>
                            <ul class="text-sm space-y-1">
                                <li>• All activities are logged and monitored</li>
                                <li>• This environment is for educational purposes only</li>
                                <li>• Malicious activities are prohibited</li>
                                <li>• Data may be reset periodically</li>
                            </ul>
                        </div>

                        <div class="bg-red-900/20 border border-red-400/30 rounded-lg p-4">
                            <h3 class="text-red-400 font-semibold mb-2">🛡️ Ethical Use Policy</h3>
                            <p class="text-sm">By using this CTF environment, you agree to use it ethically and responsibly. Any attempt to cause harm, access unauthorized systems, or violate the terms of use will result in immediate termination of access.</p>
                        </div>
                    </div>

                    <div class="mt-6 flex justify-end">
                        <button onclick="closeCTFModal()" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition-colors duration-300">
                            Understood
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Add modal to page
    const modalDiv = document.createElement('div');
    modalDiv.id = 'ctf-modal';
    modalDiv.innerHTML = modalContent;
    document.body.appendChild(modalDiv);

    // Prevent body scroll
    document.body.style.overflow = 'hidden';
}

/**
 * Close CTF Details modal
 */
function closeCTFModal() {
    const modal = document.getElementById('ctf-modal');
    if (modal) {
        modal.remove();
        document.body.style.overflow = '';
    }
}

// Make CTF functions available globally
window.showCTFDetailsModal = showCTFDetailsModal;
window.closeCTFModal = closeCTFModal;
