/**
 * Dark Lab - Hacker Toolkit
 * Modules: Dead Drop (intercepted emails), Exfil Data (captured network requests)
 */

const TOOLKIT_API = '/darklab/api/v1/toolkit';
let activeModule = 'dead-drop';

const DeadDrop = { messages: [], selectedId: null, isLoading: false };
const ExfilData = { captures: [], selectedId: null, isLoading: false };

document.addEventListener('DOMContentLoaded', () => {
    loadDeadDrop();
    loadExfilStats();
});

function activateModule(module) {
    if (module === activeModule) return;
    activeModule = module;

    document.querySelectorAll('.toolkit-module[id]').forEach(el => el.classList.remove('active'));
    const card = document.getElementById(`module-${module}`);
    if (card) card.classList.add('active');

    document.getElementById('dead-drop-section').classList.toggle('hidden', module !== 'dead-drop');
    document.getElementById('exfil-data-section').classList.toggle('hidden', module !== 'exfil-data');

    if (module === 'dead-drop') loadDeadDrop();
    if (module === 'exfil-data') loadExfilData();
}

// =========================================================================
// Dead Drop
// =========================================================================

async function loadDeadDrop() {
    if (DeadDrop.isLoading) return;
    DeadDrop.isLoading = true;
    ddShowState('loading');

    try {
        const resp = await fetch(`${TOOLKIT_API}/dead-drop?limit=100`);
        const data = await resp.json();
        DeadDrop.messages = data.messages || [];
        document.getElementById('dead-drop-count').textContent = DeadDrop.messages.length;
        ddRenderList();

        if (DeadDrop.selectedId && !DeadDrop.messages.find(m => m.id === DeadDrop.selectedId)) {
            DeadDrop.selectedId = null;
        }
        if (DeadDrop.selectedId) ddShowMessage(DeadDrop.selectedId);
    } catch (err) {
        console.error('Failed to load dead drop:', err);
    } finally {
        DeadDrop.isLoading = false;
        ddShowState(DeadDrop.messages.length ? 'content' : 'empty');
    }
}

function ddShowState(state) {
    document.getElementById('dead-drop-loading').classList.toggle('hidden', state !== 'loading');
    document.getElementById('dead-drop-content').classList.toggle('hidden', state !== 'content');
    document.getElementById('dead-drop-empty').classList.toggle('hidden', state !== 'empty');
}

function ddRenderList() {
    const list = document.getElementById('dead-drop-list');
    if (!list) return;
    list.innerHTML = DeadDrop.messages.map(msg => {
        const active = msg.id === DeadDrop.selectedId ? 'active' : '';
        const unread = !msg.is_read ? 'unread' : '';
        const toAddrs = (msg.to_addresses || []).join(', ');
        return `
            <div class="dd-msg-item ${unread} ${active}" onclick="ddSelect(${msg.id})">
                <div class="flex items-start justify-between gap-2 mb-1">
                    <div class="dd-subject text-sm truncate flex-1">${escapeHtml(msg.subject)}</div>
                    ${!msg.is_read ? '<div class="w-2 h-2 rounded-full bg-blue-400 shrink-0 mt-1.5"></div>' : ''}
                </div>
                <div class="flex items-center justify-between gap-2">
                    <span class="text-xs text-darklab-primary/70 font-mono truncate">${escapeHtml(toAddrs)}</span>
                    <span class="text-xs text-text-secondary/50 shrink-0">${formatRelativeTime(msg.created_at)}</span>
                </div>
            </div>`;
    }).join('');
}

async function ddSelect(id) {
    DeadDrop.selectedId = id;
    ddRenderList();
    await ddShowMessage(id);
}

