"""Automated Reproducibility and Safety Test Suite for VERITAS Database Initializer.

Validates that:
1. Fresh initialization from the canonical seed JSON creates a valid SQLite database.
2. Exactly 60 evidence records and 4 audit entries are populated with 100% field fidelity.
3. Curation statuses (3 APPROVED_VERIFIED, 1 REJECTED_IRRELEVANT, 56 UNREVIEWED) and verification flags are preserved.
4. Foreign-key referential integrity and ON DELETE RESTRICT are strictly enforced.
5. FTS5 index is populated and searchable with prefix and keyword terms.
6. Target databases that already exist (populated or empty) are strictly refused and untouched.
7. Interrupted or failed initializations clean up staging files without leaving partial databases.
8. Repeated initialization attempts safely abort with refusal codes.
"""

import concurrent.futures
import errno
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

# Ensure project root in sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from backend.config import settings
from backend.scripts.init_database import (
    initialize_database,
    EVIDENCE_COLUMNS,
    AUDIT_COLUMNS,
    DOL_RECORD_ID,
    DOL_EXPECTED_SHA256,
    LUCAS_RECORD_ID,
    LUCAS_EXPECTED_SHA256,
    REJECTED_RECORD_ID,
    EXPECTED_SEED_RECORD_COUNT,
    EXPECTED_SEED_AUDIT_COUNT,
)
from backend.services.evidence_repository import EvidenceRepository

CANONICAL_SEED_PATH = _project_root / "backend" / "data" / "seeds" / "evidence_seed_v1.0.json"


