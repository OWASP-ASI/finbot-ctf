/**
 * FinBot Vendor Portal - Profile Management
 */

// Profile state management
const ProfileState = {
    vendorData: null,
    isEditing: false,
    isLoading: false,
    showSensitiveData: false
};

// Initialize profile when DOM is loaded
ready(function () {
    initializeProfile();
});

/**
 * Initialize profile page
 */
async function initializeProfile() {
    console.log('🚀 Initializing Vendor Profile...');

    try {
        // Load vendor profile data
        await loadProfileData();

        // Initialize UI components
        initializeProfileUI();
        initializeEditModal();
        initializeSensitiveDataToggle();
        initializeReviewRequest();

        console.log('✅ Profile initialized successfully');

    } catch (error) {
        console.error('❌ Profile initialization failed:', error);
        showNotification('Failed to load profile data', 'error');
    }
}

/**
 * Load profile data from API
 */
async function loadProfileData() {
    try {
        showLoadingOverlay('Loading profile data...');

        // Load vendor context to get current vendor ID
        const contextResponse = await api.get('/vendor/api/v1/vendors/context');
        const currentVendor = contextResponse.data.current_vendor;

        if (!currentVendor || !currentVendor.id) {
            throw new Error('No vendor context found');
        }

        // Get full vendor details using the vendor ID
        const vendorResponse = await api.get(`/vendor/api/v1/vendors/${currentVendor.id}`);
        const vendorDetails = vendorResponse.data;

        // Load dashboard metrics for statistics
        const metricsResponse = await api.get('/vendor/api/v1/dashboard/metrics');

        ProfileState.vendorData = {
            ...vendorDetails,
            metrics: metricsResponse.data.metrics
        };

        // console.log('📊 Profile data loaded:', ProfileState.vendorData);

        // Update UI with profile data
        updateProfileUI();

        hideLoadingOverlay();

    } catch (error) {
        console.error('Error loading profile data:', error);
        hideLoadingOverlay();
        throw error;
    }
}

/**
 * Update profile UI with loaded data
 */
function updateProfileUI() {
    if (!ProfileState.vendorData) {
        console.warn('No vendor data to display');
        return;
    }

    const vendor = ProfileState.vendorData;

    // Update header
    updateElement('company-initials', getCompanyInitials(vendor.company_name));
    updateElement('company-name', vendor.company_name);
    updateElement('vendor-category', vendor.vendor_category || 'N/A');
    updateElement('vendor-status', vendor.status || 'pending');
    updateElement('vendor-id', `ID: ${vendor.id}`);
    updateElement('member-since', formatDate(vendor.created_at));

    // Update company information
    updateElement('profile-company-name', vendor.company_name);
    updateElement('profile-category', formatVendorCategory(vendor.vendor_category));
    updateElement('profile-industry', vendor.industry || 'N/A');
    updateElement('profile-services', vendor.services || 'No services listed');

    // Update contact information
    updateElement('profile-contact-name', vendor.contact_name || 'N/A');
    updateElement('profile-email', vendor.email || 'N/A');
    updateElement('profile-phone', vendor.phone || 'N/A');

    // Update payment information (masked by default)
    updateElement('profile-tin', maskSensitiveData(vendor.tin, 'tin'));
    updateElement('profile-bank-name', vendor.bank_name || 'N/A');
    updateElement('profile-account-holder', vendor.bank_account_holder_name || 'N/A');
    updateElement('profile-account-number', maskSensitiveData(vendor.bank_account_number, 'account'));
    updateElement('profile-routing-number', maskSensitiveData(vendor.bank_routing_number, 'routing'));

    // Update agent notes
    updateAgentNotes();
}

/**
 * Update agent notes section
 */
function updateAgentNotes() {
    if (!ProfileState.vendorData) {
        return;
    }

    const vendor = ProfileState.vendorData;

    // Update agent notes with visual separation for each review iteration
    renderAgentNotes(vendor.agent_notes);

    // Update trust level
    const trustLevel = formatLevel(vendor.trust_level, 'trust');
    updateElement('vendor-trust-level', trustLevel.label);
    applyLevelStyling('vendor-trust-level', trustLevel.colorClass);

    // Update risk level
    const riskLevel = formatLevel(vendor.risk_level, 'risk');
    updateElement('vendor-risk-level', riskLevel.label);
    applyLevelStyling('vendor-risk-level', riskLevel.colorClass);

    // Update last activity
    updateElement('stats-last-activity', formatRelativeTime(vendor.updated_at));
}

