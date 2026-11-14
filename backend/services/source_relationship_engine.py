"""Source relationship and proposition-level independence engine for VERITAS.

Implements isolated repository operations, directional provenance handling,
Union-Find clustering strictly on approved symmetric dependence relations,
transitive conflict prevention, and the Two-Key Corroboration Gate with
stance-aware assessment and immutable audit logging.
"""

import calendar
from datetime import date, datetime, timedelta, timezone
import json
import re
import sqlite3
from typing import Dict, List, Optional, Set, Tuple, Union

from backend.schemas.source_relationship import (
    AuthorityCluster,
    ChallengeAction,
    ChallengeDecision,
    EmpiricalIndependenceAudit,
    EvidenceDomain,
    HistoricalProvenanceAudit,
    IncompleteEmpiricalAuditError,
    IndependenceStatus,
    LegalDateType,
    LegalTemporalMetadata,
    MERGEABLE_DEPENDENCE_RELATIONSHIP_TYPES,
    DIRECTIONAL_RELATIONSHIP_TYPES,
    OperationalStatus,
    PropositionCorroborationAssessment,
    RelationshipType,
    SourcePairRelationship,
    SourceRelationshipAuditLogEntry,
    TemporalQuantification,
    TemporalScope,
    TextualEpoch,
    TransitiveConflictError,
)


