/**
 * FinBot Vendor Portal - Dashboard with Vendor Context
 */

// Dashboard state management
const DashboardState = {
    currentSection: 'dashboard',
    vendorContext: null,
    isLoading: false,
    isSwitchingVendor: false,
    sidebarOpen: false
};

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    initializeDashboard();
});

/**
 * Initialize dashboard with vendor context
 */
async function initializeDashboard() {
    console.log('🚀 Initializing FinBot Vendor Dashboard...');

    try {
        // Load vendor context first
        await loadVendorContext();

        // Initialize UI components
        initializeVendorSwitcher();
        initializeSidebar();
        initializeNavigation();

        // Load initial data
        await loadDashboardData();

        console.log('✅ Dashboard initialized successfully');

    } catch (error) {
        console.error('❌ Dashboard initialization failed:', error);
        showNotification('Failed to initialize dashboard', 'error');
    }
}

/**
 * Load vendor context from API
 */
async function loadVendorContext() {
    try {
        showLoadingState();

        const response = await api.get('/vendor/api/v1/vendors/context');
        DashboardState.vendorContext = response.data;

        console.log('📊 Vendor context loaded:', DashboardState.vendorContext);

        // Update UI with vendor context
        updateVendorSwitcherUI();

        hideLoadingState();

    } catch (error) {
        console.error('Error loading vendor context:', error);
        hideLoadingState();
        throw error;
    }
}

/**
 * Initialize vendor switcher functionality
 */
