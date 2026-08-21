from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Iterable

from litgraph.evidence import BUILTIN_SCHEMAS


class Repository:
    """Thread-safe SQLite repository for papers and citation edges."""

    def __init__(self, database_file: Path, legacy_cache_file: Path | None = None):
        self.database_file = database_file
        self.legacy_cache_file = legacy_cache_file
        self._write_lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_file, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self._write_lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    path TEXT PRIMARY KEY,
                    uuid TEXT NOT NULL UNIQUE,
                    mtime REAL NOT NULL,
                    size INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    manual_title INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'none'
                        CHECK(status IN ('none', 'read', 'prioritize')),
                    text TEXT NOT NULL DEFAULT '',
                    metadata_source TEXT NOT NULL DEFAULT 'local'
                );
                CREATE TABLE IF NOT EXISTS edges (
                    source TEXT NOT NULL REFERENCES papers(path) ON DELETE CASCADE,
                    target TEXT NOT NULL REFERENCES papers(path) ON DELETE CASCADE,
                    marker TEXT NOT NULL DEFAULT '',
                    contexts TEXT NOT NULL DEFAULT '[]',
                    bibliography TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0,
                    method TEXT NOT NULL DEFAULT 'title-reference-match',
                    PRIMARY KEY (source, target)
                );
                CREATE TABLE IF NOT EXISTS evidence_schemas (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    builtin INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS evidence_fields (
                    id TEXT PRIMARY KEY,
                    schema_id TEXT NOT NULL REFERENCES evidence_schemas(id) ON DELETE CASCADE,
                    field_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    field_type TEXT NOT NULL,
                    unit TEXT NOT NULL DEFAULT '',
                    options TEXT NOT NULL DEFAULT '[]',
                    group_name TEXT NOT NULL DEFAULT '',
                    position INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(schema_id, field_key)
                );
                CREATE TABLE IF NOT EXISTS paper_schema_overrides (
                    paper_uuid TEXT NOT NULL REFERENCES papers(uuid) ON DELETE CASCADE,
                    schema_id TEXT NOT NULL REFERENCES evidence_schemas(id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL,
                    PRIMARY KEY (paper_uuid, schema_id)
                );
                CREATE TABLE IF NOT EXISTS folder_schemas (
                    folder_path TEXT NOT NULL,
                    schema_id TEXT NOT NULL REFERENCES evidence_schemas(id) ON DELETE CASCADE,
                    PRIMARY KEY (folder_path, schema_id)
                );
                CREATE TABLE IF NOT EXISTS evidence_values (
                    paper_uuid TEXT NOT NULL REFERENCES papers(uuid) ON DELETE CASCADE,
                    field_id TEXT NOT NULL REFERENCES evidence_fields(id) ON DELETE CASCADE,
                    value_json TEXT NOT NULL DEFAULT 'null',
                    source_excerpt TEXT NOT NULL DEFAULT '',
                    page TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    extraction_method TEXT NOT NULL DEFAULT 'manual',
                    confidence REAL,
                    verification_status TEXT NOT NULL DEFAULT 'confirmed',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (paper_uuid, field_id)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
                    uuid UNINDEXED,
                    path,
                    title,
                    content,
                    tokenize='porter unicode61'
                );
                """
            )
            self._seed_builtin_schemas(connection)
            if connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 0:
                self._migrate_legacy(connection)
            if connection.execute("SELECT COUNT(*) FROM search_index").fetchone()[0] == 0:
                self._rebuild_search_index(connection)

    def _rebuild_search_index(self, connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM search_index")
        connection.execute(
            """INSERT INTO search_index (uuid, path, title, content)
               SELECT uuid, path, title, text FROM papers"""
        )

    def _seed_builtin_schemas(self, connection: sqlite3.Connection) -> None:
        first_install = connection.execute("SELECT COUNT(*) FROM evidence_schemas").fetchone()[0] == 0
        for schema in BUILTIN_SCHEMAS:
            connection.execute(
                "INSERT OR IGNORE INTO evidence_schemas (id, name, description, builtin) VALUES (?, ?, ?, 1)",
                (schema["id"], schema["name"], schema["description"]),
            )
            for position, (key, label, field_type, extra) in enumerate(schema["fields"]):
                options = extra.split("|") if field_type == "single_choice" and extra else []
                unit = "" if options else extra
                connection.execute(
                    """INSERT OR IGNORE INTO evidence_fields
                       (id, schema_id, field_key, label, field_type, unit, options, position)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (f"{schema['id']}:{key}", schema["id"], key, label, field_type, unit,
                     json.dumps(options), position),
                )
        if first_install:
            connection.execute(
                "INSERT INTO folder_schemas (folder_path, schema_id) VALUES ('', 'generic_research')"
            )

    def _migrate_legacy(self, connection: sqlite3.Connection) -> None:
        if not self.legacy_cache_file or not self.legacy_cache_file.exists():
            return
        try:
            legacy = json.loads(self.legacy_cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for path, data in legacy.get("papers", {}).items():
            paper_uuid = data.get("uuid", "")
            if len(paper_uuid) != 32:
                continue
            status = data.get("status", "none")
            connection.execute(
                """INSERT OR IGNORE INTO papers
                   (path, uuid, mtime, size, title, manual_title, status, text)
                   VALUES (?, ?, ?, 0, ?, 1, ?, '')""",
                (path, paper_uuid, data.get("mtime", 0), data.get("title") or Path(path).stem,
                 status if status in {"none", "read", "prioritize"} else "none"),
            )

    def papers(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM papers ORDER BY path COLLATE NOCASE").fetchall()
        return [dict(row) for row in rows]

    def paper_map(self) -> dict[str, dict[str, Any]]:
        return {paper["path"]: paper for paper in self.papers()}

    def paper_by_uuid(self, paper_uuid: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM papers WHERE uuid = ?", (paper_uuid,)).fetchone()
        return dict(row) if row else None

    def upsert_paper(self, paper: dict[str, Any]) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO papers
                       (path, uuid, mtime, size, title, manual_title, status, text, metadata_source)
                   VALUES
                       (:path, :uuid, :mtime, :size, :title, :manual_title, :status, :text, :metadata_source)
                   ON CONFLICT(path) DO UPDATE SET
                       uuid = excluded.uuid, mtime = excluded.mtime, size = excluded.size,
                       title = CASE WHEN papers.manual_title = 1 THEN papers.title ELSE excluded.title END,
                       manual_title = papers.manual_title, status = papers.status, text = excluded.text,
                       metadata_source = CASE WHEN papers.manual_title = 1 THEN papers.metadata_source ELSE excluded.metadata_source END""",
                paper,
            )
            self._refresh_search_entry(connection, paper["uuid"], "")

    def delete_missing(self, current_paths: set[str]) -> int:
        with self._write_lock, self._connect() as connection:
            existing = {row[0] for row in connection.execute("SELECT path FROM papers")}
            missing = existing - current_paths
            missing_uuids = [row[0] for row in connection.execute(
                f"SELECT uuid FROM papers WHERE path IN ({','.join('?' for _ in missing)})", tuple(missing)
            )] if missing else []
            connection.executemany("DELETE FROM papers WHERE path = ?", ((path,) for path in missing))
            connection.executemany("DELETE FROM search_index WHERE uuid = ?", ((item,) for item in missing_uuids))
        return len(missing)

    def delete_paper(self, path: str) -> dict[str, Any] | None:
        with self._write_lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM papers WHERE path = ?", (path,)).fetchone()
            if not row:
                return None
            connection.execute("DELETE FROM search_index WHERE uuid = ?", (row["uuid"],))
            connection.execute("DELETE FROM papers WHERE path = ?", (path,))
        return dict(row)

    def set_status(self, path: str, status: str) -> bool:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute("UPDATE papers SET status = ? WHERE path = ?", (status, path))
        return cursor.rowcount == 1

    def set_title(self, path: str, title: str) -> bool:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE papers SET title = ?, manual_title = 1, metadata_source = 'manual' WHERE path = ?",
                (title, path),
            )
            if cursor.rowcount == 1:
                paper_uuid = connection.execute("SELECT uuid FROM papers WHERE path = ?", (path,)).fetchone()[0]
                self._refresh_search_entry(connection, paper_uuid, "")
        return cursor.rowcount == 1

    def replace_edges(self, edges: Iterable[dict[str, Any]]) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute("DELETE FROM edges")
            connection.executemany(
                """INSERT INTO edges
                   (source, target, marker, contexts, bibliography, confidence, method)
                   VALUES (:source, :target, :marker, :contexts, :bibliography, :confidence, :method)""",
                list(edges),
            )

    def replace_edges_for_paths(self, affected_paths: set[str], edges: Iterable[dict[str, Any]]) -> None:
        if not affected_paths:
            return
        placeholders = ",".join("?" for _ in affected_paths)
        parameters = tuple(affected_paths)
        with self._write_lock, self._connect() as connection:
            connection.execute(
                f"DELETE FROM edges WHERE source IN ({placeholders}) OR target IN ({placeholders})",
                parameters + parameters,
            )
            connection.executemany(
                """INSERT INTO edges
                   (source, target, marker, contexts, bibliography, confidence, method)
                   VALUES (:source, :target, :marker, :contexts, :bibliography, :confidence, :method)""",
                list(edges),
            )

    def edges(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM edges ORDER BY source, target").fetchall()
        result = []
        for row in rows:
            edge = dict(row)
            edge["contexts"] = json.loads(edge["contexts"])
            result.append(edge)
        return result

    def schemas(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            schemas = [dict(row) for row in connection.execute(
                "SELECT * FROM evidence_schemas ORDER BY builtin DESC, name COLLATE NOCASE"
            )]
            fields = [dict(row) for row in connection.execute(
                "SELECT * FROM evidence_fields ORDER BY schema_id, position, label COLLATE NOCASE"
            )]
        by_schema = {schema["id"]: {**schema, "builtin": bool(schema["builtin"]), "fields": []} for schema in schemas}
        for field in fields:
            field["options"] = json.loads(field["options"])
            by_schema[field["schema_id"]]["fields"].append(field)
        return list(by_schema.values())

    def schema(self, schema_id: str) -> dict[str, Any] | None:
        return next((schema for schema in self.schemas() if schema["id"] == schema_id), None)

    def save_custom_schema(self, name: str, description: str, fields: list[dict[str, Any]], schema_id: str = "") -> str:
        with self._write_lock, self._connect() as connection:
            if schema_id:
                existing = connection.execute(
                    "SELECT builtin FROM evidence_schemas WHERE id = ?", (schema_id,)
                ).fetchone()
                if not existing:
                    raise ValueError("Template not found")
                if existing[0]:
                    raise ValueError("Built-in templates cannot be edited")
                connection.execute(
                    "UPDATE evidence_schemas SET name = ?, description = ? WHERE id = ?",
                    (name, description, schema_id),
                )
                existing_fields = {
                    row[0] for row in connection.execute(
                        "SELECT id FROM evidence_fields WHERE schema_id = ?", (schema_id,)
                    )
                }
            else:
                schema_id = f"custom_{uuid.uuid4().hex}"
                connection.execute(
                    "INSERT INTO evidence_schemas (id, name, description, builtin) VALUES (?, ?, ?, 0)",
                    (schema_id, name, description),
                )
                existing_fields = set()

            retained = set()
            for position, field in enumerate(fields):
                field_id = field.get("id") if field.get("id") in existing_fields else f"field_{uuid.uuid4().hex}"
                retained.add(field_id)
                connection.execute(
                    """INSERT INTO evidence_fields
                       (id, schema_id, field_key, label, field_type, unit, options, group_name, position)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET field_key=excluded.field_key, label=excluded.label,
                           field_type=excluded.field_type, unit=excluded.unit, options=excluded.options,
                           group_name=excluded.group_name, position=excluded.position""",
                    (field_id, schema_id, field["key"], field["label"], field["type"], field["unit"],
                     json.dumps(field["options"]), field["group_name"], position),
                )
            removed = existing_fields - retained
            connection.executemany("DELETE FROM evidence_fields WHERE id = ?", ((item,) for item in removed))
        return schema_id

    def delete_custom_schema(self, schema_id: str) -> bool:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM evidence_schemas WHERE id = ? AND builtin = 0", (schema_id,)
            )
        return cursor.rowcount == 1

    def set_paper_schema(self, paper_uuid: str, schema_id: str, enabled: bool) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO paper_schema_overrides (paper_uuid, schema_id, enabled) VALUES (?, ?, ?)
                   ON CONFLICT(paper_uuid, schema_id) DO UPDATE SET enabled = excluded.enabled""",
                (paper_uuid, schema_id, int(enabled)),
            )

    def set_folder_schema(self, folder_path: str, schema_id: str, enabled: bool) -> None:
        with self._write_lock, self._connect() as connection:
            if enabled:
                connection.execute(
                    "INSERT OR IGNORE INTO folder_schemas (folder_path, schema_id) VALUES (?, ?)",
                    (folder_path, schema_id),
                )
            else:
                connection.execute(
                    "DELETE FROM folder_schemas WHERE folder_path = ? AND schema_id = ?",
                    (folder_path, schema_id),
                )

    def folder_schema_ids(self, folder_path: str) -> list[str]:
        with self._connect() as connection:
            return [row[0] for row in connection.execute(
                "SELECT schema_id FROM folder_schemas WHERE folder_path = ? ORDER BY schema_id", (folder_path,)
            )]

    def evidence_for_paper(self, paper_uuid: str) -> dict[str, Any] | None:
        paper = self.paper_by_uuid(paper_uuid)
        if not paper:
            return None
        schemas = self.schemas()
        with self._connect() as connection:
            folder_assignments = [dict(row) for row in connection.execute("SELECT * FROM folder_schemas")]
            overrides = {row[0]: bool(row[1]) for row in connection.execute(
                "SELECT schema_id, enabled FROM paper_schema_overrides WHERE paper_uuid = ?", (paper_uuid,)
            )}
            values = [dict(row) for row in connection.execute(
                "SELECT * FROM evidence_values WHERE paper_uuid = ?", (paper_uuid,)
            )]
        active = set()
        for assignment in folder_assignments:
            folder = assignment["folder_path"]
            if not folder or paper["path"].startswith(folder.rstrip("/") + "/"):
                active.add(assignment["schema_id"])
        for schema_id, enabled in overrides.items():
            active.add(schema_id) if enabled else active.discard(schema_id)
        value_map = {}
        for value in values:
            value["value"] = json.loads(value.pop("value_json"))
            value_map[value["field_id"]] = value
        return {
            "paper": {"uuid": paper_uuid, "path": paper["path"]},
            "schemas": schemas, "active_schema_ids": sorted(active), "values": value_map,
        }

    def save_evidence_value(self, paper_uuid: str, field_id: str, value: Any, provenance: dict[str, Any]) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO evidence_values
                   (paper_uuid, field_id, value_json, source_excerpt, page, location,
                    extraction_method, confidence, verification_status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(paper_uuid, field_id) DO UPDATE SET
                       value_json=excluded.value_json, source_excerpt=excluded.source_excerpt,
                       page=excluded.page, location=excluded.location,
                       extraction_method=excluded.extraction_method, confidence=excluded.confidence,
                       verification_status=excluded.verification_status, updated_at=CURRENT_TIMESTAMP""",
                (paper_uuid, field_id, json.dumps(value, ensure_ascii=False), provenance["source_excerpt"],
                 provenance["page"], provenance["location"], provenance["extraction_method"],
                 provenance["confidence"], provenance["verification_status"]),
            )

    def refresh_search_entry(self, paper_uuid: str, note_text: str = "") -> None:
        with self._write_lock, self._connect() as connection:
            self._refresh_search_entry(connection, paper_uuid, note_text)

    def _refresh_search_entry(self, connection: sqlite3.Connection, paper_uuid: str, note_text: str) -> None:
        paper = connection.execute(
            "SELECT path, title, text FROM papers WHERE uuid = ?", (paper_uuid,)
        ).fetchone()
        if not paper:
            return
        evidence = connection.execute(
            """SELECT GROUP_CONCAT(ef.label || ' ' || ev.value_json || ' ' || ev.source_excerpt, ' ')
               FROM evidence_values ev JOIN evidence_fields ef ON ef.id = ev.field_id
               WHERE ev.paper_uuid = ?""",
            (paper_uuid,),
        ).fetchone()[0] or ""
        connection.execute("DELETE FROM search_index WHERE uuid = ?", (paper_uuid,))
        connection.execute(
            "INSERT INTO search_index (uuid, path, title, content) VALUES (?, ?, ?, ?)",
            (paper_uuid, paper["path"], paper["title"], f"{paper['text']}\n{note_text}\n{evidence}"),
        )

    def search(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        terms = [term.replace('"', "") for term in query.split() if term.strip()]
        if not terms:
            return []
        expression = " AND ".join(f'"{term}"' for term in terms[:12])
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT uuid, path, title, bm25(search_index, 0, 2, 1) AS score,
                          snippet(search_index, 3, '<mark>', '</mark>', ' … ', 18) AS snippet
                   FROM search_index WHERE search_index MATCH ? ORDER BY score LIMIT ?""",
                (expression, min(max(limit, 1), 100)),
            ).fetchall()
        return [dict(row) for row in rows]

    def evidence_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT paper_uuid, COUNT(*) FROM evidence_values WHERE value_json != 'null' GROUP BY paper_uuid"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def delete_evidence_value(self, paper_uuid: str, field_id: str) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM evidence_values WHERE paper_uuid = ? AND field_id = ?", (paper_uuid, field_id)
            )
