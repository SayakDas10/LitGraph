let csrfToken = '';

async function apiRequest(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = new Headers(options.headers || {});
    if (method !== 'GET' && method !== 'HEAD') headers.set('X-LitGraph-CSRF', csrfToken);
    const response = await fetch(url, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.error) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
}

function showError(error, fallback = 'The operation could not be completed.') {
    console.error(error);
    alert(error instanceof Error ? error.message : fallback);
}

// --- Sidebar Visibility Logic ---
window.toggleSidebar = function () {
    const sidebar = document.getElementById('sidebar');
    const openBtn = document.getElementById('openSidebarBtn');

    sidebar.classList.toggle('hidden');
    openBtn.classList.toggle('visible');
    document.body.classList.toggle('sidebar-hidden', sidebar.classList.contains('hidden'));
    localStorage.setItem('litgraph-sidebar-hidden', sidebar.classList.contains('hidden') ? '1' : '0');
    setTimeout(updateGraphViewport, 320);
};

function updateGraphViewport() {
    const sidebar = document.getElementById('sidebar');
    const hidden = sidebar.classList.contains('hidden') || document.body.classList.contains('graph-focus');
    const offset = hidden ? 0 : sidebar.getBoundingClientRect().width + 48;
    const graph = document.getElementById('cy');
    graph.style.left = `${offset}px`;
    graph.style.width = `calc(100% - ${offset}px)`;
    const toolbar = document.getElementById('graphToolbar');
    toolbar.style.left = `calc(50% + ${offset / 2}px)`;
    toolbar.style.maxWidth = `${Math.max(window.innerWidth - offset - 72, 280)}px`;
    window.cy?.resize();
}

// --- Theme Engine Logic ---
const themeSelect = document.getElementById('themeSelect');

const savedTheme = localStorage.getItem('litgraph-theme') || 'default-dark';
document.body.setAttribute('data-theme', savedTheme);
themeSelect.value = savedTheme;

const getCSSVar = (varName) => getComputedStyle(document.body).getPropertyValue(varName).trim();

themeSelect.addEventListener('change', (e) => {
    const newTheme = e.target.value;
    document.body.setAttribute('data-theme', newTheme);
    localStorage.setItem('litgraph-theme', newTheme);

    if (window.cy) {
        setTimeout(() => window.cy.style().fromJson(getDynamicStyleSheet()).update(), 50);
    }
});

const getDynamicStyleSheet = () => {
    const nodeColor = getCSSVar('--context-bg') || '#ffffff';
    const edgeColor = getCSSVar('--border-color') || '#cbd5e1';
    const labelColor = getCSSVar('--text-main') || '#0f172a';
    const highlightColor = getCSSVar('--highlight') || '#6366f1';
    const bgMain = getCSSVar('--bg-main') || '#000000';

    return [
        { selector: 'node', style: { 'shape': 'round-rectangle', 'background-color': nodeColor, 'label': 'data(short_label)', 'color': labelColor, 'font-size': '13px', 'font-family': 'Inter, sans-serif', 'font-weight': 'bold', 'text-valign': 'center', 'text-halign': 'center', 'text-wrap': 'wrap', 'text-max-width': '160px', 'padding': '14px', 'width': '180px', 'height': '60px', 'border-width': 2, 'border-color': edgeColor, 'z-index': 10, 'transition-property': 'background-color, border-color, color', 'transition-duration': '0.3s' } },
        { selector: 'node[evidence_count > 0]', style: { 'border-width': 5 } },
        { selector: 'node[?has_notes]', style: { 'border-style': 'double' } },
        { selector: 'node[status = "read"]', style: { 'background-color': '#22c55e', 'border-color': '#16a34a', 'color': '#ffffff' } },
        { selector: 'node[status = "prioritize"]', style: { 'background-color': '#eab308', 'border-color': '#ca8a04', 'color': '#0f172a' } },
        { selector: 'edge', style: { 'width': 2.5, 'line-color': edgeColor, 'target-arrow-color': edgeColor, 'target-arrow-shape': 'none', 'curve-style': 'bezier', 'opacity': 0.65, 'label': 'data(marker)', 'font-size': '11px', 'font-family': 'Inter, sans-serif', 'font-weight': 'bold', 'text-background-opacity': 1, 'text-background-color': bgMain, 'color': highlightColor, 'text-border-color': edgeColor, 'text-border-width': 1, 'text-border-opacity': 0.5, 'text-background-shape': 'roundrectangle', 'text-background-padding': '4px', 'text-opacity': 0.8, 'transition-property': 'line-color, target-arrow-color, width, opacity, text-opacity', 'transition-duration': '0.3s' } },
        { selector: '.highlighted-node', style: { 'background-color': highlightColor, 'color': bgMain, 'border-color': highlightColor, 'z-index': 999 } },
        { selector: '.highlighted-edge', style: { 'line-color': highlightColor, 'target-arrow-color': highlightColor, 'target-arrow-shape': 'triangle', 'width': 4, 'opacity': 1, 'color': highlightColor, 'text-border-color': highlightColor, 'text-opacity': 1, 'z-index': 990 } },
        { selector: 'node.zoom-far', style: { 'label': '', 'width': 20, 'height': 20, 'padding': 2, 'border-width': 1 } },
        { selector: 'edge.zoom-far', style: { 'label': '', 'target-arrow-shape': 'none', 'width': 1, 'curve-style': 'straight' } },
        { selector: 'node.zoom-near', style: { 'label': 'data(label)', 'text-max-width': '260px', 'width': '260px', 'height': '80px' } },
        { selector: 'edge.labels-hidden', style: { 'label': '' } },
        { selector: '.faded', style: { 'opacity': 0.05 } },
        { selector: '.filtered, .user-hidden', style: { 'display': 'none' } },
        { selector: 'node.pinned', style: { 'border-color': highlightColor, 'border-style': 'double' } }
    ];
};

// --- Core App Variables ---
window.cy = null;
let currentFolder = 'global';
let currentNodeData = null;
let evidenceSchemas = [];
let currentEvidenceData = null;
let activeSyncJob = null;
let graphEventsBound = false;
let graphLabelsVisible = true;
let graphEdgesVisible = true;
let neighborhoodRoot = null;
const hiddenNodeIds = new Set();
const pinnedNodeIds = new Set();
const comparisonNodeIds = new Set();
const savedGraphPositions = JSON.parse(localStorage.getItem('litgraph-positions') || '{}');

// --- Folders & Modals Logic ---
function loadFolders() {
    apiRequest('/api/folders')
        .then(folders => {
            const tree = document.getElementById('folderTree');
            tree.innerHTML = '';
            folders.forEach(f => {
                const div = document.createElement('div');
                div.className = `folder-item ${f.id === currentFolder ? 'active' : ''}`;
                const icon = document.createElement('i');
                icon.className = `fas ${f.id === 'global' ? 'fa-globe' : 'fa-folder'}`;
                div.append(icon, document.createTextNode(` ${f.name}`));
                div.onclick = () => {
                    currentFolder = f.id;
                    loadFolders();
                    checkAndLoadGraph(f.path);
                };
                tree.appendChild(div);
            });
            loadProjectTemplates();
        }).catch(showError);
}

