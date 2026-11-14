"""VERITAS Safe Database Initializer.

Creates a fresh, verified SQLite evidence database from the canonical version-controlled
seed JSON fixture ('backend/data/seeds/evidence_seed_v1.0.json').

Strict Safety Invariants Enforced:
1. Non-Overwrite Guarantee: Refuses to touch, overwrite, or re-seed any target file that already exists.
   Zero flags for force, overwrite, or reseed.
2. Isolated Staging: Constructs and validates the database in a uniquely-named staging file
   on the same filesystem before atomic activation.
3. Atomic Activation: Uses atomic no-overwrite hard-linking (os.link) to prevent concurrency collisions.
4. Clean Sidecar Teardown: Checkpoints WAL and switches to DELETE journal mode before activation to
   eliminate residual -wal and -shm sidecars.
5. Post-Activation Verification: Reopens the activated database read-only to verify integrity and foreign keys.
   Never automatically deletes the activated database even if post-activation verification fails.
6. Zero Historical Alteration: Preserves exact 60 evidence records and 4 historical audit log entries.
   Does not run Stage 4 migration; preserves baseline 35-column schema.
"""

import argparse
import gc
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is available in sys.path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_database")

# Expected canonical constants
EXPECTED_SEED_RECORD_COUNT = 60
EXPECTED_SEED_AUDIT_COUNT = 4
EXPECTED_APPROVED_COUNT = 3
EXPECTED_REJECTED_COUNT = 1
EXPECTED_UNREVIEWED_COUNT = 56
EXPECTED_VERIFIED_FLAG_1 = 3
EXPECTED_VERIFIED_FLAG_0 = 57

DOL_RECORD_ID = "dol-whd-factsheet-48-immigrant-workers"
DOL_EXPECTED_SHA256 = "ee090f136941ae03c1094f94e318d6d166dd9c059b53cd0176dd980bf47f1d40"

LUCAS_RECORD_ID = "ca8-lucas-v-jerusalem-cafe-721-f3d-927"
LUCAS_EXPECTED_SHA256 = "ad0bcc06183669aed952d49eb4e233b44a21d271066418d61c14a0cf692b845c"

REJECTED_RECORD_ID = "apollo-lunar-laser-ranging-telemetry"

EVIDENCE_COLUMNS: List[str] = [
    "id", "original_url", "canonical_url", "publisher", "canonical_publisher",
    "title", "published_date", "snippet", "source_tier", "stance",
    "is_verified", "retrieval_timestamp", "content_sha256", "source_domain",
    "canonical_domain", "is_potential_syndication", "syndication_notes", "doi",
    "is_full_text", "provenance_json", "source_type", "text_availability",
    "relevance_status", "relevance_score", "relevance_justification",
    "stance_justification", "duplicate_reason", "curation_status", "reviewer_id",
    "review_timestamp", "reviewer_notes", "reviewer_confirmed_stance",
    "peer_review_confirmed", "text_provenance", "retrieval_method"
]

AUDIT_COLUMNS: List[str] = [
    "audit_id", "evidence_id", "claim_id", "previous_status", "new_status",
    "previous_stance", "new_stance", "reviewer_id", "reviewer_notes",
    "decision_timestamp"
]