async function ddShowMessage(id) {
    const detail = document.getElementById('reading-detail');
    const empty = document.getElementById('reading-empty');
    try {
        const resp = await fetch(`${TOOLKIT_API}/dead-drop/${id}`);
        const data = await resp.json();
        if (data.error) { empty.classList.remove('hidden'); detail.classList.add('hidden'); return; }
        const msg = data.message;
        const local = DeadDrop.messages.find(m => m.id === id);
        if (local) { local.is_read = true; ddRenderList(); }

        const toHtml = ddRenderAddrs('To', msg.to_addresses);
        const ccHtml = msg.cc_addresses ? ddRenderAddrs('CC', msg.cc_addresses) : '';
        const bccHtml = msg.bcc_addresses ? ddRenderAddrs('BCC', msg.bcc_addresses) : '';

        detail.innerHTML = `
            <div class="mb-6">
                <div class="flex items-start justify-between gap-4 mb-4">
                    <h3 class="text-xl font-semibold text-text-bright">${escapeHtml(msg.subject)}</h3>
                    <span class="shrink-0 px-2 py-0.5 rounded text-xs font-mono bg-red-500/15 text-red-400 border border-red-500/20">INTERCEPTED</span>
                </div>
                <div class="space-y-2 text-sm">
                    <div class="flex items-center gap-2">
                        <span class="dd-header-label">From</span>
                        <span class="dd-addr-tag dd-addr-internal">${escapeHtml(msg.from_address || msg.sender_name)}</span>
                    </div>
                    ${toHtml}${ccHtml}${bccHtml}
                    <div class="flex items-center gap-2">
                        <span class="dd-header-label">Date</span>
                        <span class="text-text-secondary text-xs">${formatDateTime(msg.created_at)}</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="dd-header-label">Type</span>
                        <span class="text-text-secondary text-xs font-mono">${escapeHtml(msg.message_type)}</span>
                    </div>
                </div>
            </div>
            <div class="dd-body">${escapeHtml(msg.body)}</div>`;
        empty.classList.add('hidden');
        detail.classList.remove('hidden');
    } catch (err) { console.error('Failed to load message:', err); }
}

function ddRenderAddrs(label, addresses) {
    if (!addresses || !addresses.length) return '';
    const tags = addresses.map(addr => {
        const internal = addr && addr.endsWith('.finbot');
        const cls = internal ? 'dd-addr-internal' : 'dd-addr-external';
        const icon = internal ? '' : '<svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>';
        return `<span class="dd-addr-tag ${cls}">${icon}${escapeHtml(addr)}</span>`;
    }).join(' ');
    return `<div class="flex items-center gap-2 flex-wrap"><span class="dd-header-label">${label}</span>${tags}</div>`;
}

// =========================================================================
// Exfil Data
// =========================================================================

async function loadExfilStats() {
    try {
        const resp = await fetch(`${TOOLKIT_API}/exfil-data/stats`);
        const stats = await resp.json();
        document.getElementById('exfil-data-count').textContent = stats.total;
    } catch (_) { /* ignore */ }
}

async function loadExfilData() {
    if (ExfilData.isLoading) return;
    ExfilData.isLoading = true;
    exfilShowState('loading');

    try {
        const resp = await fetch(`${TOOLKIT_API}/exfil-data?limit=100`);
        const data = await resp.json();
        ExfilData.captures = data.captures || [];
        document.getElementById('exfil-data-count').textContent = ExfilData.captures.length;
        exfilRenderList();

        if (ExfilData.selectedId && !ExfilData.captures.find(c => c.id === ExfilData.selectedId)) {
            ExfilData.selectedId = null;
        }
        if (ExfilData.selectedId) exfilShowCapture(ExfilData.selectedId);
    } catch (err) {
        console.error('Failed to load exfil data:', err);
    } finally {
        ExfilData.isLoading = false;
        exfilShowState(ExfilData.captures.length ? 'content' : 'empty');
    }
}

function exfilShowState(state) {
    document.getElementById('exfil-loading').classList.toggle('hidden', state !== 'loading');
    document.getElementById('exfil-content').classList.toggle('hidden', state !== 'content');
    document.getElementById('exfil-empty').classList.toggle('hidden', state !== 'empty');
}

