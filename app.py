from __future__ import annotations

import os
import secrets
import shutil
import threading
import webbrowser
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, session
from werkzeug.utils import secure_filename

from litgraph.config import (
    ALLOWED_ATTACHMENT_EXTENSIONS, DATABASE_FILE, LEGACY_CACHE_FILE, MAX_ATTACHMENT_BYTES,
    NOTES_DIR, ONLINE_METADATA, PAPERS_DIR, paths_overlap, resolved_child,
)
from litgraph.services import build_edges, is_pdf, paper_record, valid_attachment
from litgraph.storage import Repository
from litgraph.evidence import EXTRACTION_METHODS, VERIFICATION_STATES, validate_evidence_value, validate_field

app = Flask(__name__)
app.secret_key = os.getenv("LITGRAPH_SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = MAX_ATTACHMENT_BYTES
repository = Repository(DATABASE_FILE, LEGACY_CACHE_FILE)
repository.initialize()
sync_lock = threading.Lock()
sync_jobs: dict[str, dict] = {}
sync_jobs_lock = threading.Lock()


def api_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def require_json() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def csrf_protected(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        expected = session.get("csrf_token")
        supplied = request.headers.get("X-LitGraph-CSRF")
        if not expected or not secrets.compare_digest(expected, supplied or ""):
            return api_error("Invalid or missing request token", 403)
        return function(*args, **kwargs)
    return wrapper


def valid_uuid(value: str) -> bool:
    return len(value) == 32 and all(character in "0123456789abcdef" for character in value.lower())


def known_paper_uuid(value: str):
    return repository.paper_by_uuid(value) if valid_uuid(value) else None


def refresh_paper_search(paper_uuid: str) -> None:
    note_path = NOTES_DIR / f"{paper_uuid}.txt"
    note_text = note_path.read_text(encoding="utf-8", errors="replace") if note_path.exists() else ""
    repository.refresh_search_entry(paper_uuid, note_text)


def validated_schema_payload(data: dict) -> tuple[str, str, list[dict]]:
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    raw_fields = data.get("fields", [])
    if not name or len(name) > 120:
        raise ValueError("Template name must contain between 1 and 120 characters")
    if len(description) > 1000 or not isinstance(raw_fields, list) or not raw_fields:
        raise ValueError("Provide a description of at most 1000 characters and at least one field")
    fields = [validate_field(field) for field in raw_fields]
    keys = [field["key"] for field in fields]
    if len(keys) != len(set(keys)):
        raise ValueError("Field names must be unique within a template")
    return name, description, fields


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'"
    )
    return response


@app.errorhandler(413)
def upload_too_large(_error):
    return api_error("Attachment exceeds the configured size limit", 413)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/session")
def api_session():
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return jsonify({"csrf_token": session["csrf_token"], "online_metadata": ONLINE_METADATA})


@app.route("/papers/<path:filename>")
def serve_paper(filename):
    if filename not in repository.paper_map():
        return api_error("Paper not found", 404)
    return send_from_directory(PAPERS_DIR, filename, mimetype="application/pdf")


@app.route("/notes/<filename>")
def serve_note(filename):
    safe_name = secure_filename(filename)
    paper_uuid = safe_name.split("_attachment_", 1)[0]
    if safe_name != filename or not known_paper_uuid(paper_uuid):
        return api_error("Attachment not found", 404)
    return send_from_directory(NOTES_DIR, safe_name, as_attachment=True)


@app.route("/api/folders")
def get_folders():
    folders = [{"id": "global", "name": "Global (All Papers)", "path": ""}]
    for root, dirs, _files in os.walk(PAPERS_DIR):
        dirs.sort(key=str.lower)
        relative = Path(root).relative_to(PAPERS_DIR)
        if relative == Path("."):
            continue
        clean_path = relative.as_posix()
        folders.append({"id": clean_path, "name": relative.name, "path": clean_path})
    return jsonify(folders)


@app.route("/api/add_local_paper", methods=["POST"])
@csrf_protected
def add_local_paper():
    try:
        data = require_json()
        source = Path(str(data.get("source_path", "")).strip().strip("\"'")).expanduser().resolve()
        action = data.get("action", "copy")
        if action not in {"copy", "move"}:
            return api_error("Action must be copy or move")
        if not source.is_file() or source.suffix.lower() != ".pdf" or not is_pdf(source):
            return api_error("Select a readable PDF file")
        requested_folder = str(data.get("new_folder") or data.get("folder_select") or "").strip()
        if requested_folder == "global":
            requested_folder = ""
        destination_directory = resolved_child(PAPERS_DIR, requested_folder)
        destination_directory.mkdir(parents=True, exist_ok=True)
        destination = resolved_child(destination_directory, source.name)
        if destination.exists():
            return api_error("A file with this name already exists in the destination")
        shutil.move(source, destination) if action == "move" else shutil.copy2(source, destination)
        return jsonify({"success": True})
    except (ValueError, OSError) as error:
        return api_error(str(error))


@app.route("/api/import_library", methods=["POST"])
@csrf_protected
def import_library():
    try:
        data = require_json()
        source = Path(str(data.get("source_path", "")).strip().strip("\"'")).expanduser().resolve()
        action = data.get("action", "copy")
        if action not in {"copy", "move"}:
            return api_error("Action must be copy or move")
        if not source.is_dir():
            return api_error("Select a valid library directory")
        if paths_overlap(source, PAPERS_DIR):
            return api_error("The source library and LitGraph papers directory must not contain one another")
        imported = skipped = 0
        for root, dirs, files in os.walk(source):
            dirs.sort(key=str.lower)
            relative_directory = Path(root).resolve().relative_to(source)
            target_directory = resolved_child(PAPERS_DIR, relative_directory.as_posix())
            for filename in files:
                source_file = Path(root) / filename
                if source_file.suffix.lower() != ".pdf" or not is_pdf(source_file):
                    continue
                target_directory.mkdir(parents=True, exist_ok=True)
                destination = resolved_child(target_directory, source_file.name)
                if destination.exists():
                    skipped += 1
                    continue
                shutil.move(source_file, destination) if action == "move" else shutil.copy2(source_file, destination)
                imported += 1
        return jsonify({"success": True, "count": imported, "skipped": skipped})
    except (ValueError, OSError) as error:
        return api_error(str(error))


def library_files() -> dict[str, Path]:
    return {path.relative_to(PAPERS_DIR).as_posix(): path for path in PAPERS_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() == ".pdf"}


@app.route("/api/check_updates")
def check_updates():
    cached = repository.paper_map()
    current = library_files()
    if set(cached) != set(current):
        return jsonify({"needs_update": True})
    changed = any(cached[path]["mtime"] != file.stat().st_mtime or cached[path]["size"] != file.stat().st_size
                  for path, file in current.items())
    return jsonify({"needs_update": changed})


@app.route("/api/build_cache", methods=["POST"])
@csrf_protected
def build_cache():
    with sync_jobs_lock:
        running = next((job_id for job_id, job in sync_jobs.items() if job["status"] in {"queued", "running"}), None)
        if running:
            return jsonify({"job_id": running, "status": sync_jobs[running]["status"]}), 202
        job_id = secrets.token_hex(12)
        sync_jobs[job_id] = {
            "status": "queued", "current": "", "processed": 0, "total": 0,
            "changed": 0, "removed": 0, "errors": [], "cancel_requested": False,
        }
    threading.Thread(target=run_library_sync, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id, "status": "queued"}), 202


