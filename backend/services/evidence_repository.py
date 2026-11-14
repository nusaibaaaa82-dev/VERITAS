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
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Dict, List, Optional, Set, Tuple
from backend.config import settings
from backend.schemas.claim import (
    CurationAuditLogEntry,
    CurationQueueResponse,
    CurationReviewDecision,
    CurationStatus,
    EvidenceItem,
    ReviewerConfirmedStance,
)
from backend.services.normalization import (
    compute_content_hash,
    compute_text_similarity,
    detect_syndication,
    normalize_domain,
    normalize_publisher,
)
from backend.services.relevance_engine import STOPWORDS as RELEVANCE_STOPWORDS

# High-frequency grammatical stopwords filtered from FTS5 prefix expansion to prevent broad, irrelevant matching
FTS_STOPWORDS: Set[str] = set(RELEVANCE_STOPWORDS) | {
    "the", "a", "an", "around", "of", "to", "and", "or", "is", "in", "on", "at", "by", "for", "with"
}


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
        conn.execute("PRAGMA foreign_keys = ON;")
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
                    text_provenance TEXT NOT NULL DEFAULT 'UNAVAILABLE' CHECK(text_provenance IN ('VERBATIM', 'SUMMARY', 'INTERPRETATION', 'UNAVAILABLE')),
                    retrieval_method TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(retrieval_method IN ('LIVE', 'OFFLINE_FALLBACK', 'UNKNOWN')),
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
                    provenance_json TEXT,
                    curation_status TEXT NOT NULL DEFAULT 'UNREVIEWED' CHECK(curation_status IN ('UNREVIEWED', 'UNDER_REVIEW', 'APPROVED_VERIFIED', 'REJECTED_IRRELEVANT', 'REJECTED_UNRELIABLE', 'SUPERSEDED')),
                    reviewer_id TEXT,
                    review_timestamp TEXT,
                    reviewer_notes TEXT,
                    reviewer_confirmed_stance TEXT CHECK(reviewer_confirmed_stance IS NULL OR reviewer_confirmed_stance IN ('SUPPORTING', 'CONTRADICTING', 'NEUTRAL')),
                    peer_review_confirmed INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            # Column migration check for databases created in earlier phases
            existing_cols = {col["name"] for col in cursor.execute("PRAGMA table_info(evidence_records)").fetchall()}
            migrations = {
                "source_type": "TEXT NOT NULL DEFAULT 'OTHER'",
                "text_availability": "TEXT NOT NULL DEFAULT 'METADATA_ONLY'",
                "text_provenance": "TEXT NOT NULL DEFAULT 'UNAVAILABLE' CHECK(text_provenance IN ('VERBATIM', 'SUMMARY', 'INTERPRETATION', 'UNAVAILABLE'))",
                "retrieval_method": "TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(retrieval_method IN ('LIVE', 'OFFLINE_FALLBACK', 'UNKNOWN'))",
                "relevance_status": "TEXT NOT NULL DEFAULT 'UNDETERMINED'",
                "relevance_score": "REAL",
                "relevance_justification": "TEXT",
                "stance_justification": "TEXT",
                "duplicate_reason": "TEXT",
                "curation_status": "TEXT NOT NULL DEFAULT 'UNREVIEWED' CHECK(curation_status IN ('UNREVIEWED', 'UNDER_REVIEW', 'APPROVED_VERIFIED', 'REJECTED_IRRELEVANT', 'REJECTED_UNRELIABLE', 'SUPERSEDED'))",
                "reviewer_id": "TEXT",
                "review_timestamp": "TEXT",
                "reviewer_notes": "TEXT",
                "reviewer_confirmed_stance": "TEXT CHECK(reviewer_confirmed_stance IS NULL OR reviewer_confirmed_stance IN ('SUPPORTING', 'CONTRADICTING', 'NEUTRAL'))",
                "peer_review_confirmed": "INTEGER NOT NULL DEFAULT 0",
            }
            for col_name, col_def in migrations.items():
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE evidence_records ADD COLUMN {col_name} {col_def}")

            # Safe upgrade for retrieval_method constraint to include 'UNKNOWN'
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence_records'")
            create_sql_row = cursor.fetchone()
            if create_sql_row and "UNKNOWN" not in (create_sql_row[0] or ""):
                cursor.execute("SELECT id, retrieval_method FROM evidence_records")
                saved_vals = dict(cursor.fetchall())
                cursor.execute("ALTER TABLE evidence_records DROP COLUMN retrieval_method")
                cursor.execute("ALTER TABLE evidence_records ADD COLUMN retrieval_method TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(retrieval_method IN ('LIVE', 'OFFLINE_FALLBACK', 'UNKNOWN'))")
                for eid, val in saved_vals.items():
                    target_val = val if val in ("LIVE", "OFFLINE_FALLBACK", "UNKNOWN") else "UNKNOWN"
                    cursor.execute("UPDATE evidence_records SET retrieval_method = ? WHERE id = ?", (target_val, eid))

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
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_records_curation_status ON evidence_records(curation_status)"
            )

            # 3. Create curation audit log table and indexes with ON DELETE RESTRICT and stance tracking
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='curation_audit_log'")
            audit_table_exists = cursor.fetchone() is not None

            if audit_table_exists:
                cursor.execute("SELECT COUNT(*) FROM curation_audit_log")
                audit_count = cursor.fetchone()[0]
                if audit_count == 0:
                    # Empty audit table: recreate cleanly with ON DELETE RESTRICT and stance tracking
                    cursor.execute("DROP TABLE curation_audit_log")
                    audit_table_exists = False
                else:
                    # Non-empty table: safely add columns if missing without discarding records
                    existing_audit_cols = {col["name"] for col in cursor.execute("PRAGMA table_info(curation_audit_log)").fetchall()}
                    if "previous_stance" not in existing_audit_cols:
                        cursor.execute("ALTER TABLE curation_audit_log ADD COLUMN previous_stance TEXT")
                    if "new_stance" not in existing_audit_cols:
                        cursor.execute("ALTER TABLE curation_audit_log ADD COLUMN new_stance TEXT")

            if not audit_table_exists:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS curation_audit_log (
                        audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        evidence_id TEXT NOT NULL,
                        claim_id TEXT,
                        previous_status TEXT NOT NULL,
                        new_status TEXT NOT NULL,
                        previous_stance TEXT,
                        new_stance TEXT,
                        reviewer_id TEXT NOT NULL,
                        reviewer_notes TEXT,
                        decision_timestamp TEXT NOT NULL,
                        FOREIGN KEY (evidence_id) REFERENCES evidence_records(id) ON DELETE RESTRICT
                    )
                    """
                )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_evidence_id ON curation_audit_log(evidence_id)"
            )

            # 4. Check and initialize FTS5 full-text search table
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
        """Sanitize raw query string preserving Unicode scripts (Latin, Devanagari, Bengali, etc.).

        Safeguards:
        - Drops high-frequency grammatical stopwords (the, a, an, around, of, to, and, or, is...)
          to prevent unconstrained wildcard disjunctions from matching arbitrary records.
        - Preserves substantive content terms across Unicode scripts.
        - Returns empty string for empty or stopword-only queries to fail closed safely.
        """
        if not query or not query.strip():
            return ""
        # Characters that break SQLite FTS5 query syntax or formatting
        bad_chars = set("\"'*^()[]{}<>;:,.?!/@#$%&=+~|\\।॥\n\r\t")
        raw_tokens = query.strip().split()
        tokens = []
        for t in raw_tokens:
            clean = "".join(ch for ch in t if ch not in bad_chars).strip()
            if len(clean) >= 2 and clean.lower() not in FTS_STOPWORDS:
                tokens.append(clean)
        if not tokens:
            return ""
        # Match tokens with prefix search for flexible term resolution in FTS5
        safe_terms = [f'"{t}"*' for t in tokens[:20]]
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

            # Check if record already exists to preserve human curation decisions
            cursor.execute(
                """
                SELECT id, curation_status, is_verified, stance, reviewer_id,
                       review_timestamp, reviewer_notes, reviewer_confirmed_stance,
                       peer_review_confirmed
                FROM evidence_records
                WHERE id = ?
                """,
                (item.id,),
            )
            existing = cursor.fetchone()

            if existing:
                # Existing record found: never overwrite human curation decisions!
                existing_status = existing["curation_status"]
                is_already_curated = existing_status != "UNREVIEWED"

                if is_already_curated:
                    # Preserve all human curation decisions, stance, and verification status
                    final_curation_status = existing["curation_status"]
                    final_is_verified = existing["is_verified"]
                    final_stance = existing["stance"]
                    final_reviewer_id = existing["reviewer_id"]
                    final_review_timestamp = existing["review_timestamp"]
                    final_reviewer_notes = existing["reviewer_notes"]
                    final_reviewer_confirmed_stance = existing["reviewer_confirmed_stance"]
                    final_peer_review_confirmed = existing["peer_review_confirmed"]
                else:
                    # Unreviewed record: ensure it remains strictly UNREVIEWED and is_verified=0
                    final_curation_status = "UNREVIEWED"
                    final_is_verified = 0
                    final_stance = item.stance.upper()
                    final_reviewer_id = None
                    final_review_timestamp = None
                    final_reviewer_notes = None
                    final_reviewer_confirmed_stance = None
                    final_peer_review_confirmed = 0

                # Safe UPDATE without deleting row, avoiding ON DELETE RESTRICT conflict
                cursor.execute(
                    """
                    UPDATE evidence_records SET
                        original_url = ?,
                        canonical_url = ?,
                        publisher = ?,
                        canonical_publisher = ?,
                        title = ?,
                        published_date = ?,
                        snippet = ?,
                        source_tier = ?,
                        source_type = ?,
                        text_availability = ?,
                        text_provenance = ?,
                        retrieval_method = ?,
                        relevance_status = ?,
                        relevance_score = ?,
                        relevance_justification = ?,
                        stance_justification = ?,
                        duplicate_reason = ?,
                        stance = ?,
                        is_verified = ?,
                        retrieval_timestamp = ?,
                        content_sha256 = ?,
                        source_domain = ?,
                        canonical_domain = ?,
                        is_potential_syndication = ?,
                        syndication_notes = ?,
                        doi = ?,
                        is_full_text = ?,
                        provenance_json = ?,
                        curation_status = ?,
                        reviewer_id = ?,
                        review_timestamp = ?,
                        reviewer_notes = ?,
                        reviewer_confirmed_stance = ?,
                        peer_review_confirmed = ?
                    WHERE id = ?
                    """,
                    (
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
                        item.text_provenance,
                        item.retrieval_method,
                        item.relevance_status,
                        item.relevance_score,
                        item.relevance_justification,
                        item.stance_justification,
                        item.duplicate_reason,
                        final_stance,
                        final_is_verified,
                        (item.traceability.get("recorded_at") or item.traceability.get("retrieval_timestamp") or datetime.now(timezone.utc).isoformat()) if item.traceability else datetime.now(timezone.utc).isoformat(),
                        content_hash,
                        item.source_domain or norm_dom,
                        norm_dom,
                        1 if is_syndicated else 0,
                        syn_notes,
                        item.doi,
                        1 if item.is_full_text else 0,
                        provenance_str,
                        final_curation_status,
                        final_reviewer_id,
                        final_review_timestamp,
                        final_reviewer_notes,
                        final_reviewer_confirmed_stance,
                        final_peer_review_confirmed,
                        item.id,
                    ),
                )
            else:
                # Brand new record: defaults strictly to UNREVIEWED and is_verified=0
                cursor.execute(
                    """
                    INSERT INTO evidence_records (
                        id, original_url, canonical_url, publisher, canonical_publisher,
                        title, published_date, snippet, source_tier, source_type,
                        text_availability, text_provenance, retrieval_method,
                        relevance_status, relevance_score, relevance_justification,
                        stance_justification, duplicate_reason, stance, is_verified,
                        retrieval_timestamp, content_sha256, source_domain, canonical_domain,
                        is_potential_syndication, syndication_notes, doi, is_full_text,
                        provenance_json, curation_status, reviewer_id, review_timestamp,
                        reviewer_notes, reviewer_confirmed_stance, peer_review_confirmed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNREVIEWED', NULL, NULL, NULL, NULL, 0)
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
                        item.text_provenance,
                        item.retrieval_method,
                        item.relevance_status,
                        item.relevance_score,
                        item.relevance_justification,
                        item.stance_justification,
                        item.duplicate_reason,
                        item.stance.upper(),
                        (item.traceability.get("recorded_at") or item.traceability.get("retrieval_timestamp") or datetime.now(timezone.utc).isoformat()) if item.traceability else datetime.now(timezone.utc).isoformat(),
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
            text_provenance=row["text_provenance"] if "text_provenance" in keys and row["text_provenance"] else "UNAVAILABLE",
            retrieval_method=row["retrieval_method"] if "retrieval_method" in keys and row["retrieval_method"] else "UNKNOWN",
            operational_status=row["operational_status"] if ("operational_status" in keys and row["operational_status"]) else "UNKNOWN",
            domain=row["domain"] if ("domain" in keys and row["domain"]) else ("LEGAL" if ("operational_status" in keys and row["operational_status"] in ("CURRENT_OPERATIVE", "HISTORICAL_ONLY", "REPEALED_VACATED", "SUPERSEDED", "ARCHIVED_DISCONTINUED")) else "EMPIRICAL_NON_LEGAL"),
            effective_from_date=row["effective_from_date"] if "effective_from_date" in keys else None,
            effective_to_date=row["effective_to_date"] if "effective_to_date" in keys else None,
            enactment_date=row["enactment_date"] if "enactment_date" in keys else None,
            textual_epoch=row["textual_epoch"] if "textual_epoch" in keys else None,
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
            curation_status=row["curation_status"] if "curation_status" in keys and row["curation_status"] else "UNREVIEWED",
            reviewer_id=row["reviewer_id"] if "reviewer_id" in keys else None,
            review_timestamp=row["review_timestamp"] if "review_timestamp" in keys else None,
            reviewer_notes=row["reviewer_notes"] if "reviewer_notes" in keys else None,
            reviewer_confirmed_stance=row["reviewer_confirmed_stance"] if "reviewer_confirmed_stance" in keys else None,
            peer_review_confirmed=bool(row["peer_review_confirmed"]) if "peer_review_confirmed" in keys else False,
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
        Fails closed on empty or stopword-only queries to prevent broad irrelevant retrieval.
        """
        if not query or not query.strip():
            return []

        safe_fts = self.sanitize_fts_query(query)
        if not safe_fts:
            # Query contains only stopwords, punctuation, or whitespace.
            # Fail closed: never generate broad unconstrained matches for empty/stopword queries.
            return []

        results: List[EvidenceItem] = []
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Attempt FTS5 query if available
            if self.fts5_available:
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

    def get_curation_queue(
        self,
        status: Optional[str] = "UNREVIEWED",
        limit: int = 50,
        offset: int = 0,
        domain: Optional[str] = None,
    ) -> Tuple[int, List[EvidenceItem]]:
        """Retrieve evidence records for curation review with pagination and filtering."""
        query_parts = []
        params: List[object] = []

        if status and status.upper() != "ALL":
            query_parts.append("curation_status = ?")
            params.append(status.upper())

        if domain:
            query_parts.append("(source_domain = ? OR canonical_domain = ?)")
            params.extend([domain, domain])

        where_clause = f"WHERE {' AND '.join(query_parts)}" if query_parts else ""

        with self._get_connection() as conn:
            cursor = conn.cursor()
            count_sql = f"SELECT COUNT(*) FROM evidence_records {where_clause}"
            cursor.execute(count_sql, params)
            total_count = cursor.fetchone()[0]

            data_sql = f"""
                SELECT * FROM evidence_records
                {where_clause}
                ORDER BY retrieval_timestamp DESC, id ASC
                LIMIT ? OFFSET ?
            """
            cursor.execute(data_sql, params + [limit, offset])
            rows = cursor.fetchall()
            items = [self._row_to_item(row) for row in rows]

        return total_count, items

    def apply_curation_decision(self, decision: CurationReviewDecision) -> EvidenceItem:
        """Atomically apply a human curation decision to an evidence record and append to audit log."""
        # Defense-in-depth: Validate reviewer ID
        if not decision.reviewer_id or not decision.reviewer_id.strip():
            raise ValueError("Reviewer ID cannot be empty or whitespace.")

        # Defense-in-depth: APPROVED_VERIFIED requires a decisive stance (SUPPORTING or CONTRADICTING)
        if decision.curation_status == "APPROVED_VERIFIED":
            if not decision.reviewer_confirmed_stance or decision.reviewer_confirmed_stance not in ("SUPPORTING", "CONTRADICTING"):
                raise ValueError(
                    "APPROVED_VERIFIED status requires an explicit reviewer-confirmed stance ('SUPPORTING' or 'CONTRADICTING'). "
                    f"Cannot approve evidence with stance '{decision.reviewer_confirmed_stance}'."
                )

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Fetch current record
            cursor.execute(
                """
                SELECT id, curation_status, stance, is_verified, canonical_url, original_url,
                       source_domain, source_type, text_availability, text_provenance, doi
                FROM evidence_records
                WHERE id = ?
                """,
                (decision.evidence_id,),
            )
            current = cursor.fetchone()
            if not current:
                raise ValueError(f"Evidence record with id '{decision.evidence_id}' not found.")

            previous_status = current["curation_status"]
            previous_stance = current["stance"]

            # Defense-in-depth: Inconsistent domain check for approvals
            if decision.curation_status == "APPROVED_VERIFIED":
                derived_domain = normalize_domain(current["canonical_url"] or current["original_url"])
                stored_domain = (current["source_domain"] or "").lower().strip()
                stored_norm = normalize_domain(stored_domain)
                if derived_domain and stored_domain and derived_domain != stored_domain and derived_domain != stored_norm:
                    raise ValueError(
                        f"Cannot approve record '{decision.evidence_id}' with domain mismatch: "
                        f"stored domain '{current['source_domain']}' does not match actual URL domain '{derived_domain}'. "
                        "Provenance metadata must be reconciled before approval."
                    )

            # Defense-in-depth: Protect peer-review classification
            if decision.peer_review_confirmed:
                if current["source_type"] == "GOVERNMENT_PUBLICATION":
                    raise ValueError(
                        f"Evidence record '{decision.evidence_id}' is classified as GOVERNMENT_PUBLICATION and cannot be "
                        "marked as academically peer-reviewed. Official agency standards and datasets undergo institutional review, "
                        "not academic journal peer review."
                    )

            # Defense-in-depth: Block APPROVED_VERIFIED if text is UNAVAILABLE or METADATA_ONLY
            if decision.curation_status == "APPROVED_VERIFIED":
                current_keys = current.keys()
                prov = decision.text_provenance or (current["text_provenance"] if "text_provenance" in current_keys else "UNAVAILABLE")
                if prov == "UNAVAILABLE" or current["text_availability"] == "METADATA_ONLY":
                    raise ValueError(
                        f"Cannot approve record '{decision.evidence_id}' as APPROVED_VERIFIED: "
                        "text provenance is UNAVAILABLE or text availability is METADATA_ONLY. "
                        "Records lacking empirical source text cannot serve as fact-checking proof."
                    )

            # 2. Determine verified state and stance
            # Reliability Rule: Only APPROVED_VERIFIED confers is_verified = True
            new_is_verified = 1 if decision.curation_status == "APPROVED_VERIFIED" else 0
            new_stance = decision.reviewer_confirmed_stance or previous_stance
            now_iso = datetime.now(timezone.utc).isoformat()

            # 3. Update evidence_records
            cursor.execute(
                """
                UPDATE evidence_records
                SET curation_status = ?,
                    is_verified = ?,
                    stance = ?,
                    reviewer_id = ?,
                    review_timestamp = ?,
                    reviewer_notes = ?,
                    reviewer_confirmed_stance = ?,
                    peer_review_confirmed = ?
                WHERE id = ?
                """,
                (
                    decision.curation_status,
                    new_is_verified,
                    new_stance,
                    decision.reviewer_id,
                    now_iso,
                    decision.reviewer_notes,
                    decision.reviewer_confirmed_stance,
                    1 if decision.peer_review_confirmed else 0,
                    decision.evidence_id,
                ),
            )

            # Update reviewer-confirmed text provenance if explicitly provided
            if decision.text_provenance:
                cursor.execute(
                    "UPDATE evidence_records SET text_provenance = ? WHERE id = ?",
                    (decision.text_provenance, decision.evidence_id),
                )

            # 4. Insert audit log record in same transaction
            cursor.execute(
                """
                INSERT INTO curation_audit_log (
                    evidence_id, claim_id, previous_status, new_status,
                    previous_stance, new_stance, reviewer_id, reviewer_notes,
                    decision_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.evidence_id,
                    decision.claim_id,
                    previous_status,
                    decision.curation_status,
                    previous_stance,
                    new_stance,
                    decision.reviewer_id,
                    decision.reviewer_notes,
                    now_iso,
                ),
            )

            conn.commit()

        updated = self.get_item_by_id(decision.evidence_id)
        if not updated:
            raise RuntimeError(f"Failed to retrieve updated evidence record '{decision.evidence_id}'.")
        return updated

    def get_curation_audit_history(self, evidence_id: str) -> List[CurationAuditLogEntry]:
        """Retrieve full chronological audit trail for a specific evidence record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT audit_id, evidence_id, claim_id, previous_status, new_status,
                       previous_stance, new_stance, reviewer_id, reviewer_notes,
                       decision_timestamp
                FROM curation_audit_log
                WHERE evidence_id = ?
                ORDER BY audit_id ASC
                """,
                (evidence_id,),
            )
            rows = cursor.fetchall()
            return [
                CurationAuditLogEntry(
                    audit_id=row["audit_id"],
                    evidence_id=row["evidence_id"],
                    claim_id=row["claim_id"],
                    previous_status=row["previous_status"],
                    new_status=row["new_status"],
                    previous_stance=row["previous_stance"],
                    new_stance=row["new_stance"],
                    reviewer_id=row["reviewer_id"],
                    reviewer_notes=row["reviewer_notes"],
                    decision_timestamp=row["decision_timestamp"],
                )
                for row in rows
            ]

    def get_curation_stats(self) -> Dict[str, int]:
        """Return count of records grouped by curation status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT curation_status, COUNT(*) as cnt FROM evidence_records GROUP BY curation_status"
            )
            rows = cursor.fetchall()
            stats = {
                "UNREVIEWED": 0,
                "UNDER_REVIEW": 0,
                "APPROVED_VERIFIED": 0,
                "REJECTED_IRRELEVANT": 0,
                "REJECTED_UNRELIABLE": 0,
                "SUPERSEDED": 0,
            }
            for row in rows:
                status_val = row["curation_status"]
                stats[status_val] = row["cnt"]
            return stats

