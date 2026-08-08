import os
import re
import time
import requests
import fitz  # PyMuPDF
import webbrowser
import threading
import html
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, unquote
from flask import Flask, jsonify, send_from_directory, render_template_string, request

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAPERS_DIR = os.path.join(BASE_DIR, 'papers')

os.makedirs(PAPERS_DIR, exist_ok=True)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>LitGraph</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.26.0/cytoscape.min.js"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-main: #f8fafc;
            --bg-sidebar: rgba(255, 255, 255, 0.75);
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border-color: rgba(226, 232, 240, 0.8);
            --context-bg: rgba(255, 255, 255, 0.9);
            --highlight: #6366f1; 
            --highlight-hover: #4f46e5;
            --accent: #0ea5e9;
            --scrollbar-thumb: #cbd5e1;
            --shadow-color: rgba(15, 23, 42, 0.08);
            --modal-bg: rgba(248, 250, 252, 0.6);
            --error-bg: #fef2f2;
            --error-text: #991b1b;
        }
        
        [data-theme="dark"] {
            --bg-main: #0f172a;
            --bg-sidebar: rgba(30, 41, 59, 0.75);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border-color: rgba(51, 65, 85, 0.6);
            --context-bg: rgba(15, 23, 42, 0.6);
            --highlight: #818cf8;
            --highlight-hover: #6366f1;
            --accent: #2dd4bf; 
            --scrollbar-thumb: #475569;
            --shadow-color: rgba(0, 0, 0, 0.3);
            --modal-bg: rgba(15, 23, 42, 0.7);
            --error-bg: rgba(127, 29, 29, 0.3);
            --error-text: #fca5a5;
        }

        body { font-family: 'Inter', system-ui, -apple-system, sans-serif; margin: 0; overflow: hidden; background-color: var(--bg-main); color: var(--text-main); transition: background-color 0.5s ease, color 0.5s ease; }
        ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); border-radius: 10px; }
        
        #cy { position: absolute; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 1; }
        
        #sidebar { position: absolute; top: 24px; left: 24px; width: 380px; max-height: calc(100vh - 48px); padding: 28px; box-sizing: border-box; background: var(--bg-sidebar); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid var(--border-color); border-radius: 28px; box-shadow: 0 25px 50px -12px var(--shadow-color); display: flex; flex-direction: column; z-index: 10; }
        #citation-panel { position: absolute; top: 24px; right: 24px; width: 420px; height: calc(100vh - 48px); padding: 28px; box-sizing: border-box; background: var(--bg-sidebar); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid var(--border-color); border-radius: 28px; box-shadow: 0 25px 50px -12px var(--shadow-color); display: flex; flex-direction: column; z-index: 10; transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.1), opacity 0.3s ease; transform: translateX(120%); opacity: 0; pointer-events: none; }
        #citation-panel.active { transform: translateX(0); opacity: 1; pointer-events: auto; }
        
        .header-container { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
        h2 { margin: 0; font-size: 1.5rem; font-weight: 700; letter-spacing: -0.03em; }
        
        .theme-toggle, .close-btn { background: var(--context-bg); border: 1px solid var(--border-color); color: var(--text-main); cursor: pointer; font-size: 1.1rem; width: 40px; height: 40px; border-radius: 50%; display: flex; justify-content: center; align-items: center; transition: all 0.3s ease; box-shadow: 0 4px 6px -1px var(--shadow-color); }
        .theme-toggle:hover, .close-btn:hover { background: var(--highlight); color: #fff; transform: translateY(-2px); box-shadow: 0 10px 15px -3px var(--shadow-color); }

        .controls { margin-bottom: 24px; display: flex; flex-direction: column; gap: 14px; }
        .input-group { display: flex; gap: 10px; position: relative; }
        
        .autocomplete-container { flex: 1; display: flex; }
        .autocomplete-container input { flex: 1; padding: 14px 20px; border: 1px solid var(--border-color); border-radius: 999px; background: var(--context-bg); color: var(--text-main); outline: none; font-family: inherit; font-size: 0.95rem; transition: all 0.3s; box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.02); }
        .autocomplete-container input:focus { border-color: var(--highlight); box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15); }
        
        .suggestion-box { position: absolute; top: calc(100% + 8px); left: 0; right: 48px; background: var(--bg-sidebar); backdrop-filter: blur(20px); border: 1px solid var(--border-color); z-index: 999; border-radius: 16px; max-height: 250px; overflow-y: auto; display: none; box-shadow: 0 20px 25px -5px var(--shadow-color); padding: 8px; }
        .suggestion-item { padding: 12px 16px; cursor: pointer; border-radius: 10px; font-size: 0.9rem; color: var(--text-main); transition: all 0.2s; }
        .suggestion-item:hover { background: var(--highlight); color: #fff; font-weight: 500; }

        .input-group button { background: linear-gradient(135deg, var(--highlight), var(--highlight-hover)); color: #ffffff; border: none; border-radius: 50%; width: 48px; height: 48px; cursor: pointer; display: flex; justify-content: center; align-items: center; font-size: 1.1rem; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 10px 15px -3px rgba(99, 102, 241, 0.3); flex-shrink: 0; }
        .input-group button:hover { transform: translateY(-3px) scale(1.05); box-shadow: 0 20px 25px -5px rgba(99, 102, 241, 0.4); }
        .input-group button:active { transform: translateY(0) scale(0.95); }
        
        #citation-content { flex: 1; overflow-y: auto; padding-right: 4px; }
        .context-box { background: var(--context-bg); padding: 18px; border-radius: 20px; margin-bottom: 16px; font-size: 0.95rem; line-height: 1.6; border: 1px solid var(--border-color); box-shadow: 0 4px 6px -1px var(--shadow-color); transition: transform 0.3s; }
        .context-box:hover { transform: translateY(-2px); }
        
        .highlight-text { font-weight: 600; color: var(--highlight); background: rgba(99, 102, 241, 0.1); padding: 2px 6px; border-radius: 6px; }
        .instruction { color: var(--text-muted); margin-bottom: 16px; font-size: 0.95rem; display: flex; align-items: center; gap: 12px; background: var(--context-bg); padding: 16px; border-radius: 16px; border: 1px solid var(--border-color); }
        .instruction i { color: var(--highlight); font-size: 1.2rem; }
        
        .error-message { background: var(--error-bg); color: var(--error-text); padding: 14px; border-radius: 16px; font-size: 0.9rem; font-weight: 500; display: none; box-shadow: 0 4px 6px -1px var(--shadow-color); }
        
        #searchModal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: var(--modal-bg); backdrop-filter: blur(10px); z-index: 1000; justify-content: center; align-items: center; }
        .modal-content { background: var(--bg-sidebar); width: 90%; max-width: 650px; max-height: 80vh; border-radius: 28px; padding: 32px; overflow-y: auto; border: 1px solid var(--border-color); box-shadow: 0 25px 50px -12px var(--shadow-color); }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
        .close-modal { background: var(--context-bg); border: 1px solid var(--border-color); color: var(--text-muted); width: 36px; height: 36px; border-radius: 50%; font-size: 1.2rem; cursor: pointer; transition: all 0.2s; display: flex; justify-content: center; align-items: center;}
        .close-modal:hover { color: var(--text-main); transform: scale(1.1); }
        
        .search-result { padding: 20px; border: 1px solid var(--border-color); border-radius: 20px; margin-bottom: 16px; background: var(--context-bg); display: flex; flex-direction: column; gap: 10px; transition: all 0.3s; box-shadow: 0 4px 6px -1px var(--shadow-color); }
        .search-result:hover { transform: translateY(-3px); box-shadow: 0 10px 15px -3px var(--shadow-color); border-color: var(--highlight); }
        .result-title { font-weight: 700; font-size: 1.15rem; color: var(--text-main); }
        .result-authors { font-size: 0.9rem; color: var(--text-muted); }
        .result-source { font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; display: inline-block; padding: 4px 10px; border-radius: 999px; background: rgba(99, 102, 241, 0.1); color: var(--highlight); width: fit-content;}
        .download-btn { align-self: flex-start; background: var(--highlight); color: #fff; border: none; padding: 10px 20px; border-radius: 999px; cursor: pointer; font-weight: 600; margin-top: 8px; transition: all 0.3s; }
        .download-btn:hover { background: var(--highlight-hover); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3); }
    </style>
</head>
<body data-theme="dark">
    <div id="searchModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 style="margin:0; font-weight:700;">Select a paper to download</h3>
                <button class="close-modal" onclick="closeModal()"><i class="fas fa-times"></i></button>
            </div>
            <div id="modalResults"></div>
        </div>
    </div>

    <div id="cy"></div>
    
    <div id="sidebar">
        <div class="header-container">
            <h2>LitGraph</h2>
            <button class="theme-toggle" id="themeBtn" aria-label="Toggle Theme"><i class="fas fa-sun"></i></button>
        </div>
        
        <div class="controls">
            <div class="input-group">
                <div class="autocomplete-container">
                    <input type="text" id="searchInput" placeholder="Find a paper in graph..." autocomplete="off">
                    <div id="suggestionBox" class="suggestion-box"></div>
                </div>
                <button onclick="searchNode()" title="Search"><i class="fas fa-search"></i></button>
            </div>
            
            <div class="input-group">
                <div class="autocomplete-container">
                    <input type="text" id="urlInput" placeholder="Paste URL or citation..." onkeypress="if(event.key === 'Enter') handleAddPaper()">
                </div>
                <button onclick="handleAddPaper()" id="addBtn" title="Download & Add"><i class="fas fa-plus"></i></button>
            </div>
            <div id="errorMessage" class="error-message"></div>
        </div>

        <div id="info">
            <div class="empty-state">
                <div class="instruction"><i class="fas fa-magic"></i> Hover over nodes to highlight connections in deep focus.</div>
                <div class="instruction"><i class="fas fa-external-link-alt"></i> Click a node to open the PDF instantly.</div>
                <div class="instruction"><i class="fas fa-project-diagram"></i> Click the edges to read the exact citation context.</div>
            </div>
        </div>
    </div>

    <div id="citation-panel">
        <div class="header-container" style="margin-bottom: 20px;">
            <h2 style="font-size: 1.3rem;">Citation Context</h2>
            <button class="close-btn" onclick="closeCitationPanel()" aria-label="Close Panel"><i class="fas fa-times"></i></button>
        </div>
        <div id="citation-content"></div>
    </div>

    <script>
        const themeBtn = document.getElementById('themeBtn');
        let isDark = true;
        window.cy = null;
        
        const getStyleSheet = (dark) => {
            const nodeColor = dark ? '#1e293b' : '#ffffff'; 
            const edgeColor = dark ? '#475569' : '#cbd5e1'; 
            const labelColor = dark ? '#f8fafc' : '#0f172a'; 
            const highlightColor = dark ? '#818cf8' : '#6366f1';
            const shadowColor = dark ? '#000000' : '#475569';
            const glowColor = dark ? '#2dd4bf' : '#0ea5e9';
            
            return [
                { selector: 'node', style: { 'shape': 'round-rectangle', 'background-color': nodeColor, 'label': 'data(label)', 'color': labelColor, 'font-size': '13px', 'font-family': 'Inter, sans-serif', 'font-weight': '600', 'text-valign': 'center', 'text-halign': 'center', 'text-wrap': 'wrap', 'text-max-width': '160px', 'padding': '14px', 'width': 'label', 'height': 'label', 'corner-radius': '100px', 'border-width': 1, 'border-color': edgeColor, 'shadow-blur': 15, 'shadow-color': shadowColor, 'shadow-opacity': dark ? 0.6 : 0.15, 'shadow-offset-y': 6, 'shadow-offset-x': 0, 'cursor': 'pointer', 'z-index': 10, 'transition-property': 'background-color, shadow-blur, border-color, color, transform', 'transition-duration': '0.3s' } },
                { selector: 'edge', style: { 'width': 2.5, 'line-color': edgeColor, 'target-arrow-color': edgeColor, 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'opacity': 0.4, 'label': 'data(citation_number)', 'font-size': '11px', 'font-family': 'Inter, sans-serif', 'font-weight': '700', 'text-background-opacity': 1, 'text-background-color': dark ? '#1e293b' : '#ffffff', 'color': highlightColor, 'text-border-color': edgeColor, 'text-border-width': 1, 'text-border-opacity': 0.5, 'text-background-shape': 'roundrectangle', 'text-background-padding': '4px', 'cursor': 'pointer', 'text-opacity': 0.6, 'transition-property': 'line-color, target-arrow-color, width, opacity, text-opacity', 'transition-duration': '0.3s' } },
                { selector: '.highlighted-node', style: { 'background-color': glowColor, 'color': '#0f172a', 'border-color': glowColor, 'shadow-color': glowColor, 'shadow-opacity': 0.5, 'shadow-blur': 25, 'z-index': 999 } },
                { selector: '.highlighted-edge', style: { 'line-color': glowColor, 'target-arrow-color': glowColor, 'width': 4, 'opacity': 1, 'color': glowColor, 'text-border-color': glowColor, 'text-opacity': 1, 'z-index': 990 } },
                { selector: '.faded', style: { 'opacity': 0.05 } }
            ];
        };

        function initGraph() {
            fetch('/api/graph')
                .then(res => res.json())
                .then(data => {
                    if (window.cy) window.cy.destroy();
                    
                    window.cy = cytoscape({ 
                        container: document.getElementById('cy'), elements: data, style: getStyleSheet(isDark), 
                        layout: { name: 'cose', padding: 100, nodeRepulsion: 8000000, idealEdgeLength: 300, edgeElasticity: 45, gravity: 100, numIter: 1500 }, 
                        minZoom: 0.15, maxZoom: 2.5 
                    });

                    window.cy.on('mouseover', 'node', function(evt){
                        var node = evt.target; window.cy.elements().addClass('faded'); node.removeClass('faded').addClass('highlighted-node'); node.connectedEdges().removeClass('faded').addClass('highlighted-edge'); node.connectedEdges().connectedNodes().removeClass('faded').addClass('highlighted-node');
                    });
                    
                    window.cy.on('mouseout', 'node, edge', () => window.cy.elements().removeClass('faded').removeClass('highlighted-node').removeClass('highlighted-edge'));
                    
                    window.cy.on('mouseover', 'edge', function(evt){
                        var edge = evt.target; window.cy.elements().addClass('faded'); edge.removeClass('faded').addClass('highlighted-edge'); edge.connectedNodes().removeClass('faded').addClass('highlighted-node');
                    });

                    window.cy.on('tap', 'node', evt => window.open('/papers/' + encodeURIComponent(evt.target.id()), '_blank'));
                    
                    window.cy.on('tap', 'edge', function(evt){
                        var edge = evt.target;
                        var sourceLabel = window.cy.getElementById(edge.data('source')).data('label');
                        var targetLabel = window.cy.getElementById(edge.data('target')).data('label');
                        var citeNum = edge.data('citation_number') ? ` <span style="color:var(--highlight); font-weight:bold;">${edge.data('citation_number')}</span>` : '';
                        
                        var contextHTML = `<h3 style="font-size:1.15rem; margin-bottom:16px; margin-top:0; color:var(--text-main); font-weight:700;">${sourceLabel} <br><i class="fas fa-arrow-down" style="color:var(--text-muted); font-size:1rem; margin: 10px 0;"></i> <br>${targetLabel}${citeNum}</h3>`;
                        
                        var sentences = edge.data('context').split('|||');
                        sentences.forEach(sentence => { 
                            if (sentence.trim() !== "") { 
                                // Text is safely escaped in backend. We only swap the exact regex class injection safely.
                                let styledSentence = sentence.replace(/&lt;span class=&#x27;highlight&#x27;&gt;/g, "<span class='highlight-text'>").replace(/&lt;\/span&gt;/g, "</span>");
                                contextHTML += `<div class="context-box">${styledSentence.trim()}</div>`; 
                            } 
                        });
                        
                        document.getElementById('citation-content').innerHTML = contextHTML;
                        document.getElementById('citation-panel').classList.add('active');
                    });
                });
        }
        
        window.closeCitationPanel = function() { document.getElementById('citation-panel').classList.remove('active'); };

        const searchInput = document.getElementById('searchInput');
        const suggestionBox = document.getElementById('suggestionBox');

        searchInput.addEventListener('input', function() {
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
                        searchInput.value = n.data('label');
                        suggestionBox.style.display = 'none';
                        searchNode(); 
                    });
                    suggestionBox.appendChild(div);
                });
            } else { suggestionBox.style.display = 'none'; }
        });

        window.searchNode = function() {
            suggestionBox.style.display = 'none';
            if (!window.cy) return;
            
            const query = searchInput.value.toLowerCase().trim();
            if (!query) return;
            
            const nodes = window.cy.nodes().filter(n => n.data('label').toLowerCase().includes(query) || n.data('id').toLowerCase().includes(query));
            
            if (nodes.length > 0) {
                const targetNode = nodes[0];
                window.cy.animate({ center: { eles: targetNode }, zoom: 1.2, duration: 800, easing: 'cubic-bezier(0.4, 0, 0.2, 1)' });
                window.cy.elements().addClass('faded'); 
                targetNode.removeClass('faded').addClass('highlighted-node');
                setTimeout(() => window.cy.elements().removeClass('faded').removeClass('highlighted-node'), 3000);
            } else { alert("No paper found matching that search in the graph."); }
        };

        searchInput.addEventListener('keypress', function(e) { if(e.key === 'Enter') { e.preventDefault(); searchNode(); } });
        document.addEventListener('click', function(e) { if (e.target !== searchInput && e.target !== suggestionBox) suggestionBox.style.display = 'none'; });

        function showError(msg) {
            const errDiv = document.getElementById('errorMessage'); errDiv.innerHTML = msg; errDiv.style.display = 'block';
            setTimeout(() => { errDiv.style.display = 'none'; }, 8000); 
        }

        window.handleAddPaper = function() {
            const inputVal = document.getElementById('urlInput').value.trim();
            if (!inputVal) return;
            const btn = document.getElementById('addBtn'); btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
            document.getElementById('errorMessage').style.display = 'none';

            if (inputVal.startsWith('http') || inputVal.includes('.pdf') || inputVal.includes('arxiv.org')) {
                executeDownload(inputVal);
            } else {
                fetch('/api/search_paper', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: inputVal }) })
                .then(res => res.json())
                .then(results => {
                    btn.innerHTML = '<i class="fas fa-plus"></i>'; btn.disabled = false;
                    if (results.length === 0) showError("Could not find any Open Access PDFs for this citation.");
                    else if (results.length === 1) executeDownload(results[0].pdf_url);
                    else showModal(results);
                }).catch(err => { btn.innerHTML = '<i class="fas fa-plus"></i>'; btn.disabled = false; showError('<i class="fas fa-exclamation-circle"></i> Error searching for citation.'); });
            }
        };

        function executeDownload(url) {
            const btn = document.getElementById('addBtn'); btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>'; btn.disabled = true;
            closeModal();
            fetch('/api/add_paper', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url }) })
            .then(res => res.json())
            .then(data => {
                btn.innerHTML = '<i class="fas fa-plus"></i>'; btn.disabled = false;
                if (data.error) showError(`<i class="fas fa-exclamation-triangle"></i> ${data.error}`);
                else { document.getElementById('urlInput').value = ''; initGraph(); }
            }).catch(err => { btn.innerHTML = '<i class="fas fa-plus"></i>'; btn.disabled = false; showError('<i class="fas fa-wifi"></i> Network error while downloading the paper.'); });
        }

        function showModal(results) {
            const container = document.getElementById('modalResults'); container.innerHTML = '';
            results.forEach(res => {
                const div = document.createElement('div'); div.className = 'search-result';
                div.innerHTML = `<div class="result-source"><i class="fas fa-database"></i> ${res.source}</div><div class="result-title">${res.title}</div><div class="result-authors">${res.authors}</div><button class="download-btn" onclick="executeDownload('${res.pdf_url}')"><i class="fas fa-download"></i> Download</button>`;
                container.appendChild(div);
            });
            document.getElementById('searchModal').style.display = 'flex';
        }
        
        window.closeModal = function() { document.getElementById('searchModal').style.display = 'none'; }
        window.onclick = function(event) { if (event.target == document.getElementById('searchModal')) closeModal(); }

        themeBtn.addEventListener('click', () => {
            isDark = !isDark; document.body.setAttribute('data-theme', isDark ? 'dark' : 'light');
            themeBtn.innerHTML = isDark ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
            if (window.cy) window.cy.style().fromJson(getStyleSheet(isDark)).update();
        });

        initGraph();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/papers/<path:filename>')