def update_sync_job(job_id: str, **values) -> None:
    with sync_jobs_lock:
        if job_id in sync_jobs:
            sync_jobs[job_id].update(values)


def run_library_sync(job_id: str) -> None:
    with sync_lock:
        update_sync_job(job_id, status="running")
        try:
            current = library_files()
            cached = repository.paper_map()
            changed_paths: set[str] = set()
            removed_paths = set(cached) - set(current)
            errors = []
            update_sync_job(job_id, total=len(current))
            for processed, (relative_path, absolute_path) in enumerate(current.items(), start=1):
                with sync_jobs_lock:
                    if sync_jobs[job_id]["cancel_requested"]:
                        sync_jobs[job_id].update(status="cancelled", current="")
                        return
                update_sync_job(job_id, current=relative_path, processed=processed - 1)
                stat = absolute_path.stat()
                previous = cached.get(relative_path)
                if not (previous and previous["mtime"] == stat.st_mtime and previous["size"] == stat.st_size and previous["text"]):
                    try:
                        record = paper_record(relative_path, absolute_path, previous, ONLINE_METADATA)
                        repository.upsert_paper(record)
                        # Upserting the PDF text refreshes the search row; merge the
                        # separate note/evidence content back into that same row.
                        refresh_paper_search(record["uuid"])
                        changed_paths.add(relative_path)
                    except (OSError, RuntimeError, ValueError) as error:
                        errors.append({"path": relative_path, "error": str(error)})
                update_sync_job(job_id, processed=processed, changed=len(changed_paths), errors=errors)
            removed = repository.delete_missing(set(current))
            affected = changed_paths | removed_paths
            if affected:
                repository.replace_edges_for_paths(affected, build_edges(repository.papers(), affected))
            update_sync_job(
                job_id, status="complete", current="", processed=len(current), changed=len(changed_paths),
                removed=removed, errors=errors,
            )
        except Exception as error:
            update_sync_job(job_id, status="failed", current="", errors=[{"path": "", "error": str(error)}])


