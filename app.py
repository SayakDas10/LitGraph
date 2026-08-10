import os
import re
import time
import requests
import pymupdf  
import webbrowser
import threading
import html
import json
import uuid
import shutil
from werkzeug.utils import secure_filename
from flask import Flask, jsonify, send_from_directory, render_template, request

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PAPERS_DIR = os.path.join(BASE_DIR, 'papers')
NOTES_DIR = os.path.join(BASE_DIR, 'notes')
CACHE_FILE = os.path.join(BASE_DIR, '.litgraph.json')

os.makedirs(PAPERS_DIR, exist_ok=True)
os.makedirs(NOTES_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'ppt', 'pptx', 'docx', 'txt', 'pdf', 'md'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"papers": {}, "edges": []}
    return {"papers": {}, "edges": []}

def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/papers/<path:filename>')
def serve_paper(filename):
    return send_from_directory(PAPERS_DIR, filename)

@app.route('/notes/<path:filename>')
def serve_note(filename):
    return send_from_directory(NOTES_DIR, filename)

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

@app.route('/api/add_local_paper', methods=['POST'])
def add_local_paper():
    data = request.json
    source_path = data.get('source_path', '').strip()
    folder_select = data.get('folder_select', '').strip()
    new_folder = data.get('new_folder', '').strip()
    action = data.get('action', 'copy') 
    
    source_path = source_path.strip('\"\'')
    
    if not source_path or not os.path.exists(source_path):
        return jsonify({"error": "File not found. Please check the absolute path."}), 400
        
    if not source_path.lower().endswith('.pdf'):
        return jsonify({"error": "The selected file is not a PDF."}), 400
        
    if new_folder:
        safe_new = new_folder.replace('..', '').lstrip('/')
        target_dir = os.path.join(PAPERS_DIR, safe_new)
    else:
        safe_existing = folder_select.replace('..', '').lstrip('/')
        if safe_existing == 'global' or not safe_existing:
            target_dir = PAPERS_DIR
        else:
            target_dir = os.path.join(PAPERS_DIR, safe_existing)
            
    os.makedirs(target_dir, exist_ok=True)
    
    filename = os.path.basename(source_path)
    dest_path = os.path.join(target_dir, filename)
    
    if os.path.exists(dest_path):
        return jsonify({"error": "A file with this name already exists in the target folder."}), 400
        
    try:
        if action == 'move':
            shutil.move(source_path, dest_path)
        else:
            shutil.copy2(source_path, dest_path)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to {action} file: {str(e)}"}), 500

@app.route('/api/import_library', methods=['POST'])
def import_library():
    data = request.json
    source_path = data.get('source_path', '').strip().strip('\"\'')
    action = data.get('action', 'copy')
    
    if not source_path or not os.path.exists(source_path) or not os.path.isdir(source_path):
        return jsonify({"error": "Invalid folder path. Please provide a valid absolute directory path."}), 400
        
    # Prevent importing the target folder into itself
    if os.path.abspath(source_path) == os.path.abspath(PAPERS_DIR):
        return jsonify({"error": "Cannot import the destination folder into itself."}), 400
        
    imported_count = 0
    try:
        for root, dirs, files in os.walk(source_path):
            for file in files:
                if file.lower().endswith('.pdf'):
                    # Recreate internal folder structure
                    rel_dir = os.path.relpath(root, source_path)
                    if rel_dir == '.':
                        target_dir = PAPERS_DIR
                    else:
                        target_dir = os.path.join(PAPERS_DIR, rel_dir)
                        os.makedirs(target_dir, exist_ok=True)
                    
                    src_file = os.path.join(root, file)
                    dst_file = os.path.join(target_dir, file)
                    
                    # Skip if the file already exists in the destination to prevent overwrites
                    if not os.path.exists(dst_file):
                        if action == 'move':
                            shutil.move(src_file, dst_file)
                        else:
                            shutil.copy2(src_file, dst_file)
                        imported_count += 1
        return jsonify({"success": True, "count": imported_count})
    except Exception as e:
        return jsonify({"error": f"Failed during {action}: {str(e)}"}), 500

@app.route('/api/check_updates')
def check_updates():
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
    for rel_path, mtime in current_files.items():
        if rel_path not in cached_papers or cached_papers[rel_path]['mtime'] < mtime:
            needs_update = True
            break
            
    if not needs_update:
        for rel_path in list(cached_papers.keys()):
            if rel_path not in current_files:
                needs_update = True
                break

    return jsonify({"needs_update": needs_update})