function initializeVendorSwitcher() {
    const switcherButton = document.getElementById('vendor-switcher');
    const dropdown = document.getElementById('vendor-dropdown');

    if (!switcherButton || !dropdown) {
        console.warn('Vendor switcher elements not found');
        return;
    }

    // Toggle dropdown
    switcherButton.addEventListener('click', function (e) {
        e.stopPropagation();
        toggleVendorDropdown();
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function (e) {
        if (!switcherButton.contains(e.target) && !dropdown.contains(e.target)) {
            closeVendorDropdown();
        }
    });

    // Handle vendor selection and actions
    dropdown.addEventListener('click', function (e) {
        const vendorOption = e.target.closest('.vendor-option');
        if (!vendorOption) return;

        // Handle "Add New Vendor" action
        if (vendorOption.dataset.action === 'add-vendor') {
            handleAddNewVendor();
            return;
        }

        // Handle vendor switching
        if (!vendorOption.classList.contains('current') && vendorOption.dataset.vendorId) {
            const vendorId = parseInt(vendorOption.dataset.vendorId);
            switchVendor(vendorId);
        }
    });

    console.log('🔄 Vendor switcher initialized');
}

/**
 * Switch to different vendor
 */
async function switchVendor(vendorId) {
    if (DashboardState.isSwitchingVendor) {
        console.log('⏳ Vendor switch already in progress');
        return;
    }

    const currentVendorId = DashboardState.vendorContext?.current_vendor?.id;
    if (vendorId === currentVendorId) {
        console.log('ℹ️ Already on selected vendor');
        return;
    }

    try {
        DashboardState.isSwitchingVendor = true;
        showLoadingState();

        console.log(`🔄 Switching to vendor: ${vendorId}`);

        // Switch vendor on server
        const response = await api.post(`/vendor/api/v1/vendors/switch/${vendorId}`);

        if (response.data.success) {
            // Update local context
            DashboardState.vendorContext.current_vendor = response.data.current_vendor;

            console.log('✅ Vendor switched successfully:', response.data.current_vendor);

            // Update UI
            updateVendorSwitcherUI();
            closeVendorDropdown();

            // Reload all data for new vendor
            await loadDashboardData();

            showNotification(
                `Switched to ${response.data.current_vendor.company_name}`,
                'success'
            );
        }

    } catch (error) {
        console.error('❌ Error switching vendor:', error);
        showNotification('Failed to switch vendor', 'error');
    } finally {
        DashboardState.isSwitchingVendor = false;
        hideLoadingState();
    }
}

/**
 * Update vendor switcher UI
 */
function updateVendorSwitcherUI() {
    const switcherButton = document.getElementById('vendor-switcher');
    const dropdown = document.getElementById('vendor-dropdown');

    if (!switcherButton || !dropdown || !DashboardState.vendorContext) {
        return;
    }

    const { current_vendor, available_vendors } = DashboardState.vendorContext;

    if (current_vendor) {
        // Update switcher button
        const avatar = current_vendor.company_name.substring(0, 2).toUpperCase();
        switcherButton.innerHTML = `
            <div class="flex items-center space-x-3">
                <div class="w-8 h-8 rounded-full bg-gradient-to-r from-vendor-accent to-vendor-primary flex items-center justify-center text-xs font-bold text-portal-bg-primary">
                    ${avatar}
                </div>
                <div class="text-left">
                    <div class="text-sm font-medium text-text-bright">${current_vendor.company_name}</div>
                    <div class="text-xs text-text-secondary">${current_vendor.industry}</div>
                </div>
            </div>
            <svg class="w-4 h-4 text-text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
            </svg>
        `;
    }

    // Update dropdown
    const vendorOptions = available_vendors.map(vendor => {
        const avatar = vendor.company_name.substring(0, 2).toUpperCase();
        const isCurrent = vendor.id === current_vendor?.id;

        return `
            <div class="vendor-option ${isCurrent ? 'current' : ''}" data-vendor-id="${vendor.id}">
                <div class="flex items-center space-x-3 p-3 rounded-lg ${isCurrent ? 'bg-vendor-primary/10 border border-vendor-primary/30' : 'hover:bg-portal-surface'} transition-colors cursor-pointer">
                    <div class="w-8 h-8 rounded-full bg-gradient-to-r from-vendor-accent to-vendor-primary flex items-center justify-center text-xs font-bold text-portal-bg-primary">
                        ${avatar}
                    </div>
                    <div class="flex-1">
                        <div class="text-sm font-medium text-text-bright">${vendor.company_name}</div>
                        <div class="text-xs ${isCurrent ? 'text-vendor-primary' : 'text-text-secondary'}">
                            ${isCurrent ? 'Current • ' : ''}${vendor.industry}
                        </div>
                    </div>
                    ${isCurrent ? `
                        <svg class="w-4 h-4 text-vendor-primary" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
                        </svg>
                    ` : ''}
                </div>
            </div>
        `;
    }).join('');

    // Add "Add New Vendor" option
    const addNewVendorOption = `
        <div class="vendor-option add-new-vendor" data-action="add-vendor">
            <div class="flex items-center space-x-3 p-3 rounded-lg hover:bg-portal-surface transition-colors cursor-pointer mt-2 border-t border-vendor-primary/20 pt-3">
                <div class="w-8 h-8 rounded-full bg-gradient-to-r from-vendor-secondary to-vendor-warning flex items-center justify-center text-xs font-bold text-text-bright">
                    +
                </div>
                <div class="flex-1">
                    <div class="text-sm font-medium text-text-secondary">Add New Vendor</div>
                    <div class="text-xs text-text-secondary">Register another company</div>
                </div>
            </div>
        </div>
    `;

    // Combine vendor options with add new vendor option
    dropdown.innerHTML = `<div class="p-2">${vendorOptions}${addNewVendorOption}</div>`;

    console.log('🎨 Vendor switcher UI updated');
}

/**
 * Handle "Add New Vendor" action
 */
function handleAddNewVendor() {
    console.log('🏢 Navigating to vendor onboarding...');

    // Close the dropdown first
    closeVendorDropdown();

    // Show notification
    showNotification('Redirecting to vendor registration...', 'info');

    // Navigate to onboarding
    setTimeout(() => {
        window.location.href = '/vendor/onboarding';
    }, 500);
}

/**
 * Toggle vendor dropdown
 */
function toggleVendorDropdown() {
    const dropdown = document.getElementById('vendor-dropdown');
    if (!dropdown) return;

    if (dropdown.classList.contains('hidden')) {
        dropdown.classList.remove('hidden');
        dropdown.style.opacity = '0';
        dropdown.style.transform = 'translateY(-10px)';

        requestAnimationFrame(() => {
            dropdown.style.transition = 'all 0.2s ease-out';
            dropdown.style.opacity = '1';
            dropdown.style.transform = 'translateY(0)';
        });
    } else {
        closeVendorDropdown();
    }
}

/**
 * Close vendor dropdown
 */
function closeVendorDropdown() {
    const dropdown = document.getElementById('vendor-dropdown');
    if (!dropdown) return;

    dropdown.style.opacity = '0';
    dropdown.style.transform = 'translateY(-10px)';

    setTimeout(() => {
        dropdown.classList.add('hidden');
    }, 200);
}

/**
 * Load dashboard data for current vendor
 */
async function loadDashboardData() {
    try {
        showLoadingState();

        console.log('📊 Loading dashboard data...');

        // Load metrics for current vendor
        const metricsResponse = await api.get('/vendor/api/v1/dashboard/metrics');
        updateDashboardMetrics(metricsResponse.data);

        // Load page-specific data
        await loadPageData();

        console.log('✅ Dashboard data loaded successfully');

    } catch (error) {
        console.error('❌ Error loading dashboard data:', error);
        showNotification('Failed to load dashboard data', 'error');
    } finally {
        hideLoadingState();
    }
}

/**
 * Load page-specific data based on current section
 */
async function loadPageData() {
    const section = DashboardState.currentSection;

    console.log(`📄 Loading ${section} data...`);

    try {
        switch (section) {
            case 'invoices':
                const invoicesResponse = await api.get('/vendor/api/v1/invoices');
                updateInvoicesUI(invoicesResponse.data);
                break;

            case 'payments':
                const paymentsResponse = await api.get('/vendor/api/v1/payments');
                updatePaymentsUI(paymentsResponse.data);
                break;

            case 'messages':
                // Messages endpoint would be implemented similarly
                console.log('Messages data loading not implemented yet');
                break;

            default:
                // Dashboard home - metrics already loaded
                console.log('Dashboard home - metrics loaded');
                break;
        }
    } catch (error) {
        console.error(`❌ Error loading ${section} data:`, error);
        showNotification(`Failed to load ${section} data`, 'error');
    }
}

/**
 * Update dashboard metrics UI
 */
function updateDashboardMetrics(data) {
    const { vendor_context, metrics } = data;

    console.log('📈 Updating dashboard metrics:', metrics);

    // Update metrics cards
    const metricsContainer = document.querySelector('.metrics-container');
    if (metricsContainer && metrics) {
        // Update invoice metrics
        updateMetricCard('total-invoices', metrics.invoices.total_count);
        updateMetricCard('pending-invoices', metrics.invoices.pending_count);
        updateMetricCard('total-payments', metrics.payments.total_count);
        updateMetricCard('completion-rate', `${metrics.completion_rate.toFixed(1)}%`);

        // Update amounts
        updateMetricCard('total-invoice-amount', formatCurrency(metrics.invoices.total_amount));
        updateMetricCard('paid-amount', formatCurrency(metrics.invoices.paid_amount));
    }
}

/**
 * Update individual metric card
 */
function updateMetricCard(cardId, value) {
    const card = document.getElementById(cardId);
    if (card) {
        const valueElement = card.querySelector('.metric-value');
        if (valueElement) {
            valueElement.textContent = value;
        }
    }
}

/**
 * Update invoices UI
 */
function updateInvoicesUI(data) {
    const { invoices, vendor_context, total_count } = data;

    console.log(`📋 Updating invoices UI: ${total_count} invoices`);

    const invoicesContainer = document.querySelector('.invoices-container');
    if (!invoicesContainer) return;

    if (invoices.length === 0) {
        invoicesContainer.innerHTML = `
            <div class="text-center py-8">
                <p class="text-text-secondary">No invoices found for ${vendor_context.company_name}</p>
            </div>
        `;
        return;
    }

    invoicesContainer.innerHTML = invoices.map(invoice => `
        <div class="invoice-card bg-portal-surface rounded-lg p-4 border border-vendor-primary/20">
            <div class="flex justify-between items-start">
                <div>
                    <h3 class="font-medium text-text-bright">${invoice.invoice_number}</h3>
                    <p class="text-sm text-text-secondary">${invoice.description}</p>
                    <p class="text-xs text-text-secondary mt-1">
                        Created: ${formatDate(invoice.created_at)}
                    </p>
                </div>
                <div class="text-right">
                    <p class="font-bold text-vendor-primary">${formatCurrency(invoice.amount)}</p>
                    <span class="inline-block px-2 py-1 rounded text-xs ${getStatusClass(invoice.status)}">
                        ${invoice.status.toUpperCase()}
                    </span>
                </div>
            </div>
        </div>
    `).join('');
}

/**
 * Update payments UI
 */
function updatePaymentsUI(data) {
    const { payments, vendor_context, total_count } = data;

    console.log(`💳 Updating payments UI: ${total_count} payments`);

    const paymentsContainer = document.querySelector('.payments-container');
    if (!paymentsContainer) return;

    if (payments.length === 0) {
        paymentsContainer.innerHTML = `
            <div class="text-center py-8">
                <p class="text-text-secondary">No payments found for ${vendor_context.company_name}</p>
            </div>
        `;
        return;
    }

    paymentsContainer.innerHTML = payments.map(payment => `
        <div class="payment-card bg-portal-surface rounded-lg p-4 border border-vendor-primary/20">
            <div class="flex justify-between items-start">
                <div>
                    <h3 class="font-medium text-text-bright">${payment.payment_number}</h3>
                    <p class="text-sm text-text-secondary">${payment.description}</p>
                    <p class="text-xs text-text-secondary mt-1">
                        Created: ${formatDate(payment.created_at)}
                    </p>
                </div>
                <div class="text-right">
                    <p class="font-bold text-vendor-primary">${formatCurrency(payment.amount)}</p>
                    <span class="inline-block px-2 py-1 rounded text-xs ${getStatusClass(payment.status)}">
                        ${payment.status.toUpperCase()}
                    </span>
                </div>
            </div>
        </div>
    `).join('');
}

/**
 * Get CSS class for status
 */
function getStatusClass(status) {
    switch (status.toLowerCase()) {
        case 'paid':
        case 'completed':
            return 'bg-green-500/20 text-green-400';
        case 'pending':
            return 'bg-yellow-500/20 text-yellow-400';
        case 'overdue':
            return 'bg-red-500/20 text-red-400';
        default:
            return 'bg-gray-500/20 text-gray-400';
    }
}

/**
 * Initialize sidebar functionality
 */
function initializeSidebar() {
    // Use existing sidebar utility if available
    if (typeof sidebar !== 'undefined' && sidebar.init) {
        sidebar.init();
    }

    console.log('📱 Sidebar initialized');
}

/**
 * Initialize navigation
 */
function initializeNavigation() {
    // Update navigation based on URL
    updateNavigationFromURL();

    // Note: Removed SPA-like navigation - now using normal browser navigation
    // Navigation links will work normally with their href attributes

    console.log('🧭 Navigation initialized');
}

/**
 * Navigate to section (programmatic navigation)
 */
async function navigateToSection(section) {
    console.log(`🧭 Programmatic navigation to section: ${section}`);

    // Use normal browser navigation instead of SPA-like behavior
    const newUrl = `/vendor/${section}`;
    window.location.href = newUrl;
}

/**
 * Update navigation from URL
 */
function updateNavigationFromURL() {
    const path = window.location.pathname;
    const section = path.split('/').pop() || 'dashboard';

    DashboardState.currentSection = section;

    // Update active nav item
    document.querySelectorAll('[data-section]').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.section === section) {
            item.classList.add('active');
        }
    });
}

/**
 * Show loading state
 */
function showLoadingState() {
    DashboardState.isLoading = true;

    const loadingIndicator = document.querySelector('.loading-indicator');
    if (loadingIndicator) {
        loadingIndicator.classList.remove('hidden');
    }
}

/**
 * Hide loading state
 */
function hideLoadingState() {
    DashboardState.isLoading = false;

    const loadingIndicator = document.querySelector('.loading-indicator');
    if (loadingIndicator) {
        loadingIndicator.classList.add('hidden');
    }
}

/**
 * Handle browser back/forward
 * Note: Removed SPA-like popstate handling since we're using normal navigation
 */

/**
 * Export dashboard functions for external use
 */
window.VendorDashboard = {
    switchVendor,
    handleAddNewVendor,
    loadDashboardData,
    loadPageData,
    navigateToSection, // Keep for programmatic navigation if needed
    state: DashboardState
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = window.VendorDashboard;
}

console.log('🎯 Vendor Dashboard module loaded');