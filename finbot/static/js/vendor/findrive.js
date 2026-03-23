/**
 * FinBot Vendor Portal - FinDrive (mock Google Drive)
 */

const DriveState = {
    files: [],
    editingFileId: null,
    editingFileType: null,
    selectedFileId: null,
    vendorData: null,
};

const FILE_TYPES = {
    pdf: {
        label: 'Invoice PDF',
        typeLabel: 'PDF Document',
        extension: '.pdf',
        defaultFolder: '/invoices',
        saveLabel: 'Save Invoice',
        colors: { page: '#fff5f5', border: 'rgba(248,113,113,0.45)', fold: '#fecaca', lines: 'rgba(239,68,68,0.18)', badge: '#ef4444', badgeLabel: 'PDF' },
    },
    doc: {
        label: 'Document',
        typeLabel: 'Document',
        extension: '.doc',
        defaultFolder: '/documents',
        saveLabel: 'Save Document',
        colors: { page: '#eff6ff', border: 'rgba(96,165,250,0.45)', fold: '#bfdbfe', lines: 'rgba(59,130,246,0.18)', badge: '#4285f4', badgeLabel: 'DOC' },
    },
};

ready(function () { initializeFindrive(); });

async function initializeFindrive() {
    document.getElementById('new-file-btn')?.addEventListener('click', toggleNewMenu);
    document.getElementById('close-editor-btn')?.addEventListener('click', closeEditor);
    document.getElementById('cancel-editor-btn')?.addEventListener('click', closeEditor);
    document.getElementById('save-file-btn')?.addEventListener('click', saveFile);
    document.getElementById('close-viewer-btn')?.addEventListener('click', closeViewer);

    document.getElementById('file-editor-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'file-editor-modal') closeEditor();
    });
    document.getElementById('file-viewer-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'file-viewer-modal') closeViewer();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        const ed = document.getElementById('file-editor-modal');
        const vw = document.getElementById('file-viewer-modal');
        if (ed && !ed.classList.contains('hidden')) closeEditor();
        else if (vw && !vw.classList.contains('hidden')) closeViewer();
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('#new-file-btn') && !e.target.closest('#new-file-menu'))
            document.getElementById('new-file-menu')?.classList.add('hidden');
    });

    await Promise.all([loadVendorData(), loadFiles()]);
}

// =====================================================================
// VENDOR DATA
// =====================================================================

async function loadVendorData() {
    try {
        const ctx = await api.get('/vendor/api/v1/vendors/context');
        const ctxData = ctx.data || ctx;
        const current = ctxData.current_vendor;
        if (current?.id) {
            const resp = await api.get(`/vendor/api/v1/vendors/${current.id}`);
            DriveState.vendorData = resp.data || resp;
        }
    } catch (e) {
        console.error('Error loading vendor data:', e);
    }
}

// =====================================================================
// NEW FILE MENU
// =====================================================================

function toggleNewMenu() {
    document.getElementById('new-file-menu')?.classList.toggle('hidden');
}

function newFileOfType(type) {
    document.getElementById('new-file-menu')?.classList.add('hidden');
    openEditor(type);
}

// =====================================================================
// FILE GRID
// =====================================================================

async function loadFiles() {
    const grid = document.getElementById('drive-grid');
    const emptyState = document.getElementById('files-empty-state');

    try {
        const response = await api.get('/vendor/api/v1/findrive');
        const data = response.data || response;
        const files = data.files || [];
        DriveState.files = files;

        document.getElementById('stat-file-count').textContent = files.length;

        if (files.length === 0) {
            grid.innerHTML = '';
            emptyState.classList.remove('hidden');
            closeSidecar();
            return;
        }

        emptyState.classList.add('hidden');
        renderFileGrid(files);
    } catch (error) {
        console.error('Error loading files:', error);
        grid.innerHTML = '<p class="text-center py-8 text-red-400 col-span-full">Failed to load files.</p>';
    }
}

function renderFileGrid(files) {
    const grid = document.getElementById('drive-grid');
    grid.innerHTML = files.map(f => renderFileCard(f)).join('');

    grid.querySelectorAll('.drive-card').forEach(card => {
        const fid = parseInt(card.dataset.fileId);
        card.addEventListener('click', (e) => { e.stopPropagation(); selectFile(fid); });
        card.addEventListener('dblclick', (e) => { e.stopPropagation(); openFile(fid); });
    });

    grid.addEventListener('click', (e) => {
        if (!e.target.closest('.drive-card')) closeSidecar();
    });
}