@app.route('/api/build_cache', methods=['POST'])
def build_cache():
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
    texts = {} 
    
    for rel_path, mtime in current_files.items():
        abs_path = os.path.join(PAPERS_DIR, rel_path)
        text = ""
        doc = None
        try:
            doc = pymupdf.open(abs_path)
            text = re.sub(r'\s+', ' ', " ".join([page.get_text() for page in doc]))
        except Exception as e:
            print(f"Could not read {rel_path}: {e}")
            
        texts[rel_path] = text
        
        if rel_path in cached_papers and cached_papers[rel_path]['mtime'] == mtime:
            new_cache_papers[rel_path] = cached_papers[rel_path]
        else:
            existing_status = cached_papers.get(rel_path, {}).get("status", "none")
            existing_uuid = cached_papers.get(rel_path, {}).get("uuid", uuid.uuid4().hex)
            title = None
            
            try:
                if doc:
                    first_page_text = re.sub(r'[^a-zA-Z0-9\s]', ' ', doc[0].get_text("text"))[:150].strip()
                    if first_page_text:
                        s2_url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={first_page_text}&limit=1&fields=title"
                        s2_res = requests.get(s2_url, timeout=4).json()
                        if 'data' in s2_res and len(s2_res['data']) > 0:
                            title = s2_res['data'][0]['title']
                    time.sleep(0.5) 
            except: pass
            
            if not title:
                title = doc.metadata.get("title", "").strip() if doc else ""
                if not title or title.isnumeric() or len(title) < 5 or title.lower().endswith('.pdf'):
                    if doc:
                        first_page_lines = doc[0].get_text("text").split('\n')
                        for line in first_page_lines:
                            clean_line = line.strip()
                            if len(clean_line) > 10 and not clean_line.isnumeric():
                                title = clean_line
                                break
                if not title: title = os.path.basename(rel_path).rsplit('.', 1)[0]
            
            new_cache_papers[rel_path] = {
                "uuid": existing_uuid,
                "mtime": mtime,
                "title": title,
                "status": existing_status
            }
            
    edges = []
    for u_rel_path, u_data in new_cache_papers.items():
        u_text = texts.get(u_rel_path, "")
        u_text_lower = u_text.lower()
        u_sentences = re.split(r'(?<=[.!?])\s+', u_text)
        
        for v_rel_path, v_data in new_cache_papers.items():
            if u_rel_path == v_rel_path: continue
            
            v_title_clean = v_data["title"].lower().strip()
            if len(v_title_clean) < 10: continue
            
            search_title = v_title_clean[:40] 
            title_idx = u_text_lower.rfind(search_title)
            
            if title_idx != -1:
                ref_context = u_text[max(0, title_idx - 250):title_idx]
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
                bib_end = min(len(u_text), title_idx + len(v_data["title"]) + 120)
                
                safe_bib_entry = html.escape("... " + u_text[bib_start:bib_end].strip() + " ...")
                safe_v_title = html.escape(v_data['title'][:40])
                
                try: 
                    bib_entry_highlighted = re.sub(f"({re.escape(safe_v_title)}[^\.]*)", r"<span class='highlight-text'>\1</span>", safe_bib_entry, flags=re.IGNORECASE)
                except: 
                    bib_entry_highlighted = safe_bib_entry
                
                in_text_sentences.append(f"<div style='margin-bottom:8px; color:var(--text-muted);'><i class='fas fa-book'></i> <b>Bibliography Match:</b></div>{bib_entry_highlighted}")
                
                if marker:
                    safe_marker = html.escape(marker)
                    for sent in u_sentences:
                        if marker.lower() in sent.lower():
                            if search_title not in sent.lower():
                                safe_sent = html.escape(sent)
                                try:
                                    sent_highlighted = re.sub(f"({re.escape(safe_marker)})", r"<span class='highlight-text'>\1</span>", safe_sent, flags=re.IGNORECASE)
                                    in_text_sentences.append(f"<div style='margin-bottom:8px; color:var(--text-muted); margin-top:16px;'><i class='fas fa-quote-left'></i> <b>In-Text Citation:</b></div> {sent_highlighted}")
                                except:
                                    in_text_sentences.append(f"<div style='margin-bottom:8px; color:var(--text-muted); margin-top:16px;'><i class='fas fa-quote-left'></i> <b>In-Text Citation:</b></div> {safe_sent}")

                edges.append({
                    "id": f"edge_{u_rel_path}_{v_rel_path}",
                    "source": u_rel_path,
                    "target": v_rel_path,
                    "citation_number": html.escape(marker) if marker else "",
                    "context": "|||".join(in_text_sentences)
                })
                
    cache["papers"] = new_cache_papers
    cache["edges"] = edges
    save_cache(cache) 
    return jsonify({"success": True})

