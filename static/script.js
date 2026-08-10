// --- Sidebar Visibility Logic ---
window.toggleSidebar = function() {
    const sidebar = document.getElementById('sidebar');
    const openBtn = document.getElementById('openSidebarBtn');
    const floatingSearch = document.getElementById('floatingSearchContainer');
    
    sidebar.classList.toggle('hidden');
    openBtn.classList.toggle('visible');
    floatingSearch.classList.toggle('visible');
};

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
    const shadowColor = getCSSVar('--shadow-color') || 'rgba(0,0,0,0.3)';
    const bgMain = getCSSVar('--bg-main') || '#000000';
    
    return [
        { selector: 'node', style: { 'shape': 'round-rectangle', 'background-color': nodeColor, 'label': 'data(label)', 'color': labelColor, 'font-size': '13px', 'font-family': 'Inter, sans-serif', 'font-weight': '600', 'text-valign': 'center', 'text-halign': 'center', 'text-wrap': 'wrap', 'text-max-width': '160px', 'padding': '14px', 'width': 'label', 'height': 'label', 'corner-radius': '100px', 'border-width': 2, 'border-color': edgeColor, 'shadow-blur': 15, 'shadow-color': shadowColor, 'shadow-opacity': 0.6, 'shadow-offset-y': 6, 'shadow-offset-x': 0, 'cursor': 'pointer', 'z-index': 10, 'transition-property': 'background-color, shadow-blur, border-color, color, transform', 'transition-duration': '0.3s' } },
        { selector: 'node[status = "read"]', style: { 'background-color': '#22c55e', 'border-color': '#16a34a', 'color': '#ffffff', 'shadow-color': '#22c55e' } },
        { selector: 'node[status = "prioritize"]', style: { 'background-color': '#eab308', 'border-color': '#ca8a04', 'color': '#0f172a', 'shadow-color': '#eab308' } },
        { selector: 'edge', style: { 'width': 2.5, 'line-color': edgeColor, 'target-arrow-color': edgeColor, 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'opacity': 0.4, 'label': 'data(citation_number)', 'font-size': '11px', 'font-family': 'Inter, sans-serif', 'font-weight': '700', 'text-background-opacity': 1, 'text-background-color': bgMain, 'color': highlightColor, 'text-border-color': edgeColor, 'text-border-width': 1, 'text-border-opacity': 0.5, 'text-background-shape': 'roundrectangle', 'text-background-padding': '4px', 'cursor': 'pointer', 'text-opacity': 0.8, 'transition-property': 'line-color, target-arrow-color, width, opacity, text-opacity', 'transition-duration': '0.3s' } },
        { selector: '.highlighted-node', style: { 'background-color': highlightColor, 'color': bgMain, 'border-color': highlightColor, 'shadow-color': highlightColor, 'shadow-opacity': 0.5, 'shadow-blur': 25, 'z-index': 999 } },
        { selector: '.highlighted-edge', style: { 'line-color': highlightColor, 'target-arrow-color': highlightColor, 'width': 4, 'opacity': 1, 'color': highlightColor, 'text-border-color': highlightColor, 'text-opacity': 1, 'z-index': 990 } },
        { selector: '.faded', style: { 'opacity': 0.05 } }
    ];
};

// --- Core App Variables ---
window.cy = null;
let currentFolder = 'global';
let currentNodeData = null; 

// --- Folders & Modals Logic ---
function loadFolders() {
    fetch('/api/folders')
        .then(res => res.json())
        .then(folders => {
            const tree = document.getElementById('folderTree');
            tree.innerHTML = '';
            folders.forEach(f => {
                const div = document.createElement('div');
                div.className = `folder-item ${f.id === currentFolder ? 'active' : ''}`;
                div.innerHTML = `<i class="fas ${f.id === 'global' ? 'fa-globe' : 'fa-folder'}"></i> ${f.name}`;
                div.onclick = () => {
                    currentFolder = f.id;
                    loadFolders(); 
                    checkAndLoadGraph(f.path);
                };
                tree.appendChild(div);
            });
        });
}