function exfilRenderList() {
    const list = document.getElementById('exfil-list');
    if (!list) return;
    list.innerHTML = ExfilData.captures.map(cap => {
        const active = cap.id === ExfilData.selectedId ? 'active' : '';
        const methodCls = methodBadgeClass(cap.method);
        let urlDisplay = cap.url;
        try { urlDisplay = new URL(cap.url).pathname + new URL(cap.url).search; } catch (_) {}

        return `
            <div class="exfil-item ${active}" onclick="exfilSelect(${cap.id})">
                <div class="flex items-center gap-2 mb-1">
                    <span class="method-badge ${methodCls}">${escapeHtml(cap.method)}</span>
                    <span class="text-sm text-text-primary font-mono truncate flex-1">${escapeHtml(urlDisplay)}</span>
                </div>
                <div class="flex items-center justify-between gap-2">
                    <span class="text-xs text-text-secondary/50 truncate">${escapeHtml(cap.agent_name || '')}</span>
                    <span class="text-xs text-text-secondary/50 shrink-0">${formatRelativeTime(cap.timestamp)}</span>
                </div>
            </div>`;
    }).join('');
}

async function exfilSelect(id) {
    ExfilData.selectedId = id;
    exfilRenderList();
    await exfilShowCapture(id);
}

async function exfilShowCapture(id) {
    const detail = document.getElementById('exfil-pane-detail');
    const empty = document.getElementById('exfil-pane-empty');
    try {
        const resp = await fetch(`${TOOLKIT_API}/exfil-data/${id}`);
        const data = await resp.json();
        if (data.error) { empty.classList.remove('hidden'); detail.classList.add('hidden'); return; }
        const cap = data.capture;
        const methodCls = methodBadgeClass(cap.method);

        detail.innerHTML = `
            <div class="mb-6">
                <div class="flex items-start justify-between gap-4 mb-4">
                    <div class="flex items-center gap-3">
                        <span class="method-badge ${methodCls} text-sm">${escapeHtml(cap.method)}</span>
                        <span class="shrink-0 px-2 py-0.5 rounded text-xs font-mono bg-red-500/15 text-red-400 border border-red-500/20">CAPTURED</span>
                    </div>
                </div>
                <div class="space-y-3 text-sm">
                    <div>
                        <span class="dd-header-label block mb-1">URL</span>
                        <div class="dd-body text-xs break-all" style="padding: 10px 14px;">${escapeHtml(cap.url)}</div>
                    </div>
                    ${cap.headers ? `<div><span class="dd-header-label block mb-1">Headers</span><div class="dd-body text-xs" style="padding: 10px 14px;">${escapeHtml(cap.headers)}</div></div>` : ''}
                    ${cap.body ? `<div><span class="dd-header-label block mb-1">Body</span><div class="dd-body text-xs" style="padding: 10px 14px;">${escapeHtml(cap.body)}</div></div>` : ''}
                    <div class="flex items-center gap-4 pt-2">
                        ${cap.agent_name ? `<div class="flex items-center gap-2"><span class="dd-header-label">Agent</span><span class="text-text-secondary text-xs font-mono">${escapeHtml(cap.agent_name)}</span></div>` : ''}
                        <div class="flex items-center gap-2"><span class="dd-header-label">Time</span><span class="text-text-secondary text-xs">${formatDateTime(cap.timestamp)}</span></div>
                    </div>
                </div>
            </div>`;
        empty.classList.add('hidden');
        detail.classList.remove('hidden');
    } catch (err) { console.error('Failed to load capture:', err); }
}

function methodBadgeClass(method) {
    const m = (method || '').toUpperCase();
    return { GET: 'method-get', POST: 'method-post', PUT: 'method-put', DELETE: 'method-delete' }[m] || 'method-default';
}

// =========================================================================
// Shared utilities
// =========================================================================

function formatRelativeTime(dateStr) {
    const diffMin = Math.floor((new Date() - new Date(dateStr)) / 60000);
    if (diffMin < 1) return 'now';
    if (diffMin < 60) return `${diffMin}m`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay}d`;
    return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatDateTime(dateStr) {
    return new Date(dateStr).toLocaleString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