@app.route('/api/update_status', methods=['POST'])
def update_status():
    data = request.json
    paper_id = html.unescape(data.get('id', ''))
    new_status = data.get('status', 'none')
    cache = load_cache()
    if paper_id in cache.get("papers", {}):
        cache["papers"][paper_id]["status"] = new_status
        save_cache(cache)
        return jsonify({"success": True})
    return jsonify({"error": "Paper not found"}), 404

@app.route('/api/update_title', methods=['POST'])
def update_title():
    data = request.json
    paper_id = html.unescape(data.get('id', ''))
    new_title = data.get('title', '').strip()
    if not new_title: return jsonify({"error": "Title cannot be empty"}), 400
    cache = load_cache()
    if paper_id in cache.get("papers", {}):
        cache["papers"][paper_id]["title"] = new_title
        save_cache(cache)
        return jsonify({"success": True})
    return jsonify({"error": "Paper not found"}), 404

@app.route('/api/node_details/<paper_uuid>')
def node_details(paper_uuid):
    txt_path = os.path.join(NOTES_DIR, f"{paper_uuid}.txt")
    text_content = ""
    if os.path.exists(txt_path):
        with open(txt_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
            
    attachments = []
    prefix = f"{paper_uuid}_attachment_"
    for f in os.listdir(NOTES_DIR):
        if f.startswith(prefix):
            original_name = f[len(prefix):]
            attachments.append({"filename": html.escape(f), "original_name": html.escape(original_name)})
            
    return jsonify({"text": text_content, "attachments": attachments})

@app.route('/api/save_note', methods=['POST'])
def save_note():
    data = request.json
    paper_uuid = data.get('uuid')
    text = data.get('text', '')
    if not paper_uuid: return jsonify({"error": "No UUID provided"}), 400
    
    txt_path = os.path.join(NOTES_DIR, f"{paper_uuid}.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(text)
    return jsonify({"success": True})

@app.route('/api/upload_attachment', methods=['POST'])
def upload_attachment():
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    paper_uuid = request.form.get('uuid')
    
    if file.filename == '' or not paper_uuid: return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_name = f"{paper_uuid}_attachment_{filename}"
        file.save(os.path.join(NOTES_DIR, save_name))
        return jsonify({"success": True})
    
    return jsonify({"error": "Invalid file type. Only ppt, docx, txt, pdf, md allowed."}), 400

@app.route('/api/graph')
def build_graph():
    target_folder = request.args.get('folder', '').strip()
    safe_folder = target_folder.replace('..', '').lstrip('/')
    
    cache = load_cache()
    cached_papers = cache.get("papers", {})
    cached_edges = cache.get("edges", [])
    
    papers = []
    valid_node_ids = set()
    
    for rel_path, data in cached_papers.items():
        if safe_folder and safe_folder != 'global':
            if not rel_path.startswith(safe_folder + '/'): continue
            
        papers.append({
            "id": html.escape(rel_path),
            "uuid": html.escape(data.get("uuid", "")),
            "title": html.escape(data.get("title", "")),
            "status": html.escape(data.get("status", "none"))
        })
        valid_node_ids.add(rel_path)

    elements = [{"group": "nodes", "data": {"id": p["id"], "uuid": p["uuid"], "label": p["title"], "status": p["status"]}} for p in papers]

    for edge in cached_edges:
        if edge["source"] in valid_node_ids and edge["target"] in valid_node_ids:
            elements.append({
                "group": "edges",
                "data": {
                    "id": html.escape(edge["id"]),
                    "source": html.escape(edge["source"]),
                    "target": html.escape(edge["target"]),
                    "citation_number": edge.get("citation_number", ""),
                    "context": edge.get("context", "")
                }
            })

    return jsonify(elements)

def open_browser(): webbrowser.open_new("http://127.0.0.1:5001")

if __name__ == '__main__':
    print(f"Starting server... Place your PDFs in: {PAPERS_DIR}")
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Timer(1.25, open_browser).start()
    app.run(debug=True, port=5001)