function openLocalModal() {
    fetch('/api/folders').then(res => res.json()).then(folders => {
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
    });
}
window.closeLocalModal = function() { document.getElementById('localFileModal').style.display = 'none'; };

window.submitLocalPaper = function() {
    const path = document.getElementById('localFilePath').value;
    const folder = document.getElementById('localFolderSelect').value;
    const newFolder = document.getElementById('localNewFolder').value;
    const action = document.querySelector('input[name="fileAction"]:checked').value;
    
    if (!path) { alert('Please provide the absolute path to the PDF.'); return; }
    
    const btn = document.getElementById('submitLocalBtn');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    btn.disabled = true;
    
    fetch('/api/add_local_paper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_path: path, folder_select: folder, new_folder: newFolder, action: action })
    }).then(res => res.json()).then(data => {
        btn.innerHTML = 'Add Paper';
        btn.disabled = false;
        
        if (data.error) {
            alert(data.error);
        } else {
            closeLocalModal();
            document.getElementById('localFilePath').value = '';
            document.getElementById('localNewFolder').value = '';
            
            loadFolders();
            checkAndLoadGraph(newFolder ? newFolder : (folder === 'global' ? '' : folder));
        }
    }).catch(err => {
        btn.innerHTML = 'Add Paper';
        btn.disabled = false;
        alert("Network error processing local file.");
    });
};

window.openImportModal = function() { document.getElementById('importLibraryModal').style.display = 'flex'; };
window.closeImportModal = function() { document.getElementById('importLibraryModal').style.display = 'none'; };

window.submitImportLibrary = function() {
    const path = document.getElementById('importFolderPath').value;
    const action = document.querySelector('input[name="importAction"]:checked').value;
    
    if (!path) { alert('Please provide the absolute path to the folder.'); return; }
    
    const btn = document.getElementById('submitImportBtn');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    btn.disabled = true;
    
    fetch('/api/import_library', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_path: path, action: action })
    }).then(res => res.json()).then(data => {
        btn.innerHTML = 'Import Library';
        btn.disabled = false;
        
        if (data.error) {
            alert(data.error);
        } else {
            alert(`Successfully imported ${data.count} PDFs.`);
            closeImportModal();
            document.getElementById('importFolderPath').value = '';
            
            loadFolders();
            checkAndLoadGraph('global');
        }
    }).catch(err => {
        btn.innerHTML = 'Import Library';
        btn.disabled = false;
        alert("Network error processing library import.");
    });
};

function checkAndLoadGraph(folderPath = '') {
    fetch('/api/check_updates')
        .then(res => res.json())
        .then(data => {
            if (data.needs_update) {
                document.getElementById('syncOverlay').style.display = 'flex';
                fetch('/api/build_cache', { method: 'POST' })
                    .then(() => {
                        document.getElementById('syncOverlay').style.display = 'none';
                        renderGraph(folderPath);
                    });
            } else {
                renderGraph(folderPath);
            }
        });
}

