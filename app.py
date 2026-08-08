import os
import re
import time
import requests
import pymupdf  
import webbrowser
import threading
import html
import json
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, unquote
from flask import Flask, jsonify, send_from_directory, render_template, request

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAPERS_DIR = os.path.join(BASE_DIR, 'papers')
CACHE_FILE = os.path.join(BASE_DIR, '.litgraph.json')

os.makedirs(PAPERS_DIR, exist_ok=True)

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"papers": {}}
    return {"papers": {}}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/papers/<path:filename>')
def serve_paper(filename):
    return send_from_directory(PAPERS_DIR, filename)

@app.route('/api/folders')
def get_folders():
    folders = [{"id": "global", "name": "Global (All Papers)", "path": ""}]
    for root, dirs, files in os.walk(PAPERS_DIR):
        rel_path = os.path.relpath(root, PAPERS_DIR)
        if rel_path == '.': continue
        clean_path = rel_path.replace(os.sep, '/')
        folder_name = os.path.basename(root)
        folders.append({
            "id": html.escape(clean_path), 
            "name": html.escape(folder_name), 
            "path": html.escape(clean_path)
        })
    return jsonify(folders)

@app.route('/api/search_paper', methods=['POST'])
def search_paper():
    query = request.json.get('query')
    if not query: return jsonify([])
    results = []
    
    try:
        s2_url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=3&fields=title,authors,openAccessPdf"
        s2_res = requests.get(s2_url, timeout=6).json()
        if 'data' in s2_res:
            for item in s2_res['data']:
                if item.get('openAccessPdf') and item['openAccessPdf'].get('url'):
                    safe_title = html.escape(item.get('title', 'Unknown Title'))
                    safe_authors = html.escape(", ".join([a['name'] for a in item.get('authors', [])]))
                    results.append({ 'title': safe_title, 'authors': safe_authors, 'pdf_url': item['openAccessPdf']['url'], 'source': 'Semantic Scholar' })
    except: pass

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
    target_folder = data.get('folder', '').strip()
    
    if not url: return jsonify({"error": "No URL provided"}), 400
    if not url.startswith('http://') and not url.startswith('https://'): url = 'https://' + url
    if 'arxiv.org/abs/' in url: url = url.replace('arxiv.org/abs/', 'arxiv.org/pdf/')
    if 'arxiv.org/pdf/' in url and not url.endswith('.pdf'): url += '.pdf'
    
    try:
        headers = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'application/pdf,application/xhtml+xml' }
        r = requests.get(url, headers=headers, stream=True, timeout=10)
        
        if r.status_code == 403: return jsonify({"error": f"Publisher firewall blocked the download. Please download manually."}), 400
        r.raise_for_status()
        
        iterator = r.iter_content(chunk_size=8192)
        try: first_chunk = next(iterator)
        except StopIteration: return jsonify({"error": "The downloaded file was empty."}), 400
            
        if not first_chunk.startswith(b'%PDF-'):
            return jsonify({"error": "File signature invalid. The link did not return a genuine PDF file."}), 400
            
        parsed = urlparse(url)
        filename = os.path.basename(unquote(parsed.path))
        if not filename.lower().endswith('.pdf'): filename = f"download_{int(time.time())}.pdf"
            
        safe_folder = target_folder.replace('..', '').lstrip('/')
        save_dir = os.path.join(PAPERS_DIR, safe_folder)
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)
        
        with open(save_path, 'wb') as f:
            f.write(first_chunk)
            for chunk in iterator: f.write(chunk)
                
        return jsonify({"success": True, "filename": html.escape(filename)})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Download failed: {html.escape(str(e))}"}), 500

@app.route('/api/check_updates')
def check_updates():
    """Checks if the file system differs from the cache."""
    cache = load_cache()
    cached_papers = cache.get("papers", {})
    
    current_files = {}
    for root, dirs, files in os.walk(PAPERS_DIR):
        for file in files:
            if file.lower().endswith('.pdf'):
                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, PAPERS_DIR).replace(os.sep, '/')
                current_files[rel_path] = os.path.getmtime(path)
                
    needs_update = False
    
    # Check for new or modified files
    for rel_path, mtime in current_files.items():
        if rel_path not in cached_papers or cached_papers[rel_path]['mtime'] < mtime:
            needs_update = True
            break
            
    # Check for deleted files
    if not needs_update:
        for rel_path in list(cached_papers.keys()):
            if rel_path not in current_files:
                needs_update = True
                break

    return jsonify({"needs_update": needs_update})

@app.route('/api/build_cache', methods=['POST'])
def build_cache():
    """Parses only new/modified PDFs and updates the cache file."""
    cache = load_cache()
    cached_papers = cache.get("papers", {})
    
    current_files = {}
    for root, dirs, files in os.walk(PAPERS_DIR):
        for file in files:
            if file.lower().endswith('.pdf'):
                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, PAPERS_DIR).replace(os.sep, '/')
                current_files[rel_path] = os.path.getmtime(path)
                
    new_cache_papers = {}
    
    for rel_path, mtime in current_files.items():
        if rel_path in cached_papers and cached_papers[rel_path]['mtime'] == mtime:
            # File is unchanged, keep cached data
            new_cache_papers[rel_path] = cached_papers[rel_path]
        else:
            # Parse new or modified file
            abs_path = os.path.join(PAPERS_DIR, rel_path)
            try:
                doc = pymupdf.open(abs_path)
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
                    title = os.path.basename(rel_path).rsplit('.', 1)[0]
                
                new_cache_papers[rel_path] = {
                    "mtime": mtime,
                    "title": title,
                    "text": text
                }
            except Exception as e:
                print(f"Could not read {rel_path}: {e}")
                
    cache["papers"] = new_cache_papers
    save_cache(cache)
    return jsonify({"success": True})

@app.route('/api/graph')
def build_graph():
    """Builds the graph relationships entirely from the fast JSON cache."""
    target_folder = request.args.get('folder', '').strip()
    safe_folder = target_folder.replace('..', '').lstrip('/')
    
    cache = load_cache()
    cached_papers = cache.get("papers", {})
    papers = []
    
    for rel_path, data in cached_papers.items():
        if safe_folder and safe_folder != 'global':
            # Strict folder matching
            if not rel_path.startswith(safe_folder + '/'):
                continue
                
        papers.append({
            "id": html.escape(rel_path),
            "title": html.escape(data["title"]),
            "text": html.escape(data["text"])
        })

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

def open_browser(): webbrowser.open_new("http://127.0.0.1:8080")

if __name__ == '__main__':
    print(f"Starting server... Place your PDFs in: {PAPERS_DIR}")
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Timer(1.25, open_browser).start()
    app.run(debug=True, port=8080)