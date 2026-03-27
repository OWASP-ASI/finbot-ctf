/**
 * FinBot Vendor Portal - Invoice Management
 */

// Invoice state management
const InvoiceState = {
    invoices: [],
    isLoading: false,
    currentFilter: 'all',
    editingInvoiceId: null,
    isModalOpen: false,
    isSidecarOpen: false,
    currentInvoice: null,
    pendingAttachments: [],
    pickerSelectedIds: new Set(),
    driveFiles: [],
};

// Initialize invoices when DOM is loaded
ready(function () {
    initializeInvoices();
});

/**
 * Initialize invoice page
 */
async function initializeInvoices() {
    console.log('🚀 Initializing Invoice Management...');

    try {
        // Initialize UI components
        initializeInvoiceModal();
        initializeInvoiceSidecar();
        initializeCreateButtons();
        initializeFinDrivePicker();

        // Load invoices and stats in parallel
        await Promise.all([
            loadInvoices(),
            loadInvoiceStats()
        ]);

        console.log('✅ Invoices initialized successfully');

    } catch (error) {
        console.error('❌ Invoice initialization failed:', error);
        showNotification('Failed to load invoices', 'error');
    }
}

/**
 * Load invoice stats from API
 */
async function loadInvoiceStats() {
    try {
        const response = await api.get('/vendor/api/v1/dashboard/metrics');

        // Handle both response.data and direct response structures
        const data = response.data || response;
        const stats = data.metrics?.invoices;
        const completionRate = data.metrics?.completion_rate;

        if (stats) {
            updateInvoiceStats(stats, completionRate);
        }
    } catch (error) {
        console.error('Error loading invoice stats:', error);
    }
}

/**
 * Update invoice stats UI
 */
function updateInvoiceStats(stats, completionRate) {
    // Total count
    const totalCountEl = document.getElementById('stat-total-count');
    if (totalCountEl) {
        totalCountEl.textContent = stats.total_count ?? 0;
    }

    // Total amount
    const totalAmountEl = document.getElementById('stat-total-amount');
    if (totalAmountEl) {
        const amount = parseFloat(stats.total_amount) || 0;
        totalAmountEl.textContent = formatCurrency(amount);
    }

    // Paid rate (percentage)
    const paidRateEl = document.getElementById('stat-paid-rate');
    if (paidRateEl) {
        const rate = parseFloat(completionRate) || 0;
        paidRateEl.textContent = `${Math.round(rate)}%`;
    }

    // Overdue count
    const overdueCountEl = document.getElementById('stat-overdue-count');
    if (overdueCountEl) {
        overdueCountEl.textContent = stats.overdue_count ?? 0;
    }
}

/**
 * Initialize create invoice buttons
 */
function initializeCreateButtons() {
    // Header create button
    const createBtn = document.getElementById('create-invoice-btn');
    if (createBtn) {
        createBtn.addEventListener('click', () => openInvoiceModal());
    }

    // Empty state create button
    const emptyStateBtn = document.querySelector('.create-invoice-trigger');
    if (emptyStateBtn) {
        emptyStateBtn.addEventListener('click', () => openInvoiceModal());
    }
}

/**
 * Initialize invoice modal
 */
function initializeInvoiceModal() {
    const modal = document.getElementById('invoice-modal');
    const closeBtn = document.getElementById('close-invoice-modal-btn');
    const cancelBtn = document.getElementById('cancel-invoice-btn');
    const form = document.getElementById('invoice-form');

    if (!modal || !form) {
        console.warn('Invoice modal elements not found');
        return;
    }

    // Close modal handlers
    [closeBtn, cancelBtn].forEach(btn => {
        if (btn) {
            btn.addEventListener('click', closeInvoiceModal);
        }
    });

    // Close on backdrop click
    modal.addEventListener('click', function (e) {
        if (e.target === modal) {
            closeInvoiceModal();
        }
    });

    // Close on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            closeInvoiceModal();
        }
    });

    // Form submission
    form.addEventListener('submit', handleInvoiceSubmit);

    // Set default invoice date to today
    const invoiceDateInput = document.getElementById('invoice-date');
    if (invoiceDateInput) {
        invoiceDateInput.value = formatDateForInput(new Date());
    }

    // Set default due date to 30 days from now
    const dueDateInput = document.getElementById('invoice-due-date');
    if (dueDateInput) {
        const dueDate = new Date();
        dueDate.setDate(dueDate.getDate() + 30);
        dueDateInput.value = formatDateForInput(dueDate);
        dueDateInput.addEventListener('change', () => clearFieldError(dueDateInput));
    }
}

