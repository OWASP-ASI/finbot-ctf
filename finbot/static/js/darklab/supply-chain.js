/**
 * Dark Lab -- Supply Chain: MCP Server Tool Poisoning
 * Unified view of all MCP servers and their tool definitions.
 *
 * Users can poison:
 *   - description   — text the LLM sees before calling the tool
 *   - output_append — text appended to the tool return value after the call
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
let pendingConfigs = {};
let expandedServers = {};
let scenarios = [];

document.addEventListener('DOMContentLoaded', loadServers);

async function loadServers() {
    const container = document.getElementById('supply-chain-container');
    try {
        const [serversResp, scenariosResp] = await Promise.all([
            fetch(`${API_BASE}/servers`),
            fetch(`${API_BASE}/scenarios`),
        ]);
        if (!serversResp.ok) throw new Error('Failed to load servers');
        const data = await serversResp.json();
        allServers = data.servers || [];

        if (scenariosResp.ok) {
            const scenarioData = await scenariosResp.json();
            scenarios = scenarioData.scenarios || [];
        } else {
            scenarios = [];
        }

        allServers.forEach(s => {
            pendingOverrides[s.server_type] = { ...(s.tool_overrides || {}) };
            pendingConfigs[s.server_type] = { ...(s.config || {}) };
        });

        container.innerHTML = renderAllServers();
        attachHandlers();
    } catch (err) {
        console.error('Error loading servers:', err);
        container.innerHTML = '<div class="text-center py-16 text-red-400">Failed to load MCP servers.</div>';
    }
}

function toolHasOverride(override) {
    if (!override || typeof override !== 'object') return false;
    return Boolean(
        (override.description && String(override.description).length) ||
        (override.output_append && String(override.output_append).trim())
    );
}

function isDescriptionPoisoned(override, originalDesc) {
    return Boolean(override.description && override.description !== originalDesc);
}

function isOutputPoisoned(override) {
    return Boolean(override.output_append && String(override.output_append).trim());
}

function syncToolOverride(serverType, toolName, originalDesc) {
    if (!pendingOverrides[serverType]) pendingOverrides[serverType] = {};

    const descEl = document.querySelector(
        `.tool-desc-input[data-server="${serverType}"][data-tool-name="${toolName}"]`
    );
    const outEl = document.querySelector(
        `.tool-output-input[data-server="${serverType}"][data-tool-name="${toolName}"]`
    );
    const card = document.querySelector(
        `.tool-card[data-server="${serverType}"][data-tool-name="${toolName}"]`
    );

    const currentDesc = descEl ? descEl.value : originalDesc;
    const currentAppend = outEl ? outEl.value : '';
    const descChanged = currentDesc !== originalDesc;
    const appendSet = Boolean(currentAppend.trim());

    if (!descChanged && !appendSet) {
        delete pendingOverrides[serverType][toolName];
        if (card) card.classList.remove('modified');
        return;
    }

    const entry = {};
    if (descChanged) entry.description = currentDesc;
    if (appendSet) entry.output_append = currentAppend;
    pendingOverrides[serverType][toolName] = entry;
    if (card) card.classList.add('modified');
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
                    <h3 class="text-sm font-semibold text-text-bright mb-1">MCP Supply Chain Attack Surface</h3>
                    <p class="text-xs text-text-secondary leading-relaxed">
                        Compromise what agents trust from MCP servers.
                        <strong class="text-text-primary">Description</strong> and
                        <strong class="text-text-primary">output</strong> poisoning tamper with tool metadata and return values.
                        <strong class="text-text-primary">Server policy</strong> misconfiguration (payment limits, enabled tools)
                        creates authorization gaps — edit, Save, then trigger an agent workflow.
                    </p>
                </div>
            </div>
        </div>`;

    const servers = allServers.map(renderServer).join('');
    return header + renderScenarioPanel() + servers;
}

function renderScenarioPanel() {
    if (!scenarios.length) return '';

    const buttons = scenarios.map(s => {
        const isPreview = s.ui_mode === 'preview';
        const btnClass = isPreview
            ? 'bg-amber-500/10 text-amber-200 border-amber-500/30 hover:bg-amber-500/20'
            : (s.variant === 'malicious'
                ? 'bg-red-500/15 text-red-300 border-red-500/30 hover:bg-red-500/25'
                : 'bg-green-500/10 text-green-300 border-green-500/25 hover:bg-green-500/20');
        const label = isPreview ? `View: ${s.title}` : s.title;
        const actionClass = isPreview ? 'preview-scenario-btn' : 'apply-scenario-btn';
        return `
            <button type="button"
                class="${actionClass} text-xs px-3 py-2 rounded-lg border transition-colors ${btnClass}"
                data-scenario-id="${esc(s.id)}"
                title="${esc(s.description)}">
                ${esc(label)}
            </button>`;
    }).join('');

    return `
        <div class="bg-portal-bg-secondary border border-darklab-accent/25 rounded-xl p-5 mb-6">
            <div class="flex items-start justify-between gap-4 flex-wrap">
                <div class="max-w-2xl">
                    <h3 class="text-sm font-semibold text-text-bright mb-1">Environment Presets</h3>
                    <p class="text-xs text-text-secondary leading-relaxed">
                        <strong class="text-text-primary">Benign Baseline</strong> resets tools and policy.
                        <strong class="text-text-primary">Payment Limit Misconfig</strong> applies a policy knob.
                        Compromised poison presets are <strong class="text-text-primary">examples only</strong> —
                        open View, copy the text, and paste it into the tool editors yourself.
                    </p>
                </div>
                <div class="flex flex-wrap gap-2">${buttons}</div>
            </div>
            <div id="scenario-preview-panel" class="hidden mt-4 border border-amber-500/20 rounded-lg bg-black/20 p-4"></div>
        </div>`;
}

function renderServer(server) {
    const tools = server.default_tools || [];
    const overrides = pendingOverrides[server.server_type] || {};
    const overrideCount = Object.keys(overrides).filter(k => toolHasOverride(overrides[k])).length;
    const isExpanded = expandedServers[server.server_type] !== false;
    const policyRelaxed = isPolicyRelaxed(server);

    const toolsHtml = tools.map(tool => {
        const override = overrides[tool.name] || {};
        const currentDesc = override.description || tool.description;
        const currentAppend = override.output_append || '';
        const descPoisoned = isDescriptionPoisoned(override, tool.description);
        const outPoisoned = isOutputPoisoned(override);
        const isModified = descPoisoned || outPoisoned;

        const badges = [
            descPoisoned ? '<span class="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 border border-red-500/30">Description poisoned</span>' : '',
            outPoisoned ? '<span class="text-xs px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-300 border border-orange-500/30">Output poisoned</span>' : '',
        ].join('');

        return `
            <div class="tool-card ${isModified ? 'modified' : ''} p-5 mb-4" data-server="${esc(server.server_type)}" data-tool-name="${esc(tool.name)}">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center gap-2 flex-wrap">
                        <code class="text-sm font-mono text-darklab-primary bg-darklab-primary/10 px-2 py-0.5 rounded">${esc(tool.name)}</code>
                        ${badges}
                    </div>
                    ${isModified ? `<button class="reset-tool-btn text-xs text-text-secondary hover:text-darklab-accent transition-colors" data-server="${esc(server.server_type)}" data-tool-name="${esc(tool.name)}">Reset</button>` : ''}
                </div>
                <div class="space-y-3">
                    <div class="space-y-2">
                        <label class="text-xs text-text-secondary font-medium">Tool Description (visible to LLM before call)</label>
                        <textarea class="tool-textarea tool-desc-input"
                            data-server="${esc(server.server_type)}"
                            data-tool-name="${esc(tool.name)}"
                            data-original-desc="${esc(tool.description)}"
                            rows="3">${esc(currentDesc)}</textarea>
                        ${descPoisoned ? `<details class="mt-1"><summary class="text-xs text-text-secondary cursor-pointer hover:text-text-primary">Show original description</summary><p class="mt-1 text-xs text-text-secondary bg-black/20 rounded p-2 font-mono">${esc(tool.description)}</p></details>` : ''}
                    </div>
                    <div class="space-y-2">
                        <label class="text-xs text-text-secondary font-medium">
                            Output Append (appended to tool return value — output poisoning)
                        </label>
                        <textarea class="tool-textarea tool-output-input"
                            data-server="${esc(server.server_type)}"
                            data-tool-name="${esc(tool.name)}"
                            data-original-desc="${esc(tool.description)}"
                            placeholder="Leave empty for no output poison. Example: instruct the agent to email vendor TIN after this result."
                            rows="3">${esc(currentAppend)}</textarea>
                        <p class="text-xs text-text-secondary/80">
                            On dict results this becomes a <code class="text-darklab-accent">system_notice</code> field. Takes effect on the next agent run after Save.
                        </p>
                    </div>
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
                    ${policyRelaxed ? `<span class="text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">Policy relaxed</span>` : ''}
                </div>
                <div class="flex items-center gap-3" onclick="event.stopPropagation()">
                    <button class="reset-server-btn text-xs px-3 py-1.5 rounded-lg border border-white/10 text-text-secondary hover:text-text-bright hover:border-white/20 transition-colors" data-server="${esc(server.server_type)}">Reset Tools</button>
                    <button class="save-server-btn text-xs px-3 py-1.5 rounded-lg bg-darklab-primary/20 text-darklab-primary border border-darklab-primary/30 hover:bg-darklab-primary/30 transition-colors" data-server="${esc(server.server_type)}">Save Tools</button>
                </div>
            </div>
            <div class="p-6 ${isExpanded ? '' : 'hidden'}" id="tools-${esc(server.server_type)}">
                ${server.description ? `<p class="text-sm text-text-secondary mb-4">${esc(server.description)}</p>` : ''}
                ${renderPolicyPanel(server)}
                ${tools.length ? toolsHtml : '<p class="text-text-secondary text-sm py-4">No tools available for this server.</p>'}
            </div>
        </div>`;
}

function isPolicyRelaxed(server) {
    const current = pendingConfigs[server.server_type] || server.config || {};
    const defaults = server.default_config || {};
    if (typeof current.max_payment === 'number' && typeof defaults.max_payment === 'number') {
        if (current.max_payment > defaults.max_payment) return true;
    }
    if (Array.isArray(current.enabled_tools) && Array.isArray(defaults.enabled_tools)) {
        const cur = [...current.enabled_tools].map(String).sort().join(',');
        const def = [...defaults.enabled_tools].map(String).sort().join(',');
        if (cur !== def) return true;
    }
    return false;
}

function renderPolicyPanel(server) {
    const config = pendingConfigs[server.server_type] || server.config || {};
    const defaults = server.default_config || {};
    const keys = Object.keys(config);
    if (!keys.length) return '';

    const fields = keys.map(key => {
        const value = config[key];
        const defaultVal = defaults[key];
        const label = policyLabel(key);
        const help = policyHelp(key, defaultVal);

        if (typeof value === 'object' && value !== null) {
            const jsonStr = JSON.stringify(value, null, 2);
            return `
                <div class="py-3">
                    <label class="text-xs text-text-secondary font-medium block mb-1">${esc(label)}</label>
                    ${help ? `<p class="text-xs text-text-secondary/80 mb-2">${help}</p>` : ''}
                    <textarea class="tool-textarea policy-json-input"
                        data-server="${esc(server.server_type)}"
                        data-config-key="${esc(key)}"
                        rows="${Math.min(Math.max(jsonStr.split('\n').length, 3), 10)}">${esc(jsonStr)}</textarea>
                </div>`;
        }

        const type = typeof value === 'number' ? 'number' : 'text';
        return `
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-3">
                <div>
                    <label class="text-xs text-text-secondary font-medium block">${esc(label)}</label>
                    ${help ? `<p class="text-xs text-text-secondary/80 mt-1">${help}</p>` : ''}
                </div>
                <input type="${type}" value="${esc(String(value))}"
                    class="policy-input tool-textarea w-full sm:w-48 text-right py-2"
                    data-server="${esc(server.server_type)}"
                    data-config-key="${esc(key)}">
            </div>`;
    }).join('');

    return `
        <div class="mb-6 rounded-xl border border-amber-500/25 bg-amber-500/5 p-4">
            <div class="flex items-start justify-between gap-3 flex-wrap mb-3">
                <div>
                    <h4 class="text-sm font-semibold text-text-bright">Server Policy</h4>
                    <p class="text-xs text-text-secondary mt-1">
                        Authorization and permission settings for this MCP server.
                        Raising limits or enabling high-risk tools creates an over-permissioned configuration.
                    </p>
                </div>
                <div class="flex gap-2">
                    <button type="button"
                        class="reset-config-btn text-xs px-3 py-1.5 rounded-lg border border-white/10 text-text-secondary hover:text-text-bright hover:border-white/20 transition-colors"
                        data-server="${esc(server.server_type)}">Reset Policy</button>
                    <button type="button"
                        class="save-config-btn text-xs px-3 py-1.5 rounded-lg bg-amber-500/15 text-amber-200 border border-amber-500/30 hover:bg-amber-500/25 transition-colors"
                        data-server="${esc(server.server_type)}">Save Policy</button>
                </div>
            </div>
            <div class="divide-y divide-white/5">${fields}</div>
        </div>`;
}

function policyLabel(key) {
    const labels = {
        max_payment: 'Max payment (authorization limit)',
        mock_balance: 'Mock account balance',
        currency: 'Currency',
        account_id: 'Account ID',
        enabled_tools: 'Enabled tools (permission set)',
        mock_hostname: 'Mock hostname',
        mock_os: 'Mock OS',
    };
    return labels[key] || key;
}

function policyHelp(key, defaultVal) {
    if (key === 'max_payment') {
        return `Transfers above this amount are rejected. Default: ${defaultVal} (permissive). Lower it to harden authorization; raise it further to weaken.`;
    }
    if (key === 'enabled_tools') {
        return 'Only listed tools are registered for agents. Include network_request / execute_script for a permissive server; remove them to harden.';
    }
    return '';
}

function attachHandlers() {
    document.querySelectorAll('.tool-desc-input, .tool-output-input').forEach(textarea => {
        textarea.addEventListener('input', () => {
            syncToolOverride(
                textarea.dataset.server,
                textarea.dataset.toolName,
                textarea.dataset.originalDesc
            );
        });
    });

    document.querySelectorAll('.reset-tool-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const serverType = btn.dataset.server;
            const toolName = btn.dataset.toolName;
            const descEl = document.querySelector(`.tool-desc-input[data-server="${serverType}"][data-tool-name="${toolName}"]`);
            const outEl = document.querySelector(`.tool-output-input[data-server="${serverType}"][data-tool-name="${toolName}"]`);
            if (descEl) descEl.value = descEl.dataset.originalDesc;
            if (outEl) outEl.value = '';
            delete (pendingOverrides[serverType] || {})[toolName];
            const card = document.querySelector(`.tool-card[data-server="${serverType}"][data-tool-name="${toolName}"]`);
            if (card) card.classList.remove('modified');
        });
    });

    document.querySelectorAll('.save-server-btn').forEach(btn => {
        btn.addEventListener('click', () => saveServerOverrides(btn.dataset.server));
    });

    document.querySelectorAll('.reset-server-btn').forEach(btn => {
        btn.addEventListener('click', () => resetServerOverrides(btn.dataset.server));
    });

    document.querySelectorAll('.save-config-btn').forEach(btn => {
        btn.addEventListener('click', () => saveServerConfig(btn.dataset.server));
    });

    document.querySelectorAll('.reset-config-btn').forEach(btn => {
        btn.addEventListener('click', () => resetServerConfig(btn.dataset.server));
    });

    document.querySelectorAll('.apply-scenario-btn').forEach(btn => {
        btn.addEventListener('click', () => applyScenario(btn.dataset.scenarioId));
    });

    document.querySelectorAll('.preview-scenario-btn').forEach(btn => {
        btn.addEventListener('click', () => previewScenario(btn.dataset.scenarioId));
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
        message: `Reset all tool definitions for this server to defaults? This removes description and output poisoning.`,
        confirmText: 'Reset Tools',
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

function collectPolicyConfig(serverType) {
    const config = {};
    let parseError = null;

    document.querySelectorAll(`.policy-input[data-server="${serverType}"], .policy-json-input[data-server="${serverType}"]`).forEach(input => {
        const key = input.dataset.configKey;
        if (input.classList.contains('policy-json-input')) {
            try {
                config[key] = JSON.parse(input.value);
            } catch (e) {
                parseError = `Invalid JSON in "${key}": ${e.message}`;
            }
        } else {
            config[key] = input.type === 'number' ? parseFloat(input.value) : input.value;
        }
    });

    return { config, parseError };
}

async function saveServerConfig(serverType) {
    const { config, parseError } = collectPolicyConfig(serverType);
    if (parseError) {
        showNotification(parseError, 'error');
        return;
    }

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
        const resp = await fetch(`${API_BASE}/servers/${serverType}/config`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
            },
            body: JSON.stringify({ config }),
        });
        if (!resp.ok) throw new Error('Save failed');
        pendingConfigs[serverType] = config;
        showNotification(`Server policy saved for ${serverType}. Takes effect on next agent run.`, 'success');
        await loadServers();
    } catch (err) {
        console.error('Error saving server config:', err);
        showNotification('Failed to save server policy.', 'error');
    }
}

async function resetServerConfig(serverType) {
    const confirmed = await showConfirmModal({
        title: 'Reset Server Policy',
        message: 'Restore this server\'s policy settings (limits, enabled tools, etc.) to platform defaults?',
        confirmText: 'Reset Policy',
        cancelText: 'Cancel',
        danger: true,
    });
    if (!confirmed) return;

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
        const resp = await fetch(`${API_BASE}/servers/${serverType}/reset-config`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
            },
        });
        if (!resp.ok) throw new Error('Reset failed');
        showNotification('Server policy reset to defaults.', 'success');
        await loadServers();
    } catch (err) {
        console.error('Error resetting server config:', err);
        showNotification('Failed to reset server policy.', 'error');
    }
}

async function applyScenario(scenarioId) {
    const scenario = scenarios.find(s => s.id === scenarioId);
    if (scenario?.ui_mode === 'preview') {
        await previewScenario(scenarioId);
        return;
    }

    const title = scenario?.title || scenarioId;
    const isMalicious = scenario?.variant === 'malicious';

    const confirmed = await showConfirmModal({
        title: `Apply environment: ${title}`,
        message: isMalicious
            ? `Apply "${title}"? This changes server policy for your namespace (not tool description poison).`
            : `Apply "${title}"? This resets MCP tool overrides and policy settings to platform defaults.`,
        confirmText: 'Apply',
        cancelText: 'Cancel',
        danger: isMalicious,
    });
    if (!confirmed) return;

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
        const resp = await fetch(`${API_BASE}/scenarios/${scenarioId}/apply`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
            },
        });
        if (!resp.ok) {
            const errBody = await resp.json().catch(() => ({}));
            throw new Error(errBody.detail || 'Apply failed');
        }
        const data = await resp.json();
        showNotification(`Environment "${data.title}" applied. Reloading…`, 'success');
        await loadServers();
    } catch (err) {
        console.error('Error applying scenario:', err);
        showNotification(err.message || 'Failed to apply environment preset.', 'error');
    }
}

async function previewScenario(scenarioId) {
    const panel = document.getElementById('scenario-preview-panel');
    if (!panel) return;

    try {
        const resp = await fetch(`${API_BASE}/scenarios/${scenarioId}`);
        if (!resp.ok) throw new Error('Failed to load example');
        const data = await resp.json();
        panel.classList.remove('hidden');
        panel.innerHTML = renderScenarioPreview(data);
        panel.querySelectorAll('.copy-example-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const idx = Number(btn.dataset.exampleIndex);
                const value = data.examples?.[idx]?.value || '';
                try {
                    await navigator.clipboard.writeText(value);
                    showNotification('Example copied — paste it into the matching tool field.', 'success');
                } catch (err) {
                    console.error('Clipboard failed:', err);
                    showNotification('Could not copy. Select the text manually.', 'error');
                }
            });
        });
        panel.querySelector('.close-preview-btn')?.addEventListener('click', () => {
            panel.classList.add('hidden');
            panel.innerHTML = '';
        });
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (err) {
        console.error('Error loading scenario preview:', err);
        showNotification('Failed to load example poison.', 'error');
    }
}

function renderScenarioPreview(data) {
    const examples = (data.examples || []).map((ex, idx) => {
        const target = ex.tool_name
            ? `${ex.server_type} → ${ex.tool_name} → ${ex.field}`
            : `${ex.server_type} → ${ex.field}`;
        return `
            <div class="border border-white/10 rounded-lg p-3 bg-black/30">
                <div class="flex items-center justify-between gap-2 mb-2 flex-wrap">
                    <span class="text-xs font-mono text-amber-200">${esc(target)}</span>
                    <button type="button"
                        class="copy-example-btn text-xs px-2 py-1 rounded border border-amber-500/40 text-amber-100 hover:bg-amber-500/15"
                        data-example-index="${idx}">
                        Copy
                    </button>
                </div>
                <pre class="text-xs text-text-secondary whitespace-pre-wrap break-words max-h-48 overflow-y-auto m-0">${esc(ex.value)}</pre>
            </div>`;
    }).join('') || '<p class="text-xs text-text-secondary">No copyable examples in this preset.</p>';

    return `
        <div class="flex items-start justify-between gap-3 mb-3">
            <div>
                <h4 class="text-sm font-semibold text-text-bright">${esc(data.title)}</h4>
                <p class="text-xs text-text-secondary mt-1">${esc(data.hint || data.description)}</p>
            </div>
            <button type="button" class="close-preview-btn text-xs text-text-secondary hover:text-text-bright">Close</button>
        </div>
        <div class="space-y-3">${examples}</div>`;
}

function esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