function openLocalModal() {
    apiRequest('/api/folders').then(folders => {
        const select = document.getElementById('localFolderSelect');
        select.innerHTML = '';
        folders.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f.id;
            opt.innerText = f.name;
            if (f.id === currentFolder) opt.selected = true;
            select.appendChild(opt);
        });
        document.getElementById('localFileModal').style.display = 'flex';
    }).catch(showError);
}
window.closeLocalModal = function () { document.getElementById('localFileModal').style.display = 'none'; };

window.submitLocalPaper = function () {
    const path = document.getElementById('localFilePath').value;
    const folder = document.getElementById('localFolderSelect').value;
    const newFolder = document.getElementById('localNewFolder').value;
    const action = document.querySelector('input[name="fileAction"]:checked').value;

    if (!path) { alert('Please provide the absolute path to the PDF.'); return; }

    const btn = document.getElementById('submitLocalBtn');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    btn.disabled = true;

    apiRequest('/api/add_local_paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_path: path, folder_select: folder, new_folder: newFolder, action: action })
    }).then(data => {
        btn.innerHTML = 'Add Paper';
        btn.disabled = false;

        closeLocalModal();
        document.getElementById('localFilePath').value = '';
        document.getElementById('localNewFolder').value = '';
        loadFolders();
        checkAndLoadGraph(newFolder ? newFolder : (folder === 'global' ? '' : folder));
    }).catch(err => {
        btn.innerHTML = 'Add Paper';
        btn.disabled = false;
        showError(err);
    });
};

window.openImportModal = function () { document.getElementById('importLibraryModal').style.display = 'flex'; };
window.closeImportModal = function () { document.getElementById('importLibraryModal').style.display = 'none'; };

window.submitImportLibrary = function () {
    const path = document.getElementById('importFolderPath').value;
    const action = document.querySelector('input[name="importAction"]:checked').value;

    if (!path) { alert('Please provide the absolute path to the folder.'); return; }

    const btn = document.getElementById('submitImportBtn');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    btn.disabled = true;

    apiRequest('/api/import_library', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_path: path, action: action })
    }).then(data => {
        btn.innerHTML = 'Import Library';
        btn.disabled = false;

        alert(`Imported ${data.count} PDFs; skipped ${data.skipped} existing files.`);
        closeImportModal();
        document.getElementById('importFolderPath').value = '';
        loadFolders();
        checkAndLoadGraph('global');
    }).catch(err => {
        btn.innerHTML = 'Import Library';
        btn.disabled = false;
        showError(err);
    });
};

function checkAndLoadGraph(folderPath = '') {
    apiRequest('/api/check_updates')
        .then(data => {
            if (data.needs_update) {
                document.getElementById('syncOverlay').style.display = 'flex';
                apiRequest('/api/build_cache', { method: 'POST' })
                    .then(result => {
                        activeSyncJob = result.job_id;
                        pollSyncJob(result.job_id, folderPath);
                    }).catch(error => {
                        document.getElementById('syncOverlay').style.display = 'none';
                        showError(error);
                    });
            } else {
                renderGraph(folderPath);
            }
        }).catch(showError);
}

async function pollSyncJob(jobId, folderPath) {
    try {
        const job = await apiRequest(`/api/sync_status/${encodeURIComponent(jobId)}`);
        if (activeSyncJob !== jobId) return;
        const progress = document.getElementById('syncProgress');
        progress.max = Math.max(job.total || 1, 1);
        progress.value = job.processed || 0;
        document.getElementById('syncSubtitle').textContent = job.current
            ? `${job.processed}/${job.total} · ${job.current}`
            : `${job.processed}/${job.total} papers processed`;
        if (['queued', 'running'].includes(job.status)) {
            setTimeout(() => pollSyncJob(jobId, folderPath), 450);
            return;
        }
        activeSyncJob = null;
        document.getElementById('syncOverlay').style.display = 'none';
        if (job.status === 'failed') throw new Error(job.errors?.[0]?.error || 'Synchronization failed');
        if (job.status === 'cancelled') return;
        if (job.errors?.length) alert(`Some PDFs could not be processed:\n${job.errors.map(error => error.path).join('\n')}`);
        renderGraph(folderPath);
    } catch (error) {
        activeSyncJob = null;
        document.getElementById('syncOverlay').style.display = 'none';
        showError(error);
    }
}

async function cancelSynchronization() {
    if (!activeSyncJob) return;
    try {
        await apiRequest(`/api/sync_status/${encodeURIComponent(activeSyncJob)}/cancel`, { method: 'POST' });
    } catch (error) { showError(error); }
}

function renderGraph(folderPath = '') {
    let url = '/api/graph';
    if (folderPath && folderPath !== 'global') {
        url += '?folder=' + encodeURIComponent(folderPath);
    }

    return apiRequest(url).then(data => {
        const incomingIds = new Set(data.map(element => element.data.id));
        if (!window.cy) {
            const hasSavedPositions = data.some(element => element.group === 'nodes' && savedGraphPositions[element.data.id]);
            window.cy = cytoscape({
                container: document.getElementById('cy'), elements: data, style: getDynamicStyleSheet(),
                layout: hasSavedPositions ? {
                    name: 'preset', positions: node => savedGraphPositions[node.id()] || { x: Math.random() * 600, y: Math.random() * 500 }, padding: 90
                } : graphLayoutOptions('cose'),
                minZoom: 0.08, maxZoom: 3.5,
                pixelRatio: data.length > 800 ? 1 : 'auto',
                hideEdgesOnViewport: data.length > 1200
            });
            bindGraphEvents();
        } else {
            window.cy.batch(() => {
                window.cy.elements().filter(element => !incomingIds.has(element.id())).remove();
                data.forEach(element => {
                    const existing = window.cy.getElementById(element.data.id);
                    if (existing.length) existing.data(element.data);
                    else {
                        const added = window.cy.add(element);
                        const position = savedGraphPositions[element.data.id];
                        if (position && added.isNode()) added.position(position);
                    }
                });
            });
            window.cy.style().fromJson(getDynamicStyleSheet()).update();
        }
        window.cy.nodes().forEach(node => {
            if (hiddenNodeIds.has(node.id())) node.addClass('user-hidden');
            if (pinnedNodeIds.has(node.id())) { node.addClass('pinned'); node.lock(); }
        });
        applyGraphFilters();
        applySemanticZoom();
        document.getElementById('graphEmptyState').hidden = window.cy.nodes(':visible').length > 0;
        if (window.cy.nodes(':visible').length && !Object.keys(savedGraphPositions).length) window.cy.fit(window.cy.elements(':visible'), 90);
    }).catch(showError);
}

