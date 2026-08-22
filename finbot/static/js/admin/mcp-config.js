/**
 * FinBot Admin Portal - MCP Server Configuration
 */

let serverData = null;

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('config-container');
    if (!container) return;
    const serverType = container.dataset.serverType;
    if (serverType) loadServerConfig(serverType);
});

async function loadServerConfig(serverType) {
    const container = document.getElementById('config-container');

    try {
        const response = await fetch(`/admin/api/v1/mcp/servers/${serverType}`);
        if (!response.ok) throw new Error('Failed to load server config');
        const data = await response.json();
        serverData = data.server;
        // Preserve default_config from platform defaults when API includes it
        if (!serverData.default_config && data.default_config) {
            serverData.default_config = data.default_config;
        }

        document.getElementById('config-page-title').textContent = serverData.display_name + ' Configuration';
        document.getElementById('config-page-subtitle').textContent = serverData.description || `Configure ${serverData.display_name} MCP server`;

        container.innerHTML = renderConfig(serverData);
        attachConfigHandlers(serverType);
    } catch (error) {
        console.error('Error loading server config:', error);
        container.innerHTML = '<div class="text-center py-16 text-red-400">Failed to load server configuration.</div>';
    }
}

function renderConfig(server) {
    const config = server.config || {};

    let configFieldsHtml = '';
    for (const [key, value] of Object.entries(config)) {
        const label = configLabel(key);
        const help = configHelp(key, server.default_config ? server.default_config[key] : undefined);

        if (typeof value === 'object' && value !== null) {
            const jsonStr = JSON.stringify(value, null, 2);
            configFieldsHtml += `
                <div class="py-3">
                    <label class="text-sm text-text-secondary font-medium block mb-1">${esc(label)}</label>
                    ${help ? `<p class="text-xs text-text-secondary mb-2">${help}</p>` : ''}
                    <textarea class="tool-textarea config-json-input" data-config-key="${esc(key)}"
                        rows="${Math.min(Math.max(jsonStr.split('\n').length, 3), 12)}">${esc(jsonStr)}</textarea>
                </div>
            `;
        } else {
            const type = typeof value === 'number' ? 'number' : 'text';
            configFieldsHtml += `
                <div class="py-3">
                    <div class="flex items-center justify-between gap-4">
                        <div>
                            <label class="text-sm text-text-secondary font-medium block">${esc(label)}</label>
                            ${help ? `<p class="text-xs text-text-secondary mt-1">${help}</p>` : ''}
                        </div>
                        <input type="${type}" name="config-${key}" value="${esc(String(value))}"
                            class="config-input w-48 text-right" data-config-key="${esc(key)}">
                    </div>
                </div>
            `;
        }
    }

    return `
        <!-- Server Status with Toggle -->
        <div class="bg-portal-bg-secondary border border-admin-primary/20 rounded-xl overflow-hidden mb-8">
            <div class="px-6 py-4 flex items-center justify-between">
                <div class="flex items-center gap-4">
                    <div class="flex items-center gap-2">
                        <span class="w-3 h-3 rounded-full ${server.enabled ? 'bg-green-500' : 'bg-gray-500'}"></span>
                        <span class="text-sm font-medium ${server.enabled ? 'text-green-400' : 'text-text-secondary'}">
                            ${server.enabled ? 'Enabled' : 'Disabled'}
                        </span>
                    </div>
                    <span class="text-text-secondary text-sm">|</span>
                    <span class="text-sm text-text-secondary font-mono">${esc(server.server_type)}</span>
                </div>
                <button id="toggle-server-btn"
                    class="text-sm px-4 py-1.5 rounded-lg border transition-colors ${server.enabled
                        ? 'border-red-500/30 text-red-400 hover:bg-red-500/10'
                        : 'border-green-500/30 text-green-400 hover:bg-green-500/10'
                    }"
                    data-server-type="${esc(server.server_type)}">
                    ${server.enabled ? 'Disable Server' : 'Enable Server'}
                </button>
            </div>
        </div>

        <!-- Server Settings -->
        ${configFieldsHtml ? `
        <div class="bg-portal-bg-secondary border border-admin-primary/20 rounded-xl overflow-hidden mb-8">
            <div class="px-6 py-4 border-b border-admin-primary/10 flex items-center justify-between">
                <div>
                    <h2 class="text-lg font-bold text-text-bright">Server Policy & Settings</h2>
                    <p class="text-xs text-text-secondary mt-1">Payment limits and enabled tools act as authorization policy for agents.</p>
                </div>
                <button id="save-config-btn" class="text-sm px-4 py-1.5 rounded-lg bg-admin-primary/20 text-admin-primary border border-admin-primary/30 hover:bg-admin-primary/30 transition-colors">
                    Save Settings
                </button>
            </div>
            <div class="px-6 py-4 divide-y divide-white/5">
                ${configFieldsHtml}
            </div>
        </div>
        ` : ''}
    `;
}

function configLabel(key) {
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

function configHelp(key, defaultVal) {
    if (key === 'max_payment') {
        const tip = defaultVal !== undefined ? ` Default: ${defaultVal} (permissive).` : '';
        return `FinStripe rejects transfers above this amount.${tip} Lower it to harden policy; raise it further to weaken.`;
    }
    if (key === 'enabled_tools') {
        return 'Only listed tools are exposed to agents. High-risk tools include network_request and execute_script.';
    }
    return '';
}

function attachConfigHandlers(serverType) {
    const saveConfigBtn = document.getElementById('save-config-btn');
    if (saveConfigBtn) {
        saveConfigBtn.addEventListener('click', () => saveConfig(serverType));
    }

    const toggleBtn = document.getElementById('toggle-server-btn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => toggleServer(serverType));
    }
}

async function toggleServer(serverType) {
    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
        const response = await fetch(`/admin/api/v1/mcp/servers/${serverType}/toggle`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
            },
        });
        if (!response.ok) throw new Error('Toggle failed');
        showNotification('Server toggled successfully.', 'success');
        await loadServerConfig(serverType);
    } catch (error) {
        console.error('Error toggling server:', error);
        showNotification('Failed to toggle server.', 'error');
    }
}

async function saveConfig(serverType) {
    const inputs = document.querySelectorAll('[data-config-key]');
    const config = {};
    let parseError = null;
    inputs.forEach(input => {
        const key = input.dataset.configKey;
        if (input.classList.contains('config-json-input')) {
            try {
                config[key] = JSON.parse(input.value);
            } catch (e) {
                parseError = `Invalid JSON in "${key}": ${e.message}`;
            }
        } else {
            const value = input.type === 'number' ? parseFloat(input.value) : input.value;
            config[key] = value;
        }
    });

    if (parseError) {
        showNotification(parseError, 'error');
        return;
    }

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
        const response = await fetch(`/admin/api/v1/mcp/servers/${serverType}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
            },
            body: JSON.stringify({ config }),
        });
        if (!response.ok) throw new Error('Save failed');
        showNotification('Server settings saved successfully.', 'success');
    } catch (error) {
        console.error('Error saving config:', error);
        showNotification('Failed to save settings. Please try again.', 'error');
    }
}

function esc(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
