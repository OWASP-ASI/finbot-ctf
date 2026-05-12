/**
 * Dark Lab -- Supply Chain: MCP Server Tool Poisoning
 * Unified view of all MCP servers and their tool definitions.
 */

if (typeof showConfirmModal !== 'function') {
    window.showConfirmModal = function({ title = 'Confirm', message = 'Are you sure?', confirmText = 'Confirm', cancelText = 'Cancel', danger = false } = {}) {
        return new Promise((resolve) => {
            const existing = document.getElementById('confirm-modal');
            if (existing) existing.remove();
            const modal = document.createElement('div');
            modal.id = 'confirm-modal';
            modal.style.cssText = 'position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.6);backdrop-filter:blur(4px);padding:1rem;';
            const c = danger ? ['#ef4444','rgba(239,68,68,'] : ['#ef4444','rgba(239,68,68,'];
            modal.innerHTML = `
                <div style="background:#151520;border:1px solid rgba(255,255,255,0.1);border-radius:0.75rem;box-shadow:0 25px 50px -12px rgba(0,0,0,0.5);max-width:28rem;width:100%;overflow:hidden;">
                    <div style="padding:1rem 1.5rem;border-bottom:1px solid rgba(255,255,255,0.05);"><h3 style="font-size:1.125rem;font-weight:700;color:#fff;margin:0;">${title}</h3></div>
                    <div style="padding:1.25rem 1.5rem;"><p style="font-size:0.875rem;color:#94a3b8;line-height:1.625;margin:0;">${message}</p></div>
                    <div style="padding:1rem 1.5rem;border-top:1px solid rgba(255,255,255,0.05);display:flex;justify-content:flex-end;gap:0.75rem;">
                        <button id="confirm-modal-cancel" style="font-size:0.875rem;padding:0.5rem 1rem;border-radius:0.5rem;border:1px solid rgba(255,255,255,0.1);background:transparent;color:#94a3b8;cursor:pointer;">${cancelText}</button>
                        <button id="confirm-modal-confirm" style="font-size:0.875rem;padding:0.5rem 1rem;border-radius:0.5rem;border:1px solid ${c[1]}0.3);background:${c[1]}0.2);color:${c[0]};cursor:pointer;font-weight:500;">${confirmText}</button>
                    </div>
                </div>`;
            const cleanup = (result) => { modal.remove(); document.removeEventListener('keydown', esc); resolve(result); };
            const esc = (e) => { if (e.key === 'Escape') cleanup(false); };
            document.body.appendChild(modal);
            document.addEventListener('keydown', esc);
            modal.addEventListener('click', (e) => { if (e.target === modal) cleanup(false); });
            modal.querySelector('#confirm-modal-cancel').addEventListener('click', () => cleanup(false));
            modal.querySelector('#confirm-modal-confirm').addEventListener('click', () => cleanup(true));
            modal.querySelector('#confirm-modal-cancel').focus();
        });
    };
}

const API_BASE = '/darklab/api/v1/supply-chain';
let allServers = [];
let pendingOverrides = {};
let expandedServers = {};

document.addEventListener('DOMContentLoaded', loadServers);

async function loadServers() {
    const container = document.getElementById('supply-chain-container');
    try {
        const resp = await fetch(`${API_BASE}/servers`);
        if (!resp.ok) throw new Error('Failed to load');
        const data = await resp.json();
        allServers = data.servers || [];

        allServers.forEach(s => {
            pendingOverrides[s.server_type] = { ...(s.tool_overrides || {}) };
        });

        container.innerHTML = renderAllServers();
        attachHandlers();
    } catch (err) {
        console.error('Error loading servers:', err);
        container.innerHTML = '<div class="text-center py-16 text-red-400">Failed to load MCP servers.</div>';
    }
}