function graphLayoutOptions(name) {
    if (name === 'cose') return {
        name: 'cose', padding: 90, nodeDimensionsIncludeLabels: true, nodeOverlap: 30,
        randomize: true, idealEdgeLength: 150, nodeRepulsion: 280000, gravity: 1,
        numIter: 1100, edgeElasticity: 80, animate: 'end'
    };
    if (name === 'breadthfirst') return {
        name, directed: true, spacingFactor: 1.4, padding: 90, animate: true,
        roots: neighborhoodRoot && window.cy ? window.cy.getElementById(neighborhoodRoot) : undefined
    };
    return { name, padding: 90, spacingFactor: 1.25, animate: true };
}

function bindGraphEvents() {
    if (graphEventsBound) return;
    graphEventsBound = true;
    window.cy.on('mouseover', 'node', event => {
        const node = event.target;
        window.cy.elements(':visible').addClass('faded');
        node.removeClass('faded').addClass('highlighted-node');
        node.connectedEdges(':visible').removeClass('faded').addClass('highlighted-edge');
        node.connectedEdges(':visible').connectedNodes().removeClass('faded').addClass('highlighted-node');
    });
    window.cy.on('mouseout', 'node, edge', () => window.cy.elements().removeClass('faded highlighted-node highlighted-edge'));
    window.cy.on('mouseover', 'edge', event => {
        const edge = event.target;
        window.cy.elements(':visible').addClass('faded');
        edge.removeClass('faded').addClass('highlighted-edge');
        edge.connectedNodes().removeClass('faded').addClass('highlighted-node');
    });
    window.cy.on('tap', 'node', event => {
        neighborhoodRoot = event.target.id();
        showNodePanel(event.target);
        applyGraphFilters();
    });
    window.cy.on('tap', 'edge', event => showEdgePanel(event.target));
    window.cy.on('tap', event => {
        hideGraphContextMenu();
        if (event.target === window.cy && document.getElementById('neighborhoodDepth').value !== 'all') {
            neighborhoodRoot = null;
            applyGraphFilters();
        }
    });
    window.cy.on('cxttap', 'node', event => showGraphContextMenu(event.target, event));
    window.cy.on('zoom', applySemanticZoom);
    window.cy.on('dragfree', 'node', event => saveNodePosition(event.target));
    window.cy.on('layoutstop', () => window.cy.nodes().forEach(saveNodePosition));
}

function saveNodePosition(node) {
    savedGraphPositions[node.id()] = node.position();
    localStorage.setItem('litgraph-positions', JSON.stringify(savedGraphPositions));
}

function applySemanticZoom() {
    if (!window.cy) return;
    const zoom = window.cy.zoom();
    window.cy.batch(() => {
        window.cy.nodes().removeClass('zoom-far zoom-near');
        window.cy.edges().removeClass('zoom-far');
        if (zoom < 0.38) window.cy.elements().addClass('zoom-far');
        else if (zoom > 1.35) window.cy.nodes().addClass('zoom-near');
        window.cy.edges().toggleClass('labels-hidden', !graphLabelsVisible || zoom < 0.72);
    });
}

function applyGraphFilters() {
    if (!window.cy) return;
    const status = document.getElementById('statusFilter').value;
    const depth = document.getElementById('neighborhoodDepth').value;
    window.cy.batch(() => {
        window.cy.elements().removeClass('filtered');
        if (status !== 'all') window.cy.nodes().filter(node => node.data('status') !== status).addClass('filtered');
        if (depth !== 'all' && neighborhoodRoot && window.cy.getElementById(neighborhoodRoot).length) {
            let visible = window.cy.getElementById(neighborhoodRoot);
            let frontier = visible;
            for (let hop = 0; hop < Number(depth); hop += 1) {
                frontier = frontier.neighborhood();
                visible = visible.union(frontier);
            }
            window.cy.elements().difference(visible).addClass('filtered');
        }
        window.cy.edges().toggleClass('filtered', !graphEdgesVisible);
    });
    document.getElementById('graphEmptyState').hidden = window.cy.nodes(':visible').length > 0;
}

function resetGraphView() {
    hiddenNodeIds.clear();
    neighborhoodRoot = null;
    document.getElementById('statusFilter').value = 'all';
    document.getElementById('neighborhoodDepth').value = 'all';
    window.cy?.nodes().removeClass('user-hidden');
    applyGraphFilters();
    window.cy?.fit(window.cy.elements(':visible'), 90);
}

function runSelectedLayout() {
    if (!window.cy) return;
    const visible = window.cy.elements(':visible');
    if (!visible.length) return;
    visible.layout(graphLayoutOptions(document.getElementById('layoutSelect').value)).run();
}

let contextMenuNode = null;
function showGraphContextMenu(node, event) {
    contextMenuNode = node;
    const menu = document.getElementById('graphContextMenu');
    const rect = document.getElementById('cy').getBoundingClientRect();
    menu.style.left = `${Math.min(rect.left + event.renderedPosition.x, window.innerWidth - 210)}px`;
    menu.style.top = `${Math.min(rect.top + event.renderedPosition.y, window.innerHeight - 260)}px`;
    menu.hidden = false;
}

function hideGraphContextMenu() {
    document.getElementById('graphContextMenu').hidden = true;
    contextMenuNode = null;
}

function handleGraphContextAction(action) {
    const node = contextMenuNode;
    if (!node) return;
    if (action === 'open') window.open('/papers/' + encodeURIComponent(node.id()), '_blank', 'noopener');
    if (action === 'neighbors') {
        neighborhoodRoot = node.id();
        document.getElementById('neighborhoodDepth').value = '1';
        applyGraphFilters();
        window.cy.fit(window.cy.elements(':visible'), 100);
    }
    if (action === 'pin') {
        if (node.locked()) { node.unlock(); node.removeClass('pinned'); pinnedNodeIds.delete(node.id()); }
        else { node.lock(); node.addClass('pinned'); pinnedNodeIds.add(node.id()); }
    }
    if (action === 'compare') addNodeToComparison(node);
    if (action === 'prioritize') toggleNodeStatus(node, 'prioritize');
    if (action === 'hide') { hiddenNodeIds.add(node.id()); node.addClass('user-hidden'); applyGraphFilters(); }
    hideGraphContextMenu();
}

function toggleGraphFocus() {
    document.body.classList.toggle('graph-focus');
    document.getElementById('graphFocusBtn').classList.toggle('active', document.body.classList.contains('graph-focus'));
    setTimeout(updateGraphViewport, 320);
}

function exportGraphImage() {
    if (!window.cy) return;
    const link = document.createElement('a');
    link.download = `litgraph-${new Date().toISOString().slice(0, 10)}.png`;
    link.href = window.cy.png({ full: true, scale: 2, bg: getCSSVar('--bg-main') });
    link.click();
}