SCHEMA_DDL = """
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
    source_type TEXT NOT NULL DEFAULT 'OTHER',
    text_availability TEXT NOT NULL DEFAULT 'METADATA_ONLY',
    relevance_status TEXT NOT NULL DEFAULT 'UNDETERMINED',
    relevance_score REAL,
    relevance_justification TEXT,
    stance_justification TEXT,
    duplicate_reason TEXT,
    curation_status TEXT NOT NULL DEFAULT 'UNREVIEWED' CHECK(curation_status IN ('UNREVIEWED', 'UNDER_REVIEW', 'APPROVED_VERIFIED', 'REJECTED_IRRELEVANT', 'REJECTED_UNRELIABLE', 'SUPERSEDED')),
    reviewer_id TEXT,
    review_timestamp TEXT,
    reviewer_notes TEXT,
    reviewer_confirmed_stance TEXT CHECK(reviewer_confirmed_stance IS NULL OR reviewer_confirmed_stance IN ('SUPPORTING', 'CONTRADICTING', 'NEUTRAL')),
    peer_review_confirmed INTEGER NOT NULL DEFAULT 0,
    text_provenance TEXT NOT NULL DEFAULT 'UNAVAILABLE' CHECK(text_provenance IN ('VERBATIM', 'SUMMARY', 'INTERPRETATION', 'UNAVAILABLE')),
    retrieval_method TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(retrieval_method IN ('LIVE', 'OFFLINE_FALLBACK', 'UNKNOWN'))
);

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
);

CREATE INDEX IF NOT EXISTS idx_records_sha256 ON evidence_records(content_sha256);
CREATE INDEX IF NOT EXISTS idx_records_canonical_dom ON evidence_records(canonical_domain);
CREATE INDEX IF NOT EXISTS idx_records_canonical_pub ON evidence_records(canonical_publisher);
CREATE INDEX IF NOT EXISTS idx_records_verified ON evidence_records(is_verified);
CREATE INDEX IF NOT EXISTS idx_records_curation_status ON evidence_records(curation_status);
CREATE INDEX IF NOT EXISTS idx_audit_evidence_id ON curation_audit_log(evidence_id);

CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
    id UNINDEXED,
    title,
    snippet,
    publisher,
    canonical_publisher,
    tokenize='porter unicode61'
);
"""


def load_and_validate_seed_file(seed_path: Path) -> Dict[str, Any]:
    """Read and validate the canonical JSON seed fixture."""
    if not seed_path.exists():
        raise FileNotFoundError(f"Canonical seed file not found: {seed_path}")

    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Malformed seed fixture: expected top-level JSON object, got {type(data)}")

    records = data.get("records")
    audits = data.get("curation_audit_log")

    if not isinstance(records, list) or len(records) != EXPECTED_SEED_RECORD_COUNT:
        raise ValueError(f"Seed fixture record count mismatch: expected {EXPECTED_SEED_RECORD_COUNT}, got {len(records) if isinstance(records, list) else type(records)}")

    if not isinstance(audits, list) or len(audits) != EXPECTED_SEED_AUDIT_COUNT:
        raise ValueError(f"Seed fixture audit count mismatch: expected {EXPECTED_SEED_AUDIT_COUNT}, got {len(audits) if isinstance(audits, list) else type(audits)}")

    # Verify column presence across all records
    for r in records:
        missing = [c for c in EVIDENCE_COLUMNS if c not in r]
        if missing:
            raise ValueError(f"Record '{r.get('id')}' is missing required fields: {missing}")

    for a in audits:
        missing = [c for c in AUDIT_COLUMNS if c not in a]
        if missing:
            raise ValueError(f"Audit entry '{a.get('audit_id')}' is missing required fields: {missing}")

    return data


def cleanup_staging_files(staging_path: Path) -> None:
    """Safely remove staging database and any SQLite sidecars."""
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(staging_path) + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError as err:
                logger.warning("Could not unlink staging sidecar '%s': %s", p, err)