/**
 * Open invoice modal for create or edit
 * @param {Object|null} invoice - Invoice data for edit mode, null for create mode
 */
function openInvoiceModal(invoice = null) {
    const modal = document.getElementById('invoice-modal');
    const modalTitle = document.getElementById('invoice-modal-title');
    const submitText = document.getElementById('submit-invoice-text');
    const form = document.getElementById('invoice-form');

    if (!modal || !form) return;

    // Reset form
    form.reset();

    if (invoice) {
        // Edit mode
        InvoiceState.editingInvoiceId = invoice.id;
        modalTitle.textContent = 'Edit Invoice';
        submitText.textContent = 'Save Changes';

        // Populate form fields
        document.getElementById('invoice-id').value = invoice.id;
        document.getElementById('invoice-number').value = invoice.invoice_number || '';
        document.getElementById('invoice-amount').value = invoice.amount || '';
        document.getElementById('invoice-date').value = formatDateForInput(invoice.invoice_date);
        document.getElementById('invoice-due-date').value = formatDateForInput(invoice.due_date);
        document.getElementById('invoice-description').value = invoice.description || '';
        InvoiceState.pendingAttachments = invoice.attachments || [];
    } else {
        // Create mode
        InvoiceState.editingInvoiceId = null;
        modalTitle.textContent = 'Create Invoice';
        submitText.textContent = 'Create Invoice';

        // Set default dates
        document.getElementById('invoice-date').value = formatDateForInput(new Date());
        const dueDate = new Date();
        dueDate.setDate(dueDate.getDate() + 30);
        document.getElementById('invoice-due-date').value = formatDateForInput(dueDate);
        InvoiceState.pendingAttachments = [];
    }

    renderAttachmentChips();

    // Show modal
    modal.classList.remove('hidden');
    InvoiceState.isModalOpen = true;

    // Focus first input
    setTimeout(() => {
        document.getElementById('invoice-number').focus();
    }, 100);
}

/**
 * Close invoice modal
 */
function closeInvoiceModal() {
    const modal = document.getElementById('invoice-modal');
    if (!modal) return;

    modal.classList.add('hidden');
    InvoiceState.isModalOpen = false;
    InvoiceState.editingInvoiceId = null;

    // Reset form
    const form = document.getElementById('invoice-form');
    if (form) {
        form.reset();
    }
}

/**
 * Handle invoice form submission
 */
async function handleInvoiceSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const submitBtn = document.getElementById('submit-invoice-btn');
    const isEditMode = InvoiceState.editingInvoiceId !== null;

    try {
        const hideLoading = showLoading(submitBtn, isEditMode ? 'Saving...' : 'Creating...');

        // Get form data
        const formData = new FormData(form);
        const invoiceData = {
            invoice_number: formData.get('invoice_number'),
            amount: parseFloat(formData.get('amount')),
            description: formData.get('description'),
            invoice_date: formData.get('invoice_date'),
            due_date: formData.get('due_date'),
            attachments: InvoiceState.pendingAttachments,
        };
        
        clearAllFieldErrors(form);
        
        // Validate data
        if (!invoiceData.invoice_number || !invoiceData.amount || !invoiceData.description) {
            hideLoading();
            showNotification('Please fill in all required fields', 'error');
            return;
        }

        if (invoiceData.amount <= 0) {
            hideLoading();
            showNotification('Amount must be greater than zero', 'error');
            return;
        }

        if (invoiceData.invoice_date && invoiceData.due_date) {
            if (new Date(invoiceData.due_date) < new Date(invoiceData.invoice_date)) {
                hideLoading();
                const dueDateField = document.getElementById('invoice-due-date');
                showFieldError(dueDateField, 'Due date cannot be earlier than invoice date');
                showNotification('Due date cannot be earlier than invoice date', 'error');
                return;
            }
        }

        let response;
        if (isEditMode) {
            // Update invoice via API
            response = await api.put(
                `/vendor/api/v1/invoices/${InvoiceState.editingInvoiceId}`,
                invoiceData
            );
            showNotification('Invoice updated successfully!', 'success');
        } else {
            // Create invoice via API
            response = await api.post('/vendor/api/v1/invoices', invoiceData);
            showNotification('Invoice created successfully!', 'success');
        }

        hideLoading();

        // Close modal
        closeInvoiceModal();

        // Reload invoices and stats
        await Promise.all([
            loadInvoices(),
            loadInvoiceStats()
        ]);

    } catch (error) {
        hideLoading();
        console.error('Error saving invoice:', error);

        // Handle API errors
        const errorMessage = handleAPIError(error, { showAlert: true });

        if (!(error.status === 403 && error.data?.error?.type === 'csrf_error')) {
            showNotification(`Failed to save invoice: ${errorMessage}`, 'error');
        }
    }
}