function configureResizeHandle(handleId, panelId, fromRight) {
    const handle = document.getElementById(handleId);
    const panel = document.getElementById(panelId);
    const storageKey = `litgraph-${panelId}-width`;
    const savedWidth = Number(localStorage.getItem(storageKey));
    if (savedWidth) panel.style.width = `${savedWidth}px`;
    handle.addEventListener('pointerdown', event => {
        event.preventDefault();
        handle.setPointerCapture(event.pointerId);
        const move = moveEvent => {
            const width = fromRight ? window.innerWidth - moveEvent.clientX - 24 : moveEvent.clientX - 24;
            const bounded = Math.max(320, Math.min(width, window.innerWidth * 0.65));
            panel.style.width = `${bounded}px`;
            localStorage.setItem(storageKey, String(Math.round(bounded)));
            updateGraphViewport();
        };
        handle.addEventListener('pointermove', move);
        handle.addEventListener('pointerup', () => handle.removeEventListener('pointermove', move), { once: true });
    });
}

async function addNodeToComparison(node) {
    comparisonNodeIds.add(node.id());
    await renderComparison();
}

async function renderComparison() {
    const drawer = document.getElementById('comparisonDrawer');
    if (!comparisonNodeIds.size) { drawer.classList.remove('active'); return; }
    try {
        const nodes = Array.from(comparisonNodeIds).map(id => window.cy.getElementById(id)).filter(node => node.length);
        const evidence = await Promise.all(nodes.map(node => apiRequest(`/api/evidence/${encodeURIComponent(node.data('uuid'))}`)));
        const populatedFields = new Map();
        evidence.forEach(item => Object.values(item.values).forEach(value => {
            const field = item.schemas.flatMap(schema => schema.fields).find(candidate => candidate.id === value.field_id);
            if (field) populatedFields.set(field.id, field.label);
        }));
        const table = document.createElement('table');
        table.className = 'comparison-table';
        const head = document.createElement('tr');
        head.append(document.createElement('th'));
        nodes.forEach(node => { const cell = document.createElement('th'); cell.textContent = node.data('short_label'); head.append(cell); });
        table.append(head);
        const statusRow = document.createElement('tr');
        const statusLabel = document.createElement('th'); statusLabel.textContent = 'Status'; statusRow.append(statusLabel);
        nodes.forEach(node => { const cell = document.createElement('td'); cell.textContent = node.data('status'); statusRow.append(cell); });
        table.append(statusRow);
        populatedFields.forEach((label, fieldId) => {
            const row = document.createElement('tr');
            const labelCell = document.createElement('th'); labelCell.textContent = label; row.append(labelCell);
            evidence.forEach(item => {
                const cell = document.createElement('td');
                const value = item.values[fieldId]?.value;
                cell.textContent = value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);
                row.append(cell);
            });
            table.append(row);
        });
        document.getElementById('comparisonContent').replaceChildren(table);
        drawer.classList.add('active');
    } catch (error) { showError(error); }
}

function clearComparison() {
    comparisonNodeIds.clear();
    document.getElementById('comparisonDrawer').classList.remove('active');
    document.getElementById('comparisonContent').replaceChildren();
}

let keyboardNodeIndex = -1;
function navigateGraphByKeyboard(event) {
    if (!window.cy || !['ArrowLeft', 'ArrowRight', 'Enter'].includes(event.key)) return;
    const nodes = window.cy.nodes(':visible');
    if (!nodes.length) return;
    event.preventDefault();
    if (event.key === 'Enter' && keyboardNodeIndex >= 0) return showNodePanel(nodes[keyboardNodeIndex]);
    keyboardNodeIndex = (keyboardNodeIndex + (event.key === 'ArrowRight' ? 1 : -1) + nodes.length) % nodes.length;
    window.cy.nodes().removeClass('highlighted-node');
    const node = nodes[keyboardNodeIndex];
    node.addClass('highlighted-node');
    window.cy.animate({ center: { eles: node }, duration: 180 });
}

// --- View Switching Logic ---
function showNodePanel(node) {
    currentNodeData = node;
    const uuid = node.data('uuid');

    document.getElementById('edge-view').style.display = 'none';
    document.getElementById('node-view').style.display = 'flex';
    document.getElementById('panelTitle').innerText = node.data('label');

    document.getElementById('btnOpenPdf').onclick = () => window.open('/papers/' + encodeURIComponent(node.id()), '_blank');

    document.getElementById('btnEditTitle').onclick = () => {
        const newTitle = prompt("Enter a new title for this paper:", node.data('label'));
        if (newTitle && newTitle.trim() !== "" && newTitle !== node.data('label')) {
            apiRequest('/api/update_title', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: node.id(), title: newTitle.trim() })
            }).then(() => {
                node.data('label', newTitle.trim());
                document.getElementById('panelTitle').innerText = newTitle.trim();
            }).catch(showError);
        }
    };

    const btnRead = document.getElementById('btnMarkRead');
    btnRead.className = 'action-btn ' + (node.data('status') === 'read' ? 'active-read' : '');
    btnRead.onclick = () => toggleNodeStatus(node, 'read');

    const btnPrioritize = document.getElementById('btnMarkPrioritize');
    btnPrioritize.className = 'action-btn ' + (node.data('status') === 'prioritize' ? 'active-prioritize' : '');
    btnPrioritize.onclick = () => toggleNodeStatus(node, 'prioritize');

    // Delete Logic
    document.getElementById('btnDeletePaper').onclick = () => {
        if (confirm("Are you sure you want to completely delete this paper, along with all its notes and attachments? This cannot be undone.")) {
            apiRequest('/api/delete_paper', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: node.id() })
            }).then(() => {
                closeCitationPanel();
                loadFolders();
                checkAndLoadGraph(currentFolder === 'global' ? '' : currentFolder);
            }).catch(showError);
        }
    };

    document.getElementById('nodeTextNote').value = "Loading notes...";
    document.getElementById('attachmentList').innerHTML = "";

    apiRequest('/api/node_details/' + encodeURIComponent(uuid))
        .then(data => {
            document.getElementById('nodeTextNote').value = data.text;
            renderAttachments(data.attachments);
        }).catch(showError);
    loadPaperEvidence(uuid);

    document.getElementById('citation-panel').classList.add('active');
}

function showEdgePanel(edge) {
    currentNodeData = null;
    document.getElementById('node-view').style.display = 'none';
    document.getElementById('edge-view').style.display = 'block';
    document.getElementById('panelTitle').innerText = "Citation Context";

    var sourceLabel = window.cy.getElementById(edge.data('source')).data('label');
    var targetLabel = window.cy.getElementById(edge.data('target')).data('label');
    const view = document.getElementById('edge-view');
    view.replaceChildren();
    const heading = document.createElement('h3');
    heading.className = 'edge-heading';
    heading.append(document.createTextNode(sourceLabel), document.createElement('br'));
    const arrow = document.createElement('i');
    arrow.className = 'fas fa-arrow-down edge-arrow';
    heading.append(arrow, document.createElement('br'), document.createTextNode(targetLabel));
    if (edge.data('marker')) {
        const marker = document.createElement('span');
        marker.className = 'edge-marker';
        marker.textContent = edge.data('marker').match(/^\d+$/) ? ` [${edge.data('marker')}]` : ` (${edge.data('marker')})`;
        heading.append(marker);
    }
    view.append(heading);

    const metadata = document.createElement('div');
    metadata.className = 'edge-metadata';
    metadata.textContent = `Confidence: ${Math.round((edge.data('confidence') || 0) * 100)}% · ${edge.data('method')}`;
    view.append(metadata);

    if (edge.data('bibliography')) appendContextBox(view, 'Bibliography match', edge.data('bibliography'));
    (edge.data('contexts') || []).forEach(context => appendContextBox(view, 'In-text citation', context));
    document.getElementById('citation-panel').classList.add('active');
}