function renderGraph(folderPath = '') {
    let url = '/api/graph';
    if (folderPath && folderPath !== 'global') {
        url += '?folder=' + encodeURIComponent(folderPath);
    }
    
    fetch(url).then(res => res.json()).then(data => {
        if (window.cy) window.cy.destroy();
        
        window.cy = cytoscape({ 
            container: document.getElementById('cy'), elements: data, style: getDynamicStyleSheet(), 
            layout: { name: 'cose', padding: 100, nodeDimensionsIncludeLabels: true, nodeOverlap: 50, randomize: true, idealEdgeLength: 400, nodeRepulsion: 9000000, gravity: 20, numIter: 3000, edgeElasticity: 20 }, 
            minZoom: 0.15, maxZoom: 2.5 
        });

        window.cy.on('mouseover', 'node', function(evt){
            var node = evt.target; window.cy.elements().addClass('faded'); node.removeClass('faded').addClass('highlighted-node'); node.connectedEdges().removeClass('faded').addClass('highlighted-edge'); node.connectedEdges().connectedNodes().removeClass('faded').addClass('highlighted-node');
        });
        window.cy.on('mouseout', 'node, edge', () => window.cy.elements().removeClass('faded').removeClass('highlighted-node').removeClass('highlighted-edge'));
        window.cy.on('mouseover', 'edge', function(evt){
            var edge = evt.target; window.cy.elements().addClass('faded'); edge.removeClass('faded').addClass('highlighted-edge'); edge.connectedNodes().removeClass('faded').addClass('highlighted-node');
        });

        window.cy.on('tap', 'node', function(evt){ showNodePanel(evt.target); });
        window.cy.on('tap', 'edge', function(evt){ showEdgePanel(evt.target); });
    });
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
            node.data('label', newTitle.trim()); 
            document.getElementById('panelTitle').innerText = newTitle.trim();
            fetch('/api/update_title', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: node.id(), title: newTitle.trim() }) });
        }
    };

    const btnRead = document.getElementById('btnMarkRead');
    btnRead.className = 'action-btn ' + (node.data('status') === 'read' ? 'active-read' : '');
    btnRead.onclick = () => toggleNodeStatus(node, 'read');

    const btnPrioritize = document.getElementById('btnMarkPrioritize');
    btnPrioritize.className = 'action-btn ' + (node.data('status') === 'prioritize' ? 'active-prioritize' : '');
    btnPrioritize.onclick = () => toggleNodeStatus(node, 'prioritize');

    document.getElementById('nodeTextNote').value = "Loading notes...";
    document.getElementById('attachmentList').innerHTML = "";
    
    fetch('/api/node_details/' + uuid)
        .then(res => res.json())
        .then(data => {
            document.getElementById('nodeTextNote').value = data.text;
            renderAttachments(data.attachments);
        });
        
    document.getElementById('citation-panel').classList.add('active');
}