def serve_paper(filename):
    return send_from_directory(PAPERS_DIR, filename)

@app.route('/api/search_paper', methods=['POST'])
def search_paper():
    query = request.json.get('query')
    if not query: return jsonify([])
    results = []
    
    # Semantic Scholar Search
    try:
        s2_url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=3&fields=title,authors,openAccessPdf"
        s2_res = requests.get(s2_url, timeout=6).json()
        if 'data' in s2_res:
            for item in s2_res['data']:
                if item.get('openAccessPdf') and item['openAccessPdf'].get('url'):
                    # XSS Protection
                    safe_title = html.escape(item.get('title', 'Unknown Title'))
                    safe_authors = html.escape(", ".join([a['name'] for a in item.get('authors', [])]))
                    results.append({ 'title': safe_title, 'authors': safe_authors, 'pdf_url': item['openAccessPdf']['url'], 'source': 'Semantic Scholar' })
    except: pass

    # arXiv Search
    try:
        arxiv_url = f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results=3"
        arxiv_res = requests.get(arxiv_url, timeout=6).text
        root = ET.fromstring(arxiv_res)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        for entry in root.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text.replace('\n', ' ').strip()
            authors = [a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)]
            pdf_link = next((link.attrib.get('href') for link in entry.findall('atom:link', ns) if link.attrib.get('title') == 'pdf'), None)
            if pdf_link:
                if not pdf_link.endswith('.pdf'): pdf_link += '.pdf'
                # XSS Protection
                safe_title = html.escape(title)
                safe_authors = html.escape(", ".join(authors))
                
                if not any(r['title'].lower() == safe_title.lower() for r in results):
                    results.append({ 'title': safe_title, 'authors': safe_authors, 'pdf_url': pdf_link, 'source': 'arXiv' })
    except: pass
    return jsonify(results)