def initialize_database(
    target_path: Path,
    seed_path: Optional[Path] = None,
) -> bool:
    """Perform safe, non-destructive, atomic database initialization."""
    target_path = target_path.resolve()
    seed_path = (seed_path or (_project_root / "backend" / "data" / "seeds" / "evidence_seed_v1.0.json")).resolve()

    logger.info("Initializing VERITAS database...")
    logger.info("  Target database path: %s", target_path)
    logger.info("  Seed fixture path:   %s", seed_path)

    # 1. Strict Non-Overwrite Guard
    if target_path.exists():
        logger.error(
            "REFUSAL: Target database '%s' already exists (%d bytes). "
            "VERITAS initializer strictly refuses to overwrite, truncate, or reseed existing files. "
            "Aborting.",
            target_path, target_path.stat().st_size
        )
        return False

    # 2. Validate Seed Data
    try:
        seed_data = load_and_validate_seed_file(seed_path)
    except Exception as exc:
        logger.error("Seed data validation failed: %s", exc)
        return False

    records = seed_data["records"]
    audits = seed_data["curation_audit_log"]

    # 3. Create Unique Staging File on the Same Filesystem
    target_path.parent.mkdir(parents=True, exist_ok=True)
    staging_name = f"{target_path.name}.staging_{os.getpid()}_{uuid.uuid4().hex[:8]}.db"
    staging_path = target_path.parent / staging_name

    logger.info("  Constructing staging database: %s", staging_path)

    conn = None
    try:
        conn = sqlite3.connect(str(staging_path), timeout=30.0)
        cursor = conn.cursor()

        # Initialize WAL mode and enforce foreign keys
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Create Schema
        cursor.executescript(SCHEMA_DDL)

        # Atomic Seeding Transaction
        cursor.execute("BEGIN TRANSACTION;")

        ev_placeholders = ",".join(["?"] * len(EVIDENCE_COLUMNS))
        ev_sql = f"INSERT INTO evidence_records ({','.join(EVIDENCE_COLUMNS)}) VALUES ({ev_placeholders})"
        for r in records:
            values = [r[col] for col in EVIDENCE_COLUMNS]
            cursor.execute(ev_sql, values)

        aud_placeholders = ",".join(["?"] * len(AUDIT_COLUMNS))
        aud_sql = f"INSERT INTO curation_audit_log ({','.join(AUDIT_COLUMNS)}) VALUES ({aud_placeholders})"
        for a in audits:
            values = [a[col] for col in AUDIT_COLUMNS]
            cursor.execute(aud_sql, values)

        # Populate FTS5 Virtual Table
        cursor.execute(
            """
            INSERT INTO evidence_fts (id, title, snippet, publisher, canonical_publisher)
            SELECT id, title, snippet, publisher, canonical_publisher FROM evidence_records;
            """
        )

        conn.commit()

        # Pre-Activation Validation Gates
        # Gate 1: Integrity Check
        integrity = cursor.execute("PRAGMA integrity_check;").fetchall()
        if integrity != [("ok",)]:
            raise RuntimeError(f"Integrity check failed: {integrity}")

        # Gate 2: Foreign Key Check
        fk_violations = cursor.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_violations:
            raise RuntimeError(f"Foreign key violations detected: {fk_violations}")

        # Gate 3: Record Count
        count_rec = cursor.execute("SELECT count(*) FROM evidence_records;").fetchone()[0]
        if count_rec != EXPECTED_SEED_RECORD_COUNT:
            raise RuntimeError(f"Record count mismatch: expected {EXPECTED_SEED_RECORD_COUNT}, got {count_rec}")

        # Gate 4: FTS Count
        count_fts = cursor.execute("SELECT count(*) FROM evidence_fts;").fetchone()[0]
        if count_fts != EXPECTED_SEED_RECORD_COUNT:
            raise RuntimeError(f"FTS count mismatch: expected {EXPECTED_SEED_RECORD_COUNT}, got {count_fts}")

        # Gate 5: Audit Count
        count_aud = cursor.execute("SELECT count(*) FROM curation_audit_log;").fetchone()[0]
        if count_aud != EXPECTED_SEED_AUDIT_COUNT:
            raise RuntimeError(f"Audit count mismatch: expected {EXPECTED_SEED_AUDIT_COUNT}, got {count_aud}")

        # Gate 6: Status Breakdown
        status_map = dict(cursor.execute("SELECT curation_status, count(*) FROM evidence_records GROUP BY curation_status;").fetchall())
        if status_map.get("APPROVED_VERIFIED", 0) != EXPECTED_APPROVED_COUNT:
            raise RuntimeError(f"APPROVED_VERIFIED count mismatch: expected {EXPECTED_APPROVED_COUNT}, got {status_map.get('APPROVED_VERIFIED', 0)}")
        if status_map.get("REJECTED_IRRELEVANT", 0) != EXPECTED_REJECTED_COUNT:
            raise RuntimeError(f"REJECTED_IRRELEVANT count mismatch: expected {EXPECTED_REJECTED_COUNT}, got {status_map.get('REJECTED_IRRELEVANT', 0)}")
        if status_map.get("UNREVIEWED", 0) != EXPECTED_UNREVIEWED_COUNT:
            raise RuntimeError(f"UNREVIEWED count mismatch: expected {EXPECTED_UNREVIEWED_COUNT}, got {status_map.get('UNREVIEWED', 0)}")

        # Gate 7: Verification Flags
        verif_map = dict(cursor.execute("SELECT is_verified, count(*) FROM evidence_records GROUP BY is_verified;").fetchall())
        if verif_map.get(1, 0) != EXPECTED_VERIFIED_FLAG_1 or verif_map.get(0, 0) != EXPECTED_VERIFIED_FLAG_0:
            raise RuntimeError(f"Verification flag breakdown mismatch: expected 1:{EXPECTED_VERIFIED_FLAG_1}, 0:{EXPECTED_VERIFIED_FLAG_0}, got {verif_map}")

        # Gate 8: Critical Records Check
        dol_row = cursor.execute("SELECT is_verified, curation_status, stance, content_sha256 FROM evidence_records WHERE id = ?;", (DOL_RECORD_ID,)).fetchone()
        if not dol_row or dol_row[0] != 0 or dol_row[1] != "UNREVIEWED" or dol_row[3] != DOL_EXPECTED_SHA256:
            raise RuntimeError(f"DOL Fact Sheet #48 validation failed: {dol_row}")

        lucas_row = cursor.execute("SELECT is_verified, curation_status, stance, content_sha256 FROM evidence_records WHERE id = ?;", (LUCAS_RECORD_ID,)).fetchone()
        if not lucas_row or lucas_row[0] != 0 or lucas_row[1] != "UNREVIEWED" or lucas_row[3] != LUCAS_EXPECTED_SHA256:
            raise RuntimeError(f"Lucas v. Jerusalem Cafe validation failed: {lucas_row}")

        # Gate 9: Representative FTS Search Verification
        fts_queries = [
            ('"Hoffman"* OR "Plastics"*', DOL_RECORD_ID),
            ('"Jerusalem"* OR "Cafe"*', LUCAS_RECORD_ID),
            ('"Planetary"* OR "Ephemerides"*', "de440-jpl-planetary-ephemeris"),
            ('"World"* OR "Geodetic"*', "wgs84-tr8350-geodetic-datum"),
        ]
        for q, expected_id in fts_queries:
            matches = [m[0] for m in cursor.execute("SELECT id FROM evidence_fts WHERE evidence_fts MATCH ?;", (q,)).fetchall()]
            if expected_id not in matches:
                raise RuntimeError(f"FTS verification failed for query '{q}': expected '{expected_id}' in {matches}")

        logger.info("  All pre-activation validation gates PASSED.")

        # Checkpoint WAL and eliminate sidecars
        checkpoint_res = cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
        busy, log, checkpointed = checkpoint_res[0], checkpoint_res[1], checkpoint_res[2]
        if busy != 0 or log != 0:
            raise RuntimeError(f"WAL checkpoint failure: busy={busy}, log={log}, checkpointed={checkpointed}")

        # Transition to DELETE journal mode to synchronously remove WAL sidecars
        cursor.execute("PRAGMA journal_mode = DELETE;").fetchall()
        cursor.close()
        cursor = None
        conn.close()
        conn = None
        gc.collect()

        # Confirm zero sidecars remain
        wal_file = Path(str(staging_path) + "-wal")
        shm_file = Path(str(staging_path) + "-shm")
        if wal_file.exists() or shm_file.exists():
            raise RuntimeError("Residual WAL/SHM sidecars detected after checkpoint.")

        # 4. Atomic No-Overwrite Activation via POSIX link(2)
        # Re-check target non-existence immediately prior to activation
        if target_path.exists():
            raise FileExistsError(
                f"Target path '{target_path}' already exists (detected immediately prior to activation)."
            )

        try:
            # Atomic hard-link with kernel-enforced O_EXCL / EEXIST semantics on POSIX
            os.link(staging_path, target_path)
            logger.info("  Atomic activation successful: '%s' created.", target_path)
        except FileExistsError as err:
            logger.error("Concurrency collision: target '%s' was created concurrently by another process.", target_path)
            raise FileExistsError(f"Target path '{target_path}' already exists.") from err
        except OSError as err:
            logger.error(
                "Atomic hard-link activation failed (errno=%s: %s). "
                "Failing closed: VERITAS initializer strictly refuses to use overwrite-capable "
                "or partial-copy fallbacks.",
                getattr(err, "errno", "unknown"),
                err,
            )
            raise RuntimeError(
                f"Atomic no-overwrite activation unsupported or failed on this filesystem: {err}"
            ) from err

        # Target link established atomically; now safely remove staging name
        try:
            staging_path.unlink()
        except OSError as unlink_err:
            logger.warning(
                "Target activated successfully, but staging link '%s' could not be unlinked: %s",
                staging_path, unlink_err
            )

        # 5. Post-Activation Verification (Read-Only Mode)
        # Note: In accordance with safety rules, never automatically delete target_path if post-check fails.
        act_conn = sqlite3.connect(f"file:{target_path.resolve()}?mode=ro", uri=True, timeout=15.0)
        act_cursor = act_conn.cursor()

        act_integrity = act_cursor.execute("PRAGMA integrity_check;").fetchall()
        act_fk = act_cursor.execute("PRAGMA foreign_key_check;").fetchall()
        act_recs = act_cursor.execute("SELECT count(*) FROM evidence_records;").fetchone()[0]
        act_auds = act_cursor.execute("SELECT count(*) FROM curation_audit_log;").fetchone()[0]
        act_cursor.close()
        act_conn.close()

        if act_integrity != [("ok",)] or act_fk != [] or act_recs != EXPECTED_SEED_RECORD_COUNT or act_auds != EXPECTED_SEED_AUDIT_COUNT:
            logger.critical(
                "CRITICAL: Post-activation check failed on '%s' (integrity=%s, fk=%s, recs=%d, auds=%d). "
                "The target database is NOT automatically deleted for forensic inspection.",
                target_path, act_integrity, act_fk, act_recs, act_auds
            )
            return False

        logger.info("VERITAS database initialization completed successfully.")
        logger.info("  Total records: %d | Total audits: %d | FTS entries: %d", act_recs, act_auds, count_fts)
        return True

    except Exception as err:
        logger.error("Initialization failed: %s", err)
        if "cursor" in locals() and cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        cleanup_staging_files(staging_path)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize VERITAS SQLite database from canonical seed JSON.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(settings.EVIDENCE_DB_PATH),
        help=f"Target SQLite database path (default: {settings.EVIDENCE_DB_PATH})",
    )
    parser.add_argument(
        "--seed-file",
        type=Path,
        default=_project_root / "backend" / "data" / "seeds" / "evidence_seed_v1.0.json",
        help="Canonical seed JSON file path (default: backend/data/seeds/evidence_seed_v1.0.json)",
    )

    args = parser.parse_args()
    success = initialize_database(target_path=args.db_path, seed_path=args.seed_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