@app.route("/api/sync_status/<job_id>")
def sync_status(job_id):
    with sync_jobs_lock:
        job = sync_jobs.get(job_id)
        return jsonify(job) if job else api_error("Synchronization job not found", 404)


@app.route("/api/sync_status/<job_id>/cancel", methods=["POST"])
@csrf_protected
def cancel_sync(job_id):
    with sync_jobs_lock:
        job = sync_jobs.get(job_id)
        if not job:
            return api_error("Synchronization job not found", 404)
        if job["status"] in {"queued", "running"}:
            job["cancel_requested"] = True
    return jsonify({"success": True})


@app.route("/api/delete_paper", methods=["POST"])
@csrf_protected
def delete_paper():
    try:
        paper_id = str(require_json().get("id", ""))
        paper = repository.paper_map().get(paper_id)
        if not paper:
            return api_error("Paper not found", 404)
        pdf_path = resolved_child(PAPERS_DIR, paper_id)
        if pdf_path.exists():
            pdf_path.unlink()
        deleted = repository.delete_paper(paper_id)
        if deleted:
            (NOTES_DIR / f"{deleted['uuid']}.txt").unlink(missing_ok=True)
            for attachment in NOTES_DIR.glob(f"{deleted['uuid']}_attachment_*"):
                attachment.unlink(missing_ok=True)
        return jsonify({"success": True})
    except (ValueError, OSError) as error:
        return api_error(str(error), 500)


@app.route("/api/update_status", methods=["POST"])
@csrf_protected
def update_status():
    try:
        data = require_json()
        status = data.get("status", "none")
        if status not in {"none", "read", "prioritize"}:
            return api_error("Invalid paper status")
        return jsonify({"success": True}) if repository.set_status(str(data.get("id", "")), status) else api_error("Paper not found", 404)
    except ValueError as error:
        return api_error(str(error))


@app.route("/api/update_title", methods=["POST"])
@csrf_protected
def update_title():
    try:
        data = require_json()
        title = str(data.get("title", "")).strip()
        if not title or len(title) > 500:
            return api_error("Title must contain between 1 and 500 characters")
        if not repository.set_title(str(data.get("id", "")), title):
            return api_error("Paper not found", 404)
        paper_id = str(data.get("id", ""))
        paper = repository.paper_map().get(paper_id)
        if paper:
            refresh_paper_search(paper["uuid"])
        repository.replace_edges_for_paths({paper_id}, build_edges(repository.papers(), {paper_id}))
        return jsonify({"success": True})
    except ValueError as error:
        return api_error(str(error))