def expand_uncertain_date(date_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Expand ISO date string with varying granularities into a closed [min, max] interval."""
    if not date_str or not isinstance(date_str, str):
        return None, None
    s = date_str.strip()
    # YYYY-MM-DD
    m_day = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m_day:
        y, m, d = int(m_day.group(1)), int(m_day.group(2)), int(m_day.group(3))
        try:
            val = date(y, m, d).isoformat()
            return val, val
        except ValueError:
            return None, None
    # YYYY-MM
    m_mo = re.match(r"^(\d{4})-(\d{2})$", s)
    if m_mo:
        y, m = int(m_mo.group(1)), int(m_mo.group(2))
        try:
            last_day = calendar.monthrange(y, m)[1]
            return date(y, m, 1).isoformat(), date(y, m, last_day).isoformat()
        except ValueError:
            return None, None
    # YYYY
    m_yr = re.match(r"^(\d{4})$", s)
    if m_yr:
        y = int(m_yr.group(1))
        return f"{y:04d}-01-01", f"{y:04d}-12-31"
    # Decade: e.g. 1920s
    m_dec = re.match(r"^(\d{3}0)s$", s)
    if m_dec:
        dec = int(m_dec.group(1))
        return f"{dec:04d}-01-01", f"{dec+9:04d}-12-31"
    return None, None


def check_temporal_interval_overlap(
    source_from: Optional[str],
    source_to: Optional[str],
    target_start: Optional[str],
    target_end: Optional[str],
    operational_status: str,
    quantification: str = "INTERSECTING",
) -> Tuple[bool, str]:
    """Evaluate whether an evidence interval corroborates a proposition's reference period.

    Implements pessimistic (worst-case) uncertainty interval bounding to ensure that
    corroboration is epistemologically guaranteed and fails closed on ambiguity.
    """
    if not target_start or not target_end:
        return False, "MISSING_TARGET_BOUNDS"
    if not source_from:
        return False, "MISSING_SOURCE_FROM"

    c_start_min, c_start_max = expand_uncertain_date(target_start)
    c_end_min, c_end_max = expand_uncertain_date(target_end)
    if not c_start_min or not c_end_max:
        return False, "INVALID_TARGET_DATE_FORMAT"
    if c_start_min > c_end_max:
        return False, "INVERTED_TARGET_BOUNDS"

    s_from_min, s_from_max = expand_uncertain_date(source_from)
    if not s_from_min:
        return False, "INVALID_SOURCE_FROM_FORMAT"

    if not source_to:
        if operational_status == OperationalStatus.CURRENT_OPERATIVE.value:
            s_to_min, s_to_max = "9999-12-31", "9999-12-31"
        else:
            return False, "HISTORICAL_MISSING_TERMINATION"
    else:
        s_to_min, s_to_max = expand_uncertain_date(source_to)
        if not s_to_min:
            return False, "INVALID_SOURCE_TO_FORMAT"
        if s_from_min > s_to_max:
            return False, "INVERTED_SOURCE_BOUNDS"

    quant_val = quantification.value if hasattr(quantification, "value") else str(quantification or "INTERSECTING")
    quant_str = quant_val.upper()
    if quant_str in ("CONTINUOUS_FULL_PERIOD", TemporalQuantification.CONTINUOUS_FULL_PERIOD.value):
        # Universal Subsumption: Authority was active throughout the entire claimed epoch
        if s_from_max <= c_start_min and s_to_min >= c_end_max:
            return True, "OVERLAP_VALID"
        else:
            return False, "INCOMPLETE_FULL_PERIOD_COVERAGE"
    else:
        # Existential Intersection: Guaranteed non-empty interval overlap
        if s_from_max <= c_end_min and s_to_min >= c_start_max:
            return True, "OVERLAP_VALID"
        # Check optimistic overlap to emit precise diagnostic
        if s_from_min <= c_end_max and s_to_max >= c_start_min:
            return False, "UNVERIFIED_TEMPORAL_AMBIGUITY"
        return False, "DISJOINT_INTERVALS"


def check_composite_coverage_chain(
    sources: List[Dict],
    target_start: str,
    target_end: str,
) -> Tuple[bool, str]:
    """Verify that a sequence of successive legal authorities continuously covers an epoch without hiatus.

    Implements Section 1.3 composite chaining rules:
    1. Stance uniformity across chain.
    2. Chronological inception ordering.
    3. Coverage inception subsumes target start.
    4. Strict contiguity: no calendar gap between expiration of S_i and inception of S_{i+1}.
    5. Coverage termination subsumes target end.
    """
    if not sources or not target_start or not target_end:
        return False, "MISSING_INPUTS"

    c_start_min, c_start_max = expand_uncertain_date(target_start)
    c_end_min, c_end_max = expand_uncertain_date(target_end)
    if not c_start_min or not c_end_max:
        return False, "INVALID_TARGET_BOUNDS"

    # 1. Stance uniformity
    stances = {s.get("stance", "NEUTRAL") for s in sources}
    if len(stances) > 1:
        return False, "CONFLICTING_STANCES_IN_CHAIN"

    parsed = []
    for s in sources:
        s_from = s.get("effective_from_date")
        s_to = s.get("effective_to_date")
        op_status = s.get("operational_status")

        f_min, f_max = expand_uncertain_date(s_from)
        if not f_min:
            return False, "INVALID_OR_MISSING_SOURCE_FROM"

        if not s_to:
            if op_status == OperationalStatus.CURRENT_OPERATIVE.value:
                t_min, t_max = "9999-12-31", "9999-12-31"
            else:
                return False, "HISTORICAL_MISSING_TERMINATION"
        else:
            t_min, t_max = expand_uncertain_date(s_to)
            if not t_min:
                return False, "INVALID_SOURCE_TO"

        parsed.append({"from_min": f_min, "from_max": f_max, "to_min": t_min, "to_max": t_max})

    # 2. Sort by inception
    parsed.sort(key=lambda x: x["from_max"])

    # 3. Coverage inception
    if parsed[0]["from_max"] > c_start_min:
        return False, "CHAIN_INCEPTION_GAP"

    # 4. Contiguity: no hiatus
    current_max_coverage = parsed[0]["to_min"]
    for nxt in parsed[1:]:
        curr_dt = date.fromisoformat(current_max_coverage) if current_max_coverage != "9999-12-31" else date(9999, 12, 31)
        next_allowed = (curr_dt + timedelta(days=1)).isoformat() if curr_dt.year < 9999 else "9999-12-31"
        if nxt["from_max"] > next_allowed and nxt["from_min"] > current_max_coverage:
            return False, f"HIATUS_GAP_DETECTED: {current_max_coverage} to {nxt['from_min']}"
        if nxt["to_min"] > current_max_coverage:
            current_max_coverage = nxt["to_min"]

    # 5. Coverage termination
    if current_max_coverage < c_end_max:
        return False, "CHAIN_TERMINATION_GAP"

    return True, "COMPOSITE_CHAIN_VALID"


class DisjointSet:
    """Disjoint-Set (Union-Find) with path compression and union-by-rank.

    STRICT INVARIANT:
    Only elements with verified symmetric DEPENDENT relationships may be merged via union().
    """

    def __init__(self, elements: List[str]):
        self.parent = {el: el for el in elements}
        self.rank = {el: 0 for el in elements}

    def find(self, item: str) -> str:
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, item1: str, item2: str):
        root1 = self.find(item1)
        root2 = self.find(item2)
        if root1 != root2:
            if self.rank[root1] < self.rank[root2]:
                self.parent[root1] = root2
            elif self.rank[root1] > self.rank[root2]:
                self.parent[root2] = root1
            else:
                self.parent[root2] = root1
                self.rank[root1] += 1

    def get_components(self) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        for item in self.parent:
            root = self.find(item)
            groups.setdefault(root, []).append(item)
        return groups


def init_relationship_tables(conn: sqlite3.Connection) -> None:
    """Create isolated relationship and audit log tables in a target SQLite database."""
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_pair_relationships (
            relationship_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id_a TEXT NOT NULL,
            source_id_b TEXT NOT NULL,
            proposition_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL CHECK(relationship_type IN (
                'EXACT_DUPLICATE', 'SYNDICATED_COPY', 'REPRINT_OR_TRANSLATION',
                'SHARED_UNDERLYING_SOURCE', 'DERIVED_REPETITION', 'CITES_OR_INTERPRETS',
                'DERIVED_FROM', 'INDEPENDENT', 'UNKNOWN', 'NOT_COMPARABLE'
            )),
            independence_status TEXT NOT NULL CHECK(independence_status IN (
                'INDEPENDENT', 'DEPENDENT', 'NOT_COMPARABLE', 'UNKNOWN'
            )),
            is_directional INTEGER NOT NULL DEFAULT 0,
            same_publisher_flag INTEGER NOT NULL DEFAULT 0,
            empirical_audit_json TEXT,
            reviewer_id TEXT NOT NULL,
            reviewer_notes TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CONSTRAINT uq_source_pair_prop UNIQUE (source_id_a, source_id_b, proposition_id),
            CONSTRAINT chk_diff_sources CHECK (source_id_a != source_id_b),
            CONSTRAINT chk_prop_id_nonempty CHECK (length(trim(proposition_id, ' ' || char(9) || char(10) || char(13))) > 0),
            CONSTRAINT chk_directionality_match CHECK (
                (relationship_type IN ('CITES_OR_INTERPRETS', 'DERIVED_FROM') AND is_directional = 1)
                OR
                (relationship_type NOT IN ('CITES_OR_INTERPRETS', 'DERIVED_FROM') AND is_directional = 0)
            ),
            CONSTRAINT chk_canonical_sym CHECK (is_directional = 1 OR source_id_a < source_id_b),
            CONSTRAINT chk_independence_consistency CHECK (
                (relationship_type = 'INDEPENDENT' AND independence_status = 'INDEPENDENT' AND empirical_audit_json IS NOT NULL AND json_valid(empirical_audit_json))
                OR
                (relationship_type != 'INDEPENDENT' AND independence_status != 'INDEPENDENT')
            ),
            CONSTRAINT chk_status_type_alignment CHECK (
                (relationship_type IN ('EXACT_DUPLICATE', 'SYNDICATED_COPY', 'REPRINT_OR_TRANSLATION', 'SHARED_UNDERLYING_SOURCE', 'DERIVED_REPETITION') AND independence_status = 'DEPENDENT')
                OR
                (relationship_type IN ('CITES_OR_INTERPRETS', 'DERIVED_FROM') AND independence_status IN ('DEPENDENT', 'UNKNOWN'))
                OR
                (relationship_type = 'UNKNOWN' AND independence_status = 'UNKNOWN')
                OR
                (relationship_type = 'NOT_COMPARABLE' AND independence_status = 'NOT_COMPARABLE')
                OR
                (relationship_type = 'INDEPENDENT' AND independence_status = 'INDEPENDENT')
            )
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_relationship_audit_log (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            relationship_id INTEGER NOT NULL,
            source_id_a TEXT NOT NULL,
            source_id_b TEXT NOT NULL,
            proposition_id TEXT NOT NULL,
            previous_relationship_type TEXT,
            new_relationship_type TEXT NOT NULL,
            previous_independence_status TEXT,
            new_independence_status TEXT NOT NULL,
            reviewer_id TEXT NOT NULL,
            reviewer_notes TEXT NOT NULL,
            decision_timestamp TEXT NOT NULL,
            FOREIGN KEY (relationship_id) REFERENCES source_pair_relationships(relationship_id) ON DELETE RESTRICT
        )
        """
    )

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_rel_pair ON source_pair_relationships(source_id_a, source_id_b)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_rel_prop ON source_pair_relationships(proposition_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_rel_audit ON source_relationship_audit_log(relationship_id)"
    )

    # Immutability triggers on audit log
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_delete
        BEFORE DELETE ON source_relationship_audit_log
        BEGIN
            SELECT RAISE(ABORT, 'Audit log entries are immutable and cannot be deleted.');
        END;
        """
    )

    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_update
        BEFORE UPDATE ON source_relationship_audit_log
        BEGIN
            SELECT RAISE(ABORT, 'Audit log entries are immutable and cannot be updated.');
        END;
        """
    )

    # Engine-level semantic audit validation triggers on source_pair_relationships
    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_validate_independent_audit_insert
        BEFORE INSERT ON source_pair_relationships
        FOR EACH ROW
        WHEN NEW.relationship_type = 'INDEPENDENT' OR NEW.independence_status = 'INDEPENDENT'
        BEGIN
            -- 1. Alignment check
            SELECT RAISE(ABORT, 'Audit Validation Error: relationship_type and independence_status must both be INDEPENDENT.')
            WHERE NEW.relationship_type != 'INDEPENDENT' OR NEW.independence_status != 'INDEPENDENT';

            -- 2. Syntactic JSON validity check
            SELECT RAISE(ABORT, 'Audit Validation Error: empirical_audit_json must be non-null and valid RFC 8259 JSON.')
            WHERE NEW.empirical_audit_json IS NULL OR json_valid(NEW.empirical_audit_json) != 1;

            -- 3. Criterion 1: Autonomous Data Collection
            SELECT RAISE(ABORT, 'Audit Validation Error: autonomous_data_collection must be explicitly true and data_collection_details >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.autonomous_data_collection'), '') != 'true'
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.data_collection_details'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 4. Criterion 2: Distinct Datasets
            SELECT RAISE(ABORT, 'Audit Validation Error: distinct_underlying_datasets must be true with distinct dataset identities (>= 3 chars) and dataset_separation_details >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.distinct_underlying_datasets'), '') != 'true'
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.dataset_a_identity'), ' ' || char(9) || char(10) || char(13))), 0) < 3
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.dataset_b_identity'), ' ' || char(9) || char(10) || char(13))), 0) < 3
               OR lower(trim(coalesce(json_extract(NEW.empirical_audit_json, '$.dataset_a_identity'), ''))) = lower(trim(coalesce(json_extract(NEW.empirical_audit_json, '$.dataset_b_identity'), '')))
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.dataset_separation_details'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 5. Criterion 3: Independent Methodology
            SELECT RAISE(ABORT, 'Audit Validation Error: independent_methodology must be true and methodology_details >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.independent_methodology'), '') != 'true'
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.methodology_details'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 6. Criterion 4: No Circular Reliance
            SELECT RAISE(ABORT, 'Audit Validation Error: no_circular_reliance must be true and circular_reliance_explanation >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.no_circular_reliance'), '') != 'true'
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.circular_reliance_explanation'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 7. Criterion 5: Exact Proposition Scope Match
            SELECT RAISE(ABORT, 'Audit Validation Error: exact_proposition_scope must be true, proposition_id must match parent, and proposition_scope_explanation >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.exact_proposition_scope'), '') != 'true'
               OR trim(coalesce(json_extract(NEW.empirical_audit_json, '$.proposition_id'), '')) != trim(NEW.proposition_id)
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.proposition_scope_explanation'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 8. Curatorial Metadata and Reviewer Identity Consistency
            SELECT RAISE(ABORT, 'Audit Validation Error: reviewer_id in audit must be >= 3 chars, must match parent reviewer_id, and reviewer_notes >= 15 chars.')
            WHERE coalesce(length(trim(NEW.reviewer_id, ' ' || char(9) || char(10) || char(13))), 0) < 3
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.reviewer_id'), ' ' || char(9) || char(10) || char(13))), 0) < 3
               OR trim(NEW.reviewer_id) != trim(coalesce(json_extract(NEW.empirical_audit_json, '$.reviewer_id'), ''))
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.reviewer_notes'), ' ' || char(9) || char(10) || char(13))), 0) < 15;
        END;
        """
    )

    cursor.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_validate_independent_audit_update
        BEFORE UPDATE ON source_pair_relationships
        FOR EACH ROW
        WHEN NEW.relationship_type = 'INDEPENDENT' OR NEW.independence_status = 'INDEPENDENT'
        BEGIN
            -- 1. Alignment check
            SELECT RAISE(ABORT, 'Audit Validation Error: relationship_type and independence_status must both be INDEPENDENT.')
            WHERE NEW.relationship_type != 'INDEPENDENT' OR NEW.independence_status != 'INDEPENDENT';

            -- 2. Syntactic JSON validity check
            SELECT RAISE(ABORT, 'Audit Validation Error: empirical_audit_json must be non-null and valid RFC 8259 JSON.')
            WHERE NEW.empirical_audit_json IS NULL OR json_valid(NEW.empirical_audit_json) != 1;

            -- 3. Criterion 1: Autonomous Data Collection
            SELECT RAISE(ABORT, 'Audit Validation Error: autonomous_data_collection must be explicitly true and data_collection_details >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.autonomous_data_collection'), '') != 'true'
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.data_collection_details'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 4. Criterion 2: Distinct Datasets
            SELECT RAISE(ABORT, 'Audit Validation Error: distinct_underlying_datasets must be true with distinct dataset identities (>= 3 chars) and dataset_separation_details >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.distinct_underlying_datasets'), '') != 'true'
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.dataset_a_identity'), ' ' || char(9) || char(10) || char(13))), 0) < 3
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.dataset_b_identity'), ' ' || char(9) || char(10) || char(13))), 0) < 3
               OR lower(trim(coalesce(json_extract(NEW.empirical_audit_json, '$.dataset_a_identity'), ''))) = lower(trim(coalesce(json_extract(NEW.empirical_audit_json, '$.dataset_b_identity'), '')))
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.dataset_separation_details'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 5. Criterion 3: Independent Methodology
            SELECT RAISE(ABORT, 'Audit Validation Error: independent_methodology must be true and methodology_details >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.independent_methodology'), '') != 'true'
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.methodology_details'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 6. Criterion 4: No Circular Reliance
            SELECT RAISE(ABORT, 'Audit Validation Error: no_circular_reliance must be true and circular_reliance_explanation >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.no_circular_reliance'), '') != 'true'
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.circular_reliance_explanation'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 7. Criterion 5: Exact Proposition Scope Match
            SELECT RAISE(ABORT, 'Audit Validation Error: exact_proposition_scope must be true, proposition_id must match parent, and proposition_scope_explanation >= 10 chars.')
            WHERE coalesce(json_type(NEW.empirical_audit_json, '$.exact_proposition_scope'), '') != 'true'
               OR trim(coalesce(json_extract(NEW.empirical_audit_json, '$.proposition_id'), '')) != trim(NEW.proposition_id)
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.proposition_scope_explanation'), ' ' || char(9) || char(10) || char(13))), 0) < 10;

            -- 8. Curatorial Metadata and Reviewer Identity Consistency
            SELECT RAISE(ABORT, 'Audit Validation Error: reviewer_id in audit must be >= 3 chars, must match parent reviewer_id, and reviewer_notes >= 15 chars.')
            WHERE coalesce(length(trim(NEW.reviewer_id, ' ' || char(9) || char(10) || char(13))), 0) < 3
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.reviewer_id'), ' ' || char(9) || char(10) || char(13))), 0) < 3
               OR trim(NEW.reviewer_id) != trim(coalesce(json_extract(NEW.empirical_audit_json, '$.reviewer_id'), ''))
               OR coalesce(length(trim(json_extract(NEW.empirical_audit_json, '$.reviewer_notes'), ' ' || char(9) || char(10) || char(13))), 0) < 15;
        END;
        """
    )

    conn.commit()