function renderFileCard(file) {
    const date = new Date(file.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const selected = DriveState.selectedFileId === file.id;
    const ft = file.file_type || 'pdf';

    return `
        <div class="drive-card ${selected ? 'drive-card-selected' : ''}" data-file-id="${file.id}">
            <div class="drive-card-icon">${fileIconSvg(ft, 48)}</div>
            <div class="drive-card-name">${escHtml(file.filename)}</div>
            <div class="drive-card-date">${date}</div>
        </div>
    `;
}

// =====================================================================
// SIDECAR
// =====================================================================

function selectFile(fileId) {
    DriveState.selectedFileId = fileId;
    document.querySelectorAll('.drive-card').forEach(c => {
        c.classList.toggle('drive-card-selected', parseInt(c.dataset.fileId) === fileId);
    });
    const file = DriveState.files.find(f => f.id === fileId);
    if (file) openSidecar(file);
}

function openSidecar(file) {
    const sc = document.getElementById('drive-sidecar');
    const ft = file.file_type || 'pdf';
    const meta = FILE_TYPES[ft] || FILE_TYPES.pdf;
    const date = new Date(file.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const updated = new Date(file.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const size = file.file_size < 1024 ? `${file.file_size} B` : `${(file.file_size / 1024).toFixed(1)} KB`;

    sc.innerHTML = `
        <div class="sc-header">
            <span class="sc-header-title">Details</span>
            <button onclick="closeSidecar()" class="sc-close-btn" title="Close">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </div>
        <div class="sc-icon">${fileIconSvg(ft, 72)}</div>
        <div class="sc-filename">${escHtml(file.filename)}</div>
        <div class="sc-meta">
            <div class="sc-meta-row"><span>Type</span><span>${meta.typeLabel}</span></div>
            <div class="sc-meta-row"><span>Size</span><span>${size}</span></div>
            <div class="sc-meta-row"><span>Created</span><span>${date}</span></div>
            <div class="sc-meta-row"><span>Modified</span><span>${updated}</span></div>
            <div class="sc-meta-row"><span>Location</span><span>${escHtml(file.folder_path)}</span></div>
        </div>
        <div class="sc-actions">
            <button onclick="openFile(${file.id})" class="sc-btn sc-btn-primary">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
                </svg>
                Open
            </button>
            <button onclick="editFile(${file.id})" class="sc-btn">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                </svg>
                Edit
            </button>
            <button onclick="deleteFile(${file.id})" class="sc-btn sc-btn-danger">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                </svg>
                Delete
            </button>
        </div>
    `;
    sc.classList.remove('hidden');
}

function closeSidecar() {
    document.getElementById('drive-sidecar').classList.add('hidden');
    DriveState.selectedFileId = null;
    document.querySelectorAll('.drive-card').forEach(c => c.classList.remove('drive-card-selected'));
}

// =====================================================================
// GENERIC EDITOR
// =====================================================================

function openEditor(fileType, existingFile = null) {
    const modal = document.getElementById('file-editor-modal');
    const titleEl = document.getElementById('editor-title');
    const filenameEl = document.getElementById('editor-filename');
    const saveBtn = document.getElementById('save-file-btn');
    const saveLabelEl = document.getElementById('save-file-label');
    const meta = FILE_TYPES[fileType] || FILE_TYPES.pdf;

    let contentData;
    if (existingFile) {
        DriveState.editingFileId = existingFile.id;
        DriveState.editingFileType = fileType;
        titleEl.textContent = `Edit ${meta.label}`;
        filenameEl.value = existingFile.filename;
        try { contentData = JSON.parse(existingFile.content_text); } catch (_) { contentData = null; }
    } else {
        DriveState.editingFileId = null;
        DriveState.editingFileType = fileType;
        titleEl.textContent = `New ${meta.label}`;
        contentData = null;
    }

    saveLabelEl.textContent = meta.saveLabel;

    const paper = document.getElementById('editor-paper');
    if (fileType === 'doc') {
        const data = contentData || createDefaultDocument();
        if (!existingFile) filenameEl.value = `untitled-document${meta.extension}`;
        renderDocEditor(paper, data);
    } else {
        const data = contentData || createDefaultInvoice();
        if (!existingFile) filenameEl.value = `invoice-${data.invoice_number.toLowerCase()}${meta.extension}`;
        renderInvoiceEditor(paper, data);
    }

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function closeEditor() {
    document.getElementById('file-editor-modal').classList.add('hidden');
    document.body.style.overflow = '';
    DriveState.editingFileId = null;
    DriveState.editingFileType = null;
}

async function saveFile() {
    const fileType = DriveState.editingFileType || 'pdf';
    const meta = FILE_TYPES[fileType] || FILE_TYPES.pdf;
    const filename = document.getElementById('editor-filename').value.trim();

    if (!filename) { showNotification('Filename is required', 'error'); return; }

    let contentData;
    if (fileType === 'doc') {
        contentData = collectDocData();
    } else {
        contentData = collectInvoiceData();
        if (!contentData.invoice_number) { showNotification('Invoice number is required', 'error'); return; }
    }

    const content = JSON.stringify(contentData, null, 2);

    try {
        if (DriveState.editingFileId !== null) {
            await api.put(`/vendor/api/v1/findrive/${DriveState.editingFileId}`, { filename, content });
            showNotification('File updated', 'success');
        } else {
            await api.post('/vendor/api/v1/findrive', { filename, content, folder: meta.defaultFolder, file_type: fileType });
            showNotification('File created', 'success');
        }
        closeEditor();
        await loadFiles();
    } catch (error) {
        console.error('Error saving file:', error);
        handleAPIError(error, { showAlert: true });
    }
}

// =====================================================================
// GENERIC VIEWER
// =====================================================================

async function openFile(fileId) {
    try {
        const response = await api.get(`/vendor/api/v1/findrive/${fileId}`);
        const data = response.data || response;
        const file = data.file;
        const ft = file.file_type || 'pdf';

        let contentData;
        try { contentData = JSON.parse(file.content_text); } catch (_) { contentData = {}; }

        document.getElementById('viewer-title').textContent = file.filename;
        document.getElementById('viewer-edit-btn').dataset.fileId = file.id;
        document.getElementById('viewer-edit-btn').dataset.fileType = ft;

        const paper = document.getElementById('viewer-paper');
        if (ft === 'doc') renderDocViewer(paper, contentData);
        else renderInvoiceViewer(paper, contentData);

        document.getElementById('file-viewer-modal').classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    } catch (error) {
        console.error('Error opening file:', error);
        showNotification('Failed to open file', 'error');
    }
}

function closeViewer() {
    document.getElementById('file-viewer-modal').classList.add('hidden');
    document.body.style.overflow = '';
}

async function editFile(fileId) {
    try {
        const response = await api.get(`/vendor/api/v1/findrive/${fileId}`);
        const data = response.data || response;
        const file = data.file;
        openEditor(file.file_type || 'pdf', file);
    } catch (error) {
        console.error('Error loading file for edit:', error);
        showNotification('Failed to load file', 'error');
    }
}

async function editFromViewer() {
    const btn = document.getElementById('viewer-edit-btn');
    const fileId = parseInt(btn.dataset.fileId);
    closeViewer();
    await editFile(fileId);
}

async function deleteFile(fileId) {
    const confirmed = await showConfirmModal({
        title: 'Delete File',
        message: 'This file will be permanently removed. This action cannot be undone.',
        confirmText: 'Delete',
        danger: true,
    });
    if (!confirmed) return;

    try {
        await api.delete(`/vendor/api/v1/findrive/${fileId}`);
        showNotification('File deleted', 'success');
        closeSidecar();
        await loadFiles();
    } catch (error) {
        console.error('Error deleting file:', error);
        handleAPIError(error, { showAlert: true });
    }
}

// =====================================================================
// INVOICE PDF — data + editor + viewer
// =====================================================================

function createDefaultInvoice() {
    const today = new Date();
    const dueDate = new Date(today);
    dueDate.setDate(dueDate.getDate() + 30);
    const num = DriveState.files.filter(f => (f.file_type || 'pdf') === 'pdf').length + 1;
    const v = DriveState.vendorData || {};

    return {
        invoice_number: `INV-${today.getFullYear()}-${String(num).padStart(3, '0')}`,
        date: fmtDateInput(today),
        due_date: fmtDateInput(dueDate),
        from_company: v.company_name || '', from_address: '', from_city_state_zip: '',
        from_email: v.email || '', from_phone: v.phone || '',
        bill_to_company: 'OWASP FinBot',
        bill_to_address: '1234 Innovation Drive, Suite 567',
        bill_to_city_state_zip: 'Los Angeles, CA 90028',
        bill_to_email: 'ap@owasp-finbot-ctf.org',
        items: [{ description: '', quantity: 1, rate: 0, amount: 0 }],
        notes: '', tax_rate: 0, payment_terms: 'Net 30',
    };
}

function renderInvoiceEditor(paper, inv) {
    const notesHtml = inv.notes_segments?.length ? segmentsToHtml(inv.notes_segments) : escHtml(inv.notes || '');
    paper.innerHTML = `
        <div class="inv-header">
            <div class="inv-from-block">
                <div class="inv-label">FROM</div>
                <input type="text" class="inv-input inv-input-company" data-field="from_company" placeholder="Your Company Name" value="${escAttr(inv.from_company)}">
                <input type="text" class="inv-input" data-field="from_address" placeholder="Street Address" value="${escAttr(inv.from_address)}">
                <input type="text" class="inv-input" data-field="from_city_state_zip" placeholder="City, State ZIP" value="${escAttr(inv.from_city_state_zip)}">
                <input type="text" class="inv-input" data-field="from_email" placeholder="email@company.com" value="${escAttr(inv.from_email)}">
                <input type="text" class="inv-input" data-field="from_phone" placeholder="(555) 123-4567" value="${escAttr(inv.from_phone)}">
            </div>
            <div class="inv-meta-block">
                <h1 class="inv-doc-title">INVOICE</h1>
                <div class="inv-meta-grid">
                    <label>Invoice #</label>
                    <input type="text" class="inv-input inv-input-meta" data-field="invoice_number" value="${escAttr(inv.invoice_number)}">
                    <label>Date</label>
                    <input type="date" class="inv-input inv-input-meta" data-field="date" value="${escAttr(inv.date)}">
                    <label>Due Date</label>
                    <input type="date" class="inv-input inv-input-meta" data-field="due_date" value="${escAttr(inv.due_date)}">
                    <label>Terms</label>
                    <input type="text" class="inv-input inv-input-meta" data-field="payment_terms" value="${escAttr(inv.payment_terms)}">
                </div>
            </div>
        </div>
        <div class="inv-billto">
            <div class="inv-label">BILL TO</div>
            <input type="text" class="inv-input inv-input-company" data-field="bill_to_company" placeholder="Client Company Name" value="${escAttr(inv.bill_to_company)}">
            <input type="text" class="inv-input" data-field="bill_to_address" placeholder="Street Address" value="${escAttr(inv.bill_to_address)}">
            <input type="text" class="inv-input" data-field="bill_to_city_state_zip" placeholder="City, State ZIP" value="${escAttr(inv.bill_to_city_state_zip)}">
            <input type="text" class="inv-input" data-field="bill_to_email" placeholder="client@company.com" value="${escAttr(inv.bill_to_email)}">
        </div>
        <table class="inv-table">
            <thead><tr><th class="inv-th-desc">Description</th><th class="inv-th-num">Qty</th><th class="inv-th-num">Rate</th><th class="inv-th-num">Amount</th><th class="inv-th-act"></th></tr></thead>
            <tbody id="inv-items-body">${(inv.items || []).map((item, i) => itemRowHtml(item, i)).join('')}</tbody>
        </table>
        <button type="button" id="add-item-btn" class="inv-add-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
            Add Line Item
        </button>
        <div class="inv-totals-block">
            <div class="inv-totals-row"><span>Subtotal</span><span id="inv-subtotal">$0.00</span></div>
            <div class="inv-totals-row"><span>Tax <input type="number" class="inv-input inv-input-tax" data-field="tax_rate" value="${inv.tax_rate || 0}" min="0" max="100" step="0.1">%</span><span id="inv-tax">$0.00</span></div>
            <div class="inv-totals-row inv-totals-total"><span>Total</span><span id="inv-total">$0.00</span></div>
        </div>
        <div class="inv-notes-block">
            <div class="inv-label">NOTES / TERMS</div>
            ${formatToolbarHtml()}
            <div class="inv-notes-editable fmt-editable" contenteditable="true" data-placeholder="Additional notes, payment instructions, or terms...">${notesHtml}</div>
        </div>
        <div class="paper-footer-line"></div>
        <div class="paper-footer-text">Generated with FinDrive &middot; Powered by OWASP FinBot</div>
    `;
    paper.querySelectorAll('.inv-item-qty, .inv-item-rate').forEach(el => el.addEventListener('input', recalculate));
    paper.querySelector('[data-field="tax_rate"]')?.addEventListener('input', recalculate);
    paper.querySelectorAll('.inv-remove-btn').forEach(btn => btn.addEventListener('click', () => removeItem(btn)));
    document.getElementById('add-item-btn')?.addEventListener('click', addItem);
    recalculate();
    initFormatToolbar(paper);
}

function renderInvoiceViewer(paper, inv) {
    const items = inv.items || [];
    const subtotal = items.reduce((s, i) => s + (i.amount || i.quantity * i.rate || 0), 0);
    const taxRate = inv.tax_rate || 0;
    const tax = subtotal * taxRate / 100;
    const total = subtotal + tax;
    const line = (v) => v ? `<div class="inv-view-line">${escHtml(v)}</div>` : '';
    const hasNotes = inv.notes_segments?.length > 0 || inv.notes;
    const notesHtml = inv.notes_segments?.length ? segmentsToHtml(inv.notes_segments) : escHtml(inv.notes || '');

    paper.innerHTML = `
        <div class="inv-header">
            <div class="inv-from-block">
                <div class="inv-view-company">${escHtml(inv.from_company) || '<span class="inv-view-empty">Company Name</span>'}</div>
                ${line(inv.from_address)}${line(inv.from_city_state_zip)}${line(inv.from_email)}${line(inv.from_phone)}
            </div>
            <div class="inv-meta-block">
                <h1 class="inv-doc-title">INVOICE</h1>
                <div class="inv-view-meta">
                    <div><span>Invoice #</span><span>${escHtml(inv.invoice_number)}</span></div>
                    <div><span>Date</span><span>${fmtDisplayDate(inv.date)}</span></div>
                    <div><span>Due Date</span><span>${fmtDisplayDate(inv.due_date)}</span></div>
                    <div><span>Terms</span><span>${escHtml(inv.payment_terms)}</span></div>
                </div>
            </div>
        </div>
        <div class="inv-billto">
            <div class="inv-label">BILL TO</div>
            <div class="inv-view-company">${escHtml(inv.bill_to_company) || '<span class="inv-view-empty">Client Name</span>'}</div>
            ${line(inv.bill_to_address)}${line(inv.bill_to_city_state_zip)}${line(inv.bill_to_email)}
        </div>
        <table class="inv-table inv-table-view">
            <thead><tr><th class="inv-th-desc">Description</th><th class="inv-th-num">Qty</th><th class="inv-th-num">Rate</th><th class="inv-th-num">Amount</th></tr></thead>
            <tbody>${items.map(i => `<tr><td>${escHtml(i.description)}</td><td class="text-center">${i.quantity}</td><td class="text-right">${fmtCurrency(i.rate)}</td><td class="text-right">${fmtCurrency(i.quantity * i.rate)}</td></tr>`).join('')}</tbody>
        </table>
        <div class="inv-totals-block inv-view-totals">
            <div class="inv-totals-row"><span>Subtotal</span><span>${fmtCurrency(subtotal)}</span></div>
            ${taxRate > 0 ? `<div class="inv-totals-row"><span>Tax (${taxRate}%)</span><span>${fmtCurrency(tax)}</span></div>` : ''}
            <div class="inv-totals-row inv-totals-total"><span>Total Due</span><span>${fmtCurrency(total)}</span></div>
        </div>
        ${hasNotes ? `<div class="inv-notes-block"><div class="inv-label">NOTES / TERMS</div><div class="inv-view-notes">${notesHtml}</div></div>` : ''}
        <div class="paper-footer-line"></div>
        <div class="paper-footer-text">Generated with FinDrive &middot; Powered by OWASP FinBot</div>
    `;
}

function collectInvoiceData() {
    const paper = document.getElementById('editor-paper');
    const f = (n) => paper.querySelector(`[data-field="${n}"]`)?.value || '';
    const items = [];
    paper.querySelectorAll('.inv-row').forEach(row => {
        const qty = parseFloat(row.querySelector('.inv-item-qty')?.value) || 0;
        const rate = parseFloat(row.querySelector('.inv-item-rate')?.value) || 0;
        items.push({ description: row.querySelector('.inv-item-desc')?.value || '', quantity: qty, rate, amount: qty * rate });
    });
    const subtotal = items.reduce((s, i) => s + i.amount, 0);
    const taxRate = parseFloat(f('tax_rate')) || 0;
    const tax = subtotal * taxRate / 100;
    const notesEditable = paper.querySelector('.inv-notes-editable');
    const notesSegments = notesEditable ? htmlToSegments(notesEditable) : [];
    const notesText = notesSegments.map(s => s.text).join('');
    return {
        invoice_number: f('invoice_number'), date: f('date'), due_date: f('due_date'),
        from_company: f('from_company'), from_address: f('from_address'), from_city_state_zip: f('from_city_state_zip'),
        from_email: f('from_email'), from_phone: f('from_phone'),
        bill_to_company: f('bill_to_company'), bill_to_address: f('bill_to_address'),
        bill_to_city_state_zip: f('bill_to_city_state_zip'), bill_to_email: f('bill_to_email'),
        items, subtotal, tax_rate: taxRate, tax, total: subtotal + tax,
        notes: notesText, notes_segments: notesSegments, payment_terms: f('payment_terms'),
    };
}

function itemRowHtml(item, idx) {
    return `<tr class="inv-row" data-idx="${idx}">
        <td><input type="text" class="inv-input inv-item-desc" value="${escAttr(item.description)}" placeholder="Item description"></td>
        <td><input type="number" class="inv-input inv-item-qty" value="${item.quantity}" min="0" step="1"></td>
        <td><input type="number" class="inv-input inv-item-rate" value="${item.rate}" min="0" step="0.01"></td>
        <td class="inv-item-amt">${fmtCurrency(item.quantity * item.rate)}</td>
        <td><button type="button" class="inv-remove-btn" title="Remove"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button></td>
    </tr>`;
}

function addItem() {
    const tbody = document.getElementById('inv-items-body');
    const tr = document.createElement('tr');
    tr.className = 'inv-row';
    tr.dataset.idx = tbody.children.length;
    tr.innerHTML = `<td><input type="text" class="inv-input inv-item-desc" value="" placeholder="Item description"></td>
        <td><input type="number" class="inv-input inv-item-qty" value="1" min="0" step="1"></td>
        <td><input type="number" class="inv-input inv-item-rate" value="0" min="0" step="0.01"></td>
        <td class="inv-item-amt">$0.00</td>
        <td><button type="button" class="inv-remove-btn" title="Remove"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button></td>`;
    tbody.appendChild(tr);
    tr.querySelectorAll('.inv-item-qty, .inv-item-rate').forEach(el => el.addEventListener('input', recalculate));
    tr.querySelector('.inv-remove-btn').addEventListener('click', () => removeItem(tr.querySelector('.inv-remove-btn')));
    tr.querySelector('.inv-item-desc').focus();
}

function removeItem(btn) {
    const tbody = document.getElementById('inv-items-body');
    if (tbody.children.length <= 1) return;
    btn.closest('.inv-row').remove();
    recalculate();
}

function recalculate() {
    let subtotal = 0;
    document.querySelectorAll('.inv-row').forEach(row => {
        const qty = parseFloat(row.querySelector('.inv-item-qty')?.value) || 0;
        const rate = parseFloat(row.querySelector('.inv-item-rate')?.value) || 0;
        const amt = qty * rate;
        row.querySelector('.inv-item-amt').textContent = fmtCurrency(amt);
        subtotal += amt;
    });
    const taxRate = parseFloat(document.querySelector('[data-field="tax_rate"]')?.value) || 0;
    const tax = subtotal * taxRate / 100;
    document.getElementById('inv-subtotal').textContent = fmtCurrency(subtotal);
    document.getElementById('inv-tax').textContent = fmtCurrency(tax);
    document.getElementById('inv-total').textContent = fmtCurrency(subtotal + tax);
}

// =====================================================================
// DOCUMENT — data + editor + viewer
// =====================================================================

function createDefaultDocument() {
    return { title: '', content: '' };
}

function renderDocEditor(paper, data) {
    const bodyHtml = data.segments?.length ? segmentsToHtml(data.segments) : escHtml(data.content || '');
    paper.innerHTML = `
        <input type="text" class="doc-title-input" data-field="title" placeholder="Untitled Document" value="${escAttr(data.title)}">
        <div class="doc-divider"></div>
        ${formatToolbarHtml()}
        <div class="doc-body-editable fmt-editable" contenteditable="true" data-placeholder="Start typing your document...">${bodyHtml}</div>
        <div class="paper-footer-line"></div>
        <div class="paper-footer-text">Generated with FinDrive &middot; Powered by OWASP FinBot</div>
    `;
    initFormatToolbar(paper);
}

function renderDocViewer(paper, data) {
    let bodyHtml;
    if (data.segments?.length) {
        bodyHtml = segmentsToHtml(data.segments);
    } else {
        const paragraphs = (data.content || '').split('\n').filter(p => p.trim() !== '' || true)
            .map(p => p.trim() === '' ? '<br>' : `<p class="doc-paragraph">${escHtml(p)}</p>`).join('');
        bodyHtml = paragraphs || '<p class="inv-view-empty">No content</p>';
    }

    paper.innerHTML = `
        <h1 class="doc-view-title">${escHtml(data.title) || '<span class="inv-view-empty">Untitled Document</span>'}</h1>
        <div class="doc-divider"></div>
        <div class="doc-view-body">${bodyHtml}</div>
        <div class="paper-footer-line"></div>
        <div class="paper-footer-text">Generated with FinDrive &middot; Powered by OWASP FinBot</div>
    `;
}

function collectDocData() {
    const paper = document.getElementById('editor-paper');
    const editable = paper.querySelector('.doc-body-editable');
    const segments = editable ? htmlToSegments(editable) : [];
    const plainText = segments.map(s => s.text).join('');
    return {
        title: paper.querySelector('[data-field="title"]')?.value || '',
        content: plainText,
        segments: segments,
    };
}

// =====================================================================
// RICH TEXT FORMATTING
// =====================================================================

let _savedRange = null;

const FMT_COLORS = [
    { hex: '#000000', label: 'Black' },
    { hex: '#374151', label: 'Gray' },
    { hex: '#dc2626', label: 'Red' },
    { hex: '#2563eb', label: 'Blue' },
    { hex: '#16a34a', label: 'Green' },
    { hex: '#ea580c', label: 'Orange' },
    { hex: '#7c3aed', label: 'Purple' },
    { hex: '#ffffff', label: 'White' },
];

function formatToolbarHtml() {
    const swatches = FMT_COLORS.map(c =>
        `<button type="button" class="fmt-swatch${c.hex === '#ffffff' ? ' fmt-swatch-light' : ''}" ` +
        `style="background:${c.hex}" title="${c.label}" onmousedown="event.preventDefault()" ` +
        `onclick="fmtColor('${c.hex}')"></button>`
    ).join('');

    return `<div class="fmt-toolbar">
        <button type="button" class="fmt-btn" title="Bold" onmousedown="event.preventDefault()" onclick="fmtBold()"><strong>B</strong></button>
        <button type="button" class="fmt-btn fmt-btn-italic" title="Italic" onmousedown="event.preventDefault()" onclick="fmtItalic()"><em>I</em></button>
        <div class="fmt-sep"></div>
        <select class="fmt-select" title="Font Size" onmousedown="fmtSaveSelection()" onchange="fmtFontSize(this.value);this.selectedIndex=0">
            <option value="">Size</option>
            <option value="1">1px</option>
            <option value="8">8px</option>
            <option value="10">10px</option>
            <option value="12">12px</option>
            <option value="14">14px</option>
            <option value="16">16px</option>
            <option value="20">20px</option>
            <option value="24">24px</option>
            <option value="36">36px</option>
        </select>
        <div class="fmt-sep"></div>
        <div class="fmt-swatches">${swatches}</div>
        <input type="color" class="fmt-color-input" value="#000000" title="Custom color" onmousedown="fmtSaveSelection()" onchange="fmtColor(this.value)">
    </div>`;
}

function initFormatToolbar(container) {
    const editable = container.querySelector('.fmt-editable');
    if (!editable) return;
    editable.addEventListener('paste', (e) => {
        e.preventDefault();
        document.execCommand('insertText', false, e.clipboardData.getData('text/plain'));
    });
}

function fmtSaveSelection() {
    const sel = window.getSelection();
    if (sel.rangeCount > 0) _savedRange = sel.getRangeAt(0).cloneRange();
}

function fmtRestoreSelection() {
    if (!_savedRange) return false;
    const editable = document.querySelector('.fmt-editable');
    if (editable) editable.focus();
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(_savedRange);
    _savedRange = null;
    return true;
}

function fmtBold() { document.execCommand('bold'); }
function fmtItalic() { document.execCommand('italic'); }

function fmtColor(color) {
    fmtRestoreSelection();
    document.execCommand('styleWithCSS', false, true);
    document.execCommand('foreColor', false, color);
}

function fmtFontSize(size) {
    if (!size) return;
    fmtRestoreSelection();
    const sel = window.getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return;
    const range = sel.getRangeAt(0);
    const span = document.createElement('span');
    span.style.fontSize = size + 'px';
    const contents = range.extractContents();
    span.appendChild(contents);
    range.insertNode(span);
    sel.removeAllRanges();
    const r = document.createRange();
    r.selectNodeContents(span);
    sel.addRange(r);
}

function segmentsToHtml(segments) {
    if (!segments || segments.length === 0) return '';
    return segments.map(seg => {
        if (seg.text === '\n') return '<br>';
        const text = escHtml(seg.text);
        const s = seg.style || {};
        const parts = [];
        if (s.fontSize && typeof s.fontSize === 'number') parts.push(`font-size:${s.fontSize}px`);
        if (s.color && typeof s.color === 'string') parts.push(`color:${escAttr(s.color)}`);
        if (s.bold) parts.push('font-weight:bold');
        if (s.italic) parts.push('font-style:italic');
        return parts.length > 0 ? `<span style="${parts.join(';')}">${text}</span>` : text;
    }).join('');
}

function htmlToSegments(container) {
    const segments = [];
    const cs = window.getComputedStyle(container);
    const defColor = cs.color;
    const defSize = Math.round(parseFloat(cs.fontSize));

    function walk(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent;
            if (!text) return;
            const el = node.parentElement;
            const st = window.getComputedStyle(el);
            const style = {};
            const fw = st.fontWeight;
            if (fw === 'bold' || fw === '700' || parseInt(fw) >= 700) style.bold = true;
            if (st.fontStyle === 'italic') style.italic = true;
            const fs = Math.round(parseFloat(st.fontSize));
            if (fs !== defSize) style.fontSize = fs;
            const clr = st.color;
            if (clr !== defColor) style.color = rgbToHex(clr);
            const prev = segments.length > 0 ? segments[segments.length - 1] : null;
            if (prev && prev.text !== '\n' && JSON.stringify(prev.style) === JSON.stringify(style)) {
                prev.text += text;
            } else {
                segments.push({ text, style });
            }
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            const tag = node.tagName.toLowerCase();
            if (tag === 'br') {
                segments.push({ text: '\n', style: {} });
            } else {
                if ((tag === 'div' || tag === 'p') && segments.length > 0) {
                    const last = segments[segments.length - 1];
                    if (last.text !== '\n') segments.push({ text: '\n', style: {} });
                }
                for (const child of node.childNodes) walk(child);
            }
        }
    }

    for (const child of container.childNodes) walk(child);
    return segments;
}

function rgbToHex(rgb) {
    if (!rgb) return '#000000';
    if (rgb.startsWith('#')) return rgb;
    const m = rgb.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
    if (!m) return '#000000';
    return '#' + [m[1], m[2], m[3]].map(x => parseInt(x).toString(16).padStart(2, '0')).join('');
}

// =====================================================================
// FILE ICONS
// =====================================================================

function fileIconSvg(type, size) {
    const h = Math.round(size * 64 / 48);
    const c = (FILE_TYPES[type] || FILE_TYPES.pdf).colors;

    return `<svg viewBox="0 0 48 64" width="${size}" height="${h}" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 2C4 .9 4.9 0 6 0H30L44 14V60C44 61.1 43.1 62 42 62H6C4.9 62 4 61.1 4 60V2Z" fill="${c.page}" stroke="${c.border}" stroke-width="1"/>
        <path d="M30 0L44 14H34C31.8 14 30 12.2 30 10V0Z" fill="${c.fold}"/>
        <rect x="10" y="22" width="24" height="1.5" rx=".75" fill="${c.lines}"/>
        <rect x="10" y="27" width="20" height="1.5" rx=".75" fill="${c.lines}" opacity=".8"/>
        <rect x="10" y="32" width="22" height="1.5" rx=".75" fill="${c.lines}" opacity=".6"/>
        <rect x="10" y="37" width="18" height="1.5" rx=".75" fill="${c.lines}" opacity=".5"/>
        <rect x="8" y="46" width="22" height="11" rx="2" fill="${c.badge}"/>
        <text x="19" y="54.5" text-anchor="middle" fill="#fff" font-size="7" font-weight="bold" font-family="Inter,system-ui,sans-serif">${c.badgeLabel}</text>
    </svg>`;
}

// =====================================================================
// UTILITIES
// =====================================================================

function fmtCurrency(n) { return '$' + (n || 0).toFixed(2).replace(/\d(?=(\d{3})+\.)/g, '$&,'); }
function fmtDateInput(d) { return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }
function fmtDisplayDate(s) {
    if (!s) return '';
    try { return new Date(s + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); }
    catch (_) { return s; }
}

function escHtml(text) {
    if (!text) return '';
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

function escAttr(text) {
    if (!text) return '';
    return String(text).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