@app.route("/api/node_details/<paper_uuid>")
def node_details(paper_uuid):
    if not known_paper_uuid(paper_uuid):
        return api_error("Paper not found", 404)
    note_path = NOTES_DIR / f"{paper_uuid}.txt"
    text = note_path.read_text(encoding="utf-8") if note_path.exists() else ""
    attachments = [{"filename": path.name, "original_name": path.name.split("_attachment_", 1)[1]}
                   for path in sorted(NOTES_DIR.glob(f"{paper_uuid}_attachment_*")) if path.is_file()]
    return jsonify({"text": text, "attachments": attachments})


@app.route("/api/save_note", methods=["POST"])
@csrf_protected
def save_note():
    try:
        data = require_json()
        paper_uuid = str(data.get("uuid", ""))
        if not known_paper_uuid(paper_uuid):
            return api_error("Paper not found", 404)
        (NOTES_DIR / f"{paper_uuid}.txt").write_text(str(data.get("text", "")), encoding="utf-8")
        refresh_paper_search(paper_uuid)
        return jsonify({"success": True})
    except (ValueError, OSError) as error:
        return api_error(str(error), 500)


@app.route("/api/upload_attachment", methods=["POST"])
@csrf_protected
def upload_attachment():
    uploaded = request.files.get("file")
    paper_uuid = request.form.get("uuid", "")
    if not uploaded or not uploaded.filename or not known_paper_uuid(paper_uuid):
        return api_error("Select a file and a valid paper")
    filename = secure_filename(uploaded.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        return api_error("Unsupported attachment type")
    if not valid_attachment(uploaded.stream, extension):
        return api_error("The file content does not match its extension")
    destination = NOTES_DIR / f"{paper_uuid}_attachment_{filename}"
    if destination.exists():
        return api_error("An attachment with this name already exists", 409)
    uploaded.save(destination)
    return jsonify({"success": True})


@app.route("/api/evidence/schemas")
def evidence_schemas():
    return jsonify(repository.schemas())


@app.route("/api/evidence/schemas", methods=["POST"])
@csrf_protected
def create_evidence_schema():
    try:
        name, description, fields = validated_schema_payload(require_json())
        schema_id = repository.save_custom_schema(name, description, fields)
        return jsonify({"success": True, "id": schema_id}), 201
    except ValueError as error:
        return api_error(str(error))


@app.route("/api/evidence/schemas/<schema_id>", methods=["PUT"])
@csrf_protected
def update_evidence_schema(schema_id):
    try:
        name, description, fields = validated_schema_payload(require_json())
        repository.save_custom_schema(name, description, fields, schema_id)
        # Editing a template may remove fields and their stored values.
        for paper in repository.papers():
            refresh_paper_search(paper["uuid"])
        return jsonify({"success": True})
    except ValueError as error:
        return api_error(str(error), 404 if str(error) == "Template not found" else 400)


@app.route("/api/evidence/schemas/<schema_id>", methods=["DELETE"])
@csrf_protected
def delete_evidence_schema(schema_id):
    if not repository.delete_custom_schema(schema_id):
        return api_error("Only existing custom templates can be deleted", 400)
    for paper in repository.papers():
        refresh_paper_search(paper["uuid"])
    return jsonify({"success": True})


@app.route("/api/evidence/<paper_uuid>")
def paper_evidence(paper_uuid):
    evidence = repository.evidence_for_paper(paper_uuid) if valid_uuid(paper_uuid) else None
    return jsonify(evidence) if evidence else api_error("Paper not found", 404)


@app.route("/api/evidence/<paper_uuid>/schemas", methods=["POST"])
@csrf_protected
def assign_paper_schema(paper_uuid):
    try:
        data = require_json()
        schema_id = str(data.get("schema_id", ""))
        if not known_paper_uuid(paper_uuid) or not repository.schema(schema_id):
            return api_error("Paper or template not found", 404)
        repository.set_paper_schema(paper_uuid, schema_id, bool(data.get("enabled", True)))
        return jsonify({"success": True})
    except ValueError as error:
        return api_error(str(error))


@app.route("/api/evidence/projects")
def project_evidence_schemas():
    folder = request.args.get("folder", "").strip().strip("/")
    try:
        if folder:
            resolved_child(PAPERS_DIR, folder)
        return jsonify({"folder": folder, "schema_ids": repository.folder_schema_ids(folder), "schemas": repository.schemas()})
    except ValueError as error:
        return api_error(str(error))


@app.route("/api/evidence/projects", methods=["POST"])
@csrf_protected
def assign_project_schema():
    try:
        data = require_json()
        folder = str(data.get("folder", "")).strip().strip("/")
        schema_id = str(data.get("schema_id", ""))
        if folder:
            resolved_child(PAPERS_DIR, folder)
        if not repository.schema(schema_id):
            return api_error("Template not found", 404)
        repository.set_folder_schema(folder, schema_id, bool(data.get("enabled", True)))
        return jsonify({"success": True})
    except ValueError as error:
        return api_error(str(error))


@app.route("/api/evidence/<paper_uuid>/values/<field_id>", methods=["PUT", "DELETE"])
@csrf_protected
def evidence_value(paper_uuid, field_id):
    evidence = repository.evidence_for_paper(paper_uuid) if valid_uuid(paper_uuid) else None
    if not evidence:
        return api_error("Paper not found", 404)
    fields = {field["id"]: field for schema in evidence["schemas"] if schema["id"] in evidence["active_schema_ids"]
              for field in schema["fields"]}
    field = fields.get(field_id)
    if not field:
        return api_error("Field is not active for this paper", 404)
    if request.method == "DELETE":
        repository.delete_evidence_value(paper_uuid, field_id)
        refresh_paper_search(paper_uuid)
        return jsonify({"success": True})
    try:
        data = require_json()
        value = validate_evidence_value(field["field_type"], data.get("value"))
        method = str(data.get("extraction_method", "manual"))
        verification = str(data.get("verification_status", "confirmed"))
        if method not in EXTRACTION_METHODS or verification not in VERIFICATION_STATES:
            raise ValueError("Invalid extraction method or verification state")
        confidence = data.get("confidence")
        confidence = None if confidence in (None, "") else float(confidence)
        if confidence is not None and not 0 <= confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        repository.save_evidence_value(paper_uuid, field_id, value, {
            "source_excerpt": str(data.get("source_excerpt", ""))[:10_000],
            "page": str(data.get("page", ""))[:40], "location": str(data.get("location", ""))[:500],
            "extraction_method": method, "confidence": confidence, "verification_status": verification,
        })
        refresh_paper_search(paper_uuid)
        return jsonify({"success": True})
    except (TypeError, ValueError) as error:
        return api_error(str(error))


@app.route("/api/graph")
def graph():
    folder = request.args.get("folder", "").strip().strip("/")
    try:
        if folder and folder != "global":
            resolved_child(PAPERS_DIR, folder)
    except ValueError as error:
        return api_error(str(error))
    selected = [paper for paper in repository.papers()
                if not folder or folder == "global" or paper["path"].startswith(folder + "/")]
    ids = {paper["path"] for paper in selected}
    evidence_counts = repository.evidence_counts()
    elements = [{"group": "nodes", "data": {
        "id": paper["path"], "uuid": paper["uuid"], "label": paper["title"],
        "short_label": paper["title"][:55] + ("…" if len(paper["title"]) > 55 else ""),
        "status": paper["status"], "metadata_source": paper["metadata_source"],
        "evidence_count": evidence_counts.get(paper["uuid"], 0),
        "has_notes": (NOTES_DIR / f"{paper['uuid']}.txt").exists(),
    }} for paper in selected]
    elements.extend({"group": "edges", "data": {
        "id": f"edge:{edge['source']}->{edge['target']}", **edge,
    }} for edge in repository.edges() if edge["source"] in ids and edge["target"] in ids)
    return jsonify(elements)


@app.route("/api/search")
def search_library():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])
    try:
        return jsonify(repository.search(query, request.args.get("limit", 30, type=int)))
    except Exception:
        return api_error("Search query could not be processed")


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5001")


if __name__ == "__main__":
    print(f"Starting LitGraph. Paper library: {PAPERS_DIR}")
    threading.Timer(1.25, open_browser).start()
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)
