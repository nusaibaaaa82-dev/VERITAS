"""Local SQLite Evidence Repository for VERITAS with FTS5 Full-Text Search.

Provides safe, persistent, zero-cost storage and querying of verified evidence
records using Python's standard library sqlite3.

Features:
1. Normalized relational table ('evidence_records') storing all required fields.
2. High-performance FTS5 virtual table ('evidence_fts') for safe full-text search.
3. O(1) content hash indexing for exact cross-domain duplicate detection.
4. Syndication tracking to prevent wire dispatches from masquerading as independent sources.
5. Starts completely empty (no mock or demonstration evidence).
"""

from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
from typing import Dict, List, Optional, Tuple
from backend.config import settings
from backend.schemas.claim import EvidenceItem
from backend.services.normalization import (
    compute_content_hash,
    compute_text_similarity,
    detect_syndication,
    normalize_domain,
    normalize_publisher,
)


class EvidenceRepository:
    """Manages local SQLite database operations and FTS5 full-text queries."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.EVIDENCE_DB_PATH
        # Ensure parent directory exists safely
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.fts5_available: bool = False
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Create a connection with row factory and foreign keys enabled, ensuring clean closure."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialize database schema, indexes, and FTS5 virtual tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA foreign_keys = ON;")

            # 1. Primary evidence records table storing all required fields
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_records (
                    id TEXT PRIMARY KEY,
                    original_url TEXT,
                    canonical_url TEXT,
                    publisher TEXT,
                    canonical_publisher TEXT,
                    title TEXT NOT NULL,
                    published_date TEXT,
                    snippet TEXT NOT NULL,
                    source_tier TEXT NOT NULL DEFAULT 'SECONDARY',
                    source_type TEXT NOT NULL DEFAULT 'OTHER',
                    text_availability TEXT NOT NULL DEFAULT 'METADATA_ONLY',
                    relevance_status TEXT NOT NULL DEFAULT 'UNDETERMINED',
                    relevance_score REAL,
                    relevance_justification TEXT,
                    stance_justification TEXT,
                    duplicate_reason TEXT,
                    stance TEXT NOT NULL DEFAULT 'NEUTRAL',
                    is_verified INTEGER NOT NULL DEFAULT 0,
                    retrieval_timestamp TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    source_domain TEXT,
                    canonical_domain TEXT,
                    is_potential_syndication INTEGER NOT NULL DEFAULT 0,
                    syndication_notes TEXT,
                    doi TEXT,
                    is_full_text INTEGER NOT NULL DEFAULT 0,
                    provenance_json TEXT
                )
                """
            )

            # Column migration check for databases created in earlier phases
            existing_cols = {col["name"] for col in cursor.execute("PRAGMA table_info(evidence_records)").fetchall()}
            migrations = {
                "source_type": "TEXT NOT NULL DEFAULT 'OTHER'",
                "text_availability": "TEXT NOT NULL DEFAULT 'METADATA_ONLY'",
                "relevance_status": "TEXT NOT NULL DEFAULT 'UNDETERMINED'",
                "relevance_score": "REAL",
                "relevance_justification": "TEXT",
                "stance_justification": "TEXT",
                "duplicate_reason": "TEXT",
            }
            for col_name, col_def in migrations.items():
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE evidence_records ADD COLUMN {col_name} {col_def}")

            # 2. Performance & integrity indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_sha256 ON evidence_records(content_sha256)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_canonical_dom ON evidence_records(canonical_domain)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_canonical_pub ON evidence_records(canonical_publisher)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_verified ON evidence_records(is_verified)"
            )

            # 3. Check and initialize FTS5 full-text search table
            if settings.ENABLE_FTS5:
                try:
                    cursor.execute(
                        """
                        CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
                            id UNINDEXED,
                            title,
                            snippet,
                            publisher,
                            canonical_publisher,
                            tokenize='porter unicode61'
                        )
                        """
                    )
                    self.fts5_available = True
                except sqlite3.OperationalError:
                    # SQLite compiled without FTS5
                    self.fts5_available = False
            else:
                self.fts5_available = False

            conn.commit()

    @staticmethod
    def sanitize_fts_query(query: str) -> str:
        """Sanitize raw query string preserving Unicode scripts (Latin, Devanagari, Bengali, etc.)."""
        if not query or not query.strip():
            return ""
        # Characters that break SQLite FTS5 query syntax or formatting
        bad_chars = set("\"'*^()[]{}<>;:,.?!/@#$%&=+~|\\।॥\n\r\t")
        raw_tokens = query.strip().split()
        tokens = []
        for t in raw_tokens:
            clean = "".join(ch for ch in t if ch not in bad_chars).strip()
            if len(clean) >= 2:
                tokens.append(clean)
        if not tokens:
            return ""
        # Match tokens with prefix search for flexible term resolution in FTS5
        safe_terms = [f'"{t}"*' for t in tokens[:10]]
        return " OR ".join(safe_terms)

    def store_evidence_item(self, item: EvidenceItem) -> Tuple[bool, str]:
        """Insert or update an evidence item with normalization, hash checking, and syndication detection."""
        # 1. Compute content hash if missing
        content_hash = item.content_sha256 or compute_content_hash(item.snippet)

        # 2. Run normalization
        norm_dom = item.canonical_domain or normalize_domain(item.canonical_url or item.url)
        norm_pub = item.canonical_publisher or normalize_publisher(item.publisher, norm_dom)

        # 3. Check for potential syndication
        is_syndicated, syn_notes, wire_agency = detect_syndication(
            snippet=item.snippet,
            publisher=item.publisher,
            domain=norm_dom,
        )
        if item.is_potential_syndication:
            is_syndicated = True
            syn_notes = item.syndication_notes or syn_notes

        # 4. Check for exact duplicate snippet hash
        existing = self.get_item_by_content_hash(content_hash)
        if existing and existing.id != item.id:
            duplicate_note = (
                f"Duplicate content detected: identical snippet SHA-256 ({content_hash[:12]}...) "
                f"matches existing record '{existing.id}' from '{existing.canonical_publisher or existing.canonical_domain}'."
            )
            item.duplicate_reason = f"EXACT_HASH_MATCH: {duplicate_note}"
            return False, duplicate_note

        # 5. Check for slightly modified syndicated copies vs independent reporting
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, snippet, canonical_publisher, canonical_domain FROM evidence_records WHERE id != ?", (item.id,))
            for other_row in cursor.fetchall():
                sim = compute_text_similarity(item.snippet, other_row["snippet"])
                if sim >= 0.85:
                    is_syndicated = True
                    syn_notes = (
                        f"MODIFIED_SYNDICATION_DETECTED: High textual overlap ({sim:.1%}) with record '{other_row['id']}' "
                        f"from '{other_row['canonical_publisher'] or other_row['canonical_domain']}'. Minor editorial variations do not constitute independent corroboration."
                    )
                    item.is_potential_syndication = True
                    item.syndication_notes = syn_notes
                    item.duplicate_reason = syn_notes
                    break
                elif 0.20 <= sim < 0.60 and not item.duplicate_reason:
                    item.duplicate_reason = (
                        f"INDEPENDENT_REPORTING: Thematic overlap ({sim:.1%}) with record '{other_row['id']}' reflects "
                        "independent journalistic phrasing rather than wire syndication."
                    )

        # Ensure provenance dict preserves all independence and translation metadata
        trace_dict = dict(item.traceability or {})
        if item.underlying_source_id:
            trace_dict["underlying_source_id"] = item.underlying_source_id
        if item.independence_status:
            trace_dict["independence_status"] = item.independence_status
        if item.is_machine_translated:
            trace_dict["is_machine_translated"] = True
        if item.translation_engine:
            trace_dict["translation_engine"] = item.translation_engine
        if item.original_language:
            trace_dict["original_language"] = item.original_language
        provenance_str = json.dumps(trace_dict)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO evidence_records (
                    id, original_url, canonical_url, publisher, canonical_publisher,
                    title, published_date, snippet, source_tier, source_type,
                    text_availability, relevance_status, relevance_score, relevance_justification,
                    stance_justification, duplicate_reason, stance, is_verified,
                    retrieval_timestamp, content_sha256, source_domain, canonical_domain,
                    is_potential_syndication, syndication_notes, doi, is_full_text,
                    provenance_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.original_url or item.url,
                    item.canonical_url or item.url,
                    item.publisher,
                    norm_pub,
                    item.title,
                    item.published_date,
                    item.snippet,
                    item.source_tier,
                    item.source_type,
                    item.text_availability,
                    item.relevance_status,
                    item.relevance_score,
                    item.relevance_justification,
                    item.stance_justification,
                    item.duplicate_reason,
                    item.stance.upper(),
                    1 if item.is_verified else 0,
                    item.traceability.get("recorded_at") if item.traceability else "",
                    content_hash,
                    item.source_domain or norm_dom,
                    norm_dom,
                    1 if is_syndicated else 0,
                    syn_notes,
                    item.doi,
                    1 if item.is_full_text else 0,
                    provenance_str,
                ),
            )

            # Update FTS5 index if available
            if self.fts5_available:
                try:
                    cursor.execute("DELETE FROM evidence_fts WHERE id = ?", (item.id,))
                    cursor.execute(
                        """
                        INSERT INTO evidence_fts (id, title, snippet, publisher, canonical_publisher)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (item.id, item.title, item.snippet, item.publisher, norm_pub),
                    )
                except Exception:
                    pass

            conn.commit()

        status_msg = "Successfully stored evidence item."
        if is_syndicated:
            status_msg += f" (Notice: Flagged as potential syndicated wire content: {syn_notes})"
        return True, status_msg

    def _row_to_item(self, row: sqlite3.Row) -> EvidenceItem:
        """Map a database row to a validated EvidenceItem."""
        provenance = {}
        if row["provenance_json"]:
            try:
                provenance = json.loads(row["provenance_json"])
            except Exception:
                provenance = {}

        keys = row.keys()

        return EvidenceItem(
            id=row["id"],
            title=row["title"],
            publisher=row["publisher"],
            url=row["canonical_url"] or row["original_url"],
            published_date=row["published_date"],
            snippet=row["snippet"],
            stance=row["stance"],
            is_verified=bool(row["is_verified"]),
            source_domain=row["source_domain"],
            original_url=row["original_url"],
            canonical_url=row["canonical_url"],
            canonical_domain=row["canonical_domain"],
            canonical_publisher=row["canonical_publisher"],
            source_tier=row["source_tier"],
            source_type=row["source_type"] if "source_type" in keys else "OTHER",
            text_availability=row["text_availability"] if "text_availability" in keys else "METADATA_ONLY",
            relevance_status=row["relevance_status"] if "relevance_status" in keys else "UNDETERMINED",
            relevance_score=row["relevance_score"] if "relevance_score" in keys else None,
            relevance_justification=row["relevance_justification"] if "relevance_justification" in keys else None,
            stance_justification=row["stance_justification"] if "stance_justification" in keys else None,
            duplicate_reason=row["duplicate_reason"] if "duplicate_reason" in keys else None,
            content_sha256=row["content_sha256"],
            is_potential_syndication=bool(row["is_potential_syndication"]),
            syndication_notes=row["syndication_notes"],
            doi=row["doi"],
            is_full_text=bool(row["is_full_text"]),
            underlying_source_id=provenance.get("underlying_source_id"),
            independence_status=provenance.get("independence_status", "INDEPENDENT"),
            is_machine_translated=bool(provenance.get("is_machine_translated", False)),
            translation_engine=provenance.get("translation_engine"),
            original_language=provenance.get("original_language"),
            traceability=provenance,
        )

    def get_item_by_id(self, item_id: str) -> Optional[EvidenceItem]:
        """Retrieve a single evidence record by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM evidence_records WHERE id = ?", (item_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_item(row)
        return None

    def get_item_by_content_hash(self, content_hash: str) -> Optional[EvidenceItem]:
        """Find existing record by exact snippet content hash."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM evidence_records WHERE content_sha256 = ? LIMIT 1",
                (content_hash,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_item(row)
        return None

    def get_record_count(self) -> int:
        """Count total evidence records in repository."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM evidence_records")
            return cursor.fetchone()[0]

    def search_evidence(
        self,
        query: str,
        limit: int = 10,
        verified_only: bool = False,
    ) -> List[EvidenceItem]:
        """Perform full-text search against the evidence repository.

        Uses FTS5 when available; gracefully falls back to parameterized LIKE matching.
        """
        if not query or not query.strip():
            return []

        results: List[EvidenceItem] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Attempt FTS5 query if available
            if self.fts5_available:
                safe_fts = self.sanitize_fts_query(query)
                if safe_fts:
                    try:
                        sql = """
                        SELECT r.*
                        FROM evidence_fts f
                        JOIN evidence_records r ON f.id = r.id
                        WHERE evidence_fts MATCH ?
                        """
                        params: List[object] = [safe_fts]
                        if verified_only:
                            sql += " AND r.is_verified = 1"
                        sql += " ORDER BY rank LIMIT ?"
                        params.append(limit)

                        cursor.execute(sql, params)
                        rows = cursor.fetchall()
                        for row in rows:
                            results.append(self._row_to_item(row))
                        return results
                    except sqlite3.OperationalError:
                        # FTS5 syntax or matching issue -> fallback to LIKE
                        pass

            # Fallback parameterized LIKE matching
            search_pattern = f"%{query.strip()[:100]}%"
            sql = """
            SELECT * FROM evidence_records
            WHERE (title LIKE ? OR snippet LIKE ? OR publisher LIKE ?)
            """
            params = [search_pattern, search_pattern, search_pattern]
            if verified_only:
                sql += " AND is_verified = 1"
            sql += " ORDER BY retrieval_timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            for row in rows:
                results.append(self._row_to_item(row))

        return results