class TestDatabaseReproducibility(unittest.TestCase):
    """Rigorous isolated test cases executing against disposable temporary directories."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.temp_dir.name)
        self.target_db = self.sandbox / "test_evidence.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_fresh_database_initialization(self):
        """Test 1: Fresh initialization on a non-existent path succeeds and passes integrity check."""
        self.assertFalse(self.target_db.exists(), "Target database must not exist before initialization.")
        success = initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)
        self.assertTrue(success, "Initialization must return True on fresh target path.")
        self.assertTrue(self.target_db.exists(), "Target database must exist after successful initialization.")

        # Reopen read-only and verify integrity
        conn = sqlite3.connect(f"file:{self.target_db}?mode=ro", uri=True)
        cursor = conn.cursor()
        integrity = cursor.execute("PRAGMA integrity_check;").fetchall()
        self.assertEqual(integrity, [("ok",)], "PRAGMA integrity_check must return 'ok'.")
        fk_check = cursor.execute("PRAGMA foreign_key_check;").fetchall()
        self.assertEqual(fk_check, [], "PRAGMA foreign_key_check must return 0 violations.")
        conn.close()

    def test_02_exact_60_record_field_by_field_round_trip(self):
        """Test 2: All 60 records and all 35 columns match the canonical seed JSON field by field."""
        initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)

        with open(CANONICAL_SEED_PATH, "r", encoding="utf-8") as f:
            seed_data = json.load(f)
        seed_records = {r["id"]: r for r in seed_data["records"]}

        conn = sqlite3.connect(f"file:{self.target_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        db_records = {r["id"]: dict(r) for r in cursor.execute("SELECT * FROM evidence_records;").fetchall()}
        conn.close()

        self.assertEqual(len(db_records), EXPECTED_SEED_RECORD_COUNT)
        self.assertEqual(set(db_records.keys()), set(seed_records.keys()))

        # Check all 35 columns across all 60 records
        for rid, s_rec in seed_records.items():
            d_rec = db_records[rid]
            for col in EVIDENCE_COLUMNS:
                self.assertEqual(
                    s_rec[col],
                    d_rec[col],
                    f"Mismatch in record '{rid}', column '{col}': seed={s_rec[col]!r}, db={d_rec[col]!r}",
                )

    def test_03_exact_four_audit_log_round_trip(self):
        """Test 3: All 4 audit log entries and all 10 columns match the canonical seed JSON field by field."""
        initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)

        with open(CANONICAL_SEED_PATH, "r", encoding="utf-8") as f:
            seed_data = json.load(f)
        seed_audits = {a["audit_id"]: a for a in seed_data["curation_audit_log"]}

        conn = sqlite3.connect(f"file:{self.target_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        db_audits = {a["audit_id"]: dict(a) for a in cursor.execute("SELECT * FROM curation_audit_log;").fetchall()}
        conn.close()

        self.assertEqual(len(db_audits), EXPECTED_SEED_AUDIT_COUNT)
        self.assertEqual(set(db_audits.keys()), set(seed_audits.keys()))

        for aid, s_aud in seed_audits.items():
            d_aud = db_audits[aid]
            for col in AUDIT_COLUMNS:
                self.assertEqual(
                    s_aud[col],
                    d_aud[col],
                    f"Mismatch in audit '{aid}', column '{col}': seed={s_aud[col]!r}, db={d_aud[col]!r}",
                )

    def test_04_curation_status_and_verification_flag_preservation(self):
        """Test 4: Exact curation status breakdown and verification flags are preserved."""
        initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)

        conn = sqlite3.connect(f"file:{self.target_db}?mode=ro", uri=True)
        cursor = conn.cursor()

        status_counts = dict(cursor.execute("SELECT curation_status, count(*) FROM evidence_records GROUP BY curation_status;").fetchall())
        self.assertEqual(status_counts.get("APPROVED_VERIFIED", 0), 3)
        self.assertEqual(status_counts.get("REJECTED_IRRELEVANT", 0), 1)
        self.assertEqual(status_counts.get("UNREVIEWED", 0), 56)

        verif_counts = dict(cursor.execute("SELECT is_verified, count(*) FROM evidence_records GROUP BY is_verified;").fetchall())
        self.assertEqual(verif_counts.get(1, 0), 3)
        self.assertEqual(verif_counts.get(0, 0), 57)

        # Check rejected record ID
        rej_id = cursor.execute("SELECT id FROM evidence_records WHERE curation_status = 'REJECTED_IRRELEVANT';").fetchone()[0]
        self.assertEqual(rej_id, REJECTED_RECORD_ID)

        # Check critical hashes and unreviewed status
        dol_row = cursor.execute("SELECT is_verified, curation_status, stance, content_sha256 FROM evidence_records WHERE id = ?;", (DOL_RECORD_ID,)).fetchone()
        self.assertEqual(dol_row, (0, "UNREVIEWED", "NEUTRAL", DOL_EXPECTED_SHA256))

        lucas_row = cursor.execute("SELECT is_verified, curation_status, stance, content_sha256 FROM evidence_records WHERE id = ?;", (LUCAS_RECORD_ID,)).fetchone()
        self.assertEqual(lucas_row, (0, "UNREVIEWED", "NEUTRAL", LUCAS_EXPECTED_SHA256))

        conn.close()

    def test_05_foreign_key_integrity_and_restrict(self):
        """Test 5: Foreign key integrity holds and ON DELETE RESTRICT prevents deleting referenced records."""
        initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)

        conn = sqlite3.connect(str(self.target_db))
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        # Confirm 0 foreign key violations
        self.assertEqual(cursor.execute("PRAGMA foreign_key_check;").fetchall(), [])

        # Attempt to delete record referenced in audit log (de440)
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute("DELETE FROM evidence_records WHERE id = 'de440-jpl-planetary-ephemeris';")

        conn.close()

    def test_06_fts5_search_consistency(self):
        """Test 6: FTS5 virtual table is populated and returns expected records for multi-domain queries."""
        initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)

        conn = sqlite3.connect(f"file:{self.target_db}?mode=ro", uri=True)
        cursor = conn.cursor()

        fts_count = cursor.execute("SELECT count(*) FROM evidence_fts;").fetchone()[0]
        self.assertEqual(fts_count, EXPECTED_SEED_RECORD_COUNT)

        test_queries = [
            ("Hoffman Plastics", DOL_RECORD_ID),
            ("Jerusalem Cafe", LUCAS_RECORD_ID),
            ("Planetary Ephemerides", "de440-jpl-planetary-ephemeris"),
            ("altimetry geoid", "jgr-ocean-satellite-geoid-curvature"),
            ("World Geodetic System", "wgs84-tr8350-geodetic-datum"),
            ("Apollo Lunar Laser", REJECTED_RECORD_ID),
        ]

        for raw_q, expected_id in test_queries:
            safe_q = EvidenceRepository.sanitize_fts_query(raw_q)
            matches = [r[0] for r in cursor.execute("SELECT id FROM evidence_fts WHERE evidence_fts MATCH ?;", (safe_q,)).fetchall()]
            self.assertIn(expected_id, matches, f"FTS query '{raw_q}' did not return expected record '{expected_id}'.")

        conn.close()

    def test_07_refusal_to_overwrite_populated_database(self):
        """Test 7: The initializer strictly refuses to overwrite an existing populated database."""
        # Create a pre-existing populated database
        conn = sqlite3.connect(str(self.target_db))
        conn.execute("CREATE TABLE evidence_records (id TEXT PRIMARY KEY, title TEXT);")
        conn.execute("INSERT INTO evidence_records VALUES ('custom-preexisting', 'Custom Title');")
        conn.commit()
        conn.close()

        # Invoking initializer on existing target must return False
        success = initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)
        self.assertFalse(success, "Initializer must refuse to overwrite an existing database.")

        # Confirm original custom record remains intact
        conn = sqlite3.connect(f"file:{self.target_db}?mode=ro", uri=True)
        cursor = conn.cursor()
        rows = cursor.execute("SELECT id, title FROM evidence_records;").fetchall()
        conn.close()

        self.assertEqual(rows, [("custom-preexisting", "Custom Title")], "Original records must not be altered.")

    def test_08_refusal_to_overwrite_empty_existing_file(self):
        """Test 8: The initializer strictly refuses to overwrite even an empty (0-byte) existing file."""
        # Create a 0-byte file
        self.target_db.touch()
        self.assertTrue(self.target_db.exists())

        success = initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)
        self.assertFalse(success, "Initializer must refuse to overwrite even an existing empty file.")
        self.assertEqual(self.target_db.stat().st_size, 0, "Target file must remain 0 bytes.")

    def test_09_interrupted_initialization_safety(self):
        """Test 9: A failed or interrupted initialization cleans up staging files and does not create target."""
        # Create a corrupt temporary seed file
        corrupt_seed = self.sandbox / "corrupt_seed.json"
        with open(corrupt_seed, "w", encoding="utf-8") as f:
            json.dump({"records": [{"id": "bad_record"}]}, f)

        success = initialize_database(target_path=self.target_db, seed_path=corrupt_seed)
        self.assertFalse(success, "Initialization with malformed seed must fail.")
        self.assertFalse(self.target_db.exists(), "Target database must not exist after failed initialization.")

        # Confirm no residual staging files or sidecars remain in directory
        residuals = list(self.sandbox.glob("*.staging_*"))
        self.assertEqual(residuals, [], f"Residual staging files found: {residuals}")

    def test_10_repeat_initialization_safety(self):
        """Test 10: Running the initializer twice against the same target path safely refuses the second run."""
        # Run 1: Should succeed
        first_run = initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)
        self.assertTrue(first_run)

        size_after_first = self.target_db.stat().st_size
        self.assertGreater(size_after_first, 0)

        # Run 2: Should refuse
        second_run = initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)
        self.assertFalse(second_run, "Second initialization must be refused.")

        # Confirm database size and records did not change
        conn = sqlite3.connect(f"file:{self.target_db}?mode=ro", uri=True)
        cursor = conn.cursor()
        count = cursor.execute("SELECT count(*) FROM evidence_records;").fetchone()[0]
        conn.close()

        self.assertEqual(count, EXPECTED_SEED_RECORD_COUNT, "Record count must not duplicate on repeated run.")
        self.assertEqual(self.target_db.stat().st_size, size_after_first, "File size must not change.")

    def test_11_concurrent_initialization_safety(self):
        """Test 11: Two concurrent initialization attempts targeting the same path result in exactly one winner without corruption."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(initialize_database, self.target_db, CANONICAL_SEED_PATH)
            future2 = executor.submit(initialize_database, self.target_db, CANONICAL_SEED_PATH)
            results = [future1.result(), future2.result()]

        # Exactly one process must succeed, and one must safely fail/refuse
        self.assertEqual(sorted(results), [False, True], f"Expected exactly one success and one refusal, got {results}")

        # Target database must be valid and complete
        self.assertTrue(self.target_db.exists(), "Target database must exist after concurrent run.")
        conn = sqlite3.connect(f"file:{self.target_db}?mode=ro", uri=True)
        cursor = conn.cursor()
        integrity = cursor.execute("PRAGMA integrity_check;").fetchall()
        count = cursor.execute("SELECT count(*) FROM evidence_records;").fetchone()[0]
        conn.close()

        self.assertEqual(integrity, [("ok",)])
        self.assertEqual(count, EXPECTED_SEED_RECORD_COUNT)

        # Residual staging files for BOTH processes must be cleaned up
        residuals = list(self.sandbox.glob("*.staging_*"))
        self.assertEqual(residuals, [], f"Residual staging files found after concurrency test: {residuals}")

    def test_12_atomic_collision_at_link_time(self):
        """Test 12: Collision at os.link time fails closed and preserves the existing winning database."""
        # Establish a pre-existing "winning" database with known content
        self.target_db.write_text("pre_existing_unmodified_winner")

        def fake_link(src, dst):
            raise FileExistsError(f"Target path '{dst}' already exists.")

        with patch("os.link", side_effect=fake_link):
            success = initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)

        self.assertFalse(success, "Initialization must fail on activation collision.")
        self.assertEqual(
            self.target_db.read_text(),
            "pre_existing_unmodified_winner",
            "Winning database content must never be overwritten on collision.",
        )

        residuals = list(self.sandbox.glob("*.staging_*"))
        self.assertEqual(residuals, [], f"Staging files must be cleaned up after collision: {residuals}")

    def test_13_unsupported_hardlink_fails_closed(self):
        """Test 13: Unsupported hard-link activation fails closed without partial copies or overwrite fallbacks."""
        unsupported_err = OSError(errno.ENOTSUP, "Operation not supported on this filesystem")

        with patch("os.link", side_effect=unsupported_err):
            success = initialize_database(target_path=self.target_db, seed_path=CANONICAL_SEED_PATH)

        self.assertFalse(success, "Initialization must fail closed when os.link is unsupported.")
        self.assertFalse(self.target_db.exists(), "No target database must be created if atomic link is unsupported.")

        residuals = list(self.sandbox.glob("*.staging_*"))
        self.assertEqual(residuals, [], f"Staging files must be cleaned up: {residuals}")

    def test_14_no_partial_target_database_on_failure(self):
        """Test 14: Failed validation gates clean up staging and never expose a partial target file."""
        # Corrupt JSON missing mandatory columns
        bad_seed = self.sandbox / "incomplete_seed.json"
        with open(bad_seed, "w", encoding="utf-8") as f:
            json.dump({"records": [{"id": f"rec_{i}"} for i in range(60)], "curation_audit_log": []}, f)

        success = initialize_database(target_path=self.target_db, seed_path=bad_seed)
        self.assertFalse(success)
        self.assertFalse(self.target_db.exists(), "Target database must not exist on failed validation.")

        residuals = list(self.sandbox.glob("*.staging_*"))
        self.assertEqual(residuals, [], f"Residual files found: {residuals}")


if __name__ == "__main__":
    unittest.main()