function appendContextBox(parent, label, text) {
    const box = document.createElement('div');
    box.className = 'context-box';
    const title = document.createElement('strong');
    title.textContent = label;
    const content = document.createElement('p');
    content.textContent = text;
    box.append(title, content);
    parent.append(box);
}

// --- Note Saving Logic ---
document.getElementById('btnSaveNote').onclick = () => {
    if (!currentNodeData) return;
    const text = document.getElementById('nodeTextNote').value;
    const btn = document.getElementById('btnSaveNote');
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

    apiRequest('/api/save_note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uuid: currentNodeData.data('uuid'), text: text })
    }).then(() => {
        btn.innerHTML = '<i class="fas fa-check"></i> Saved!';
        setTimeout(() => btn.innerHTML = originalHTML, 2000);
    }).catch(error => {
        btn.innerHTML = originalHTML;
        showError(error);
    });
};

// --- Drag & Drop Upload Logic ---
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) uploadAttachment(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => {
    if (fileInput.files.length) uploadAttachment(fileInput.files[0]);
});

function uploadAttachment(file) {
    if (!currentNodeData) return;
    const formData = new FormData();
    formData.append('file', file);
    formData.append('uuid', currentNodeData.data('uuid'));

    dropZone.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';

    apiRequest('/api/upload_attachment', { method: 'POST', body: formData })
        .then(data => {
            dropZone.innerHTML = '<i class="fas fa-cloud-upload-alt" style="font-size: 1.5rem; margin-bottom: 8px; display: block;"></i> Drag & Drop or click to attach<br><small style="opacity:0.7">ppt, docx, txt, pdf, md</small>';
            if (data.success) {
                apiRequest('/api/node_details/' + encodeURIComponent(currentNodeData.data('uuid')))
                    .then(d => renderAttachments(d.attachments));
            }
        }).catch(error => {
            dropZone.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> Drag & Drop or click to attach';
            showError(error);
        });
}

function renderAttachments(attachments) {
    const list = document.getElementById('attachmentList');
    list.replaceChildren();
    attachments.forEach(att => {
        const item = document.createElement('div');
        item.className = 'attachment-item';
        const icon = document.createElement('i');
        icon.className = 'fas fa-paperclip';
        const link = document.createElement('a');
        link.href = `/notes/${encodeURIComponent(att.filename)}`;
        link.target = '_blank';
        link.rel = 'noopener';
        link.title = att.original_name;
        link.textContent = att.original_name;
        item.append(icon, link);
        list.append(item);
    });
}

function toggleNodeStatus(node, targetType) {
    const oldStatus = node.data('status');
    let newStatus = (node.data('status') === targetType) ? 'none' : targetType;
    node.data('status', newStatus);

    document.getElementById('btnMarkRead').className = 'action-btn ' + (newStatus === 'read' ? 'active-read' : '');
    document.getElementById('btnMarkPrioritize').className = 'action-btn ' + (newStatus === 'prioritize' ? 'active-prioritize' : '');

    apiRequest('/api/update_status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: node.id(), status: newStatus })
    }).catch(error => {
        node.data('status', oldStatus);
        document.getElementById('btnMarkRead').className = 'action-btn ' + (oldStatus === 'read' ? 'active-read' : '');
        document.getElementById('btnMarkPrioritize').className = 'action-btn ' + (oldStatus === 'prioritize' ? 'active-prioritize' : '');
        showError(error);
    });
}

window.closeCitationPanel = function () { document.getElementById('citation-panel').classList.remove('active'); };

// --- Evidence Templates ---
function folderApiValue() {
    return currentFolder === 'global' ? '' : currentFolder;
}

async function loadProjectTemplates() {
    try {
        const data = await apiRequest(`/api/evidence/projects?folder=${encodeURIComponent(folderApiValue())}`);
        evidenceSchemas = data.schemas;
        const active = new Set(data.schema_ids);
        const select = document.getElementById('projectTemplateSelect');
        select.replaceChildren();
        data.schemas.filter(schema => !active.has(schema.id)).forEach(schema => {
            const option = document.createElement('option');
            option.value = schema.id;
            option.textContent = schema.name;
            select.append(option);
        });
        const list = document.getElementById('projectTemplateList');
        list.replaceChildren();
        data.schemas.filter(schema => active.has(schema.id)).forEach(schema => {
            const chip = document.createElement('span');
            chip.className = 'template-chip';
            chip.append(document.createTextNode(schema.name));
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.title = 'Remove from this project';
            remove.setAttribute('aria-label', `Remove ${schema.name}`);
            remove.textContent = '×';
            remove.addEventListener('click', () => setProjectTemplate(schema.id, false));
            chip.append(remove);
            list.append(chip);
        });
    } catch (error) {
        showError(error);
    }
}

async function setProjectTemplate(schemaId, enabled) {
    if (!schemaId) return;
    try {
        await apiRequest('/api/evidence/projects', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder: folderApiValue(), schema_id: schemaId, enabled })
        });
        await loadProjectTemplates();
        if (currentNodeData) await loadPaperEvidence(currentNodeData.data('uuid'));
    } catch (error) {
        showError(error);
    }
}

async function loadPaperEvidence(paperUuid) {
    try {
        const data = await apiRequest(`/api/evidence/${encodeURIComponent(paperUuid)}`);
        if (!currentNodeData || currentNodeData.data('uuid') !== paperUuid) return;
        currentEvidenceData = data;
        evidenceSchemas = data.schemas;
        renderPaperEvidence(data);
    } catch (error) {
        showError(error);
    }
}

function renderPaperEvidence(data) {
    const active = new Set(data.active_schema_ids);
    const select = document.getElementById('paperTemplateSelect');
    select.replaceChildren();
    data.schemas.filter(schema => !active.has(schema.id)).forEach(schema => {
        const option = document.createElement('option');
        option.value = schema.id;
        option.textContent = schema.name;
        select.append(option);
    });

    const container = document.getElementById('activeEvidenceTemplates');
    container.replaceChildren();
    data.schemas.filter(schema => active.has(schema.id)).forEach(schema => {
        const card = document.createElement('details');
        card.className = 'evidence-template-card';
        const header = document.createElement('summary');
        header.className = 'evidence-template-header';
        const title = document.createElement('h4');
        const populated = schema.fields.filter(field => data.values[field.id]?.value != null).length;
        title.textContent = `${schema.name} · ${populated}/${schema.fields.length}`;
        title.title = schema.description;
        const remove = document.createElement('button');
        remove.className = 'compact-btn';
        remove.type = 'button';
        remove.textContent = 'Disable';
        remove.addEventListener('click', event => { event.preventDefault(); setPaperTemplate(schema.id, false); });
        header.append(title, remove);
        card.append(header);
        const body = document.createElement('div');
        body.className = 'evidence-template-body';
        card.append(body);
        card.addEventListener('toggle', () => {
            if (!card.open || body.childElementCount) return;
            let previousGroup = null;
            [...schema.fields].sort((a, b) => Number(data.values[b.id]?.value != null) - Number(data.values[a.id]?.value != null)).forEach(field => {
                if (field.group_name && field.group_name !== previousGroup) {
                    const group = document.createElement('div'); group.className = 'evidence-group-title'; group.textContent = field.group_name; body.append(group);
                }
                previousGroup = field.group_name;
                body.append(createEvidenceField(field, data.values[field.id]));
            });
        });
        container.append(card);
    });
}