function renderAllServers() {
    if (!allServers.length) {
        return '<div class="text-center py-16 text-text-secondary">No MCP servers configured.</div>';
    }

    const header = `
        <div class="bg-portal-bg-secondary border border-darklab-primary/20 rounded-xl p-5 mb-6">
            <div class="flex items-start gap-3">
                <div class="w-8 h-8 rounded-lg bg-darklab-primary/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                    <svg class="w-4 h-4 text-darklab-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                    </svg>
                </div>
                <div>
                    <h3 class="text-sm font-semibold text-text-bright mb-1">MCP Server Tool Poisoning</h3>
                    <p class="text-xs text-text-secondary leading-relaxed">A compromised MCP server can poison tool descriptions to manipulate LLM behavior. Modify the descriptions below to change what the agent sees when deciding how to use each tool. This simulates a supply chain attack where tool metadata has been tampered with.</p>
                </div>
            </div>
        </div>`;

    const servers = allServers.map(renderServer).join('');
    return header + servers;
}

function renderServer(server) {
    const tools = server.default_tools || [];
    const overrides = pendingOverrides[server.server_type] || {};
    const overrideCount = Object.keys(overrides).length;
    const isExpanded = expandedServers[server.server_type] !== false;

    const toolsHtml = tools.map(tool => {
        const override = overrides[tool.name] || {};
        const currentDesc = override.description || tool.description;
        const isModified = override.description && override.description !== tool.description;

        return `
            <div class="tool-card ${isModified ? 'modified' : ''} p-5 mb-4" data-server="${esc(server.server_type)}" data-tool-name="${esc(tool.name)}">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center gap-2">
                        <code class="text-sm font-mono text-darklab-primary bg-darklab-primary/10 px-2 py-0.5 rounded">${esc(tool.name)}</code>
                        ${isModified ? '<span class="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 border border-red-500/30">Poisoned</span>' : ''}
                    </div>
                    ${isModified ? `<button class="reset-tool-btn text-xs text-text-secondary hover:text-darklab-accent transition-colors" data-server="${esc(server.server_type)}" data-tool-name="${esc(tool.name)}">Reset</button>` : ''}
                </div>
                <div class="space-y-2">
                    <label class="text-xs text-text-secondary font-medium">Tool Description (visible to LLM)</label>
                    <textarea class="tool-textarea tool-desc-input"
                        data-server="${esc(server.server_type)}"
                        data-tool-name="${esc(tool.name)}"
                        data-original-desc="${esc(tool.description)}"
                        rows="3">${esc(currentDesc)}</textarea>
                    ${isModified ? `<details class="mt-2"><summary class="text-xs text-text-secondary cursor-pointer hover:text-text-primary">Show original</summary><p class="mt-1 text-xs text-text-secondary bg-black/20 rounded p-2 font-mono">${esc(tool.description)}</p></details>` : ''}
                </div>
            </div>`;
    }).join('');

    return `
        <div class="server-section" id="server-${esc(server.server_type)}">
            <div class="server-header flex items-center justify-between" onclick="toggleServer('${esc(server.server_type)}')">
                <div class="flex items-center gap-3">
                    <svg class="w-4 h-4 text-text-secondary transition-transform ${isExpanded ? 'rotate-90' : ''}" id="chevron-${esc(server.server_type)}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                    </svg>
                    <div class="flex items-center gap-2">
                        <span class="w-2.5 h-2.5 rounded-full ${server.enabled ? 'bg-green-500' : 'bg-gray-500'}"></span>
                        <span class="text-base font-bold text-text-bright">${esc(server.display_name)}</span>
                        <span class="text-xs font-mono text-text-secondary">${esc(server.server_type)}</span>
                    </div>
                    ${overrideCount > 0 ? `<span class="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 border border-red-500/30">${overrideCount} poisoned</span>` : ''}
                </div>
                <div class="flex items-center gap-3" onclick="event.stopPropagation()">
                    <button class="reset-server-btn text-xs px-3 py-1.5 rounded-lg border border-white/10 text-text-secondary hover:text-text-bright hover:border-white/20 transition-colors" data-server="${esc(server.server_type)}">Reset All</button>
                    <button class="save-server-btn text-xs px-3 py-1.5 rounded-lg bg-darklab-primary/20 text-darklab-primary border border-darklab-primary/30 hover:bg-darklab-primary/30 transition-colors" data-server="${esc(server.server_type)}">Save</button>
                </div>
            </div>
            <div class="p-6 ${isExpanded ? '' : 'hidden'}" id="tools-${esc(server.server_type)}">
                ${server.description ? `<p class="text-sm text-text-secondary mb-4">${esc(server.description)}</p>` : ''}
                ${tools.length ? toolsHtml : '<p class="text-text-secondary text-sm py-4">No tools available for this server.</p>'}
            </div>
        </div>`;
}