@app.route('/api/add_paper', methods=['POST'])
def add_paper():
    data = request.json
    url = data.get('url', '').strip()
    if not url: return jsonify({"error": "No URL provided"}), 400
    if not url.startswith('http://') and not url.startswith('https://'): url = 'https://' + url
    
    if 'arxiv.org/abs/' in url: url = url.replace('arxiv.org/abs/', 'arxiv.org/pdf/')
    if 'arxiv.org/pdf/' in url and not url.endswith('.pdf'): url += '.pdf'
    
    try:
        headers = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'application/pdf,application/xhtml+xml' }
        r = requests.get(url, headers=headers, stream=True, timeout=10)
        
        if r.status_code == 403: return jsonify({"error": f"Publisher firewall blocked the download. Please download manually and move it to the 'papers' folder."}), 400
        r.raise_for_status()
        
        # --- File Signature (Magic Byte) Validation ---
        iterator = r.iter_content(chunk_size=8192)
        try:
            first_chunk = next(iterator)
        except StopIteration:
            return jsonify({"error": "The downloaded file was empty."}), 400
            
        # A genuine PDF file must start with the hex signature for %PDF-
        if not first_chunk.startswith(b'%PDF-'):
            return jsonify({"error": "File signature invalid. The link did not return a genuine PDF file. It may be behind a paywall."}), 400
            
        parsed = urlparse(url)
        filename = os.path.basename(unquote(parsed.path))
        if not filename.lower().endswith('.pdf'): filename = f"download_{int(time.time())}.pdf"
            
        save_path = os.path.join(PAPERS_DIR, filename)
        
        # Safely write the validated first chunk, then the rest
        with open(save_path, 'wb') as f:
            f.write(first_chunk)
            for chunk in iterator: 
                f.write(chunk)
                
        return jsonify({"success": True, "filename": html.escape(filename)})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Download failed: {html.escape(str(e))}"}), 500