async function setPaperTemplate(schemaId, enabled) {
    if (!currentNodeData || !schemaId) return;
    try {
        await apiRequest(`/api/evidence/${encodeURIComponent(currentNodeData.data('uuid'))}/schemas`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ schema_id: schemaId, enabled })
        });
        await loadPaperEvidence(currentNodeData.data('uuid'));
    } catch (error) {
        showError(error);
    }
}

function createEvidenceField(field, stored) {
    const wrapper = document.createElement('div');
    wrapper.className = `evidence-field verification-${stored?.verification_status || 'confirmed'}`;
    const label = document.createElement('label');
    label.className = 'evidence-field-label';
    label.append(document.createTextNode(field.label));
    if (field.unit) {
        const unit = document.createElement('span');
        unit.className = 'evidence-unit';
        unit.textContent = field.unit;
        label.append(unit);
    }
    const valueInput = evidenceInput(field, stored?.value);
    wrapper.append(label, valueInput.element);

    const details = document.createElement('details');
    details.className = 'evidence-provenance';
    if (stored?.source_excerpt || stored?.page) details.open = true;
    const summary = document.createElement('summary');
    summary.textContent = 'Evidence and provenance';
    const grid = document.createElement('div');
    grid.className = 'provenance-grid';
    const excerpt = formElement('textarea', 'Source excerpt', stored?.source_excerpt || '', 'wide');
    const page = formElement('input', 'Page', stored?.page || '');
    const location = formElement('input', 'Location / table / figure', stored?.location || '');
    const method = selectElement('Extraction', ['manual', 'imported', 'automatic'], stored?.extraction_method || 'manual');
    const verification = selectElement('Verification', ['confirmed', 'suggested', 'rejected'], stored?.verification_status || 'confirmed');
    const confidence = formElement('input', 'Confidence (0–1)', stored?.confidence ?? '');
    confidence.input.type = 'number'; confidence.input.min = '0'; confidence.input.max = '1'; confidence.input.step = '0.01';
    grid.append(excerpt.wrap, page.wrap, location.wrap, method.wrap, verification.wrap, confidence.wrap);
    details.append(summary, grid);

    const actions = document.createElement('div');
    actions.className = 'evidence-actions';
    const clear = button('Clear', 'compact-btn');
    const save = button('Save evidence', 'compact-btn');
    const saveStatus = document.createElement('span');
    saveStatus.className = 'save-status'; saveStatus.setAttribute('aria-live', 'polite');
    clear.addEventListener('click', () => deleteEvidenceValue(field.id));
    save.addEventListener('click', () => saveEvidenceValue(field.id, valueInput.read(), {
        source_excerpt: excerpt.input.value, page: page.input.value, location: location.input.value,
        extraction_method: method.input.value, verification_status: verification.input.value,
        confidence: confidence.input.value
    }, saveStatus));
    actions.append(clear, save, saveStatus);
    wrapper.append(details, actions);
    return wrapper;
}

function evidenceInput(field, value) {
    let element;
    if (field.field_type === 'boolean') {
        element = document.createElement('select');
        ['', 'true', 'false'].forEach(item => {
            const option = document.createElement('option'); option.value = item;
            option.textContent = item === '' ? 'Not specified' : item; element.append(option);
        });
        element.value = value === true ? 'true' : value === false ? 'false' : '';
    } else if (field.field_type === 'single_choice' || field.field_type === 'multi_choice') {
        element = document.createElement('select');
        element.multiple = field.field_type === 'multi_choice';
        if (!element.multiple) element.append(new Option('Not specified', ''));
        field.options.forEach(item => element.append(new Option(item, item)));
        if (element.multiple) Array.from(element.options).forEach(option => option.selected = (value || []).includes(option.value));
        else element.value = value || '';
    } else if (field.field_type === 'range') {
        element = document.createElement('div');
        element.className = 'provenance-grid';
        ['min', 'max', 'uncertainty'].forEach(key => {
            const input = document.createElement('input'); input.className = 'form-control'; input.type = 'number';
            input.placeholder = key; input.dataset.rangePart = key; input.value = value?.[key] ?? ''; element.append(input);
        });
    } else if (['text', 'table', 'citation'].includes(field.field_type)) {
        element = document.createElement('textarea'); element.rows = 2; element.value = value || '';
    } else {
        element = document.createElement('input');
        element.type = field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : field.field_type === 'url' ? 'url' : 'text';
        element.value = value ?? '';
    }
    if (!element.classList.contains('provenance-grid')) element.classList.add('form-control');
    return { element, read: () => {
        if (field.field_type === 'boolean') return element.value === '' ? null : element.value === 'true';
        if (field.field_type === 'multi_choice') return Array.from(element.selectedOptions).map(option => option.value);
        if (field.field_type === 'range') return Object.fromEntries(Array.from(element.querySelectorAll('input')).map(input => [input.dataset.rangePart, input.value]));
        return element.value;
    }};
}

function formElement(tag, labelText, value, extraClass = '') {
    const wrap = document.createElement('label'); wrap.className = extraClass;
    wrap.append(document.createTextNode(labelText));
    const input = document.createElement(tag); input.className = 'form-control'; input.value = value;
    if (tag === 'textarea') input.rows = 3;
    wrap.append(input); return { wrap, input };
}

function selectElement(labelText, options, value) {
    const result = formElement('select', labelText, '');
    options.forEach(item => result.input.append(new Option(item, item)));
    result.input.value = value; return result;
}

function button(text, className) {
    const result = document.createElement('button'); result.type = 'button'; result.className = className; result.textContent = text; return result;
}

