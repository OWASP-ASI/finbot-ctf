/**
 * FinBot CTF - Activity Stream
 * Horizontal swimlane Gantt-chart visualization for multi-agent workflows
 */

(function () {
    'use strict';

    let allEvents = [];
    let allAchievements = {};
    let currentView = 'workflow';
    let selectedWorkflowId = null;
    let sortOrder = 'desc';

    const PAGE_SIZE = 500;
    let nextPage = 1;
    let hasMore = false;
    let totalEvents = 0;
    let isLoading = false;

    const AGENTS = {
        orchestrator_agent:   { icon: '🎯', cls: 'orchestrator',   label: 'Orchestrator',   color: '#00d4ff' },
        onboarding_agent:     { icon: '🤖', cls: 'onboarding',     label: 'Onboarding',     color: '#7c3aed' },
        fraud_agent:          { icon: '🛡️', cls: 'fraud',          label: 'Fraud',          color: '#ef4444' },
        communication_agent:  { icon: '📧', cls: 'communication',  label: 'Communication',  color: '#3b82f6' },
        chat_assistant:       { icon: '💬', cls: 'chat',           label: 'Chat',           color: '#a78bfa' },
    };

    document.addEventListener('DOMContentLoaded', init);

    async function init() {
        setupViewToggle();
        setupLoadMore();
        await loadEvents();
    }

    function setupLoadMore() {
        const btn = document.getElementById('load-more-btn');
        if (btn) {
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                btn.textContent = 'Loading…';
                await loadEvents(true);
                btn.textContent = 'Load Older Activity';
            });
        }
    }

    // ==================== DATA ====================

    async function loadEvents(append = false) {
        if (isLoading) return;
        isLoading = true;

        try {
            const options = { page: nextPage, page_size: PAGE_SIZE };
            const data = await CTF.getActivity(options);
            const items = data.items || [];

            if (append) {
                allEvents = allEvents.concat(items);
            } else {
                allEvents = items;
                allAchievements = data.achievements || {};
                totalEvents = data.total || 0;
            }

            hasMore = data.has_more;
            if (hasMore) nextPage++;

            renderCurrentView();
            updateLoadMoreButton();
        } catch (err) {
            console.error('Failed to load activity:', err);
            document.getElementById('orch-loading').classList.add('hidden');
            document.getElementById('orch-empty').classList.remove('hidden');
        } finally {
            isLoading = false;
        }
    }

    function updateLoadMoreButton() {
        const container = document.getElementById('load-more-container');
        if (!container) return;

        if (!hasMore || allEvents.length === 0) {
            container.classList.add('hidden');
            return;
        }

        const remaining = totalEvents - allEvents.length;
        container.classList.remove('hidden');
        const btn = container.querySelector('#load-more-btn');
        const info = container.querySelector('#load-more-info');
        if (btn) btn.disabled = false;
        if (info) info.textContent = `Showing ${allEvents.length.toLocaleString()} of ${totalEvents.toLocaleString()} events · ${remaining.toLocaleString()} older events available`;
    }

    // ==================== VIEW TOGGLE ====================

    function setupViewToggle() {
        document.getElementById('btn-workflow-view').addEventListener('click', () => switchView('workflow'));
        document.getElementById('btn-timeline-view').addEventListener('click', () => switchView('timeline'));

        document.getElementById('trace-back-btn').addEventListener('click', () => {
            document.getElementById('trace-view').classList.add('hidden');
            switchView(currentView);
        });
    }

    function switchView(view) {
        currentView = view;
        document.getElementById('trace-view').classList.add('hidden');
        ['workflow', 'timeline'].forEach(v => {
            const btn = document.getElementById(`btn-${v}-view`);
            if (btn) btn.classList.toggle('active', view === v);
            const el = document.getElementById(`${v}-view`);
            if (el) el.classList.toggle('hidden', view !== v);
        });
        renderCurrentView();
    }

    function renderCurrentView() {
        if (currentView === 'workflow') render();
        else if (currentView === 'timeline') renderTimeline();
        updateLoadMoreButton();
    }

    // ==================== RENDER ====================

    function render() {
        const events = allEvents;
        const loading = document.getElementById('orch-loading');
        const list = document.getElementById('orch-list');
        const empty = document.getElementById('orch-empty');
        loading.classList.add('hidden');

        if (events.length === 0) {
            list.classList.add('hidden');
            empty.classList.remove('hidden');
            return;
        }

        empty.classList.add('hidden');
        list.classList.remove('hidden');

        const { workflows } = groupByWorkflow(events);

        list.innerHTML = workflows.map(wf => renderWorkflowCard(wf)).join('');

        list.querySelectorAll('.orch-card').forEach(card => {
            card.addEventListener('click', () => selectWorkflow(card.dataset.workflowId));
        });

        list.querySelectorAll('.trace-show-btn').forEach(btn => {
            btn.addEventListener('click', (ev) => {
                ev.stopPropagation();
                showTraceForWorkflow(btn.dataset.wfId);
            });
        });

        bindSegmentTooltips(list);

        if (selectedWorkflowId) {
            const existing = list.querySelector(`[data-workflow-id="${selectedWorkflowId}"]`);
            if (existing) {
                existing.classList.add('selected');
                renderDetailPanel(selectedWorkflowId);
            }
        }
    }

    // ==================== WORKFLOW GROUPING ====================

    function groupByWorkflow(events) {
        const sorted = [...events].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
        const map = new Map();

        for (const e of sorted) {
            if (!e.workflow_id) continue;
            if (!map.has(e.workflow_id)) {
                map.set(e.workflow_id, { id: e.workflow_id, events: [] });
            }
            map.get(e.workflow_id).events.push(e);
        }

        const workflows = Array.from(map.values());
        workflows.sort((a, b) => {
            const aT = a.events[a.events.length - 1]?.timestamp || '';
            const bT = b.events[b.events.length - 1]?.timestamp || '';
            return bT.localeCompare(aT);
        });

        return { workflows };
    }

    // ==================== WORKFLOW CARD ====================

    function renderWorkflowCard(wf) {
        const events = wf.events;
        const agents = getWorkflowAgents(events);
        const triggerInfo = getWorkflowTrigger(wf);
        const status = getWorkflowStatus(events);
        const vendorId = events.find(e => e.vendor_id)?.vendor_id;
        const vendorName = getVendorName(events);
        const duration = computeDuration(events);
        const llmCount = events.filter(e => e.event_subtype === 'llm' && e.event_type.includes('success')).length;
        const toolCount = events.filter(e => e.event_type.includes('tool_call_start') && !e.event_type.includes('mcp_')).length;
        const mcpCount = events.filter(e => e.event_type.includes('mcp_tool_call_start')).length;
        const lastTs = events[events.length - 1]?.timestamp;

        const swimResult = buildSwimlanes(events);
        const timeScale = buildTimeScale(events);
        const innerWidth = Math.max(100, swimResult.totalSegments * 48);
        const minWidthStyle = innerWidth > 100 ? `min-width:${innerWidth}px` : '';

        return `
        <div class="orch-card" data-workflow-id="${wf.id}">
            <div class="orch-header">
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-3 mb-2 flex-wrap">
                        <span class="text-sm font-medium text-text-bright">${esc(triggerInfo.title)}</span>
                        <span class="wf-status ${status.cls}">${status.label}</span>
                        ${vendorName ? `<div class="vendor-chip"><div class="vendor-chip-icon">🏢</div><span>${esc(vendorName)}</span></div>` : ''}
                        ${renderAchievementBadges(wf.id)}
                    </div>
                    <div class="flex items-center gap-3 flex-wrap">
                        <div class="trigger-badge">
                            <span>${triggerInfo.icon}</span>
                            <span>${esc(triggerInfo.action)}</span>
                        </div>
                        <div class="agent-summary">
                            ${agents.map(a => {
                                const info = AGENTS[a] || { color: '#888', label: a };
                                return `<div class="agent-chip"><div class="agent-chip-dot" style="background: ${info.color}"></div><span>${info.label}</span></div>`;
                            }).join('')}
                        </div>
                    </div>
                </div>
                <div class="text-right flex-shrink-0">
                    <div class="text-xs text-text-secondary font-mono opacity-50" title="${esc(wf.id)}">${shortWfId(wf.id)}</div>
                    ${lastTs ? `<div class="text-xs text-text-secondary mt-1">${relTime(lastTs)}</div>` : ''}
                </div>
            </div>

            <div class="agent-lanes-scroll">
                <div style="${minWidthStyle}">
                    ${timeScale}
                    <div class="agent-lanes">
                        ${swimResult.html}
                    </div>
                </div>
            </div>

            <div class="wf-meta">
                <span>Duration: <span class="wf-meta-value">${fmtDur(duration)}</span></span>
                <span>Agents: <span class="wf-meta-value">${agents.length}</span></span>
                ${llmCount ? `<span>LLM: <span class="wf-meta-value">${llmCount}</span></span>` : ''}
                ${toolCount ? `<span>Tools: <span class="wf-meta-value">${toolCount}</span></span>` : ''}
                ${mcpCount ? `<span>MCP: <span class="wf-meta-value">${mcpCount}</span></span>` : ''}
                <span class="ml-auto"><button class="trace-show-btn" data-wf-id="${wf.id}">Show Trace →</button></span>
            </div>
        </div>`;
    }

    // ==================== SWIMLANE BUILDER ====================

    function buildSwimlanes(events) {
        const agents = getWorkflowAgents(events);
        const timeMap = buildCompressedTimeMap(events);

        let totalSegments = 0;

        const html = agents.map(agentName => {
            const info = AGENTS[agentName] || { icon: '⚙️', cls: 'orchestrator', label: agentName };
            const agentEvents = events.filter(e => e.agent_name === agentName);
            const result = buildSegments(agentEvents, timeMap);
            totalSegments += result.count;

            return `
            <div class="agent-lane">
                <div class="agent-label">
                    <div class="agent-icon-sm ${info.cls}">${info.icon}</div>
                    <span class="text-xs text-text-secondary">${info.label}</span>
                </div>
                <div class="lane-timeline">
                    ${result.html}
                </div>
            </div>`;
        }).join('');

        return { html, totalSegments };
    }

    function buildCompressedTimeMap(events) {
        const timestamps = events.map(e => parseTS(e.timestamp).getTime()).sort((a, b) => a - b);
        if (timestamps.length < 2) return { toPercent: () => 0, duration: 1 };

        const gaps = [];
        for (let i = 1; i < timestamps.length; i++) {
            gaps.push(timestamps[i] - timestamps[i - 1]);
        }

        const medianGap = gaps.slice().sort((a, b) => a - b)[Math.floor(gaps.length / 2)] || 1;
        const maxGap = medianGap * 8;

        let compressedTotal = 0;
        const breakpoints = [{ real: timestamps[0], compressed: 0 }];
        for (let i = 1; i < timestamps.length; i++) {
            const rawGap = timestamps[i] - timestamps[i - 1];
            compressedTotal += Math.min(rawGap, maxGap);
            breakpoints.push({ real: timestamps[i], compressed: compressedTotal });
        }

        const duration = compressedTotal || 1;

        function toPercent(realTime) {
            for (let i = breakpoints.length - 1; i >= 0; i--) {
                if (realTime >= breakpoints[i].real) {
                    const extra = realTime - breakpoints[i].real;
                    const capped = Math.min(extra, maxGap);
                    return (breakpoints[i].compressed + capped) / duration;
                }
            }
            return 0;
        }

        return { toPercent, duration };
    }

    function buildSegments(agentEvents, timeMap) {
        if (agentEvents.length === 0) return { html: '', count: 0 };

        const spans = [];
        let i = 0;

        while (i < agentEvents.length) {
            const e = agentEvents[i];
            const eTime = parseTS(e.timestamp).getTime();
            const relPos = timeMap.toPercent(eTime);

            if (e.event_type.includes('llm_request_start')) {
                const successor = agentEvents[i + 1];
                let dur = 0;
                if (successor && successor.event_type.includes('llm_request_success') && successor.duration_ms) {
                    dur = successor.duration_ms;
                }
                const model = e.details?.llm_model || successor?.llm_model || '';
                const msgCount = e.details?.messages?.length || e.summary.match(/messages: (\d+)/)?.[1] || '';
                spans.push({
                    type: 'llm', pos: relPos, dur,
                    icon: '🧠', label: 'LLM',
                    tipTitle: 'LLM Request',
                    tipDetail: [model, msgCount ? `${msgCount} msgs` : '', dur ? fmtDur(dur) : ''].filter(Boolean).join(' · '),
                });
                if (successor && successor.event_type.includes('llm_request_success')) i++;
            } else if (e.event_type.includes('mcp_tool_call_start')) {
                const toolName = e.details?.namespaced_tool_name || e.details?.tool_name || e.tool_name || 'mcp_tool';
                const serverName = e.details?.mcp_server || '';
                const successor = agentEvents[i + 1];
                let dur = 0;
                if (successor && successor.event_type.includes('mcp_tool_call_success') && successor.duration_ms) {
                    dur = successor.duration_ms;
                } else if (successor && successor.event_type.includes('mcp_tool_call_success') && successor.details?.duration_ms) {
                    dur = successor.details.duration_ms;
                }
                const args = e.details?.tool_arguments;
                const argSnippet = args ? shortArgs(args) : '';
                spans.push({
                    type: 'mcp', pos: relPos, dur,
                    icon: '⚡', label: shortToolName(toolName),
                    tipTitle: `MCP: ${toolName}`,
                    tipDetail: [serverName, argSnippet, dur ? fmtDur(dur) : ''].filter(Boolean).join(' · '),
                });
                if (successor && (successor.event_type.includes('mcp_tool_call_success') || successor.event_type.includes('mcp_tool_call_failure'))) i++;
            } else if (e.event_type.includes('mcp_tools_discovered')) {
                const serverName = e.details?.mcp_server || '';
                const toolCount = e.details?.tool_count || 0;
                spans.push({
                    type: 'mcp-discover', pos: relPos, dur: 0,
                    icon: '🔌', label: 'MCP',
                    tipTitle: `MCP Connect: ${serverName}`,
                    tipDetail: `${toolCount} tools discovered`,
                });
            } else if (e.event_type.includes('tool_call_start')) {
                const toolName = e.tool_name || 'tool';
                const successor = agentEvents[i + 1];
                let dur = 0;
                if (successor && successor.event_type.includes('tool_call_success') && successor.duration_ms) {
                    dur = successor.duration_ms;
                }
                const isDelegation = toolName.startsWith('delegate_to_');
                const args = e.details?.arguments || e.details?.tool_kwargs;
                const argSnippet = args ? shortArgs(args) : '';
                spans.push({
                    type: isDelegation ? 'delegation' : 'tool',
                    pos: relPos, dur,
                    icon: isDelegation ? '↗' : '🔧',
                    label: shortToolName(toolName),
                    tipTitle: toolName,
                    tipDetail: [argSnippet, dur ? fmtDur(dur) : ''].filter(Boolean).join(' · '),
                });
                if (successor && successor.event_type.includes('tool_call_success')) i++;
            } else if (e.event_type.includes('task_start')) {
                spans.push({
                    type: 'thinking', pos: relPos, dur: 0,
                    icon: '▶', label: 'Start',
                    tipTitle: `${(AGENTS[e.agent_name] || {}).label || e.agent_name} started`,
                    tipDetail: '',
                });
            } else if (e.event_type.includes('task_completion')) {
                const status = e.details?.task_result?.task_status || 'done';
                spans.push({
                    type: 'decision', pos: relPos, dur: 0,
                    icon: '✓', label: 'Done',
                    tipTitle: 'Task complete',
                    tipDetail: status,
                });
            }
            i++;
        }

        if (spans.length === 0) return { html: '', count: 0 };

        let html = '';
        let cursor = 0;

        for (const span of spans) {
            const startPct = span.pos * 100;
            const gap = startPct - cursor;
            if (gap > 0.5) {
                html += `<div class="lane-segment idle" style="flex: ${gap.toFixed(1)}"></div>`;
            }

            const rawW = (span.dur / timeMap.duration) * 100;
            const widthPct = Math.max(3, rawW);

            html += `<div class="lane-segment active ${span.type}" style="flex: ${widthPct.toFixed(1)}">
                ${span.icon}
                <div class="seg-tooltip">
                    <div class="tip-title">${esc(span.tipTitle)}</div>
                    ${span.tipDetail ? `<div class="tip-detail">${esc(span.tipDetail)}</div>` : ''}
                </div>
            </div>`;

            cursor = startPct + widthPct;
        }

        const tail = 100 - cursor;
        if (tail > 0.5) {
            html += `<div class="lane-segment idle" style="flex: ${tail.toFixed(1)}"></div>`;
        }

        return { html, count: spans.length };
    }

    function buildTimeScale(events) {
        if (events.length < 2) return '';
        const start = parseTS(events[0].timestamp).getTime();
        const end = parseTS(events[events.length - 1].timestamp).getTime();
        const duration = end - start;
        if (duration < 100) return '';

        return `<div class="time-scale">
            <div class="time-marker">0</div>
            <div class="time-marker" style="flex:1"></div>
            <div class="time-marker">Total: ${fmtDur(duration)}</div>
        </div>`;
    }

    // ==================== WORKFLOW SELECTION & DETAIL PANEL ====================

    function selectWorkflow(wfId) {
        selectedWorkflowId = wfId;

        document.querySelectorAll('.orch-card').forEach(c => c.classList.remove('selected'));
        const card = document.querySelector(`[data-workflow-id="${wfId}"]`);
        if (card) card.classList.add('selected');

        renderDetailPanel(wfId);

        if (window.innerWidth < 1024) {
            renderMobileDetail(wfId);
        }
    }

    function renderDetailPanel(wfId) {
        const detailEmpty = document.getElementById('detail-empty');
        const detailContent = document.getElementById('detail-content');
        if (!detailEmpty || !detailContent) return;

        const wfEventsAsc = allEvents.filter(e => e.workflow_id === wfId)
            .sort((a, b) => a.timestamp.localeCompare(b.timestamp));

        if (wfEventsAsc.length === 0) return;

        detailEmpty.style.display = 'none';
        detailContent.style.display = 'flex';

        const triggerInfo = getWorkflowTrigger({ id: wfId, events: wfEventsAsc });
        document.getElementById('detail-title').textContent = triggerInfo.title;
        document.getElementById('detail-subtitle').textContent = `${wfId} · ${getWorkflowStatus(wfEventsAsc).label}`;

        const agents = ['All', ...getWorkflowAgents(wfEventsAsc).map(a => (AGENTS[a] || {}).label || a)];
        const tabsEl = document.getElementById('detail-tabs');
        const sortBtn = `<button class="detail-tab sort-toggle" data-sort="${sortOrder}" title="Toggle sort order">${sortOrder === 'desc' ? '↓ Newest' : '↑ Oldest'}</button>`;
        tabsEl.innerHTML = agents.map((a, idx) =>
            `<button class="detail-tab ${idx === 0 ? 'active' : ''}" data-agent-filter="${idx === 0 ? 'all' : a}">${a}</button>`
        ).join('') + sortBtn;

        let currentAgentFilter = 'all';

        tabsEl.querySelectorAll('.detail-tab[data-agent-filter]').forEach(btn => {
            btn.addEventListener('click', () => {
                tabsEl.querySelectorAll('.detail-tab[data-agent-filter]').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentAgentFilter = btn.dataset.agentFilter;
                renderDetailEvents(wfEventsAsc, currentAgentFilter);
            });
        });

        tabsEl.querySelector('.sort-toggle').addEventListener('click', (ev) => {
            sortOrder = sortOrder === 'desc' ? 'asc' : 'desc';
            ev.target.textContent = sortOrder === 'desc' ? '↓ Newest' : '↑ Oldest';
            ev.target.dataset.sort = sortOrder;
            renderDetailEvents(wfEventsAsc, currentAgentFilter);
            renderTimeline();
        });

        renderDetailEvents(wfEventsAsc, 'all');
    }

    function renderDetailEvents(events, agentFilter) {
        let filtered = [...events];
        if (agentFilter !== 'all') {
            filtered = filtered.filter(e => {
                const label = (AGENTS[e.agent_name] || {}).label || e.agent_name;
                return label === agentFilter || e.event_category === 'business';
            });
        }
        if (sortOrder === 'desc') filtered.reverse();

        const container = document.getElementById('detail-events');
        container.innerHTML = filtered.map(e => renderDetailEvent(e)).join('');

        container.querySelectorAll('.detail-event[data-expandable]').forEach(el => {
            el.addEventListener('click', () => {
                const jsonEl = el.querySelector('.detail-expand');
                if (jsonEl) jsonEl.classList.toggle('hidden');
            });
        });
    }

    function renderDetailEvent(e) {
        const subtype = e.event_subtype || 'lifecycle';
        const isBusiness = e.event_category === 'business';
        const agentInfo = AGENTS[e.agent_name];
        const agentLabel = agentInfo ? agentInfo.label : '';
        const durationStr = e.duration_ms ? fmtDur(e.duration_ms) : '';

        let icon = '⟳';
        let iconCls = subtype;
        if (subtype === 'mcp') icon = '⚡';
        else if (subtype === 'llm') icon = '🧠';
        else if (subtype === 'tool') icon = '🔧';
        else if (subtype === 'decision') icon = '⚖️';
        else if (subtype === 'chat') icon = '💬';
        else if (isBusiness) { icon = '📋'; iconCls = 'business'; }

        const isMcpEvent = subtype === 'mcp';
        const mcpServer = isMcpEvent ? (e.details?.mcp_server || '') : '';

        const summary = condenseSummary(e);
        const expandText = getExpandContent(e.details);
        const hasExpandable = expandText !== null;

        let expandContent = '';
        if (hasExpandable) {
            expandContent = `<div class="detail-expand hidden mt-2"><div class="detail-json">${esc(expandText)}</div></div>`;
        }

        return `
        <div class="detail-event ${isBusiness ? 'business-ev' : ''}" ${hasExpandable ? 'data-expandable' : ''}>
            <div class="detail-event-icon ${iconCls}">${icon}</div>
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                    ${agentLabel ? `<span class="text-text-bright text-xs font-medium">${agentLabel}:</span>` : ''}
                    <span class="text-text-primary text-xs">${esc(summary)}</span>
                    ${hasExpandable ? '<span class="text-text-secondary text-xs opacity-40">▸</span>' : ''}
                </div>
                ${e.tool_name ? `<div class="text-xs font-mono text-ctf-primary mt-0.5">${esc(e.tool_name)}</div>` : ''}
                ${mcpServer ? `<div class="text-xs font-mono mt-0.5" style="color:#e879f9">⚡ ${esc(mcpServer)}</div>` : ''}
                ${expandContent}
            </div>
            <span class="text-xs text-text-secondary whitespace-nowrap flex-shrink-0">${durationStr || fmtTime(e.timestamp)}</span>
        </div>`;
    }

    // ==================== MOBILE DETAIL MODAL ====================

    function renderMobileDetail(wfId) {
        const modal = document.getElementById('detail-modal');
        const events = allEvents.filter(e => e.workflow_id === wfId)
            .sort((a, b) => a.timestamp.localeCompare(b.timestamp));

        const triggerInfo = getWorkflowTrigger({ id: wfId, events });
        document.getElementById('mobile-detail-title').textContent = triggerInfo.title;
        document.getElementById('mobile-detail-events').innerHTML = events.map(e => renderDetailEvent(e)).join('');

        modal.style.display = 'flex';

        modal.querySelectorAll('.detail-event[data-expandable]').forEach(el => {
            el.addEventListener('click', () => {
                const jsonEl = el.querySelector('.detail-expand');
                if (jsonEl) jsonEl.classList.toggle('hidden');
            });
        });
    }

    window.closeDetailModal = function () {
        document.getElementById('detail-modal').style.display = 'none';
    };

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeDetailModal();
    });

    // ==================== VERTICAL TIMELINE VIEW ====================

    function renderTimeline() {
        const container = document.getElementById('timeline-container');
        const empty = document.getElementById('timeline-empty');
        const events = allEvents;

        if (events.length === 0) {
            container.innerHTML = '';
            empty.classList.remove('hidden');
            return;
        }

        empty.classList.add('hidden');

        const sorted = [...events].sort((a, b) =>
            sortOrder === 'desc'
                ? b.timestamp.localeCompare(a.timestamp)
                : a.timestamp.localeCompare(b.timestamp)
        );

        let html = '';
        let lastAgent = null;

        for (const e of sorted) {
            const agentName = e.agent_name;
            const agentInfo = AGENTS[agentName];
            const isBusiness = e.event_category === 'business';
            const subtype = e.event_subtype || 'lifecycle';

            if (agentName && agentName !== lastAgent) {
                const label = agentInfo ? agentInfo.label : agentName;
                html += `<div class="tl-group-label">${esc(label)}</div>`;
                lastAgent = agentName;
            } else if (isBusiness && lastAgent !== '__business__') {
                html += `<div class="tl-group-label">Business Event</div>`;
                lastAgent = '__business__';
            }

            let icon = '⟳';
            let iconCls = 'lifecycle';
            if (isBusiness) { icon = getBusinessIcon(e); iconCls = 'business'; }
            else if (subtype === 'mcp') { icon = '⚡'; iconCls = 'mcp'; }
            else if (subtype === 'llm') { icon = '🧠'; iconCls = 'llm'; }
            else if (subtype === 'tool') { icon = '🔧'; iconCls = 'tool'; }
            else if (subtype === 'decision') { icon = '⚖️'; iconCls = 'decision'; }
            else if (subtype === 'chat') { icon = '💬'; iconCls = 'chat'; }

            const agentBadge = agentInfo
                ? `<span class="tl-agent-badge ${agentInfo.cls}">${agentInfo.label}</span>`
                : '';

            const durationHtml = e.duration_ms ? renderTlDuration(e.duration_ms) : '';
            const isMcpEvt = subtype === 'mcp';
            const mcpSrv = isMcpEvt ? (e.details?.mcp_server || '') : '';
            const toolHtml = e.tool_name
                ? `<span class="text-xs font-mono text-ctf-primary">${esc(e.tool_name)}</span>`
                : '';
            const mcpBadgeHtml = mcpSrv
                ? `<span class="text-xs font-mono" style="color:#e879f9">⚡ ${esc(mcpSrv)}</span>`
                : '';
            const timeHtml = `<span class="text-xs text-text-secondary opacity-40 ml-auto whitespace-nowrap">${fmtTime(e.timestamp)}</span>`;

            const summary = condenseSummary(e);

            const expandText = getExpandContent(e.details);
            const hasExpand = expandText !== null;
            let expandHtml = '';
            if (hasExpand) {
                expandHtml = `<div class="tl-expand hidden"><div class="detail-json">${esc(expandText)}</div></div>`;
            }

            html += `
            <div class="tl-event subtype-${subtype} ${isBusiness ? 'is-business' : ''}" data-event-id="${e.id}" ${hasExpand ? 'data-expandable' : ''}>
                <div class="tl-event-icon ${iconCls}">${icon}</div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2 flex-wrap">
                        ${agentBadge}
                        <span class="text-sm text-text-primary">${esc(summary)}</span>
                        ${hasExpand ? '<span class="text-text-secondary text-xs opacity-40">▸</span>' : ''}
                    </div>
                    <div class="flex items-center gap-2 flex-wrap mt-1">
                        ${toolHtml}
                        ${mcpBadgeHtml}
                        ${durationHtml}
                        ${timeHtml}
                    </div>
                    ${expandHtml}
                </div>
            </div>`;
        }

        container.innerHTML = html;

        container.querySelectorAll('.tl-event[data-expandable]').forEach(el => {
            el.addEventListener('click', () => {
                const expandEl = el.querySelector('.tl-expand');
                if (expandEl) expandEl.classList.toggle('hidden');
            });
        });
    }

    function getBusinessIcon(e) {
        if (e.event_type.includes('vendor.created')) return '🏢';
        if (e.event_type.includes('decision')) return '⚖️';
        if (e.event_type.includes('notification')) return '📧';
        if (e.event_type.includes('risk')) return '🛡️';
        return '📋';
    }

    function renderTlDuration(ms) {
        const cls = ms < 100 ? 'fast' : ms < 5000 ? 'medium' : 'slow';
        return `<span class="tl-duration ${cls}">${fmtDur(ms)}</span>`;
    }

    // ==================== AGENTIC TRACE VIEW ====================

    function showTraceForWorkflow(wfId) {
        document.getElementById('workflow-view').classList.add('hidden');
        document.getElementById('timeline-view').classList.add('hidden');
        document.getElementById('load-more-container').classList.add('hidden');

        const traceView = document.getElementById('trace-view');
        const container = document.getElementById('trace-container');

        const wfEvents = allEvents.filter(e => e.workflow_id === wfId);
        const triggerInfo = getWorkflowTrigger({ id: wfId, events: wfEvents.sort((a, b) => a.timestamp.localeCompare(b.timestamp)) });
        document.getElementById('trace-title').textContent = triggerInfo.title;

        traceView.classList.remove('hidden');
        renderTraceForWorkflow(wfId, container);
    }

    function renderTraceForWorkflow(wfId, container) {
        const events = allEvents.filter(e => e.workflow_id === wfId)
            .sort((a, b) => a.timestamp.localeCompare(b.timestamp));

        if (events.length === 0) { container.innerHTML = ''; return; }

        const tree = buildTraceTree(events);
        container.innerHTML = `<div class="trace-pipeline">${renderTraceTree(tree)}</div>`;

        const outputNode = container.querySelector('.trace-output-expandable');
        if (outputNode) {
            outputNode.style.cursor = 'pointer';
            outputNode.addEventListener('click', () => {
                const full = container.querySelector('.trace-output-full');
                if (full) full.classList.toggle('hidden');
            });
        }

        container.querySelectorAll('.trace-agent-header').forEach(h => {
            h.addEventListener('click', () => {
                h.nextElementSibling.classList.toggle('collapsed');
                const arrow = h.querySelector('.trace-collapse-arrow');
                if (arrow) arrow.textContent = h.nextElementSibling.classList.contains('collapsed') ? '▸' : '▾';
            });
        });

        container.querySelectorAll('.trace-step-clickable').forEach(step => {
            step.addEventListener('click', (ev) => {
                ev.stopPropagation();
                const existing = document.querySelector('.trace-drawer');
                if (existing) {
                    const isSame = existing._sourceStep === step;
                    existing.remove();
                    if (isSame) return;
                }

                const meta = JSON.parse(step.dataset.meta || '{}');
                const entries = Object.entries(meta).filter(([, v]) => v !== null && v !== undefined && v !== '');
                if (entries.length === 0) return;

                const drawer = document.createElement('div');
                drawer.className = 'trace-drawer';
                drawer._sourceStep = step;
                drawer.innerHTML = `<div class="trace-drawer-content">
                    ${entries.map(([k, v]) => {
                        const val = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v);
                        const isLong = val.length > 80;
                        return `<div class="trace-drawer-row">
                            <span class="trace-drawer-key">${k}</span>
                            <span class="trace-drawer-val ${isLong ? 'trace-drawer-val-long' : ''}">${esc(val)}</span>
                        </div>`;
                    }).join('')}
                </div>`;

                step.closest('.trace-iteration, .trace-orch-card').appendChild(drawer);
            });
        });

        document.addEventListener('click', (ev) => {
            if (!ev.target.closest('.trace-drawer') && !ev.target.closest('.trace-step-clickable')) {
                const d = document.querySelector('.trace-drawer');
                if (d) d.remove();
            }
        });
    }

    function buildTraceTree(events) {
        const tree = { input: null, output: null, steps: [] };

        const firstEvent = events[0];
        if (firstEvent.event_category === 'business') {
            tree.input = { summary: firstEvent.summary, type: firstEvent.event_type };
        } else {
            tree.input = { summary: getWorkflowTrigger({ id: '', events }).title, type: 'trigger' };
        }

        let currentOrchIteration = null;
        let currentAgent = null;
        let currentIteration = null;
        let agentCardIndex = 0;

        for (const e of events) {
            const isOrch = e.agent_name === 'orchestrator_agent';

            if (e.event_type.includes('iteration_start') && isOrch) {
                currentOrchIteration = { reason: null, act: null, agentBlock: null };
                continue;
            }

            if (e.event_type.includes('llm_request_start') && isOrch && currentOrchIteration && !currentOrchIteration.reason) {
                continue;
            }

            if (e.event_type.includes('llm_request_success') && isOrch && currentOrchIteration) {
                currentOrchIteration.reason = {
                    model: e.details?.model || e.llm_model || '',
                    duration: e.duration_ms,
                    msgCount: e.details?.message_count || 0,
                    toolCalls: e.details?.tool_call_count || 0,
                };
                continue;
            }

            if (e.event_type.includes('mcp_') && isOrch) {
                continue;
            }

            if (e.event_type.includes('tool_call_start') && isOrch) {
                const toolName = e.tool_name || '';
                const isDelegation = toolName.startsWith('delegate_to_');
                if (currentOrchIteration) {
                    currentOrchIteration.act = { tool: toolName, isDelegation, args: e.details?.tool_kwargs || e.details?.arguments };
                }
                if (isDelegation) {
                    currentAgent = null;
                    currentIteration = null;
                }
                continue;
            }

            if (e.event_type.includes('tool_call_success') && isOrch) continue;
            if (e.event_type.includes('delegation_complete') && isOrch) continue;

            if (e.event_type.includes('iteration_complete') && isOrch) {
                if (currentOrchIteration) {
                    tree.steps.push(currentOrchIteration);
                    currentOrchIteration = null;
                }
                continue;
            }

            if (e.event_type.includes('task_start') && !isOrch) {
                const agentInfo = AGENTS[e.agent_name] || { cls: 'orchestrator', label: e.agent_name, icon: '⚙️' };
                currentAgent = {
                    type: 'agent',
                    name: e.agent_name,
                    info: agentInfo,
                    iterations: [],
                    taskResult: null,
                    expandDefault: agentCardIndex === 0,
                };
                agentCardIndex++;
                currentIteration = null;
                continue;
            }

            if (e.event_type.includes('task_completion') && !isOrch && currentAgent) {
                const taskStatus = e.details?.task_result?.task_status || 'success';
                currentAgent.taskResult = e.details?.task_result?.task_summary || 'Completed';
                currentAgent.taskStatus = taskStatus;
                if (currentIteration) {
                    const completeType = taskStatus === 'failed' ? 'error' : 'complete';
                    currentIteration.steps.push({ type: completeType, text: currentAgent.taskResult, meta: { status: taskStatus, summary: currentAgent.taskResult } });
                    currentAgent.iterations.push(currentIteration);
                    currentIteration = null;
                }
                if (currentOrchIteration) {
                    currentOrchIteration.agentBlock = currentAgent;
                } else {
                    tree.steps.push({ reason: null, act: null, agentBlock: currentAgent });
                }
                currentAgent = null;
                continue;
            }

            if (e.event_type.includes('iteration_start') && !isOrch) {
                if (currentIteration && currentAgent) {
                    currentAgent.iterations.push(currentIteration);
                }
                const iterNum = e.summary.match(/iteration (\d+)/)?.[1] || '?';
                const iterMax = e.summary.match(/\/(\d+)/)?.[1] || '?';
                currentIteration = { num: iterNum, max: iterMax, steps: [] };
                if (currentAgent?._mcpConnect) {
                    currentIteration.steps.push(currentAgent._mcpConnect);
                    currentAgent._mcpConnect = null;
                }
                continue;
            }

            if (e.event_type.includes('iteration_complete') && !isOrch) continue;

            if (e.event_type.includes('llm_request_start') && !isOrch) continue;

            if (e.event_type.includes('llm_request_success') && !isOrch && currentIteration) {
                currentIteration.steps.push({
                    type: 'reason',
                    model: e.details?.model || e.llm_model || '',
                    duration: e.duration_ms,
                    msgCount: e.details?.message_count || 0,
                    meta: { model: e.details?.model || e.llm_model, messages: e.details?.message_count, duration: e.duration_ms ? fmtDur(e.duration_ms) : '', response_length: e.details?.response_length, tool_calls: e.details?.tool_call_count, roles: e.details?.message_roles },
                });
                continue;
            }

            if (e.event_type.includes('mcp_tools_discovered') && !isOrch) {
                const mcpServer = e.details?.mcp_server || '';
                const mcpToolCount = e.details?.tool_count || 0;
                const mcpTools = e.details?.tools || [];
                const mcpStep = {
                    type: 'mcp',
                    tool: `MCP connect: ${mcpServer}`,
                    dur: '',
                    meta: { server: mcpServer, tool_count: mcpToolCount, tools: mcpTools },
                };
                if (currentIteration) {
                    currentIteration.steps.push(mcpStep);
                } else if (currentAgent) {
                    currentAgent._mcpConnect = mcpStep;
                }
                continue;
            }

            if (e.event_type.includes('mcp_tool_call_start') && !isOrch && currentIteration) {
                currentIteration._pendingMcp = {
                    tool: e.details?.namespaced_tool_name || e.details?.tool_name || e.tool_name || '',
                    server: e.details?.mcp_server || '',
                    args: e.details?.tool_arguments,
                };
                continue;
            }

            if (e.event_type.includes('mcp_tool_call_success') && !isOrch && currentIteration) {
                const dur = (e.duration_ms || e.details?.duration_ms) ? fmtDur(e.duration_ms || e.details?.duration_ms) : '';
                const pending = currentIteration._pendingMcp || {};
                const toolOutput = e.details?.tool_output;
                currentIteration.steps.push({
                    type: 'mcp',
                    tool: pending.tool || e.details?.namespaced_tool_name || '',
                    dur,
                    meta: { tool: pending.tool, server: pending.server, duration: dur, input: pending.args, output: toolOutput },
                });
                currentIteration._pendingMcp = null;
                continue;
            }

            if (e.event_type.includes('mcp_tool_call_failure') && !isOrch && currentIteration) {
                const dur = (e.duration_ms || e.details?.duration_ms) ? fmtDur(e.duration_ms || e.details?.duration_ms) : '';
                const pending = currentIteration._pendingMcp || {};
                currentIteration.steps.push({
                    type: 'error',
                    text: `MCP failed: ${pending.tool || e.details?.namespaced_tool_name || ''}`,
                    meta: { tool: pending.tool, server: pending.server || e.details?.mcp_server, error: e.details?.error_message, duration: dur },
                });
                currentIteration._pendingMcp = null;
                continue;
            }

            if (e.event_type.includes('tool_call_start') && !isOrch && currentIteration) {
                currentIteration._pendingTool = {
                    tool: e.tool_name || '',
                    args: e.details?.tool_kwargs || e.details?.arguments,
                };
                continue;
            }

            if (e.event_type.includes('tool_call_success') && !isOrch && currentIteration) {
                const dur = e.duration_ms ? fmtDur(e.duration_ms) : '';
                const pending = currentIteration._pendingTool || {};
                const toolOutput = e.details?.tool_output;
                currentIteration.steps.push({
                    type: 'act',
                    tool: pending.tool || e.tool_name || '',
                    dur,
                    meta: { tool: pending.tool || e.tool_name, duration: dur, input: pending.args, output: toolOutput },
                });
                currentIteration._pendingTool = null;
                continue;
            }

            if ((e.event_type.includes('stall_detected') || e.event_type.includes('invalid_tool_call')) && currentIteration) {
                currentIteration.steps.push({
                    type: 'error',
                    text: e.summary || e.event_type,
                    meta: { event: e.event_type, detail: e.details?.attempted_tool || e.details?.consecutive_stalls || '' },
                });
                continue;
            }

            if (e.event_category === 'business' && currentIteration) {
                const d = e.details || {};
                currentIteration.steps.push({
                    type: 'decision',
                    summary: e.summary,
                    eventType: e.event_type,
                    meta: { event: e.event_type, company: d.company_name, risk: d.new_risk_level, trust: d.new_trust_level, reasoning: d.reasoning },
                });
                continue;
            }
        }

        const lastEvent = events[events.length - 1];
        if (lastEvent.event_type.includes('task_completion')) {
            tree.output = { summary: lastEvent.details?.task_result?.task_summary || 'Workflow completed', status: lastEvent.details?.task_result?.task_status || 'success' };
        } else {
            tree.output = { summary: 'Workflow completed', status: 'success' };
        }

        return tree;
    }

    function renderTraceTree(tree) {
        let html = '';

        html += `<div class="trace-node input">
            <span>📥</span>
            <span>${esc(tree.input.summary)}</span>
        </div>`;

        let stepNum = 0;

        for (let i = 0; i < tree.steps.length; i++) {
            const step = tree.steps[i];
            stepNum++;

            html += `<div class="trace-connector"><div class="trace-connector-line"></div></div>`;

            const reason = step.reason || { model: '', duration: 0, msgCount: 0 };
            const actLabel = step.act
                ? `${step.act.isDelegation ? '↗ ' : '🔧 '}${esc(step.act.tool)}`
                : 'Processing';

            html += `<div class="trace-orch-card">
                <div class="trace-card-title">Orchestrator · Step ${stepNum}</div>
                <div class="trace-card-body">
                    ${step.reason ? `<div class="trace-orch-row">
                        <span class="row-label reason">Reason</span>
                        <span class="row-content">🧠 ${esc(reason.model || 'LLM')} · ${fmtDur(reason.duration || 0)} · ${reason.msgCount} msgs</span>
                    </div>` : ''}
                    ${step.act ? `<div class="trace-orch-row">
                        <span class="row-label act">Act</span>
                        <span class="row-content">${actLabel}</span>
                    </div>` : ''}
                </div>
            </div>`;

            if (step.agentBlock) {
                const delegationTool = step.act ? step.act.tool : '';
                html += `<div class="trace-connector">
                    <div class="trace-connector-label">${esc(delegationTool)}</div>
                </div>`;
                html += renderAgentCard(step.agentBlock);
            }
        }

        html += `<div class="trace-connector"><div class="trace-connector-line"></div></div>`;

        const outShort = tree.output.summary.length > 100;
        const outFailed = tree.output.status === 'failed';
        html += `<div class="trace-node ${outFailed ? 'output-failed' : 'output'} trace-output-expandable">
            <span>${outFailed ? '❌' : '✅'}</span>
            <span class="trace-output-text">${esc(outShort ? tree.output.summary.substring(0, 100) + '…' : tree.output.summary)}</span>
        </div>`;
        if (outShort) {
            html += `<div class="trace-output-full hidden">
                <div class="detail-json" style="max-height:200px">${esc(tree.output.summary)}</div>
            </div>`;
        }

        return html;
    }

    function renderAgentCard(agent) {
        const info = agent.info;
        const iterCount = agent.iterations.length;
        const toolCount = agent.iterations.reduce((sum, it) => sum + it.steps.filter(s => s.type === 'act').length, 0);
        const mcpToolCount = agent.iterations.reduce((sum, it) => sum + it.steps.filter(s => s.type === 'mcp').length, 0);
        const collapsed = !agent.expandDefault;

        let iterHtml = agent.iterations.map((iter, idx) => {
            const stepsHtml = iter.steps.map((s, si) => {
                const metaAttr = s.meta ? `data-meta='${JSON.stringify(s.meta).replace(/'/g, "&#39;")}'` : '';
                const clickable = s.meta ? 'trace-step-clickable' : '';
                const prev = si > 0 ? iter.steps[si - 1] : null;
                const needsSep = prev && (prev.type === 'act' || prev.type === 'mcp' || prev.type === 'decision') && (s.type === 'decision' || s.type === 'complete' || s.type === 'error');
                const sep = needsSep ? '<span class="trace-step-plus">+</span>' : '';

                if (s.type === 'error') {
                    return `${sep}<span class="trace-step error ${clickable}" ${metaAttr}>
                        <span class="trace-step-dot"></span>
                        <span class="step-label">Error</span>
                    </span>`;
                }

                if (s.type === 'reason') {
                    return `<span class="trace-step reason ${clickable}" ${metaAttr}>
                        <span class="trace-step-dot"></span>
                        <span class="step-label">Reason</span>
                        <span class="step-detail">${fmtDur(s.duration || 0)}</span>
                    </span><span class="trace-step-arrow">→</span>`;
                }
                if (s.type === 'mcp') {
                    return `<span class="trace-step mcp ${clickable}" ${metaAttr}>
                        <span class="trace-step-dot"></span>
                        <span class="step-label">MCP</span>
                        <span class="step-detail">${esc(s.tool)}${s.dur ? ' · ' + s.dur : ''}</span>
                    </span>`;
                }
                if (s.type === 'act') {
                    return `<span class="trace-step act ${clickable}" ${metaAttr}>
                        <span class="trace-step-dot"></span>
                        <span class="step-label">Act</span>
                        <span class="step-detail">${esc(s.tool)}${s.dur ? ' · ' + s.dur : ''}</span>
                    </span>`;
                }
                if (s.type === 'decision') {
                    const shortSummary = s.summary.replace(/^Vendor\s+/i, '').replace(/^Notification\s+/i, '');
                    return `${sep}<span class="trace-step decision ${clickable}" ${metaAttr}>
                        <span class="trace-step-dot"></span>
                        <span class="step-label">Decision</span>
                    </span>`;
                }
                if (s.type === 'complete') {
                    return `${sep}<span class="trace-step complete ${clickable}" ${metaAttr}>
                        <span class="trace-step-dot"></span>
                        <span class="step-label">Done</span>
                    </span>`;
                }
                return '';
            }).join('');

            return `<div class="trace-iteration">
                <div class="trace-iter-label">Loop ${iter.num}/${iter.max}</div>
                <div class="trace-steps">${stepsHtml}</div>
            </div>`;
        }).join('');

        const isFailed = agent.taskStatus === 'failed';
        const hasErrors = agent.iterations.some(it => it.steps.some(s => s.type === 'error'));
        const statusBadge = isFailed
            ? '<span class="trace-status-badge failed">Failed</span>'
            : hasErrors
                ? '<span class="trace-status-badge warning">Errors</span>'
                : '';

        return `<div class="trace-agent-card ${info.cls} ${isFailed ? 'trace-failed' : ''}">
            <div class="trace-agent-header">
                <div class="flex items-center gap-2">
                    <span>${info.icon}</span>
                    <span class="text-sm font-semibold text-text-bright">${info.label}</span>
                    <span class="text-xs text-text-secondary">${iterCount} loops · ${toolCount} tools${mcpToolCount ? ` · ${mcpToolCount} MCP` : ''}</span>
                    ${statusBadge}
                </div>
                <span class="trace-collapse-arrow text-text-secondary text-xs">${collapsed ? '▸' : '▾'}</span>
            </div>
            <div class="trace-agent-body ${collapsed ? 'collapsed' : ''}">
                ${iterHtml}
            </div>
        </div>`;
    }

    // ==================== ACHIEVEMENT BADGES ====================

    function renderAchievementBadges(workflowId) {
        const items = allAchievements[workflowId];
        if (!items || items.length === 0) return '';

        return items.map(a => {
            if (a.kind === 'challenge') {
                const icon = a.status === 'completed' ? '🚩' : '🎯';
                const cls = a.status === 'completed' ? 'achievement-flag' : 'achievement-attempt';
                const label = a.status === 'completed' ? a.title : `${a.title}`;
                return `<span class="${cls}" title="${esc(a.title)} (${a.status})">${icon} ${esc(label)}</span>`;
            }
            return `<span class="achievement-badge" title="${esc(a.title)} (${a.points} pts)">🏅 ${esc(a.title)}</span>`;
        }).join('');
    }

    // ==================== SEGMENT TOOLTIP CLICK ====================

    let segDismissBound = false;

    function bindSegmentTooltips(container) {
        container.querySelectorAll('.lane-segment.active').forEach(seg => {
            seg.addEventListener('click', (ev) => {
                ev.stopPropagation();
                const wasOpen = seg.classList.contains('tooltip-open');
                document.querySelectorAll('.lane-segment.tooltip-open').forEach(s => s.classList.remove('tooltip-open'));
                if (!wasOpen) seg.classList.add('tooltip-open');
            });
        });

        if (!segDismissBound) {
            segDismissBound = true;
            document.addEventListener('click', () => {
                document.querySelectorAll('.lane-segment.tooltip-open').forEach(s => s.classList.remove('tooltip-open'));
            });
        }
    }

    // ==================== EXPAND CONTENT BUILDER ====================

    const BORING_KEYS = new Set([
        'namespace', 'user_id', 'session_id', 'event_type', 'event_subtype',
        'agent_name', 'workflow_id', 'timestamp', 'summary', 'vendor_id',
    ]);

    function getExpandContent(details) {
        if (!details || typeof details !== 'object') return null;

        const interesting = Object.keys(details).filter(k => !BORING_KEYS.has(k));
        if (interesting.length === 0) return null;

        const d = details;

        if (d.task_result) {
            return typeof d.task_result === 'string'
                ? d.task_result
                : JSON.stringify(d.task_result, null, 2);
        }
        if (d.reasoning) return d.reasoning;
        if (d.response_content) return d.response_content;

        if (d.request_dump || d.response_dump) {
            const parts = [];
            if (d.model) parts.push(`model: ${d.model}`);
            if (d.temperature !== undefined) parts.push(`temperature: ${d.temperature}`);
            if (d.message_count) parts.push(`messages: ${d.message_count}`);
            if (d.message_roles) parts.push(`roles: ${JSON.stringify(d.message_roles)}`);
            if (d.response_length) parts.push(`response_length: ${d.response_length}`);
            if (d.tool_call_count) parts.push(`tool_calls: ${d.tool_call_count}`);
            if (d.duration_ms) parts.push(`duration: ${fmtDur(d.duration_ms)}`);
            if (d.user_prompt) parts.push(`\ntask_prompt:\n${d.user_prompt}`);
            if (d.user_message) parts.push(`\nuser_message:\n${d.user_message}`);
            return parts.join('\n');
        }

        if (d.mcp_server) {
            const parts = [`mcp_server: ${d.mcp_server}`];
            if (d.tool_name) parts.push(`tool: ${d.tool_name}`);
            if (d.namespaced_tool_name) parts.push(`namespaced: ${d.namespaced_tool_name}`);
            if (d.tool_description) parts.push(`description: ${d.tool_description}`);
            if (d.tool_arguments && Object.keys(d.tool_arguments).length) {
                parts.push(`args: ${JSON.stringify(d.tool_arguments, null, 2)}`);
            }
            if (d.tool_output) parts.push(`\noutput:\n${d.tool_output}`);
            if (d.tools) parts.push(`tools: ${JSON.stringify(d.tools)}`);
            if (d.tool_count) parts.push(`tool_count: ${d.tool_count}`);
            if (d.error_message) parts.push(`error: ${d.error_message}`);
            if (d.duration_ms) parts.push(`duration: ${fmtDur(d.duration_ms)}`);
            return parts.join('\n');
        }

        if (d.tool_name) {
            const parts = [`tool: ${d.tool_name}`];
            if (d.tool_kwargs && Object.keys(d.tool_kwargs).length) {
                parts.push(`args: ${JSON.stringify(d.tool_kwargs, null, 2)}`);
            }
            if (d.arguments && Object.keys(d.arguments).length) {
                parts.push(`args: ${JSON.stringify(d.arguments, null, 2)}`);
            }
            if (d.duration_ms) parts.push(`duration: ${fmtDur(d.duration_ms)}`);
            if (d.llm_model) parts.push(`model: ${d.llm_model}`);
            if (d.user_prompt) parts.push(`\ntask_prompt:\n${d.user_prompt}`);
            return parts.join('\n');
        }

        if (d.user_message) return `user_message:\n${d.user_message}`;
        if (d.user_prompt) return `task_prompt:\n${d.user_prompt}`;

        const curated = {};
        for (const k of interesting) {
            const v = d[k];
            if (v !== null && v !== undefined && v !== '') curated[k] = v;
        }
        if (Object.keys(curated).length === 0) return null;
        return JSON.stringify(curated, null, 2);
    }

    // ==================== HELPERS ====================

    function getWorkflowAgents(events) {
        const seen = new Set();
        const ordered = [];
        for (const e of events) {
            if (e.agent_name && !seen.has(e.agent_name)) {
                seen.add(e.agent_name);
                ordered.push(e.agent_name);
            }
        }
        return ordered;
    }

    function getWorkflowTrigger(wf) {
        const first = wf.events[0];
        if (!first) return { title: wf.id, icon: '⚙️', action: 'Unknown' };

        if (first.event_type.includes('vendor.created')) {
            const name = first.details?.company_name || first.summary.replace('New vendor registered: ', '');
            return { title: `New Vendor: ${name}`, icon: '🏢', action: 'Vendor Registration' };
        }

        if (wf.id.includes('chat')) {
            const chatMsg = wf.events.find(e => e.event_type.includes('message_received'));
            const msg = chatMsg?.details?.user_message;
            const title = msg ? `"${msg.length > 60 ? msg.substring(0, 60) + '…' : msg}"` : 'Chat Conversation';
            return { title, icon: '💬', action: 'Chat Message' };
        }

        const taskCompletion = wf.events.find(e => e.event_type.includes('task_completion'));
        if (taskCompletion?.details?.task_result?.task_summary) {
            const s = taskCompletion.details.task_result.task_summary;
            return { title: s.length > 80 ? s.substring(0, 80) + '…' : s, icon: '🎯', action: 'Agent Task' };
        }

        return { title: first.summary, icon: '⚙️', action: 'System' };
    }

    function getWorkflowStatus(events) {
        const last = events[events.length - 1];
        if (last?.event_type.includes('task_completion')) {
            const status = last.details?.task_result?.task_status;
            if (status === 'success') return { cls: 'success', label: 'Completed' };
            if (status === 'failed') return { cls: 'failed', label: 'Failed' };
        }
        if (last?.event_type.includes('response_complete')) return { cls: 'success', label: 'Completed' };
        return { cls: 'success', label: 'Completed' };
    }

    function getVendorName(events) {
        for (const e of events) {
            if (e.details?.company_name) return e.details.company_name;
        }
        return null;
    }

    function computeDuration(events) {
        if (events.length < 2) return 0;
        return parseTS(events[events.length - 1].timestamp).getTime() - parseTS(events[0].timestamp).getTime();
    }

    function condenseSummary(e) {
        return e.summary.replace(/^Agent /, '');
    }

    function shortWfId(id) {
        if (!id || id.length <= 16) return id;
        return id.substring(0, 16) + '…';
    }

    function shortToolName(name) {
        if (name.length <= 12) return name;
        return name.replace('delegate_to_', '→ ').replace('get_', '').replace('update_', '↑ ');
    }

    function shortArgs(args) {
        if (!args || typeof args !== 'object') return '';
        const entries = Object.entries(args);
        if (entries.length === 0) return '';
        const parts = entries.slice(0, 2).map(([k, v]) => {
            const val = typeof v === 'string' ? (v.length > 20 ? v.substring(0, 20) + '…' : v) : v;
            return `${k}: ${val}`;
        });
        if (entries.length > 2) parts.push('…');
        return parts.join(', ');
    }

    function fmtDur(ms) {
        if (ms < 1) return '<1ms';
        if (ms < 1000) return `${Math.round(ms)}ms`;
        if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
        return `${(ms / 60000).toFixed(1)}m`;
    }

    function fmtTime(ts) {
        return parseTS(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function relTime(ts) {
        const d = parseTS(ts);
        const diff = Date.now() - d.getTime();
        if (diff < 60000) return 'just now';
        if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
        if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }

    function parseTS(ts) {
        if (!ts) return new Date();
        const s = String(ts);
        if (!s.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(s)) return new Date(s + 'Z');
        return new Date(s);
    }

    function esc(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }
})();