@app.route('/api/graph')
def build_graph():
    papers = []
    for filename in os.listdir(PAPERS_DIR):
        if filename.lower().endswith(".pdf"):
            path = os.path.join(PAPERS_DIR, filename)
            try:
                doc = fitz.open(path)
                text = re.sub(r'\s+', ' ', " ".join([page.get_text() for page in doc]))
                
                title = doc.metadata.get("title", "").strip()
                if not title or title.isnumeric() or len(title) < 5 or title.lower().endswith('.pdf'):
                    first_page_lines = doc[0].get_text("text").split('\n')
                    for line in first_page_lines:
                        clean_line = line.strip()
                        if len(clean_line) > 10 and not clean_line.isnumeric():
                            title = clean_line
                            break
                            
                if not title:
                    title = filename.rsplit('.', 1)[0]
                
                # XSS Protection for Core Data
                papers.append({
                    "id": html.escape(filename), 
                    "title": html.escape(title), 
                    "text": html.escape(text)
                })
            except Exception as e: print(f"Could not read {filename}: {e}")

    elements = [{"group": "nodes", "data": {"id": p["id"], "label": p["title"]}} for p in papers]

    for u in papers:
        u_text_lower = u["text"].lower()
        u_sentences = re.split(r'(?<=[.!?])\s+', u["text"])
        
        for v in papers:
            if u["id"] == v["id"]: continue
            
            v_title_clean = v["title"].lower().strip()
            if len(v_title_clean) < 10: continue
            
            search_title = v_title_clean[:40] 
            title_idx = u_text_lower.rfind(search_title)
            
            if title_idx != -1:
                ref_context = u["text"][max(0, title_idx - 250):title_idx]
                marker = None
                
                brackets = re.findall(r'\[([^\]]+)\]', ref_context)
                if brackets: marker = f"[{brackets[-1]}]"
                else:
                    nums = re.findall(r'(?:\s|^)(\d+)\.\s', ref_context)
                    if nums: marker = f"[{nums[-1]}]"
                    else:
                        years = re.findall(r'\b([12]\d{3}[a-z]?)\b', ref_context)
                        if years: marker = years[-1]
                
                in_text_sentences = []
                bib_start = max(0, title_idx - 80)
                bib_end = min(len(u["text"]), title_idx + len(v["title"]) + 120)
                bib_entry = "... " + u["text"][bib_start:bib_end].strip() + " ..."
                
                # Create a specific class for the JS to target for styling, 
                # ensuring the HTML doesn't break XSS
                try: bib_entry_highlighted = re.sub(f"({re.escape(v['title'][:40])}[^\.]*)", r"<span class='highlight'>\1</span>", bib_entry, flags=re.IGNORECASE)
                except: bib_entry_highlighted = bib_entry
                
                in_text_sentences.append(f"<div style='margin-bottom:8px; color:var(--text-muted);'><i class='fas fa-book'></i> <b>Bibliography Match:</b></div>{bib_entry_highlighted}")
                
                if marker:
                    for sent in u_sentences:
                        if marker.lower() in sent.lower():
                            if search_title not in sent.lower():
                                try:
                                    sent_highlighted = re.sub(f"({re.escape(marker)})", r"<span class='highlight'>\1</span>", sent, flags=re.IGNORECASE)
                                    in_text_sentences.append(f"<div style='margin-bottom:8px; color:var(--text-muted); margin-top:16px;'><i class='fas fa-quote-left'></i> <b>In-Text Citation:</b></div> {sent_highlighted}")
                                except:
                                    in_text_sentences.append(f"<div style='margin-bottom:8px; color:var(--text-muted); margin-top:16px;'><i class='fas fa-quote-left'></i> <b>In-Text Citation:</b></div> {sent}")

                elements.append({ "group": "edges", "data": { "id": f"edge_{u['id']}_{v['id']}", "source": u["id"], "target": v["id"], "citation_number": marker if marker else "", "context": "|||".join(in_text_sentences) } })

    return jsonify(elements)

def open_browser(): webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == '__main__':
    print(f"Starting server... Place your PDFs in: {PAPERS_DIR}")
    
    # Only open the browser once by checking if we are in the reloader process
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Timer(1.25, open_browser).start()
        
    app.run(debug=True, port=5000)