async function saveEvidenceValue(fieldId, value, provenance, statusElement) {
    try {
        statusElement.textContent = 'Saving…';
        await apiRequest(`/api/evidence/${encodeURIComponent(currentNodeData.data('uuid'))}/values/${encodeURIComponent(fieldId)}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ value, ...provenance })
        });
        statusElement.textContent = 'Saved';
        setTimeout(() => { statusElement.textContent = ''; }, 1800);
    } catch (error) { statusElement.textContent = 'Not saved'; showError(error); }
}

async function deleteEvidenceValue(fieldId) {
    try {
        await apiRequest(`/api/evidence/${encodeURIComponent(currentNodeData.data('uuid'))}/values/${encodeURIComponent(fieldId)}`, { method: 'DELETE' });
        await loadPaperEvidence(currentNodeData.data('uuid'));
    } catch (error) { showError(error); }
}

// --- Unified Search Engine ---
function executeSearch(query) {
    if (!window.cy) return;
    query = query.toLowerCase().trim();
    if (!query) return;
    const nodes = window.cy.nodes().filter(n => n.data('label').toLowerCase().includes(query) || n.data('id').toLowerCase().includes(query));
    if (nodes.length > 0) {
        const targetNode = nodes[0];
        window.cy.animate({ center: { eles: targetNode }, zoom: 1.2, duration: 800, easing: 'cubic-bezier(0.4, 0, 0.2, 1)' });
        window.cy.elements().addClass('faded');
        targetNode.removeClass('faded').addClass('highlighted-node');
        setTimeout(() => window.cy.elements().removeClass('faded').removeClass('highlighted-node'), 3000);

        document.getElementById('searchInput').value = '';
        document.getElementById('toolbarSearchInput').value = '';
    } else {
        alert("No paper found matching that search in the graph.");
    }
}

function bindSearchLogic(inputId, suggestionBoxId, triggerFunc, afterSelection = () => {}) {
    const input = document.getElementById(inputId);
    const suggestionBox = document.getElementById(suggestionBoxId);

    let searchSequence = 0;
    input.addEventListener('input', async function () {
        const sequence = ++searchSequence;
        const val = this.value.toLowerCase().trim();
        suggestionBox.innerHTML = '';
        if (!val || !window.cy) { suggestionBox.style.display = 'none'; return; }
        const localNodes = window.cy.nodes().filter(n => n.data('label').toLowerCase().includes(val) || n.data('id').toLowerCase().includes(val));
        let remote = [];
        try {
            if (val.length >= 2) remote = await apiRequest(`/api/search?q=${encodeURIComponent(val)}&limit=8`);
        } catch (_error) { /* Local title search remains available if FTS is unavailable. */ }
        if (sequence !== searchSequence) return;
        const results = [];
        const seen = new Set();
        localNodes.slice(0, 8).forEach(node => {
            seen.add(node.id()); results.push({ path: node.id(), title: node.data('label'), snippet: '' });
        });
        remote.forEach(result => { if (!seen.has(result.path)) results.push(result); });
        if (results.length > 0) {
            suggestionBox.style.display = 'block';
            results.slice(0, 8).forEach(result => {
                const div = document.createElement('div');
                div.className = 'suggestion-item';
                const title = document.createElement('strong'); title.textContent = result.title; div.append(title);
                if (result.snippet) {
                    const snippet = document.createElement('small');
                    snippet.textContent = result.snippet.replace(/<\/?mark>/g, ''); div.append(snippet);
                }
                div.addEventListener('click', () => {
                    input.value = result.title;
                    suggestionBox.style.display = 'none';
                    focusSearchResult(result);
                    afterSelection();
                });
                suggestionBox.appendChild(div);
            });
        } else { suggestionBox.style.display = 'none'; }
    });

    input.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            suggestionBox.style.display = 'none';
            triggerFunc(input.value);
        }
    });

    document.addEventListener('click', function (e) {
        if (e.target !== input && e.target !== suggestionBox) {
            suggestionBox.style.display = 'none';
        }
    });
}

async function focusSearchResult(result) {
    let node = window.cy?.getElementById(result.path);
    if (!node?.length) {
        currentFolder = 'global';
        loadFolders();
        await renderGraph('');
        node = window.cy.getElementById(result.path);
    }
    if (!node.length) return showError(new Error('The matching paper is not available in the graph.'));
    window.cy.animate({ center: { eles: node }, zoom: 1.15, duration: 500 });
    window.cy.elements().addClass('faded'); node.removeClass('faded').addClass('highlighted-node');
    setTimeout(() => window.cy.elements().removeClass('faded highlighted-node'), 2200);
}

bindSearchLogic('searchInput', 'suggestionBox', executeSearch);

function setToolbarSearch(open) {
    const container = document.getElementById('toolbarSearchContainer');
    const toolbar = document.getElementById('graphToolbar');
    const toggle = document.getElementById('toggleToolbarSearchBtn');
    container.classList.toggle('visible', open);
    toolbar.classList.toggle('search-open', open);
    container.setAttribute('aria-hidden', String(!open));
    toggle.setAttribute('aria-expanded', String(open));
    toggle.classList.toggle('active', open);
    if (open) {
        requestAnimationFrame(() => document.getElementById('toolbarSearchInput').focus());
    } else {
        document.getElementById('toolbarSuggestionBox').style.display = 'none';
    }
}

function closeToolbarSearch() {
    setToolbarSearch(false);
}

bindSearchLogic(
    'toolbarSearchInput',
    'toolbarSuggestionBox',
    query => { executeSearch(query); closeToolbarSearch(); },
    closeToolbarSearch,
);

window.searchNode = function () {
    document.getElementById('suggestionBox').style.display = 'none';
    executeSearch(document.getElementById('searchInput').value);
};

window.searchNodeToolbar = function () {
    document.getElementById('toolbarSuggestionBox').style.display = 'none';
    executeSearch(document.getElementById('toolbarSearchInput').value);
    closeToolbarSearch();
};

async function openTemplateEditor() {
    try {
        evidenceSchemas = await apiRequest('/api/evidence/schemas');
        const select = document.getElementById('templateToEdit');
        select.replaceChildren(new Option('Create a new template', ''));
        evidenceSchemas.filter(schema => !schema.builtin).forEach(schema => select.append(new Option(schema.name, schema.id)));
        select.value = '';
        populateTemplateEditor(null);
        document.getElementById('templateEditorModal').style.display = 'flex';
    } catch (error) { showError(error); }
}

function populateTemplateEditor(schema) {
    document.getElementById('templateName').value = schema?.name || '';
    document.getElementById('templateDescription').value = schema?.description || '';
    document.getElementById('templateFieldRows').replaceChildren();
    (schema?.fields || []).forEach(addTemplateFieldRow);
    if (!schema) addTemplateFieldRow();
    document.getElementById('deleteTemplateBtn').style.display = schema ? 'block' : 'none';
}

function addTemplateFieldRow(field = {}) {
    const row = document.createElement('div');
    row.className = 'template-field-row';
    row.dataset.fieldId = field.id || '';
    const label = document.createElement('input'); label.className = 'form-control field-label'; label.placeholder = 'Field label'; label.value = field.label || '';
    const type = document.createElement('select'); type.className = 'form-control field-type';
    ['text', 'number', 'boolean', 'date', 'single_choice', 'multi_choice', 'citation', 'url', 'range', 'table'].forEach(item => type.append(new Option(item.replace('_', ' '), item)));
    type.value = field.field_type || field.type || 'text';
    const unit = document.createElement('input'); unit.className = 'form-control field-unit'; unit.placeholder = 'Unit'; unit.value = field.unit || '';
    const group = document.createElement('input'); group.className = 'form-control field-group'; group.placeholder = 'Group'; group.value = field.group_name || field.group || '';
    const options = document.createElement('input'); options.className = 'form-control field-options'; options.placeholder = 'Choices separated by |'; options.value = (field.options || []).join('|');
    const remove = button('×', 'compact-btn'); remove.title = 'Remove field'; remove.addEventListener('click', () => row.remove());
    row.append(label, type, unit, group, options, remove);
    document.getElementById('templateFieldRows').append(row);
}

function templatePayload() {
    return {
        name: document.getElementById('templateName').value,
        description: document.getElementById('templateDescription').value,
        fields: Array.from(document.querySelectorAll('#templateFieldRows .template-field-row')).map(row => ({
            id: row.dataset.fieldId, label: row.querySelector('.field-label').value,
            type: row.querySelector('.field-type').value, unit: row.querySelector('.field-unit').value,
            group: row.querySelector('.field-group').value, options: row.querySelector('.field-options').value
        }))
    };
}

async function saveTemplate() {
    const schemaId = document.getElementById('templateToEdit').value;
    try {
        await apiRequest(schemaId ? `/api/evidence/schemas/${encodeURIComponent(schemaId)}` : '/api/evidence/schemas', {
            method: schemaId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(templatePayload())
        });
        document.getElementById('templateEditorModal').style.display = 'none';
        await loadProjectTemplates();
        if (currentNodeData) await loadPaperEvidence(currentNodeData.data('uuid'));
    } catch (error) { showError(error); }
}

async function deleteTemplate() {
    const schemaId = document.getElementById('templateToEdit').value;
    if (!schemaId || !confirm('Delete this custom template and its saved evidence values?')) return;
    try {
        await apiRequest(`/api/evidence/schemas/${encodeURIComponent(schemaId)}`, { method: 'DELETE' });
        document.getElementById('templateEditorModal').style.display = 'none';
        await loadProjectTemplates();
        if (currentNodeData) await loadPaperEvidence(currentNodeData.data('uuid'));
    } catch (error) { showError(error); }
}

document.getElementById('openSidebarBtn').addEventListener('click', toggleSidebar);
document.getElementById('hideSidebarBtn').addEventListener('click', toggleSidebar);
document.getElementById('toggleToolbarSearchBtn').addEventListener('click', () => {
    setToolbarSearch(!document.getElementById('toolbarSearchContainer').classList.contains('visible'));
});
document.getElementById('toolbarSearchInput').addEventListener('keydown', event => {
    if (event.key === 'Escape') closeToolbarSearch();
});
document.getElementById('toolbarSearchBtn').addEventListener('click', searchNodeToolbar);
document.getElementById('searchBtn').addEventListener('click', searchNode);
document.getElementById('openLocalModalBtn').addEventListener('click', openLocalModal);
document.getElementById('closeLocalModalBtn').addEventListener('click', closeLocalModal);
document.getElementById('submitLocalBtn').addEventListener('click', submitLocalPaper);
document.getElementById('openImportModalBtn').addEventListener('click', openImportModal);
document.getElementById('closeImportModalBtn').addEventListener('click', closeImportModal);
document.getElementById('submitImportBtn').addEventListener('click', submitImportLibrary);
document.getElementById('closeCitationPanelBtn').addEventListener('click', closeCitationPanel);
document.getElementById('cancelSyncBtn').addEventListener('click', cancelSynchronization);
document.getElementById('fitGraphBtn').addEventListener('click', () => window.cy?.fit(window.cy.elements(':visible'), 90));
document.getElementById('zoomInBtn').addEventListener('click', () => window.cy?.animate({ zoom: Math.min(window.cy.zoom() * 1.25, 3.5), duration: 180 }));
document.getElementById('zoomOutBtn').addEventListener('click', () => window.cy?.animate({ zoom: Math.max(window.cy.zoom() / 1.25, 0.08), duration: 180 }));
document.getElementById('runLayoutBtn').addEventListener('click', runSelectedLayout);
document.getElementById('statusFilter').addEventListener('change', applyGraphFilters);
document.getElementById('neighborhoodDepth').addEventListener('change', applyGraphFilters);
document.getElementById('toggleLabelsBtn').addEventListener('click', event => {
    graphLabelsVisible = !graphLabelsVisible; event.currentTarget.classList.toggle('active', graphLabelsVisible); applySemanticZoom();
});
document.getElementById('toggleEdgesBtn').addEventListener('click', event => {
    graphEdgesVisible = !graphEdgesVisible; event.currentTarget.classList.toggle('active', graphEdgesVisible); applyGraphFilters();
});
document.getElementById('resetGraphViewBtn').addEventListener('click', resetGraphView);
document.getElementById('graphFocusBtn').addEventListener('click', toggleGraphFocus);
document.getElementById('exportGraphBtn').addEventListener('click', exportGraphImage);
document.getElementById('graphContextMenu').addEventListener('click', event => {
    const action = event.target.closest('button')?.dataset.action; if (action) handleGraphContextAction(action);
});
document.getElementById('cy').addEventListener('keydown', navigateGraphByKeyboard);
document.getElementById('clearComparisonBtn').addEventListener('click', clearComparison);
document.getElementById('closeComparisonBtn').addEventListener('click', () => document.getElementById('comparisonDrawer').classList.remove('active'));
configureResizeHandle('sidebarResizeHandle', 'sidebar', false);
configureResizeHandle('citationResizeHandle', 'citation-panel', true);
document.getElementById('addProjectTemplateBtn').addEventListener('click', () => setProjectTemplate(document.getElementById('projectTemplateSelect').value, true));
document.getElementById('addPaperTemplateBtn').addEventListener('click', () => setPaperTemplate(document.getElementById('paperTemplateSelect').value, true));
document.getElementById('manageTemplatesBtn').addEventListener('click', openTemplateEditor);
document.getElementById('closeTemplateEditorBtn').addEventListener('click', () => document.getElementById('templateEditorModal').style.display = 'none');
document.getElementById('addTemplateFieldBtn').addEventListener('click', () => addTemplateFieldRow());
document.getElementById('saveTemplateBtn').addEventListener('click', saveTemplate);
document.getElementById('deleteTemplateBtn').addEventListener('click', deleteTemplate);
document.getElementById('templateToEdit').addEventListener('change', event => {
    populateTemplateEditor(evidenceSchemas.find(schema => schema.id === event.target.value) || null);
});

document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    closeCitationPanel();
    closeLocalModal();
    closeImportModal();
    document.getElementById('templateEditorModal').style.display = 'none';
});

// Initialize App only after obtaining the session-bound request token.
apiRequest('/api/session').then(data => {
    csrfToken = data.csrf_token;
    if (localStorage.getItem('litgraph-sidebar-hidden') === '1') toggleSidebar();
    else updateGraphViewport();
    loadFolders();
    checkAndLoadGraph();
}).catch(showError);