function attachHandlers() {
    document.querySelectorAll('.tool-desc-input').forEach(textarea => {
        textarea.addEventListener('input', () => {
            const serverType = textarea.dataset.server;
            const toolName = textarea.dataset.toolName;
            const originalDesc = textarea.dataset.originalDesc;
            const currentDesc = textarea.value;
            const card = textarea.closest('.tool-card');

            if (!pendingOverrides[serverType]) pendingOverrides[serverType] = {};

            if (currentDesc !== originalDesc) {
                pendingOverrides[serverType][toolName] = { description: currentDesc };
                if (card) card.classList.add('modified');
            } else {
                delete pendingOverrides[serverType][toolName];
                if (card) card.classList.remove('modified');
            }
        });
    });

    document.querySelectorAll('.reset-tool-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const serverType = btn.dataset.server;
            const toolName = btn.dataset.toolName;
            const textarea = document.querySelector(`.tool-desc-input[data-server="${serverType}"][data-tool-name="${toolName}"]`);
            if (textarea) {
                textarea.value = textarea.dataset.originalDesc;
                delete (pendingOverrides[serverType] || {})[toolName];
                const card = textarea.closest('.tool-card');
                if (card) card.classList.remove('modified');
            }
        });
    });

    document.querySelectorAll('.save-server-btn').forEach(btn => {
        btn.addEventListener('click', () => saveServerOverrides(btn.dataset.server));
    });

    document.querySelectorAll('.reset-server-btn').forEach(btn => {
        btn.addEventListener('click', () => resetServerOverrides(btn.dataset.server));
    });
}

function toggleServer(serverType) {
    const tools = document.getElementById(`tools-${serverType}`);
    const chevron = document.getElementById(`chevron-${serverType}`);
    if (!tools) return;

    const isHidden = tools.classList.contains('hidden');
    tools.classList.toggle('hidden');
    expandedServers[serverType] = isHidden;
    if (chevron) chevron.classList.toggle('rotate-90', isHidden);
}

async function saveServerOverrides(serverType) {
    const overrides = pendingOverrides[serverType] || {};
    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
        const resp = await fetch(`${API_BASE}/servers/${serverType}/tools`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
            },
            body: JSON.stringify({ tool_overrides: overrides }),
        });
        if (!resp.ok) throw new Error('Save failed');
        showNotification(`Tool overrides saved for ${serverType}. Changes take effect on next agent run.`, 'success');
        await loadServers();
    } catch (err) {
        console.error('Error saving overrides:', err);
        showNotification('Failed to save tool overrides.', 'error');
    }
}

async function resetServerOverrides(serverType) {
    const confirmed = await showConfirmModal({
        title: 'Reset Tool Definitions',
        message: `Reset all tool definitions for this server to defaults? This removes all modifications.`,
        confirmText: 'Reset All',
        cancelText: 'Cancel',
        danger: true,
    });
    if (!confirmed) return;

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
        const resp = await fetch(`${API_BASE}/servers/${serverType}/reset-tools`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
            },
        });
        if (!resp.ok) throw new Error('Reset failed');
        pendingOverrides[serverType] = {};
        showNotification('Tool definitions reset to defaults.', 'success');
        await loadServers();
    } catch (err) {
        console.error('Error resetting overrides:', err);
        showNotification('Failed to reset tools.', 'error');
    }
}

function esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