function showEdgePanel(edge) {
    currentNodeData = null; 
    document.getElementById('node-view').style.display = 'none';
    document.getElementById('edge-view').style.display = 'block';
    document.getElementById('panelTitle').innerText = "Citation Context";

    var sourceLabel = window.cy.getElementById(edge.data('source')).data('label');
    var targetLabel = window.cy.getElementById(edge.data('target')).data('label');
    var citeNum = edge.data('citation_number') ? ` <span style="color:var(--highlight); font-weight:bold;">${edge.data('citation_number')}</span>` : '';
    
    var contextHTML = `<h3 style="font-size:1.15rem; margin-bottom:16px; margin-top:0; color:var(--text-main); font-weight:700;">${sourceLabel} <br><i class="fas fa-arrow-down" style="color:var(--text-muted); font-size:1rem; margin: 10px 0;"></i> <br>${targetLabel}${citeNum}</h3>`;
    
    var sentences = edge.data('context').split('|||');
    sentences.forEach(sentence => { 
        if (sentence.trim() !== "") { 
            let styledSentence = sentence.replace(/&lt;span class=&#x27;highlight&#x27;&gt;/g, "<span class='highlight-text'>").replace(/&lt;\/span&gt;/g, "</span>");
            contextHTML += `<div class="context-box">${styledSentence.trim()}</div>`; 
        } 
    });
    document.getElementById('edge-view').innerHTML = contextHTML;
    document.getElementById('citation-panel').classList.add('active');
}

// --- Note Saving Logic ---
document.getElementById('btnSaveNote').onclick = () => {
    if (!currentNodeData) return;
    const text = document.getElementById('nodeTextNote').value;
    const btn = document.getElementById('btnSaveNote');
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    
    fetch('/api/save_note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uuid: currentNodeData.data('uuid'), text: text })
    }).then(() => {
        btn.innerHTML = '<i class="fas fa-check"></i> Saved!';
        setTimeout(() => btn.innerHTML = originalHTML, 2000);
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
    
    fetch('/api/upload_attachment', { method: 'POST', body: formData })
        .then(res => res.json())
        .then(data => {
            dropZone.innerHTML = '<i class="fas fa-cloud-upload-alt" style="font-size: 1.5rem; margin-bottom: 8px; display: block;"></i> Drag & Drop or click to attach<br><small style="opacity:0.7">ppt, docx, txt, pdf, md</small>';
            if (data.success) {
                fetch('/api/node_details/' + currentNodeData.data('uuid'))
                    .then(res => res.json())
                    .then(d => renderAttachments(d.attachments));
            } else { alert(data.error); }
        });
}

function renderAttachments(attachments) {
    const list = document.getElementById('attachmentList');
    list.innerHTML = '';
    attachments.forEach(att => {
        list.innerHTML += `
            <div class="attachment-item">
                <i class="fas fa-paperclip"></i>
                <a href="/notes/${att.filename}" target="_blank" title="${att.original_name}">${att.original_name}</a>
            </div>`;
    });
}

function toggleNodeStatus(node, targetType) {
    let newStatus = (node.data('status') === targetType) ? 'none' : targetType;
    node.data('status', newStatus);
    
    document.getElementById('btnMarkRead').className = 'action-btn ' + (newStatus === 'read' ? 'active-read' : '');
    document.getElementById('btnMarkPrioritize').className = 'action-btn ' + (newStatus === 'prioritize' ? 'active-prioritize' : '');

    fetch('/api/update_status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: node.id(), status: newStatus })
    });
}

window.closeCitationPanel = function() { document.getElementById('citation-panel').classList.remove('active'); };

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
        document.getElementById('floatingSearchInput').value = '';
    } else { 
        alert("No paper found matching that search in the graph."); 
    }
}

function bindSearchLogic(inputId, suggestionBoxId, triggerFunc) {
    const input = document.getElementById(inputId);
    const suggestionBox = document.getElementById(suggestionBoxId);

    input.addEventListener('input', function() {
        const val = this.value.toLowerCase().trim();
        suggestionBox.innerHTML = '';
        if (!val || !window.cy) { suggestionBox.style.display = 'none'; return; }
        const nodes = window.cy.nodes().filter(n => n.data('label').toLowerCase().includes(val) || n.data('id').toLowerCase().includes(val));

        if(nodes.length > 0) {
            suggestionBox.style.display = 'block';
            nodes.slice(0, 8).forEach(n => {
                const div = document.createElement('div');
                div.className = 'suggestion-item';
                div.innerText = n.data('label');
                div.addEventListener('click', () => {
                    input.value = n.data('label');
                    suggestionBox.style.display = 'none';
                    triggerFunc(input.value); 
                });
                suggestionBox.appendChild(div);
            });
        } else { suggestionBox.style.display = 'none'; }
    });

    input.addEventListener('keypress', function(e) { 
        if(e.key === 'Enter') { 
            e.preventDefault(); 
            suggestionBox.style.display = 'none';
            triggerFunc(input.value); 
        } 
    });

    document.addEventListener('click', function(e) { 
        if (e.target !== input && e.target !== suggestionBox) {
            suggestionBox.style.display = 'none'; 
        }
    });
}

bindSearchLogic('searchInput', 'suggestionBox', executeSearch);
bindSearchLogic('floatingSearchInput', 'floatingSuggestionBox', executeSearch);

window.searchNode = function() {
    document.getElementById('suggestionBox').style.display = 'none';
    executeSearch(document.getElementById('searchInput').value);
};

window.searchNodeFloating = function() {
    document.getElementById('floatingSuggestionBox').style.display = 'none';
    executeSearch(document.getElementById('floatingSearchInput').value);
};

// Initialize App
loadFolders();
setTimeout(() => { checkAndLoadGraph(); }, 50);