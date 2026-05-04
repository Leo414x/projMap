from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


def now_iso() -> datetime:
    return datetime.now(timezone.utc)


CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    file_type TEXT,
    content_hash TEXT,
    size_bytes BIGINT,
    modified_at TIMESTAMP,
    last_scanned_at TIMESTAMP,
    last_extracted_at TIMESTAMP,
    status TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    file_path TEXT,
    chunk_index INTEGER,
    heading_path TEXT,
    semantic_anchor TEXT,
    content TEXT,
    content_hash TEXT,
    start_line INTEGER,
    end_line INTEGER,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    type TEXT,
    content TEXT,
    title TEXT,
    summary TEXT,
    detail TEXT,
    context TEXT,
    rationale TEXT,
    scope TEXT,
    non_goals TEXT,
    status TEXT,
    project TEXT,
    version TEXT,
    module TEXT,
    submodule TEXT,
    topic TEXT,
    source_file TEXT,
    source_chunk_id TEXT,
    source_line TEXT,
    source_heading TEXT,
    source_line_start INTEGER,
    source_line_end INTEGER,
    evidence_quote TEXT,
    confidence DOUBLE,
    content_hash TEXT,
    decision_time TEXT,
    decision_time_basis TEXT,
    decision_time_confidence DOUBLE,
    sort_time TEXT,
    timeline_bucket TEXT,
    first_seen_at TIMESTAMP,
    last_seen_at TIMESTAMP,
    extracted_at TIMESTAMP,
    classification_confidence DOUBLE,
    classification_basis TEXT,
    display_priority DOUBLE,
    is_default_visible BOOLEAN DEFAULT true,
    hidden_reason TEXT,
    entities TEXT,
    schema_version TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    from_node_id TEXT,
    to_node_id TEXT,
    relationship TEXT,
    evidence_quote TEXT,
    confidence DOUBLE,
    source_file TEXT,
    source_chunk_id TEXT,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS extractions (
    id TEXT PRIMARY KEY,
    chunk_id TEXT,
    file_path TEXT,
    model TEXT,
    raw_response TEXT,
    parsed_json TEXT,
    status TEXT,
    error TEXT,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    node_id TEXT,
    source_file TEXT,
    source_heading TEXT,
    line_start INTEGER,
    line_end INTEGER,
    evidence_quote TEXT,
    evidence_hash TEXT,
    source_created_at TIMESTAMP,
    source_modified_at TIMESTAMP,
    file_hash TEXT,
    source_confidence TEXT,
    created_at TIMESTAMP
);
"""

# v5 migration: add columns to nodes if they don't exist
V5_MIGRATIONS = [
    "ALTER TABLE nodes ADD COLUMN title TEXT",
    "ALTER TABLE nodes ADD COLUMN summary TEXT",
    "ALTER TABLE nodes ADD COLUMN context TEXT",
    "ALTER TABLE nodes ADD COLUMN rationale TEXT",
    "ALTER TABLE nodes ADD COLUMN scope TEXT",
    "ALTER TABLE nodes ADD COLUMN non_goals TEXT",
    "ALTER TABLE nodes ADD COLUMN status TEXT",
    "ALTER TABLE nodes ADD COLUMN project TEXT",
    "ALTER TABLE nodes ADD COLUMN version TEXT",
    "ALTER TABLE nodes ADD COLUMN module TEXT",
    "ALTER TABLE nodes ADD COLUMN submodule TEXT",
    "ALTER TABLE nodes ADD COLUMN topic TEXT",
    "ALTER TABLE nodes ADD COLUMN source_heading TEXT",
    "ALTER TABLE nodes ADD COLUMN source_line_start INTEGER",
    "ALTER TABLE nodes ADD COLUMN source_line_end INTEGER",
    "ALTER TABLE nodes ADD COLUMN decision_time TEXT",
    "ALTER TABLE nodes ADD COLUMN decision_time_basis TEXT",
    "ALTER TABLE nodes ADD COLUMN decision_time_confidence DOUBLE",
    "ALTER TABLE nodes ADD COLUMN sort_time TEXT",
    "ALTER TABLE nodes ADD COLUMN timeline_bucket TEXT",
    "ALTER TABLE nodes ADD COLUMN first_seen_at TIMESTAMP",
    "ALTER TABLE nodes ADD COLUMN last_seen_at TIMESTAMP",
    "ALTER TABLE nodes ADD COLUMN extracted_at TIMESTAMP",
    "ALTER TABLE nodes ADD COLUMN classification_confidence DOUBLE",
    "ALTER TABLE nodes ADD COLUMN classification_basis TEXT",
    "ALTER TABLE nodes ADD COLUMN display_priority DOUBLE",
    "ALTER TABLE nodes ADD COLUMN is_default_visible BOOLEAN DEFAULT true",
    "ALTER TABLE nodes ADD COLUMN hidden_reason TEXT",
    "ALTER TABLE nodes ADD COLUMN entities TEXT",
    "ALTER TABLE nodes ADD COLUMN schema_version TEXT",
]


class DuckDBStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))
        self.conn.execute(CREATE_TABLES)
        self._run_migrations()

    def _run_migrations(self) -> None:
        existing = self._get_columns("nodes")
        for sql in V5_MIGRATIONS:
            col = sql.split("ADD COLUMN ")[1].split(" ")[0]
            if col not in existing:
                try:
                    self.conn.execute(sql)
                except Exception:
                    pass

    def _get_columns(self, table: str) -> set[str]:
        rows = self.conn.execute(
            f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}'"
        ).fetchall()
        return {r[0] for r in rows}

    def close(self) -> None:
        self.conn.close()

    # ── files ──────────────────────────────────────────────────

    def upsert_file(
        self,
        path: str,
        file_type: str,
        content_hash: str,
        size_bytes: int,
        modified_at: datetime | None,
        status: str,
        extracted: bool = False,
    ) -> None:
        ts = now_iso()
        self.conn.execute(
            """
            INSERT INTO files (path, file_type, content_hash, size_bytes, modified_at,
                               last_scanned_at, last_extracted_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (path) DO UPDATE SET
                file_type = excluded.file_type,
                content_hash = excluded.content_hash,
                size_bytes = excluded.size_bytes,
                modified_at = excluded.modified_at,
                last_scanned_at = excluded.last_scanned_at,
                last_extracted_at = CASE WHEN ? THEN ? ELSE files.last_extracted_at END,
                status = excluded.status
            """,
            [
                path, file_type, content_hash, size_bytes, modified_at,
                ts, ts if extracted else None, status,
                extracted, ts,
            ],
        )

    def get_file_hash(self, path: str) -> str | None:
        row = self.conn.execute(
            "SELECT content_hash FROM files WHERE path = ?", [path]
        ).fetchone()
        return row[0] if row else None

    def get_all_file_hashes(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT path, content_hash FROM files").fetchall()
        return dict(rows)

    # ── chunks ─────────────────────────────────────────────────

    def delete_chunks_for_file(self, file_path: str) -> None:
        self.conn.execute("DELETE FROM chunks WHERE file_path = ?", [file_path])

    def insert_chunk(
        self,
        chunk_id: str,
        file_path: str,
        chunk_index: int,
        heading_path: str | None,
        semantic_anchor: str | None,
        content: str,
        content_hash: str,
        start_line: int | None,
        end_line: int | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO chunks (id, file_path, chunk_index, heading_path,
                                semantic_anchor, content, content_hash,
                                start_line, end_line, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [chunk_id, file_path, chunk_index, heading_path,
             semantic_anchor, content, content_hash,
             start_line, end_line, now_iso()],
        )

    # ── nodes (v5) ─────────────────────────────────────────────

    def delete_nodes_for_file(self, file_path: str) -> None:
        self.conn.execute("DELETE FROM nodes WHERE source_file = ?", [file_path])

    def insert_node(
        self,
        node_id: str,
        node_type: str,
        content: str,
        detail: str = "",
        source_file: str = "",
        source_chunk_id: str = "",
        source_line: str | None = None,
        evidence_quote: str = "",
        confidence: float = 0.0,
        content_hash: str = "",
        # v5 fields
        title: str = "",
        summary: str = "",
        context: str = "",
        rationale: str = "",
        scope: str = "",
        non_goals: list[str] | None = None,
        status: str | None = None,
        project: str | None = None,
        version: str | None = None,
        module: str | None = None,
        submodule: str | None = None,
        topic: str | None = None,
        source_heading: str | None = None,
        source_line_start: int | None = None,
        source_line_end: int | None = None,
        decision_time: str | None = None,
        decision_time_basis: str | None = None,
        decision_time_confidence: float | None = None,
        sort_time: str | None = None,
        timeline_bucket: str | None = None,
        classification_confidence: float | None = None,
        classification_basis: str | None = None,
        display_priority: float | None = None,
        is_default_visible: bool = True,
        hidden_reason: str | None = None,
        entities: list[str] | None = None,
        schema_version: str = "v5",
    ) -> bool:
        ts = now_iso()
        exists = self.conn.execute(
            "SELECT 1 FROM nodes WHERE id = ?", [node_id]
        ).fetchone()
        if exists:
            return False

        import json
        ng = json.dumps(non_goals or [])
        ent = json.dumps(entities or [])

        self.conn.execute(
            """
            INSERT INTO nodes (
                id, type, content, title, summary, detail, context, rationale,
                scope, non_goals, status, project, version, module, submodule, topic,
                source_file, source_chunk_id, source_line, source_heading,
                source_line_start, source_line_end,
                evidence_quote, confidence, content_hash,
                decision_time, decision_time_basis, decision_time_confidence,
                sort_time, timeline_bucket,
                first_seen_at, last_seen_at, extracted_at,
                classification_confidence, classification_basis,
                display_priority, is_default_visible, hidden_reason,
                entities, schema_version,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?
            )
            """,
            [
                node_id, node_type, content, title, summary, detail, context, rationale,
                scope, ng, status, project, version, module, submodule, topic,
                source_file, source_chunk_id, source_line, source_heading,
                source_line_start, source_line_end,
                evidence_quote, confidence, content_hash,
                decision_time, decision_time_basis, decision_time_confidence,
                sort_time, timeline_bucket,
                ts, ts, ts,
                classification_confidence, classification_basis,
                display_priority, is_default_visible, hidden_reason,
                ent, schema_version,
                ts, ts,
            ],
        )
        return True

    def get_node_ids_for_file(self, file_path: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT id FROM nodes WHERE source_file = ?", [file_path]
        ).fetchall()
        return {r[0] for r in rows}

    def get_node_id_by_content(self, node_type: str, normalized_content: str) -> str | None:
        from projmap.schemas import node_id
        nid = node_id(node_type, normalized_content)
        row = self.conn.execute("SELECT 1 FROM nodes WHERE id = ?", [nid]).fetchone()
        return nid if row else None

    def query_nodes(
        self,
        include_hidden: bool = False,
        node_types: list[str] | None = None,
        project: str | None = None,
        version: str | None = None,
        module: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query nodes and return as dicts for ViewModel building."""
        conditions = []
        params: list[Any] = []

        if not include_hidden:
            conditions.append("is_default_visible = true")
        if node_types:
            placeholders = ",".join(["?"] * len(node_types))
            conditions.append(f"type IN ({placeholders})")
            params.extend(node_types)
        if project:
            conditions.append("project = ?")
            params.append(project)
        if version:
            conditions.append("version = ?")
            params.append(version)
        if module:
            conditions.append("module = ?")
            params.append(module)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM nodes WHERE {where} ORDER BY sort_time DESC NULLS LAST LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        columns = [desc[0] for desc in self.conn.description]
        return [dict(zip(columns, row)) for row in rows]

    def get_all_nodes_as_dicts(self, limit: int = 1000) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT * FROM nodes ORDER BY sort_time DESC NULLS LAST LIMIT {limit}"
        ).fetchall()
        columns = [desc[0] for desc in self.conn.description]
        return [dict(zip(columns, row)) for row in rows]

    # ── edges ──────────────────────────────────────────────────

    def delete_edges_for_file(self, file_path: str) -> None:
        self.conn.execute("DELETE FROM edges WHERE source_file = ?", [file_path])

    def insert_edge(
        self,
        edge_id: str,
        from_node_id: str,
        to_node_id: str,
        relationship: str,
        evidence_quote: str,
        confidence: float,
        source_file: str,
        source_chunk_id: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO edges (id, from_node_id, to_node_id, relationship,
                               evidence_quote, confidence, source_file,
                               source_chunk_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [edge_id, from_node_id, to_node_id, relationship,
             evidence_quote, confidence, source_file, source_chunk_id, now_iso()],
        )

    def get_edge_counts_by_node(self) -> dict[str, dict[str, int]]:
        """Get edge counts grouped by from_node_id."""
        rows = self.conn.execute(
            "SELECT from_node_id, relationship, COUNT(*) FROM edges GROUP BY from_node_id, relationship"
        ).fetchall()
        result: dict[str, dict[str, int]] = {}
        for from_id, rel, cnt in rows:
            if from_id not in result:
                result[from_id] = {}
            result[from_id][rel] = cnt
        return result

    def get_edges_for_node(self, node_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM edges WHERE from_node_id = ? OR to_node_id = ?",
            [node_id, node_id],
        ).fetchall()
        columns = [desc[0] for desc in self.conn.description]
        return [dict(zip(columns, row)) for row in rows]

    # ── sources ────────────────────────────────────────────────

    def insert_source(
        self,
        source_id: str,
        node_id: str,
        source_file: str,
        source_heading: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        evidence_quote: str | None = None,
        evidence_hash: str | None = None,
        source_created_at: datetime | None = None,
        source_modified_at: datetime | None = None,
        file_hash: str | None = None,
        source_confidence: str = "verified",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO sources (id, node_id, source_file, source_heading,
                                 line_start, line_end, evidence_quote, evidence_hash,
                                 source_created_at, source_modified_at, file_hash,
                                 source_confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [source_id, node_id, source_file, source_heading,
             line_start, line_end, evidence_quote, evidence_hash,
             source_created_at, source_modified_at, file_hash,
             source_confidence, now_iso()],
        )

    def get_sources_for_node(self, node_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM sources WHERE node_id = ?", [node_id]
        ).fetchall()
        columns = [desc[0] for desc in self.conn.description]
        return [dict(zip(columns, row)) for row in rows]

    # ── extractions ────────────────────────────────────────────

    def insert_extraction(
        self,
        extraction_id: str,
        chunk_id: str,
        file_path: str,
        model: str,
        raw_response: str | None,
        parsed_json: str | None,
        status: str,
        error: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO extractions (id, chunk_id, file_path, model, raw_response,
                                     parsed_json, status, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [extraction_id, chunk_id, file_path, model, raw_response,
             parsed_json, status, error, now_iso()],
        )

    # ── summary / status ───────────────────────────────────────

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for table in ("files", "chunks", "nodes", "edges", "extractions", "sources"):
            try:
                row = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                result[table] = row[0]
            except Exception:
                result[table] = 0
        return result

    def node_type_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT type, COUNT(*) FROM nodes GROUP BY type ORDER BY COUNT(*) DESC"
        ).fetchall()
        return dict(rows)

    def last_rebuild(self) -> str | None:
        row = self.conn.execute(
            "SELECT MAX(created_at) FROM extractions"
        ).fetchone()
        return str(row[0]) if row and row[0] else None

    def get_project_name(self) -> str | None:
        row = self.conn.execute("SELECT path FROM files LIMIT 1").fetchone()
        return row[0] if row else None