/**
 * Render agent notes with visual separation for each review iteration
 */
function renderAgentNotes(agentNotes) {
    const container = document.getElementById('agent-notes');
    if (!container) return;

    if (!agentNotes || agentNotes.trim() === '') {
        container.innerHTML = '<span class="text-text-secondary italic">No notes available.</span>';
        return;
    }

    // Split notes by double newline (each review iteration)
    const noteEntries = agentNotes.split(/\n\n+/).filter(entry => entry.trim());

    if (noteEntries.length === 0) {
        container.innerHTML = '<span class="text-text-secondary italic">No notes available.</span>';
        return;
    }

    if (noteEntries.length === 1) {
        // Single entry - render simply
        container.innerHTML = `<span class="text-text-bright">${escapeHtml(noteEntries[0])}</span>`;
        return;
    }

    // Multiple entries - reverse to show latest first (notes are appended in DB)
    const reversedEntries = [...noteEntries].reverse();
    const entriesHtml = reversedEntries.map((entry, index) => {
        const isLatest = index === 0;
        const entryNumber = reversedEntries.length - index;

        return `
            <div class="relative pl-6 pb-4 ${index < reversedEntries.length - 1 ? 'border-l border-vendor-primary/30' : ''}">
                <div class="absolute left-0 top-0 w-3 h-3 rounded-full ${isLatest ? 'bg-vendor-accent' : 'bg-vendor-primary/50'} -translate-x-1.5"></div>
                <div class="flex items-center space-x-2 mb-1">
                    <span class="text-xs font-medium ${isLatest ? 'text-vendor-accent' : 'text-text-secondary'}">
                        ${isLatest ? 'Latest Review' : `Review #${entryNumber}`}
                    </span>
                </div>
                <p class="text-sm text-text-bright leading-relaxed">${escapeHtml(entry).replace(/\n/g, '<br>')}</p>
            </div>
        `;
    }).join('');

    container.innerHTML = `<div class="space-y-2">${entriesHtml}</div>`;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Format trust/risk level for display
 */
function formatLevel(level, type) {
    if (!level) {
        return type === 'trust'
            ? { label: 'Not Assessed', colorClass: 'text-text-secondary' }
            : { label: 'Unknown', colorClass: 'text-text-secondary' };
    }

    const levelLower = level.toLowerCase();

    if (type === 'trust') {
        const trustMap = {
            'high': { label: 'High', colorClass: 'text-green-400' },
            'standard': { label: 'Standard', colorClass: 'text-vendor-primary' },
            'low': { label: 'Low', colorClass: 'text-vendor-warning' },
            'restricted': { label: 'Restricted', colorClass: 'text-red-400' }
        };
        return trustMap[levelLower] || { label: level, colorClass: 'text-vendor-primary' };
    } else {
        const riskMap = {
            'low': { label: 'Low', colorClass: 'text-green-400' },
            'medium': { label: 'Medium', colorClass: 'text-vendor-warning' },
            'high': { label: 'High', colorClass: 'text-red-400' },
            'critical': { label: 'Critical', colorClass: 'text-red-500' }
        };
        return riskMap[levelLower] || { label: level, colorClass: 'text-vendor-warning' };
    }
}

/**
 * Apply color styling to level element
 */
function applyLevelStyling(elementId, colorClass) {
    const element = document.getElementById(elementId);
    if (element) {
        // Remove existing color classes
        element.className = element.className.replace(/text-\S+/g, '');
        // Add new color class and base classes
        element.className = `text-lg font-semibold ${colorClass}`;
    }
}

/**
 * Initialize profile UI components
 */
function initializeProfileUI() {
    // Edit profile button
    const editBtn = document.getElementById('edit-profile-btn');
    if (editBtn) {
        editBtn.addEventListener('click', openEditModal);
    }
}

/**
 * Initialize edit modal
 */
function initializeEditModal() {
    const modal = document.getElementById('edit-profile-modal');
    const closeBtn = document.getElementById('close-modal-btn');
    const cancelBtn = document.getElementById('cancel-edit-btn');
    const form = document.getElementById('edit-profile-form');

    if (!modal || !form) {
        console.warn('Edit modal elements not found');
        return;
    }

    // Close modal handlers
    [closeBtn, cancelBtn].forEach(btn => {
        if (btn) {
            btn.addEventListener('click', closeEditModal);
        }
    });

    // Close on backdrop click
    modal.addEventListener('click', function (e) {
        if (e.target === modal) {
            closeEditModal();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            closeEditModal();
        }
    });

    // Form submission
    form.addEventListener('submit', handleProfileUpdate);
}

/**
 * Open edit modal and populate form
 */
function openEditModal() {
    if (!ProfileState.vendorData) {
        showNotification('Profile data not loaded yet', 'warning');
        return;
    }

    const modal = document.getElementById('edit-profile-modal');
    if (!modal) return;

    // Populate form with current data
    const vendor = ProfileState.vendorData;
    document.getElementById('edit-company-name').value = vendor.company_name || '';
    document.getElementById('edit-services').value = vendor.services || '';
    document.getElementById('edit-contact-name').value = vendor.contact_name || '';
    document.getElementById('edit-email').value = vendor.email || '';
    document.getElementById('edit-phone').value = vendor.phone || '';

    // Show modal
    modal.classList.remove('hidden');
    ProfileState.isEditing = true;

    // Focus first input
    setTimeout(() => {
        document.getElementById('edit-company-name').focus();
    }, 100);
}

/**
 * Close edit modal
 */
function closeEditModal() {
    const modal = document.getElementById('edit-profile-modal');
    if (!modal) return;

    modal.classList.add('hidden');
    ProfileState.isEditing = false;

    // Clear form
    document.getElementById('edit-profile-form').reset();
}

/**
 * Handle profile update form submission
 */
async function handleProfileUpdate(e) {
    e.preventDefault();

    if (!ProfileState.vendorData) {
        showNotification('No profile data to update', 'error');
        return;
    }

    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');

    try {
        const hideLoading = showLoading(submitBtn, 'Saving Changes...');

        // Get form data
        const formData = new FormData(form);
        const updateData = {
            company_name: formData.get('company_name'),
            services: formData.get('services'),
            contact_name: formData.get('contact_name'),
            email: formData.get('email'),
            phone: formData.get('phone')
        };

        // Validate data
        if (!updateData.company_name || !updateData.email) {
            hideLoading();
            showNotification('Company name and email are required', 'error');
            return;
        }

        // Update profile via API
        const response = await api.put(
            `/vendor/api/v1/vendors/${ProfileState.vendorData.id}`,
            updateData
        );

        hideLoading();

        // Update local state
        ProfileState.vendorData = {
            ...ProfileState.vendorData,
            ...updateData
        };

        // Update UI
        updateProfileUI();

        // Close modal
        closeEditModal();

        // Show success message
        showNotification('Profile updated successfully!', 'success');

    } catch (error) {
        console.error('Error updating profile:', error);

        // Handle API errors
        const errorMessage = handleAPIError(error, { showAlert: true });

        if (!(error.status === 403 && error.data?.error?.type === 'csrf_error')) {
            showNotification(`Failed to update profile: ${errorMessage}`, 'error');
        }
    }
}

/**
 * Initialize sensitive data toggle
 */
function initializeSensitiveDataToggle() {
    // Add click handlers to show/hide buttons
    const toggleButtons = document.querySelectorAll('[data-toggle="sensitive-data"]');

    // Create show/hide button for payment section
    const paymentHeader = document.querySelector('.holo-card .holo-header button');
    if (paymentHeader) {
        paymentHeader.addEventListener('click', toggleSensitiveData);
    }
}

/**
 * Toggle sensitive data visibility
 */
function toggleSensitiveData() {
    ProfileState.showSensitiveData = !ProfileState.showSensitiveData;

    if (!ProfileState.vendorData) return;

    const vendor = ProfileState.vendorData;

    if (ProfileState.showSensitiveData) {
        // Show actual data
        updateElement('profile-tin', vendor.tin || 'N/A');
        updateElement('profile-account-number', vendor.bank_account_number || 'N/A');
        updateElement('profile-routing-number', vendor.bank_routing_number || 'N/A');
        showNotification('Sensitive data is now visible', 'info');
    } else {
        // Mask data
        updateElement('profile-tin', maskSensitiveData(vendor.tin, 'tin'));
        updateElement('profile-account-number', maskSensitiveData(vendor.bank_account_number, 'account'));
        updateElement('profile-routing-number', maskSensitiveData(vendor.bank_routing_number, 'routing'));
        showNotification('Sensitive data is now hidden', 'info');
    }
}

/**
 * Initialize review request button
 */
function initializeReviewRequest() {
    const reviewBtn = document.getElementById('request-review-btn');
    if (reviewBtn) {
        reviewBtn.addEventListener('click', handleReviewRequest);
    }
}

/**
 * Handle review request button click
 */
async function handleReviewRequest() {
    if (!ProfileState.vendorData) {
        showNotification('Profile data not loaded yet', 'warning');
        return;
    }

    const reviewBtn = document.getElementById('request-review-btn');
    const statusMessage = document.getElementById('review-status-message');

    try {
        // Show loading state
        const originalContent = reviewBtn.innerHTML;
        reviewBtn.disabled = true;
        reviewBtn.innerHTML = `
            <svg class="w-4 h-4 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
            Submitting...
        `;

        // Make API request
        const response = await api.post(
            `/vendor/api/v1/vendors/${ProfileState.vendorData.id}/request-review`
        );

        // Show success message
        statusMessage.className = 'mt-3 p-3 rounded-lg text-sm bg-green-500/20 border border-green-500/30 text-green-400';
        statusMessage.innerHTML = `
            <div class="flex items-center">
                <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                <span>${response.data.message || 'Review request submitted successfully!'}</span>
            </div>
        `;
        statusMessage.classList.remove('hidden');

        showNotification('Review request submitted!', 'success');

        // Reset button after delay
        setTimeout(() => {
            reviewBtn.disabled = false;
            reviewBtn.innerHTML = originalContent;
        }, 3000);

    } catch (error) {
        console.error('Error requesting review:', error);

        // Show error message
        statusMessage.className = 'mt-3 p-3 rounded-lg text-sm bg-red-500/20 border border-red-500/30 text-red-400';
        statusMessage.innerHTML = `
            <div class="flex items-center">
                <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
                <span>${error.data?.detail || 'Failed to submit review request. Please try again.'}</span>
            </div>
        `;
        statusMessage.classList.remove('hidden');

        // Handle API errors
        const errorMessage = handleAPIError(error, { showAlert: true });

        if (!(error.status === 403 && error.data?.error?.type === 'csrf_error')) {
            showNotification(`Failed to request review: ${errorMessage}`, 'error');
        }

        // Reset button
        reviewBtn.disabled = false;
        reviewBtn.innerHTML = `
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
            Request Re-Review
        `;
    }
}

/**
 * Helper function to update element content
 */
function updateElement(id, content) {
    const element = document.getElementById(id);
    if (element) {
        element.textContent = content;
    }
}

/**
 * Get company initials from name
 */
function getCompanyInitials(companyName) {
    if (!companyName) return 'V';

    const words = companyName.split(' ').filter(word => word.length > 0);
    if (words.length === 0) return 'V';
    if (words.length === 1) return words[0].substring(0, 2).toUpperCase();

    return (words[0][0] + words[1][0]).toUpperCase();
}

/**
 * Format vendor category for display
 */
function formatVendorCategory(category) {
    if (!category) return 'N/A';

    const categoryMap = {
        'professional_services': 'Professional Services (Consulting, Advisory, Accounting, Legal)',
        'technology_software': 'Technology & Software (SaaS, Cloud, Dev Tools, Platforms)',
        'marketing_creative': 'Marketing & Creative (Agencies, Design, Content, Media)',
        'facilities_operations': 'Facilities & Operations (Maintenance, Office Services)',
        'hr_staffing': 'HR & Staffing (Recruitment, Training, Temp Staffing)',
        'logistics_supply_chain': 'Logistics & Supply Chain (Shipping, Warehousing, Fleet)',
        'financial_services': 'Financial Services (Payments, Lending, Insurance, Wealth)',
        'healthcare_life_sciences': 'Healthcare & Life Sciences (Medical, Pharma, Biotech)',
        'manufacturing_engineering': 'Manufacturing & Engineering (Industrial, Components)',
        'construction_real_estate': 'Construction & Real Estate (Contractors, Architecture)',
        'security_compliance': 'Security & Compliance (Physical Security, Cyber, GRC)',
        'catering_hospitality': 'Catering & Hospitality (Food Services, Events, Travel)',
        'other_specialized': 'Other Specialized Services'
    };

    return categoryMap[category] || category;
}

/**
 * Mask sensitive data based on type
 */
function maskSensitiveData(data, type) {
    if (!data) return 'N/A';

    switch (type) {
        case 'tin':
            // Mask TIN/EIN: XX-XXXXXXX -> **-*******
            return data.replace(/\d/g, '*');
        case 'account':
            // Mask account number: show last 4 digits
            return '****' + data.slice(-4);
        case 'routing':
            // Mask routing number: show last 4 digits
            return '****' + data.slice(-4);
        default:
            return data.replace(/./g, '*');
    }
}

/**
 * Format date for display
 */
function formatDate(dateString) {
    if (!dateString) return 'N/A';

    try {
        const date = parseUTCDate(dateString);
        const options = { year: 'numeric', month: 'long', day: 'numeric' };
        return date.toLocaleDateString('en-US', options);
    } catch (error) {
        console.error('Error formatting date:', error);
        return 'Invalid Date';
    }
}

/**
 * Format date for relative time (e.g., "2 hours ago")
 */
function formatRelativeTime(dateString) {
    if (!dateString) return 'N/A';

    try {
        const date = parseUTCDate(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffSeconds = Math.floor(diffMs / 1000);
        const diffMinutes = Math.floor(diffSeconds / 60);
        const diffHours = Math.floor(diffMinutes / 60);
        const diffDays = Math.floor(diffHours / 24);
        const diffWeeks = Math.floor(diffDays / 7);
        const diffMonths = Math.floor(diffDays / 30);
        const diffYears = Math.floor(diffDays / 365);

        if (diffSeconds < 0) {
            return 'just now';
        } else if (diffSeconds < 60) {
            return diffSeconds === 1 ? '1 second ago' : `${diffSeconds} seconds ago`;
        } else if (diffMinutes < 60) {
            return diffMinutes === 1 ? '1 minute ago' : `${diffMinutes} minutes ago`;
        } else if (diffHours < 24) {
            return diffHours === 1 ? '1 hour ago' : `${diffHours} hours ago`;
        } else if (diffDays < 7) {
            return diffDays === 1 ? '1 day ago' : `${diffDays} days ago`;
        } else if (diffWeeks < 4) {
            return diffWeeks === 1 ? '1 week ago' : `${diffWeeks} weeks ago`;
        } else if (diffMonths < 12) {
            return diffMonths === 1 ? '1 month ago' : `${diffMonths} months ago`;
        } else {
            return diffYears === 1 ? '1 year ago' : `${diffYears} years ago`;
        }
    } catch (error) {
        console.error('Error formatting relative time:', error);
        return 'Invalid Date';
    }
}
/**
 * Format currency for display
 */
function formatCurrency(amount) {
    if (amount === null || amount === undefined) return '$0';

    try {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(amount);
    } catch (error) {
        console.error('Error formatting currency:', error);
        return `$${amount}`;
    }
}

/**
 * Show loading overlay
 */
function showLoadingOverlay(message = 'Loading...') {
    // Use existing loading notification
    showNotification(message, 'info');
}

/**
 * Hide loading overlay
 */
function hideLoadingOverlay() {
    // Handled by notification auto-hide
}