/**
 * Load invoices from API
 */
async function loadInvoices() {
    const tableBody = document.getElementById('invoices-table-body');
    const emptyState = document.getElementById('invoices-empty-state');

    InvoiceState.isLoading = true;

    try {
        const response = await fetch('/vendor/api/v1/invoices');
        if (!response.ok) {
            throw new Error('Failed to load invoices');
        }

        const data = await response.json();
        const invoices = data.invoices || [];

        InvoiceState.invoices = invoices;

        // Clear loading state
        tableBody.innerHTML = '';

        if (invoices.length === 0) {
            // Show empty state
            document.querySelector('.neural-table').classList.add('hidden');
            emptyState.classList.remove('hidden');
            return;
        }

        // Hide empty state, show table
        document.querySelector('.neural-table').classList.remove('hidden');
        emptyState.classList.add('hidden');

        // Render invoices
        invoices.forEach(invoice => {
            const row = createInvoiceRow(invoice);
            tableBody.appendChild(row);
        });

    } catch (error) {
        console.error('Error loading invoices:', error);
        tableBody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-8 text-text-secondary">
                    Failed to load invoices. Please try again.
                </td>
            </tr>
        `;
    } finally {
        InvoiceState.isLoading = false;
    }
}

/**
 * Create invoice table row element
 */
function createInvoiceRow(invoice) {
    const row = document.createElement('tr');

    // Format amount
    const amount = formatCurrency(invoice.amount);

    // Format dates
    const invoiceDate = formatDate(invoice.invoice_date);
    const dueDate = formatDate(invoice.due_date);
    const isOverdue = new Date(invoice.due_date) < new Date() && invoice.status !== 'paid';

    // Status mapping
    const status = getStatusConfig(invoice.status);

    row.innerHTML = `
        <td>
            <span class="font-medium text-text-bright">${escapeHtml(invoice.invoice_number || 'N/A')}</span>
        </td>
        <td>
            <span class="font-semibold text-vendor-accent">${amount}</span>
        </td>
        <td>
            <span class="text-text-primary">${invoiceDate}</span>
        </td>
        <td>
            <span class="${isOverdue ? 'text-vendor-danger' : 'text-text-primary'}">${dueDate}</span>
        </td>
        <td>
            <span class="status-indicator ${status.class}">${status.label}</span>
        </td>
        <td>
            <div class="flex items-center space-x-2">
                <button class="action-btn view" data-invoice-id="${invoice.id}" title="View">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
                    </svg>
                </button>
                <button class="action-btn edit" data-invoice-id="${invoice.id}" title="Edit">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                    </svg>
                </button>
            </div>
        </td>
    `;

    // Add event listeners
    const viewBtn = row.querySelector('.action-btn.view');
    const editBtn = row.querySelector('.action-btn.edit');

    if (viewBtn) {
        viewBtn.addEventListener('click', () => viewInvoice(invoice.id));
    }
    if (editBtn) {
        editBtn.addEventListener('click', () => editInvoice(invoice.id));
    }

    return row;
}

/**
 * Get status configuration for display
 */
function getStatusConfig(status) {
    const statusConfig = {
        'submitted': { class: 'pending', label: 'Submitted' },
        'processing': { class: 'processing', label: 'Processing' },
        'approved': { class: 'approved', label: 'Approved' },
        'rejected': { class: 'rejected', label: 'Rejected' },
        'paid': { class: 'approved', label: 'Paid' }
    };

    return statusConfig[status] || { class: 'pending', label: status };
}

/**
 * Format date for display
 */
function formatDate(dateString) {
    if (!dateString) return 'N/A';

    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        });
    } catch (error) {
        console.error('Error formatting date:', error);
        return 'Invalid Date';
    }
}

/**
 * Format date for input field (YYYY-MM-DD)
 */
function formatDateForInput(dateString) {
    if (!dateString) return '';

    try {
        const date = new Date(dateString);
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    } catch (error) {
        console.error('Error formatting date for input:', error);
        return '';
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
            currency: 'USD'
        }).format(amount);
    } catch (error) {
        console.error('Error formatting currency:', error);
        return `$${amount}`;
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Initialize invoice sidecar
 */
function initializeInvoiceSidecar() {
    const sidecar = document.getElementById('invoice-sidecar');
    const backdrop = document.getElementById('invoice-sidecar-backdrop');
    const closeBtn = document.getElementById('close-sidecar-btn');
    const editBtn = document.getElementById('sidecar-edit-btn');
    const reprocessBtn = document.getElementById('reprocess-invoice-btn');

    if (!sidecar) {
        console.warn('Invoice sidecar elements not found');
        return;
    }

    // Close sidecar handlers
    if (closeBtn) {
        closeBtn.addEventListener('click', closeInvoiceSidecar);
    }

    if (backdrop) {
        backdrop.addEventListener('click', closeInvoiceSidecar);
    }

    // Edit button handler
    if (editBtn) {
        editBtn.addEventListener('click', () => {
            if (InvoiceState.currentInvoice) {
                const invoiceId = InvoiceState.currentInvoice.id;
                closeInvoiceSidecar();
                setTimeout(() => {
                    if (invoiceId) {
                        editInvoice(invoiceId);
                    } else {
                        openInvoiceModal();
                    }
                }, 300);
            }
        });
    }

    // Re-process button handler
    if (reprocessBtn) {
        reprocessBtn.addEventListener('click', handleReprocessInvoice);
    }

    // Close on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && InvoiceState.isSidecarOpen) {
            closeInvoiceSidecar();
        }
    });
}

/**
 * Handle re-process invoice button click
 */
async function handleReprocessInvoice() {
    if (!InvoiceState.currentInvoice) {
        showNotification('No invoice selected', 'warning');
        return;
    }

    const reprocessBtn = document.getElementById('reprocess-invoice-btn');
    const statusMessage = document.getElementById('reprocess-status-message');

    try {
        // Show loading state
        const originalContent = reprocessBtn.innerHTML;
        reprocessBtn.disabled = true;
        reprocessBtn.innerHTML = `
            <svg class="w-4 h-4 mr-1 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
            Processing...
        `;

        // Make API request
        const response = await api.post(
            `/vendor/api/v1/invoices/${InvoiceState.currentInvoice.id}/reprocess`
        );

        // Show success message
        statusMessage.className = 'mt-3 p-3 rounded-lg text-sm bg-green-500/20 border border-green-500/30 text-green-400';
        statusMessage.innerHTML = `
            <div class="flex items-center">
                <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                <span>${response.data.message || 'Re-processing request submitted!'}</span>
            </div>
        `;
        statusMessage.classList.remove('hidden');

        showNotification('Invoice re-processing queued!', 'success');

        // Reset button after delay
        setTimeout(() => {
            reprocessBtn.disabled = false;
            reprocessBtn.innerHTML = originalContent;
        }, 3000);

    } catch (error) {
        console.error('Error requesting invoice re-processing:', error);

        // Show error message
        statusMessage.className = 'mt-3 p-3 rounded-lg text-sm bg-red-500/20 border border-red-500/30 text-red-400';
        statusMessage.innerHTML = `
            <div class="flex items-center">
                <svg class="w-4 h-4 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
                <span>${error.data?.detail || 'Failed to request re-processing. Please try again.'}</span>
            </div>
        `;
        statusMessage.classList.remove('hidden');

        // Handle API errors
        const errorMessage = handleAPIError(error, { showAlert: true });

        if (!(error.status === 403 && error.data?.error?.type === 'csrf_error')) {
            showNotification(`Failed to re-process invoice: ${errorMessage}`, 'error');
        }

        // Reset button
        reprocessBtn.disabled = false;
        reprocessBtn.innerHTML = `
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
            </svg>
            Re-process
        `;
    }
}

/**
 * Open invoice sidecar with invoice details
 */
function openInvoiceSidecar(invoice) {
    const sidecar = document.getElementById('invoice-sidecar');
    const backdrop = document.getElementById('invoice-sidecar-backdrop');

    if (!sidecar || !invoice) return;

    // Store current invoice
    InvoiceState.currentInvoice = invoice;
    InvoiceState.isSidecarOpen = true;

    // Populate sidecar content
    populateSidecarContent(invoice);

    // Show backdrop and sidecar with animation
    backdrop.classList.remove('hidden');
    requestAnimationFrame(() => {
        backdrop.classList.add('open');
        sidecar.classList.add('open');
    });
}

/**
 * Close invoice sidecar
 */
function closeInvoiceSidecar() {
    const sidecar = document.getElementById('invoice-sidecar');
    const backdrop = document.getElementById('invoice-sidecar-backdrop');

    if (!sidecar) return;

    InvoiceState.isSidecarOpen = false;

    // Animate out
    sidecar.classList.remove('open');
    backdrop.classList.remove('open');

    // Hide after animation
    setTimeout(() => {
        backdrop.classList.add('hidden');
        InvoiceState.currentInvoice = null;
    }, 300);
}

/**
 * Populate sidecar content with invoice data
 */
function populateSidecarContent(invoice) {
    // Invoice number
    const invoiceNumberEl = document.getElementById('sidecar-invoice-number');
    if (invoiceNumberEl) {
        invoiceNumberEl.textContent = invoice.invoice_number || 'N/A';
    }

    // Status
    const statusEl = document.getElementById('sidecar-status');
    if (statusEl) {
        const status = getStatusConfig(invoice.status);
        statusEl.className = `status-indicator ${status.class}`;
        statusEl.textContent = status.label;
    }

    // Amount
    const amountEl = document.getElementById('sidecar-amount');
    if (amountEl) {
        amountEl.textContent = formatCurrency(invoice.amount);
    }

    // Invoice date
    const invoiceDateEl = document.getElementById('sidecar-invoice-date');
    if (invoiceDateEl) {
        invoiceDateEl.textContent = formatDateLong(invoice.invoice_date);
    }

    // Due date
    const dueDateEl = document.getElementById('sidecar-due-date');
    if (dueDateEl) {
        const isOverdue = new Date(invoice.due_date) < new Date() && invoice.status !== 'paid';
        dueDateEl.textContent = formatDateLong(invoice.due_date);
        dueDateEl.className = `text-sm font-medium ${isOverdue ? 'text-vendor-danger' : 'text-text-bright'}`;
    }

    // Description
    const descriptionEl = document.getElementById('sidecar-description');
    if (descriptionEl) {
        descriptionEl.textContent = invoice.description || 'No description provided.';
    }

    // Attachments
    const attachSection = document.getElementById('sidecar-attachments-section');
    const attachList = document.getElementById('sidecar-attachments-list');
    const attachments = invoice.attachments || [];
    if (attachments.length > 0 && attachSection && attachList) {
        attachSection.classList.remove('hidden');
        attachList.innerHTML = attachments.map(a => `
            <div class="sidecar-attach-row">
                <span class="sa-icon" style="color:${(a.file_type || 'pdf') === 'doc' ? '#60a5fa' : '#f87171'}">
                    ${(a.file_type || 'pdf').toUpperCase()}
                </span>
                <span class="sa-name">${escapeHtml(a.filename)}</span>
            </div>
        `).join('');
    } else if (attachSection) {
        attachSection.classList.add('hidden');
    }

    // Agent notes
    renderAgentNotes(invoice.agent_notes);

    // Created at
    const createdAtEl = document.getElementById('sidecar-created-at');
    if (createdAtEl) {
        createdAtEl.textContent = formatDateTimeLong(invoice.created_at);
    }

    // Updated at
    const updatedAtEl = document.getElementById('sidecar-updated-at');
    if (updatedAtEl) {
        updatedAtEl.textContent = formatDateTimeLong(invoice.updated_at);
    }

    // Reset re-process status message
    const statusMessage = document.getElementById('reprocess-status-message');
    if (statusMessage) {
        statusMessage.classList.add('hidden');
        statusMessage.innerHTML = '';
    }
}

/**
 * Render agent notes with visual separation for each review iteration
 */
function renderAgentNotes(agentNotes) {
    const container = document.getElementById('sidecar-agent-notes');
    if (!container) return;

    if (!agentNotes || agentNotes.trim() === '') {
        container.innerHTML = '<span class="text-text-secondary italic">No processing notes available.</span>';
        return;
    }

    // Split notes by double newline (each review iteration)
    const noteEntries = agentNotes.split(/\n\n+/).filter(entry => entry.trim());

    if (noteEntries.length === 0) {
        container.innerHTML = '<span class="text-text-secondary italic">No processing notes available.</span>';
        return;
    }

    if (noteEntries.length === 1) {
        // Single entry - render simply
        container.innerHTML = `<p class="text-text-bright">${escapeHtml(noteEntries[0]).replace(/\n/g, '<br>')}</p>`;
        return;
    }

    // Multiple entries - reverse to show latest first (notes are appended in DB)
    const reversedEntries = [...noteEntries].reverse();
    const entriesHtml = reversedEntries.map((entry, index) => {
        const isLatest = index === 0;
        const entryNumber = reversedEntries.length - index;

        return `
            <div class="agent-note-entry ${isLatest ? 'latest' : ''}">
                <div class="flex items-center space-x-2 mb-1">
                    <span class="text-xs font-medium ${isLatest ? 'text-vendor-accent' : 'text-text-secondary'}">
                        ${isLatest ? 'Latest' : `Entry #${entryNumber}`}
                    </span>
                </div>
                <p class="text-sm text-text-bright leading-relaxed">${escapeHtml(entry).replace(/\n/g, '<br>')}</p>
            </div>
        `;
    }).join('');

    container.innerHTML = `<div class="space-y-2">${entriesHtml}</div>`;
}

/**
 * Format date for long display (e.g., "January 27, 2026")
 */
function formatDateLong(dateString) {
    if (!dateString) return 'N/A';

    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            month: 'long',
            day: 'numeric',
            year: 'numeric'
        });
    } catch (error) {
        console.error('Error formatting date:', error);
        return 'Invalid Date';
    }
}

/**
 * Format datetime for long display (e.g., "Jan 27, 2026 at 3:45 PM")
 */
function formatDateTimeLong(dateString) {
    if (!dateString) return 'N/A';

    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        });
    } catch (error) {
        console.error('Error formatting datetime:', error);
        return 'Invalid Date';
    }
}

/**
 * View invoice details in sidecar
 */
async function viewInvoice(invoiceId) {
    try {
        const response = await api.get(`/vendor/api/v1/invoices/${invoiceId}`);
        const invoice = response.data.invoice;

        openInvoiceSidecar(invoice);
    } catch (error) {
        console.error('Error loading invoice:', error);
        showNotification('Failed to load invoice details', 'error');
    }
}

/**
 * Edit invoice
 */
async function editInvoice(invoiceId) {
    try {
        const response = await api.get(`/vendor/api/v1/invoices/${invoiceId}`);
        const invoice = response.data.invoice;

        openInvoiceModal(invoice);
    } catch (error) {
        console.error('Error loading invoice:', error);
        showNotification('Failed to load invoice details', 'error');
    }
}

// =====================================================================
// FinDrive Attachment Picker
// =====================================================================

function initializeFinDrivePicker() {
    document.getElementById('attach-files-btn')?.addEventListener('click', openFinDrivePicker);
    document.getElementById('close-picker-btn')?.addEventListener('click', closeFinDrivePicker);
    document.getElementById('picker-done-btn')?.addEventListener('click', confirmPickerSelection);
    document.getElementById('findrive-picker-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'findrive-picker-modal') closeFinDrivePicker();
    });
}

async function openFinDrivePicker() {
    const modal = document.getElementById('findrive-picker-modal');
    const grid = document.getElementById('picker-files-grid');
    modal.classList.remove('hidden');

    InvoiceState.pickerSelectedIds = new Set(InvoiceState.pendingAttachments.map(a => a.file_id));

    try {
        const response = await api.get('/vendor/api/v1/findrive');
        const data = response.data || response;
        InvoiceState.driveFiles = data.files || [];

        if (InvoiceState.driveFiles.length === 0) {
            grid.innerHTML = '<p class="col-span-full text-center text-text-secondary py-8">No files in FinDrive yet.</p>';
            return;
        }

        grid.innerHTML = InvoiceState.driveFiles.map(f => {
            const selected = InvoiceState.pickerSelectedIds.has(f.id);
            const ft = f.file_type || 'pdf';
            return `<div class="picker-card ${selected ? 'selected' : ''}" data-file-id="${f.id}" data-filename="${_esc(f.filename)}" data-file-type="${ft}">
                <div style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.2))">${_pickerIcon(ft)}</div>
                <div class="picker-card-name">${_esc(f.filename)}</div>
            </div>`;
        }).join('');

        grid.querySelectorAll('.picker-card').forEach(card => {
            card.addEventListener('click', () => {
                const fid = parseInt(card.dataset.fileId);
                if (InvoiceState.pickerSelectedIds.has(fid)) {
                    InvoiceState.pickerSelectedIds.delete(fid);
                    card.classList.remove('selected');
                } else {
                    InvoiceState.pickerSelectedIds.add(fid);
                    card.classList.add('selected');
                }
            });
        });
    } catch (error) {
        console.error('Error loading FinDrive files:', error);
        grid.innerHTML = '<p class="col-span-full text-center text-red-400 py-8">Failed to load files.</p>';
    }
}

function closeFinDrivePicker() {
    document.getElementById('findrive-picker-modal').classList.add('hidden');
}

function confirmPickerSelection() {
    InvoiceState.pendingAttachments = InvoiceState.driveFiles
        .filter(f => InvoiceState.pickerSelectedIds.has(f.id))
        .map(f => ({ file_id: f.id, filename: f.filename, file_type: f.file_type || 'pdf' }));
    renderAttachmentChips();
    closeFinDrivePicker();
}

function renderAttachmentChips() {
    const container = document.getElementById('invoice-attachments');
    if (!container) return;

    const attachments = Array.isArray(InvoiceState.pendingAttachments)
        ? InvoiceState.pendingAttachments
        : [];
    InvoiceState.pendingAttachments = attachments;

    let noMsgEl = document.getElementById('no-attachments-msg');
    if (!noMsgEl || !(noMsgEl instanceof Node)) {
        noMsgEl = document.createElement('p');
        noMsgEl.id = 'no-attachments-msg';
        noMsgEl.className = 'text-xs text-text-secondary italic';
        noMsgEl.textContent =
            'No files attached. Click "Attach from FinDrive" to add supporting documents.';
    }

    container.innerHTML = '';
    container.appendChild(noMsgEl);

    if (attachments.length === 0) {
        noMsgEl.classList.remove('hidden');
        return;
    }

    noMsgEl.classList.add('hidden');

    const chipsHtml = attachments.map(a => `
        <span class="attach-chip">
            <span style="color:${a.file_type === 'doc' ? '#60a5fa' : '#f87171'}">${(a.file_type || 'pdf').toUpperCase()}</span>
            ${_esc(a.filename)}
            <button type="button" class="attach-chip-remove" data-fid="${a.file_id}">&times;</button>
        </span>
    `).join('');
    container.insertAdjacentHTML('beforeend', chipsHtml);

    container.querySelectorAll('.attach-chip-remove').forEach(btn => {
        btn.addEventListener('click', () => {
            const fid = parseInt(btn.dataset.fid);
            InvoiceState.pendingAttachments = InvoiceState.pendingAttachments.filter(a => a.file_id !== fid);
            renderAttachmentChips();
        });
    });
}

function _pickerIcon(type) {
    const colors = type === 'doc'
        ? { page: '#eff6ff', border: 'rgba(96,165,250,0.45)', fold: '#bfdbfe', badge: '#4285f4', label: 'DOC' }
        : { page: '#fff5f5', border: 'rgba(248,113,113,0.45)', fold: '#fecaca', badge: '#ef4444', label: 'PDF' };
    return `<svg viewBox="0 0 48 64" width="36" height="48" fill="none">
        <path d="M4 2C4 .9 4.9 0 6 0H30L44 14V60C44 61.1 43.1 62 42 62H6C4.9 62 4 61.1 4 60V2Z" fill="${colors.page}" stroke="${colors.border}" stroke-width="1"/>
        <path d="M30 0L44 14H34C31.8 14 30 12.2 30 10V0Z" fill="${colors.fold}"/>
        <rect x="8" y="46" width="22" height="11" rx="2" fill="${colors.badge}"/>
        <text x="19" y="54.5" text-anchor="middle" fill="#fff" font-size="7" font-weight="bold" font-family="Inter,system-ui,sans-serif">${colors.label}</text>
    </svg>`;
}

function _esc(t) {
    if (!t) return '';
    const d = document.createElement('div');
    d.textContent = t;
    return d.innerHTML;
}
