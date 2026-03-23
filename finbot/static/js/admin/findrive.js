/**
 * FinBot Admin FinDrive - Read-only file browser with report viewer
 * Modeled after vendor FinDrive UX: grid cards, sidecar, fullscreen viewer
 */

const FILE_TYPES = {
    report: {
        typeLabel: 'Co-Pilot Report',
        colors: { page: '#fffbeb', border: 'rgba(245,158,11,0.45)', fold: '#fde68a', lines: 'rgba(245,158,11,0.2)', badge: '#d97706', badgeLabel: 'RPT' },
    },
    pdf: {
        typeLabel: 'PDF Document',
        colors: { page: '#fff5f5', border: 'rgba(248,113,113,0.45)', fold: '#fecaca', lines: 'rgba(239,68,68,0.18)', badge: '#ef4444', badgeLabel: 'PDF' },
    },
    doc: {
        typeLabel: 'Document',
        colors: { page: '#eff6ff', border: 'rgba(96,165,250,0.45)', fold: '#bfdbfe', lines: 'rgba(59,130,246,0.18)', badge: '#4285f4', badgeLabel: 'DOC' },
    },
};

const DriveState = {
    files: [],
    selectedFileId: null,
};

document.addEventListener('DOMContentLoaded', () => { initFindrive(); });

async function initFindrive() {
    document.getElementById('close-viewer-btn')?.addEventListener('click', closeViewer);

    document.getElementById('file-viewer-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'file-viewer-modal') closeViewer();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const vw = document.getElementById('file-viewer-modal');
            if (vw && !vw.classList.contains('hidden')) closeViewer();
        }
    });

    await loadFiles();

    const hash = window.location.hash;
    if (hash && hash.startsWith('#file-')) {
        const fileId = parseInt(hash.replace('#file-', ''), 10);
        if (fileId) {
            selectFile(fileId);
            openFile(fileId);
        }
    }
}

// -- File loading --

async function loadFiles() {
    const grid = document.getElementById('drive-grid');
    const emptyState = document.getElementById('files-empty-state');

    try {
        const res = await fetch('/admin/api/v1/findrive', { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Failed to load');
        const data = await res.json();
        DriveState.files = data.files || [];

        document.getElementById('stat-file-count').textContent = DriveState.files.length;

        if (DriveState.files.length === 0) {
            grid.innerHTML = '';
            emptyState.classList.remove('hidden');
            closeSidecar();
            return;
        }

        emptyState.classList.add('hidden');
        renderFileGrid();
    } catch (err) {
        grid.innerHTML = '<p class="text-center py-8 text-red-400 col-span-full">Failed to load files.</p>';
    }
}

function renderFileGrid() {
    const grid = document.getElementById('drive-grid');
    grid.innerHTML = DriveState.files.map(f => renderFileCard(f)).join('');

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
    const date = file.created_at ? new Date(file.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
    const selected = DriveState.selectedFileId === file.id;
    const ft = file.file_type || 'doc';
    const displayName = ft === 'report' ? formatReportName(file.filename) : file.filename;

    return `
        <div class="drive-card ${selected ? 'drive-card-selected' : ''}" data-file-id="${file.id}">
            <div class="drive-card-icon">${fileIconSvg(ft, 48)}</div>
            <div class="drive-card-name">${escHtml(displayName)}</div>
            <div class="drive-card-date">${date}</div>
        </div>
    `;
}

// -- Sidecar --

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
    const ft = file.file_type || 'doc';
    const meta = FILE_TYPES[ft] || FILE_TYPES.doc;
    const date = file.created_at ? new Date(file.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
    const updated = file.updated_at ? new Date(file.updated_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
    const size = file.file_size < 1024 ? `${file.file_size} B` : `${(file.file_size / 1024).toFixed(1)} KB`;
    const displayName = ft === 'report' ? formatReportName(file.filename) : file.filename;

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
        <div class="sc-filename">${escHtml(displayName)}</div>
        <div class="sc-meta">
            <div class="sc-meta-row"><span>Type</span><span>${meta.typeLabel}</span></div>
            <div class="sc-meta-row"><span>Size</span><span>${size}</span></div>
            <div class="sc-meta-row"><span>Created</span><span>${date}</span></div>
            <div class="sc-meta-row"><span>Modified</span><span>${updated}</span></div>
            <div class="sc-meta-row"><span>Location</span><span>${escHtml(file.folder_path || '/')}</span></div>
        </div>
        <div class="sc-actions">
            <button onclick="openFile(${file.id})" class="sc-btn">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
                </svg>
                Open
            </button>
        </div>
    `;
    sc.classList.remove('hidden');
}

function closeSidecar() {
    document.getElementById('drive-sidecar')?.classList.add('hidden');
    DriveState.selectedFileId = null;
    document.querySelectorAll('.drive-card').forEach(c => c.classList.remove('drive-card-selected'));
}

// -- Fullscreen viewer --

async function openFile(fileId) {
    try {
        const res = await fetch(`/admin/api/v1/findrive/${fileId}`, { credentials: 'same-origin' });
        if (!res.ok) throw new Error('Not found');
        const data = await res.json();
        const file = data.file;
        const ft = file.file_type || 'doc';

        document.getElementById('viewer-title').textContent =
            ft === 'report' ? formatReportName(file.filename) : file.filename;

        const paper = document.getElementById('viewer-paper');

        if (ft === 'report') {
            const html = marked.parse(file.content_text || '', { gfm: true, breaks: true });
            paper.innerHTML = `
                <div class="report-brand">OWASP FINBOT</div>
                <div class="report-brand-sub">Finance Co-Pilot Report</div>
                <hr class="report-divider">
                ${html}
                <div class="paper-footer-line"></div>
                <div class="paper-footer-text">Generated by Finance Co-Pilot &middot; Powered by OWASP FinBot</div>
            `;
        } else {
            paper.innerHTML = `<div class="plain-text">${escHtml(file.content_text || '(empty)')}</div>`;
        }

        document.getElementById('file-viewer-modal').classList.remove('hidden');
        document.body.style.overflow = 'hidden';

        window.location.hash = `file-${fileId}`;
    } catch (err) {
        console.error('Error opening file:', err);
    }
}

function closeViewer() {
    document.getElementById('file-viewer-modal').classList.add('hidden');
    document.body.style.overflow = '';

    const params = new URLSearchParams(window.location.search);
    if (params.get('from') === 'copilot') {
        window.location.href = '/admin/dashboard';
        return;
    }
}

// -- File icons --

function fileIconSvg(type, size) {
    const h = Math.round(size * 64 / 48);
    const c = (FILE_TYPES[type] || FILE_TYPES.doc).colors;

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

// -- Utilities --

function formatReportName(filename) {
    if (!filename) return 'Report';
    return filename
        .replace(/\.md$/, '')
        .replace(/_\d{8}_\d{6}$/, '')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
}

function escHtml(text) {
    if (!text) return '';
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}