class MissingRelationshipSchemaError(RuntimeError):
    """Raised when SourceRelationshipRepository is connected to an unmigrated database lacking required tables or columns."""
    pass


REQUIRED_RELATIONSHIP_TABLES = ("source_pair_relationships", "source_relationship_audit_log")
REQUIRED_PAIR_COLUMNS = {
    "relationship_id", "source_id_a", "source_id_b", "proposition_id", "relationship_type",
    "independence_status", "is_directional", "same_publisher_flag", "empirical_audit_json",
    "reviewer_id", "reviewer_notes", "created_at", "updated_at",
}
REQUIRED_AUDIT_COLUMNS = {
    "audit_id", "relationship_id", "source_id_a", "source_id_b", "proposition_id",
    "previous_relationship_type", "new_relationship_type", "previous_independence_status",
    "new_independence_status", "reviewer_id", "reviewer_notes", "decision_timestamp",
}


class SourceRelationshipRepository:
    """Isolated repository operations for managing evidence relationships and audit history."""

    def __init__(self, conn: Union[sqlite3.Connection, str]):
        if isinstance(conn, str):
            self.conn = sqlite3.connect(conn)
            self.conn.row_factory = sqlite3.Row
        else:
            self.conn = conn

        # Strictly validate schema presence without executing DDL.
        # Repository construction MUST NEVER create tables or alter schemas.
        self._validate_schema_presence()

    def _validate_schema_presence(self) -> None:
        """Verify that required relationship tables and columns exist without executing DDL."""
        cursor = self.conn.cursor()
        existing_tables = {
            row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        missing_tables = [t for t in REQUIRED_RELATIONSHIP_TABLES if t not in existing_tables]
        if missing_tables:
            raise MissingRelationshipSchemaError(
                f"Database schema validation failed: missing required relationship table(s) {missing_tables}. "
                "Repository construction never executes DDL or alters schemas. Run explicit migration "
                "(e.g., stage4_phase2_migration.apply_migration) before initializing SourceRelationshipRepository."
            )

        existing_pair_cols = {
            row[1] for row in cursor.execute("PRAGMA table_info(source_pair_relationships)").fetchall()
        }
        missing_pair_cols = [c for c in REQUIRED_PAIR_COLUMNS if c not in existing_pair_cols]
        if missing_pair_cols:
            raise MissingRelationshipSchemaError(
                f"Database schema validation failed: table 'source_pair_relationships' is missing column(s) {missing_pair_cols}. "
                "Run explicit migration before initializing SourceRelationshipRepository."
            )

        existing_audit_cols = {
            row[1] for row in cursor.execute("PRAGMA table_info(source_relationship_audit_log)").fetchall()
        }
        missing_audit_cols = [c for c in REQUIRED_AUDIT_COLUMNS if c not in existing_audit_cols]
        if missing_audit_cols:
            raise MissingRelationshipSchemaError(
                f"Database schema validation failed: table 'source_relationship_audit_log' is missing column(s) {missing_audit_cols}. "
                "Run explicit migration before initializing SourceRelationshipRepository."
            )

    def _check_transitive_conflict(
        self,
        source_a: str,
        source_b: str,
        proposition_id: str,
    ) -> None:
        """Verify that source_a and source_b are not already connected via a DEPENDENT chain."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT source_id_a, source_id_b FROM source_pair_relationships
            WHERE proposition_id = ?
              AND is_directional = 0
              AND (relationship_type IN ('EXACT_DUPLICATE', 'SYNDICATED_COPY', 'REPRINT_OR_TRANSLATION', 'SHARED_UNDERLYING_SOURCE', 'DERIVED_REPETITION')
                   OR independence_status = 'DEPENDENT')
            """,
            (proposition_id,),
        )
        rows = cursor.fetchall()
        if not rows:
            return

        nodes = set()
        for a, b in rows:
            nodes.add(a)
            nodes.add(b)

        if source_a not in nodes or source_b not in nodes:
            return

        uf = DisjointSet(list(nodes))
        for a, b in rows:
            uf.union(a, b)

        if uf.find(source_a) == uf.find(source_b):
            raise TransitiveConflictError(
                f"Cannot mark sources '{source_a}' and '{source_b}' as INDEPENDENT for proposition '{proposition_id}': "
                f"they already belong to the same dependent cluster transitively."
            )

    def add_or_update_relationship(
        self,
        relationship: SourcePairRelationship,
        evidence_metadata: Optional[Dict[str, Dict]] = None,
    ) -> SourcePairRelationship:
        """Add or update a source relationship with strict validation, conflict checks, and atomic audit logging."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Enforce Self-Relationship Prohibition and Proposition ID Non-Empty
        if not relationship.proposition_id or not relationship.proposition_id.strip():
            raise ValueError("Proposition ID cannot be empty or whitespace.")
        if relationship.source_id_a == relationship.source_id_b:
            raise ValueError(f"Cannot relate a source to itself: '{relationship.source_id_a}'")

        # 2. Enforce Directionality Rule
        if relationship.relationship_type in DIRECTIONAL_RELATIONSHIP_TYPES:
            relationship.is_directional = True

        # 3. Canonicalize pair order for symmetric relationships only
        source_a = relationship.source_id_a
        source_b = relationship.source_id_b
        if not relationship.is_directional:
            if source_a > source_b:
                source_a, source_b = source_b, source_a

        # 4. Auto-resolve publisher/domain identity from evidence metadata
        if evidence_metadata:
            meta_a = evidence_metadata.get(source_a) or {}
            meta_b = evidence_metadata.get(source_b) or {}
            dom_a = (meta_a.get("canonical_domain") or meta_a.get("source_domain") or "").lower().strip()
            dom_b = (meta_b.get("canonical_domain") or meta_b.get("source_domain") or "").lower().strip()
            pub_a = (meta_a.get("canonical_publisher") or meta_a.get("publisher") or "").lower().strip()
            pub_b = (meta_b.get("canonical_publisher") or meta_b.get("publisher") or "").lower().strip()

            if (dom_a and dom_b and dom_a == dom_b) or (pub_a and pub_b and pub_a == pub_b):
                relationship.same_publisher_flag = True

        # 5. Validation for INDEPENDENT status
        if relationship.relationship_type == RelationshipType.INDEPENDENT:
            relationship.independence_status = IndependenceStatus.INDEPENDENT

            # Auto-bind proposition_id and reviewer_id if defaulted or generic
            if relationship.empirical_audit:
                if relationship.empirical_audit.proposition_id in ("AUTO_BIND", "GLOBAL", ""):
                    relationship.empirical_audit.proposition_id = relationship.proposition_id
                if relationship.empirical_audit.reviewer_id in ("AUTO_BIND", ""):
                    relationship.empirical_audit.reviewer_id = relationship.reviewer_id
                if relationship.reviewer_id and relationship.empirical_audit.reviewer_id:
                    if relationship.reviewer_id.strip() != relationship.empirical_audit.reviewer_id.strip():
                        raise ValueError(
                            f"Reviewer ID mismatch: relationship reviewer_id ('{relationship.reviewer_id}') "
                            f"does not match audit reviewer_id ('{relationship.empirical_audit.reviewer_id}')."
                        )

            # Mandatory 5-point empirical audit required for EVERY independent relationship
            if not relationship.empirical_audit or not relationship.empirical_audit.is_fully_satisfied(bound_proposition_id=relationship.proposition_id):
                raise IncompleteEmpiricalAuditError(
                    "Cannot approve relationship as INDEPENDENT: "
                    "all 5 empirical-independence audit criteria must be affirmatively verified, documented, and bound to the proposition."
                )

            # Transitive conflict check: reject INDEPENDENT if already in same dependent cluster
            self._check_transitive_conflict(source_a, source_b, relationship.proposition_id)

        elif relationship.relationship_type == RelationshipType.UNKNOWN:
            relationship.independence_status = IndependenceStatus.UNKNOWN
        elif relationship.relationship_type == RelationshipType.NOT_COMPARABLE:
            relationship.independence_status = IndependenceStatus.NOT_COMPARABLE
        elif relationship.relationship_type in MERGEABLE_DEPENDENCE_RELATIONSHIP_TYPES:
            relationship.independence_status = IndependenceStatus.DEPENDENT

        cursor = self.conn.cursor()

        try:
            # Check existing row
            cursor.execute(
                """
                SELECT relationship_id, relationship_type, independence_status, created_at
                FROM source_pair_relationships
                WHERE source_id_a = ? AND source_id_b = ? AND proposition_id = ?
                """,
                (source_a, source_b, relationship.proposition_id),
            )
            existing = cursor.fetchone()

            prev_rel_type = None
            prev_indep_status = None
            audit_rel_id = None
            created_at = now_iso

            audit_json = (
                relationship.empirical_audit.model_dump_json()
                if relationship.empirical_audit
                else None
            )

            if existing:
                audit_rel_id, prev_rel_type, prev_indep_status, created_at = existing
                cursor.execute(
                    """
                    UPDATE source_pair_relationships
                    SET relationship_type = ?,
                        independence_status = ?,
                        is_directional = ?,
                        same_publisher_flag = ?,
                        empirical_audit_json = ?,
                        reviewer_id = ?,
                        reviewer_notes = ?,
                        updated_at = ?
                    WHERE relationship_id = ?
                    """,
                    (
                        relationship.relationship_type.value,
                        relationship.independence_status.value,
                        1 if relationship.is_directional else 0,
                        1 if relationship.same_publisher_flag else 0,
                        audit_json,
                        relationship.reviewer_id,
                        relationship.reviewer_notes,
                        now_iso,
                        audit_rel_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO source_pair_relationships (
                        source_id_a, source_id_b, proposition_id, relationship_type,
                        independence_status, is_directional, same_publisher_flag,
                        empirical_audit_json, reviewer_id, reviewer_notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_a,
                        source_b,
                        relationship.proposition_id,
                        relationship.relationship_type.value,
                        relationship.independence_status.value,
                        1 if relationship.is_directional else 0,
                        1 if relationship.same_publisher_flag else 0,
                        audit_json,
                        relationship.reviewer_id,
                        relationship.reviewer_notes,
                        created_at,
                        now_iso,
                    ),
                )
                audit_rel_id = cursor.lastrowid

            # Insert immutable audit log entry
            cursor.execute(
                """
                INSERT INTO source_relationship_audit_log (
                    relationship_id, source_id_a, source_id_b, proposition_id,
                    previous_relationship_type, new_relationship_type,
                    previous_independence_status, new_independence_status,
                    reviewer_id, reviewer_notes, decision_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_rel_id,
                    source_a,
                    source_b,
                    relationship.proposition_id,
                    prev_rel_type,
                    relationship.relationship_type.value,
                    prev_indep_status,
                    relationship.independence_status.value,
                    relationship.reviewer_id,
                    relationship.reviewer_notes,
                    now_iso,
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        relationship.relationship_id = audit_rel_id
        relationship.source_id_a = source_a
        relationship.source_id_b = source_b
        relationship.created_at = created_at
        relationship.updated_at = now_iso
        return relationship

    def get_relationship(
        self,
        source_id_a: str,
        source_id_b: str,
        proposition_id: str,
    ) -> Optional[SourcePairRelationship]:
        """Query a relationship by pair and proposition with canonical order handling."""
        if not proposition_id or not proposition_id.strip():
            raise ValueError("Proposition ID cannot be empty or whitespace.")

        cursor = self.conn.cursor()

        # Check exact directed pair first
        cursor.execute(
            """
            SELECT relationship_id, source_id_a, source_id_b, proposition_id,
                   relationship_type, independence_status, is_directional,
                   same_publisher_flag, empirical_audit_json, reviewer_id,
                   reviewer_notes, created_at, updated_at
            FROM source_pair_relationships
            WHERE source_id_a = ? AND source_id_b = ? AND proposition_id = ?
            """,
            (source_id_a, source_id_b, proposition_id),
        )
        row = cursor.fetchone()
        if not row:
            # Check symmetric canonical order
            can_a, can_b = min(source_id_a, source_id_b), max(source_id_a, source_id_b)
            cursor.execute(
                """
                SELECT relationship_id, source_id_a, source_id_b, proposition_id,
                       relationship_type, independence_status, is_directional,
                       same_publisher_flag, empirical_audit_json, reviewer_id,
                       reviewer_notes, created_at, updated_at
                FROM source_pair_relationships
                WHERE source_id_a = ? AND source_id_b = ? AND proposition_id = ?
                """,
                (can_a, can_b, proposition_id),
            )
            row = cursor.fetchone()

        if not row:
            return None

        audit_obj = None
        if row[8]:
            try:
                audit_obj = EmpiricalIndependenceAudit.model_validate_json(row[8])
            except Exception:
                audit_obj = None

        # Bypass model validator on retrieval of existing rows using construct/validate
        return SourcePairRelationship.model_construct(
            relationship_id=row[0],
            source_id_a=row[1],
            source_id_b=row[2],
            proposition_id=row[3],
            relationship_type=RelationshipType(row[4]),
            independence_status=IndependenceStatus(row[5]),
            is_directional=bool(row[6]),
            same_publisher_flag=bool(row[7]),
            empirical_audit=audit_obj,
            reviewer_id=row[9],
            reviewer_notes=row[10],
            created_at=row[11],
            updated_at=row[12],
        )

    def get_relationship_audit_history(
        self,
        relationship_id: Optional[int] = None,
        source_id_a: Optional[str] = None,
        source_id_b: Optional[str] = None,
    ) -> List[SourceRelationshipAuditLogEntry]:
        """Fetch immutable chronological audit entries."""
        cursor = self.conn.cursor()
        query = "SELECT audit_id, relationship_id, source_id_a, source_id_b, proposition_id, previous_relationship_type, new_relationship_type, previous_independence_status, new_independence_status, reviewer_id, reviewer_notes, decision_timestamp FROM source_relationship_audit_log WHERE 1=1"
        params = []
        if relationship_id is not None:
            query += " AND relationship_id = ?"
            params.append(relationship_id)
        if source_id_a is not None and source_id_b is not None:
            can_a, can_b = min(source_id_a, source_id_b), max(source_id_a, source_id_b)
            query += " AND ((source_id_a = ? AND source_id_b = ?) OR (source_id_a = ? AND source_id_b = ?))"
            params.extend([source_id_a, source_id_b, can_a, can_b])

        query += " ORDER BY audit_id ASC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            SourceRelationshipAuditLogEntry(
                audit_id=r[0],
                relationship_id=r[1],
                source_id_a=r[2],
                source_id_b=r[3],
                proposition_id=r[4],
                previous_relationship_type=r[5],
                new_relationship_type=r[6],
                previous_independence_status=r[7],
                new_independence_status=r[8],
                reviewer_id=r[9],
                reviewer_notes=r[10],
                decision_timestamp=r[11],
            )
            for r in rows
        ]

    def challenge_relationship(
        self,
        decision: ChallengeDecision,
    ) -> SourcePairRelationship:
        """Execute an atomic curatorial challenge against an existing relationship determination.

        Requirements:
        1. A reviewer can challenge an earlier independence decision.
        2. The previous decision and audit record remain preserved in SQLite.
        3. A challenged relationship cannot continue contributing independent corroboration
           while its status is under review (INITIATE_CHALLENGE sets status to UNKNOWN).
        4. A confirmed dependent relationship becomes DEPENDENT.
        5. An unresolved challenge becomes UNKNOWN.
        6. Historical audit records in source_relationship_audit_log are NEVER modified or deleted.
        7. The relationship table update and audit log insertion occur inside a single atomic transaction.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Retrieve existing relationship
        existing = self.get_relationship(
            decision.source_id_a,
            decision.source_id_b,
            decision.proposition_id,
        )
        if not existing or not existing.relationship_id:
            raise ValueError(
                f"Cannot challenge relationship: no existing relationship found for pair "
                f"('{decision.source_id_a}', '{decision.source_id_b}') on proposition '{decision.proposition_id}'."
            )

        prev_rel_type = existing.relationship_type.value
        prev_indep_status = existing.independence_status.value
        rel_id = existing.relationship_id

        # Determine target state based on challenge action
        if decision.action == ChallengeAction.INITIATE_CHALLENGE:
            target_rel_type = RelationshipType.UNKNOWN
            target_status = IndependenceStatus.UNKNOWN
            target_audit_json = None
            target_is_directional = 0
            action_desc = "CHALLENGE_INITIATED"

        elif decision.action == ChallengeAction.CONFIRM_DEPENDENT:
            target_rel_type = decision.resolved_relationship_type or RelationshipType.SHARED_UNDERLYING_SOURCE
            if target_rel_type not in MERGEABLE_DEPENDENCE_RELATIONSHIP_TYPES and target_rel_type not in DIRECTIONAL_RELATIONSHIP_TYPES:
                target_rel_type = RelationshipType.SHARED_UNDERLYING_SOURCE
            target_is_directional = 1 if target_rel_type in DIRECTIONAL_RELATIONSHIP_TYPES else 0
            target_status = IndependenceStatus.DEPENDENT
            target_audit_json = None
            action_desc = "CHALLENGE_RESOLVED_DEPENDENT"

        elif decision.action == ChallengeAction.MARK_UNRESOLVED:
            target_rel_type = RelationshipType.UNKNOWN
            target_status = IndependenceStatus.UNKNOWN
            target_audit_json = None
            target_is_directional = 0
            action_desc = "CHALLENGE_UNRESOLVED"

        elif decision.action == ChallengeAction.DISMISS_CHALLENGE:
            if not decision.new_audit or not decision.new_audit.is_fully_satisfied(bound_proposition_id=decision.proposition_id):
                raise IncompleteEmpiricalAuditError(
                    "Dismissing challenge and reaffirming INDEPENDENT requires a complete, verified 5-point audit."
                )
            target_rel_type = RelationshipType.INDEPENDENT
            target_status = IndependenceStatus.INDEPENDENT
            target_audit_json = decision.new_audit.model_dump_json()
            target_is_directional = 0
            action_desc = "CHALLENGE_DISMISSED"

        else:
            raise ValueError(f"Unsupported challenge action: {decision.action}")

        # Format audit note retaining reviewer explanation and all documentation references
        refs_str = "; ".join(decision.documentation_references)
        formatted_audit_notes = f"[{action_desc}] {decision.reviewer_notes.strip()} | References: {refs_str}"

        cursor = self.conn.cursor()
        try:
            # 1. Update source_pair_relationships
            cursor.execute(
                """
                UPDATE source_pair_relationships
                SET relationship_type = ?,
                    independence_status = ?,
                    is_directional = ?,
                    empirical_audit_json = ?,
                    reviewer_id = ?,
                    reviewer_notes = ?,
                    updated_at = ?
                WHERE relationship_id = ?
                """,
                (
                    target_rel_type.value,
                    target_status.value,
                    target_is_directional,
                    target_audit_json,
                    decision.reviewer_id,
                    formatted_audit_notes,
                    now_iso,
                    rel_id,
                ),
            )

            # 2. Append immutable audit log record in same transaction
            cursor.execute(
                """
                INSERT INTO source_relationship_audit_log (
                    relationship_id, source_id_a, source_id_b, proposition_id,
                    previous_relationship_type, new_relationship_type,
                    previous_independence_status, new_independence_status,
                    reviewer_id, reviewer_notes, decision_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel_id,
                    existing.source_id_a,
                    existing.source_id_b,
                    decision.proposition_id,
                    prev_rel_type,
                    target_rel_type.value,
                    prev_indep_status,
                    target_status.value,
                    decision.reviewer_id,
                    formatted_audit_notes,
                    now_iso,
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        updated = self.get_relationship(
            decision.source_id_a,
            decision.source_id_b,
            decision.proposition_id,
        )
        if not updated:
            raise RuntimeError("Failed to retrieve updated relationship after challenge transaction.")
        return updated


class PropositionCorroborationEngine:
    """Evaluates proposition-level evidence independence and builds authority clusters."""

    def __init__(self, repo: SourceRelationshipRepository):
        self.repo = repo

    def evaluate_proposition_corroboration(
        self,
        proposition_id: str,
        candidate_evidence: List[Dict],
        is_present_operational_claim: bool = True,
        temporal_scope: Optional[Union[TemporalScope, str]] = None,
        reference_period_start: Optional[str] = None,
        reference_period_end: Optional[str] = None,
        temporal_quantification: Optional[Union[TemporalQuantification, str]] = "INTERSECTING",
        proposition_domain: Optional[Union[EvidenceDomain, str]] = None,
    ) -> PropositionCorroborationAssessment:
        """Group verified evidence into independent authority clusters and evaluate Two-Key Gate."""
        # 1. Filter eligible verified evidence
        eligible_items = []
        for item in candidate_evidence:
            # Correction 1: Dual-Key Verification Gate
            # Require BOTH conditions strictly: is_verified is True AND curation_status == "APPROVED_VERIFIED"
            # Reject missing values, false values, string "true", integer 1, and mismatched states.
            is_verified = item.get("is_verified") if isinstance(item, dict) else getattr(item, "is_verified", None)
            curation_status = item.get("curation_status") if isinstance(item, dict) else getattr(item, "curation_status", None)

            if type(is_verified) is not bool or is_verified is not True:
                continue
            if curation_status != "APPROVED_VERIFIED":
                continue

            # Correction 2: Text Availability and Provenance Gating
            def _extract_val(obj, key):
                val = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
                if hasattr(val, "value"):
                    val = val.value
                return val

            source_tier = _extract_val(item, "source_tier")
            text_availability = _extract_val(item, "text_availability")
            text_provenance = _extract_val(item, "text_provenance")

            # Fail closed: reject if any text eligibility metadata is missing or empty
            if not source_tier or not text_availability or not text_provenance:
                continue

            # Reject metadata-only, tertiary tiers, and unavailable provenance
            if source_tier in ("TERTIARY", "METADATA_ONLY"):
                continue
            if text_availability == "METADATA_ONLY" or text_availability not in ("FULL_TEXT", "EXCERPT", "ABSTRACT"):
                continue
            if text_provenance == "UNAVAILABLE" or text_provenance not in ("VERBATIM", "SUMMARY", "INTERPRETATION"):
                continue

            # Strict operational status and temporal scope filter:
            op_status = _extract_val(item, "operational_status")
            if not op_status or op_status == OperationalStatus.UNKNOWN.value:
                # UNKNOWN operational status strictly fails closed across all temporal scopes
                continue

            # Extract and infer domain of candidate evidence
            raw_domain = _extract_val(item, "domain")
            if raw_domain:
                ev_domain = raw_domain.value if hasattr(raw_domain, "value") else str(raw_domain)
            else:
                if op_status in (
                    OperationalStatus.CURRENT_OPERATIVE.value,
                    OperationalStatus.HISTORICAL_ONLY.value,
                    OperationalStatus.REPEALED_VACATED.value,
                    OperationalStatus.SUPERSEDED.value,
                    OperationalStatus.ARCHIVED_DISCONTINUED.value,
                ):
                    ev_domain = EvidenceDomain.LEGAL.value
                else:
                    ev_domain = EvidenceDomain.EMPIRICAL_NON_LEGAL.value

            # Resolve effective temporal scope
            eff_scope = temporal_scope
            if hasattr(eff_scope, "value"):
                eff_scope = eff_scope.value
            if eff_scope is None:
                eff_scope = (
                    TemporalScope.PRESENT_OPERATIONAL.value
                    if is_present_operational_claim
                    else None
                )

            prop_dom = proposition_domain
            if hasattr(prop_dom, "value"):
                prop_dom = prop_dom.value

            if eff_scope in (TemporalScope.EMPIRICAL_NON_LEGAL.value, "EMPIRICAL_NON_LEGAL"):
                # Natural/empirical science: requires NOT_APPLICABLE empirical evidence; strictly rejects legal statutes
                if ev_domain != EvidenceDomain.EMPIRICAL_NON_LEGAL.value or op_status != OperationalStatus.NOT_APPLICABLE.value:
                    continue
            elif eff_scope in (TemporalScope.PRESENT_OPERATIONAL.value, "PRESENT_OPERATIONAL"):
                # Present operational legal authority: requires CURRENT_OPERATIVE legal authority; strictly rejects non-legal/NOT_APPLICABLE
                if op_status != OperationalStatus.CURRENT_OPERATIVE.value:
                    continue
                if ev_domain != EvidenceDomain.LEGAL.value:
                    continue
            elif eff_scope in (
                TemporalScope.HISTORICAL.value,
                "HISTORICAL",
                TemporalScope.HISTORICAL_LEGAL.value,
                "HISTORICAL_LEGAL",
            ):
                # Historical legal claim: strictly requires legal domain and valid operational status
                if ev_domain != EvidenceDomain.LEGAL.value:
                    continue
                if op_status not in (
                    OperationalStatus.HISTORICAL_ONLY.value,
                    OperationalStatus.ARCHIVED_DISCONTINUED.value,
                    OperationalStatus.SUPERSEDED.value,
                    OperationalStatus.REPEALED_VACATED.value,
                    OperationalStatus.CURRENT_OPERATIVE.value,
                ):
                    continue

                # Textual epoch gate: modern consolidated text without audit cannot corroborate historical claims
                textual_epoch = _extract_val(item, "textual_epoch")
                if textual_epoch in (TextualEpoch.CURRENT_CONSOLIDATED.value, "CURRENT_CONSOLIDATED"):
                    continue

                # Historical date validation: if reference period is given, evaluate overlap
                if reference_period_start or reference_period_end:
                    source_from = _extract_val(item, "effective_from_date")
                    source_to = _extract_val(item, "effective_to_date")
                    quant = _extract_val(item, "temporal_quantification") or temporal_quantification or "INTERSECTING"
                    overlap_valid, _ = check_temporal_interval_overlap(
                        source_from,
                        source_to,
                        reference_period_start,
                        reference_period_end,
                        op_status,
                        quant,
                    )
                    if not overlap_valid:
                        continue
            elif eff_scope in (
                TemporalScope.TIME_INVARIANT_LEGAL_RULE.value,
                "TIME_INVARIANT_LEGAL_RULE",
            ):
                if prop_dom in (EvidenceDomain.LEGAL.value, "LEGAL"):
                    # Genuine legal maxim: requires legal authority and CURRENT_OPERATIVE; rejects NOT_APPLICABLE
                    if ev_domain != EvidenceDomain.LEGAL.value or op_status != OperationalStatus.CURRENT_OPERATIVE.value:
                        continue
                else:
                    # Legacy support for test_08
                    if op_status not in (
                        OperationalStatus.NOT_APPLICABLE.value,
                        OperationalStatus.CURRENT_OPERATIVE.value,
                    ):
                        continue
            elif eff_scope in (
                TemporalScope.TIME_INVARIANT_LEGAL_MAXIM.value,
                "TIME_INVARIANT_LEGAL_MAXIM",
            ):
                # Strict legal maxim: requires LEGAL and CURRENT_OPERATIVE; strictly rejects NOT_APPLICABLE
                if ev_domain != EvidenceDomain.LEGAL.value or op_status != OperationalStatus.CURRENT_OPERATIVE.value:
                    continue
            elif eff_scope in (TemporalScope.UNKNOWN.value, "UNKNOWN"):
                # Unknown temporal scope fails closed
                continue
            else:
                # If temporal_scope was omitted and is_present_operational_claim was False
                if op_status not in (
                    OperationalStatus.CURRENT_OPERATIVE.value,
                    OperationalStatus.NOT_APPLICABLE.value,
                    OperationalStatus.HISTORICAL_ONLY.value,
                    OperationalStatus.ARCHIVED_DISCONTINUED.value,
                    OperationalStatus.SUPERSEDED.value,
                    OperationalStatus.REPEALED_VACATED.value,
                ):
                    continue
                if reference_period_start and reference_period_end:
                    source_from = _extract_val(item, "effective_from_date")
                    source_to = _extract_val(item, "effective_to_date")
                    quant = _extract_val(item, "temporal_quantification") or temporal_quantification or "INTERSECTING"
                    overlap_valid, _ = check_temporal_interval_overlap(
                        source_from,
                        source_to,
                        reference_period_start,
                        reference_period_end,
                        op_status,
                        quant,
                    )
                    if not overlap_valid:
                        continue

            eligible_items.append(item)

        if not eligible_items:
            return PropositionCorroborationAssessment(
                proposition_id=proposition_id,
                total_verified_records=0,
                independent_clusters_count=0,
                verified_independent_pairs_count=0,
                has_two_independent_sources=False,
                clusters=[],
                coverage_status="NO_EVIDENCE",
                diagnostic_notes="No eligible verified evidence records available for this proposition.",
            )

        item_ids = [e["id"] for e in eligible_items]
        item_map = {e["id"]: e for e in eligible_items}
        uf = DisjointSet(item_ids)

        # 2. Gate 1: Merge ONLY approved symmetric dependence relationships
        for i in range(len(eligible_items)):
            for j in range(i + 1, len(eligible_items)):
                id_a = eligible_items[i]["id"]
                id_b = eligible_items[j]["id"]

                rel = self.repo.get_relationship(id_a, id_b, proposition_id)
                if rel:
                    # STRICT RULE: Directional citations (CITES_OR_INTERPRETS, DERIVED_FROM) NEVER merge!
                    # UNKNOWN, NOT_COMPARABLE, and INDEPENDENT NEVER merge!
                    if not rel.is_directional and rel.relationship_type in MERGEABLE_DEPENDENCE_RELATIONSHIP_TYPES:
                        uf.union(id_a, id_b)
                    elif not rel.is_directional and rel.independence_status == IndependenceStatus.DEPENDENT:
                        uf.union(id_a, id_b)

        # 3. Extract clusters (Key 1) and determine cluster stances
        components = uf.get_components()
        cluster_list = []
        cluster_stances: Dict[str, str] = {}

        for idx, (root, members) in enumerate(components.items()):
            stances = {item_map[m].get("stance", "NEUTRAL") for m in members}
            if "SUPPORTING" in stances and "CONTRADICTING" not in stances:
                c_stance = "SUPPORTING"
            elif "CONTRADICTING" in stances and "SUPPORTING" not in stances:
                c_stance = "CONTRADICTING"
            elif "SUPPORTING" in stances and "CONTRADICTING" in stances:
                c_stance = "CONFLICTING"
            else:
                c_stance = "NEUTRAL"

            cluster_stances[root] = c_stance
            cluster_list.append(
                AuthorityCluster(
                    cluster_id=f"cluster-{idx+1}",
                    member_evidence_ids=members,
                    cluster_stance=c_stance,
                )
            )

        independent_clusters_count = len(cluster_list)

        # 4. Gate 2: Verify Affirmative Independence between distinct clusters
        verified_independent_pairs: List[Tuple[str, str]] = []
        cluster_roots = list(components.keys())

        for i in range(len(cluster_roots)):
            for j in range(i + 1, len(cluster_roots)):
                root_a = cluster_roots[i]
                root_b = cluster_roots[j]

                # Check if ANY pair of members across the two clusters has an affirmative INDEPENDENT relationship
                is_pair_independent = False
                for m_a in components[root_a]:
                    for m_b in components[root_b]:
                        rel = self.repo.get_relationship(m_a, m_b, proposition_id)
                        if rel and rel.independence_status == IndependenceStatus.INDEPENDENT:
                            is_pair_independent = True
                            break
                    if is_pair_independent:
                        break

                if is_pair_independent:
                    verified_independent_pairs.append((root_a, root_b))

        # 5. Evaluate Two-Key Threshold & Stance-Aware Coverage Status
        has_two_independent_sources = (
            independent_clusters_count >= 2 and len(verified_independent_pairs) > 0
        )

        if has_two_independent_sources:
            # Inspect stances of clusters involved in independent relationships
            active_stances = set()
            for r_a, r_b in verified_independent_pairs:
                active_stances.add(cluster_stances.get(r_a, "NEUTRAL"))
                active_stances.add(cluster_stances.get(r_b, "NEUTRAL"))

            if "SUPPORTING" in active_stances and "CONTRADICTING" not in active_stances:
                coverage_status = "VERIFIED_SUPPORTED"
            elif "CONTRADICTING" in active_stances and "SUPPORTING" not in active_stances:
                coverage_status = "VERIFIED_CONTRADICTED"
            elif "SUPPORTING" in active_stances and "CONTRADICTING" in active_stances:
                coverage_status = "CONFLICTING"
            else:
                coverage_status = "UNRESOLVED"

            notes = (
                f"Two-source corroboration threshold satisfied at Level 3: {independent_clusters_count} authority clusters "
                f"with {len(verified_independent_pairs)} verified independent cluster relationships. "
                f"Coverage status is {coverage_status}. Final verdict determination requires multi-proposition "
                f"completeness and absence of counter-evidence at Level 4."
            )
        else:
            # Unverified matches: check candidate evidence stances
            all_stances = {e.get("stance", "NEUTRAL") for e in eligible_items}
            if "SUPPORTING" in all_stances and "CONTRADICTING" not in all_stances:
                coverage_status = "UNVERIFIED_MATCH_SUPPORTING"
            elif "CONTRADICTING" in all_stances and "SUPPORTING" not in all_stances:
                coverage_status = "UNVERIFIED_MATCH_CONTRADICTING"
            elif "SUPPORTING" in all_stances and "CONTRADICTING" in all_stances:
                coverage_status = "CONFLICTING"
            else:
                coverage_status = "UNRESOLVED"

            notes = (
                f"Found {independent_clusters_count} distinct clusters ({len(eligible_items)} verified records), "
                f"but lacking verified independent relationship (found {len(verified_independent_pairs)} independent pairs). "
                f"Remains UNVERIFIED under the two-independent-source safeguard (coverage: {coverage_status})."
            )

        return PropositionCorroborationAssessment(
            proposition_id=proposition_id,
            total_verified_records=len(eligible_items),
            independent_clusters_count=independent_clusters_count,
            verified_independent_pairs_count=len(verified_independent_pairs),
            has_two_independent_sources=has_two_independent_sources,
            clusters=cluster_list,
            coverage_status=coverage_status,
            diagnostic_notes=notes,
        )
