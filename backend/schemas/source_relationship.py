"""Source relationship and proposition-level independence data models for VERITAS.

This module defines Pydantic schemas, enums, and audit structures for
proposition-specific source relationships, directional provenance,
empirical independence verification, and authority clustering.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator, model_validator


class RelationshipType(str, Enum):
    """Categorization of pairwise relationships between evidence sources."""

    # Symmetric dependence relationships (eligible for Union-Find merging)
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    SYNDICATED_COPY = "SYNDICATED_COPY"
    REPRINT_OR_TRANSLATION = "REPRINT_OR_TRANSLATION"
    SHARED_UNDERLYING_SOURCE = "SHARED_UNDERLYING_SOURCE"
    DERIVED_REPETITION = "DERIVED_REPETITION"

    # Directional provenance relationships (never automatically merged)
    CITES_OR_INTERPRETS = "CITES_OR_INTERPRETS"
    DERIVED_FROM = "DERIVED_FROM"

    # Other pairwise classifications
    INDEPENDENT = "INDEPENDENT"
    UNKNOWN = "UNKNOWN"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class IndependenceStatus(str, Enum):
    """Epistemological independence determination between two sources."""

    INDEPENDENT = "INDEPENDENT"
    DEPENDENT = "DEPENDENT"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    UNKNOWN = "UNKNOWN"


class OperationalStatus(str, Enum):
    """Current administrative and legal operational vitality of an authority."""

    CURRENT_OPERATIVE = "CURRENT_OPERATIVE"
    ARCHIVED_DISCONTINUED = "ARCHIVED_DISCONTINUED"
    REPEALED_VACATED = "REPEALED_VACATED"
    SUPERSEDED = "SUPERSEDED"
    HISTORICAL_ONLY = "HISTORICAL_ONLY"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceDomain(str, Enum):
    """Epistemological domain of an evidence item."""

    LEGAL = "LEGAL"
    EMPIRICAL_NON_LEGAL = "EMPIRICAL_NON_LEGAL"
    EMPIRICAL_POLICY_CONTEXT = "EMPIRICAL_POLICY_CONTEXT"


class TemporalScope(str, Enum):
    """Temporal frame of reference for claim evaluation."""

    PRESENT_OPERATIONAL = "PRESENT_OPERATIONAL"
    HISTORICAL = "HISTORICAL"
    HISTORICAL_LEGAL = "HISTORICAL_LEGAL"
    TIME_INVARIANT_LEGAL_RULE = "TIME_INVARIANT_LEGAL_RULE"
    TIME_INVARIANT_LEGAL_MAXIM = "TIME_INVARIANT_LEGAL_MAXIM"
    EMPIRICAL_NON_LEGAL = "EMPIRICAL_NON_LEGAL"
    UNKNOWN = "UNKNOWN"


class TemporalQuantification(str, Enum):
    """Temporal quantification modality for proposition verification."""

    INTERSECTING = "INTERSECTING"
    CONTINUOUS_FULL_PERIOD = "CONTINUOUS_FULL_PERIOD"
    POINT_IN_TIME = "POINT_IN_TIME"


class LegalDateType(str, Enum):
    """Specific legal lifecycle date classifications."""

    ENACTMENT = "ENACTMENT"
    EFFECTIVE = "EFFECTIVE"
    PROMULGATION = "PROMULGATION"
    SUNSET = "SUNSET"
    REPEAL = "REPEAL"
    JUDICIAL_INVALIDATION = "JUDICIAL_INVALIDATION"
    INJUNCTION_STAY = "INJUNCTION_STAY"


class TextualEpoch(str, Enum):
    """Chronological authenticity of legal text."""

    HISTORICAL_CONTEMPORARY = "HISTORICAL_CONTEMPORARY"
    CODIFIED_RETROSPECTIVE = "CODIFIED_RETROSPECTIVE"
    CURRENT_CONSOLIDATED = "CURRENT_CONSOLIDATED"


class HistoricalProvenanceAudit(BaseModel):
    """Archival provenance record certifying authenticity of historical legal text."""

    session_law_citation: Optional[str] = Field(
        default=None,
        description="Official primary session law citation (e.g. '52 Stat. 1060').",
    )
    statutory_volume: Optional[str] = Field(
        default=None,
        description="Volume number in official gazette or Statutes at Large.",
    )
    page_number: Optional[str] = Field(
        default=None,
        description="Page number in official publication.",
    )
    textual_epoch: TextualEpoch = Field(
        default=TextualEpoch.HISTORICAL_CONTEMPORARY,
        description="Chronological authenticity of the excerpted text.",
    )
    unamended_through_period_certified: bool = Field(
        default=False,
        description="Certifies that revision history notes confirm no interim amendments altered the excerpted rule.",
    )
    archival_repository_url: Optional[str] = Field(
        default=None,
        description="URL to scanned original gazette/statute.",
    )

    @model_validator(mode="after")
    def validate_historical_authenticity(self) -> "HistoricalProvenanceAudit":
        if self.textual_epoch == TextualEpoch.CURRENT_CONSOLIDATED:
            raise ValueError(
                "CURRENT_CONSOLIDATED modern text cannot be certified for historical legal corroboration."
            )
        if not self.session_law_citation and not self.archival_repository_url:
            raise ValueError(
                "Historical legal authority requires an official session law citation or primary archival URL."
            )
        return self


class LegalTemporalMetadata(BaseModel):
    """Granular legal lifecycle dates supporting rigorous temporal corroboration."""

    enactment_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
        description="Date legislation was signed or passed.",
    )
    effective_from_date: str = Field(
        ...,
        pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
        description="Binding legal effective start date (Mandatory lower bound S_from).",
    )
    promulgation_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
        description="Date published in official gazette/Federal Register.",
    )
    effective_to_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
        description="Binding legal expiration, repeal, or supersession date (Upper bound S_to).",
    )
    sunset_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
        description="Built-in statutory expiration date, if any.",
    )
    judicial_invalidation_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$",
        description="Date declared unconstitutional or void ab initio by binding court.",
    )
    is_void_ab_initio: bool = Field(
        default=False,
        description="True if judicial invalidation completely nullified authority retroactively.",
    )
    injunction_windows: List[Tuple[str, str]] = Field(
        default_factory=list,
        description="List of [stay_start, stay_end] intervals where enforcement was stayed.",
    )


class LegalVitalityAudit(BaseModel):
    """Structured legal vitality audit required to assign CURRENT_OPERATIVE."""

    legal_provision: str = Field(..., min_length=3, description="Exact statutory or regulatory provision (e.g. '29 U.S.C. § 215(a)(3)').")
    jurisdiction: str = Field(..., min_length=2, description="Legal jurisdiction (e.g. 'US_FEDERAL', 'US_NY').")
    authoritative_source_url: str = Field(..., min_length=10, description="Official government source URL inspected.")
    effective_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="ISO 8601 effective date.")
    effective_from_date: Optional[str] = Field(default=None, pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$", description="Standardized effective from date.")
    effective_to_date: Optional[str] = Field(default=None, pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$", description="Standardized effective to date.")
    domain: EvidenceDomain = Field(default=EvidenceDomain.LEGAL, description="Epistemological domain.")
    repeal_checked: bool = Field(..., description="Confirmed not repealed or vacated.")
    amendment_checked: bool = Field(..., description="Confirmed not amended out of vitality.")
    supersession_checked: bool = Field(..., description="Confirmed not superseded by subsequent authority.")
    discontinuation_checked: bool = Field(..., description="Confirmed policy has not been discontinued.")
    reviewer_notes: str = Field(..., min_length=15, description="Substantive legal analysis and cross-references.")

    @model_validator(mode="after")
    def validate_vitality_checklist(self) -> "LegalVitalityAudit":
        if not (self.repeal_checked and self.amendment_checked and
                self.supersession_checked and self.discontinuation_checked):
            raise ValueError("All four vitality checks must be explicitly confirmed True.")
        return self


class ChallengeAction(str, Enum):
    """Actions available during a human curatorial challenge of an independence decision."""

    INITIATE_CHALLENGE = "INITIATE_CHALLENGE"  # Immediately demotes relationship to UNKNOWN; corroboration suspended
    CONFIRM_DEPENDENT = "CONFIRM_DEPENDENT"    # Confirms relationship is DEPENDENT (shared underlying, citation, etc.)
    DISMISS_CHALLENGE = "DISMISS_CHALLENGE"    # Reaffirms INDEPENDENT with complete verified audit
    MARK_UNRESOLVED = "MARK_UNRESOLVED"        # Challenge cannot be resolved; permanently remains UNKNOWN


class ChallengeDecision(BaseModel):
    """Structured human review decision challenging or resolving an earlier relationship determination."""

    source_id_a: str = Field(..., description="First evidence ID.")
    source_id_b: str = Field(..., description="Second evidence ID.")
    proposition_id: str = Field(..., description="Proposition tracking identifier.")
    action: ChallengeAction = Field(..., description="Specific challenge action being executed.")
    reviewer_id: str = Field(..., description="Accountable human reviewer submitting this challenge.")
    reviewer_notes: str = Field(..., description="Substantive reasoning explaining the evidentiary basis of the challenge.")
    documentation_references: List[str] = Field(
        default_factory=list,
        description="List of supporting documentation references, citations, or investigation links."
    )
    resolved_relationship_type: Optional[RelationshipType] = Field(
        default=None,
        description="Target relationship type if confirming dependency or dismissing challenge."
    )
    new_audit: Optional["EmpiricalIndependenceAudit"] = Field(
        default=None,
        description="Mandatory 5-point empirical audit required if action is DISMISS_CHALLENGE."
    )
    decision_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("reviewer_id")
    @classmethod
    def validate_reviewer_id(cls, v: str) -> str:
        trimmed = (v or "").strip()
        if len(trimmed) < 3:
            raise ValueError("Reviewer ID must contain at least 3 characters.")
        return trimmed

    @field_validator("reviewer_notes")
    @classmethod
    def validate_reviewer_notes(cls, v: str) -> str:
        trimmed = (v or "").strip()
        if len(trimmed) < 15:
            raise ValueError("Reviewer notes must contain at least 15 characters explaining the challenge basis.")
        return trimmed

    @field_validator("documentation_references")
    @classmethod
    def validate_doc_refs(cls, v: List[str]) -> List[str]:
        if not v or len(v) == 0:
            raise ValueError("Challenge requires at least one supporting documentation reference.")
        cleaned = [ref.strip() for ref in v if ref and len(ref.strip()) >= 5]
        if not cleaned:
            raise ValueError("Documentation references must be non-empty and descriptive (>= 5 chars).")
        return cleaned


# Set of relationship types that are inherently directional (A cites/derives from B)
DIRECTIONAL_RELATIONSHIP_TYPES = {
    RelationshipType.CITES_OR_INTERPRETS,
    RelationshipType.DERIVED_FROM,
}

# Approved symmetric dependence relationships eligible to merge Union-Find clusters
MERGEABLE_DEPENDENCE_RELATIONSHIP_TYPES = {
    RelationshipType.EXACT_DUPLICATE,
    RelationshipType.SYNDICATED_COPY,
    RelationshipType.REPRINT_OR_TRANSLATION,
    RelationshipType.SHARED_UNDERLYING_SOURCE,
    RelationshipType.DERIVED_REPETITION,
}


class IncompleteEmpiricalAuditError(ValueError):
    """Raised when an empirical independence exception lacks required audit documentation."""
    pass


class TransitiveConflictError(ValueError):
    """Raised when an INDEPENDENT relationship conflicts with an existing DEPENDENT chain."""
    pass


class EmpiricalIndependenceAudit(BaseModel):
    """Mandatory 5-point audit required before granting an empirical independence exception.

    Enforces explicit boolean confirmations and dedicated substantive justifications
    across all five empirical independence dimensions:
    1. Autonomous data collection
    2. Distinct underlying dataset identity
    3. Independent methodology
    4. No circular reliance
    5. Exact proposition scope
    """

    # 1. Autonomous Data Collection
    autonomous_data_collection: bool = Field(
        default=False,
        description="Affirmative confirmation that primary raw data was gathered by autonomous investigative teams.",
    )
    data_collection_details: str = Field(
        ...,
        description="Specific operational identities, fieldwork locations, and mandates of autonomous collection teams.",
    )

    # 2. Distinct Underlying Dataset Identity
    distinct_underlying_datasets: bool = Field(
        default=False,
        description="Affirmative confirmation that raw datasets, survey series, or case dockets are completely distinct and non-overlapping.",
    )
    dataset_a_identity: str = Field(
        ...,
        description="Specific survey series, docket number, database identifier, or observational corpus for Source A.",
    )
    dataset_b_identity: str = Field(
        ...,
        description="Specific survey series, docket number, database identifier, or observational corpus for Source B.",
    )
    dataset_separation_details: str = Field(
        ...,
        description="Documented rationale establishing why the two identified datasets do not overlap or share origin.",
    )

    # 3. Independent Methodology
    independent_methodology: bool = Field(
        default=False,
        description="Affirmative confirmation that research, sampling, or investigative methodologies were established autonomously.",
    )
    methodology_details: str = Field(
        ...,
        description="Detailed description of autonomous sampling, adjudication, measurement, or investigative protocols.",
    )

    # 4. No Circular Reliance
    no_circular_reliance: bool = Field(
        default=False,
        description="Affirmative confirmation that neither source derives substantive factual proof from the other.",
    )
    circular_reliance_explanation: str = Field(
        ...,
        description="Dedicated explanation establishing that neither source cites, repeats, or assumes findings of the other.",
    )

    # 5. Exact Proposition Scope
    exact_proposition_scope: bool = Field(
        default=False,
        description="Affirmative confirmation that both sources independently substantiate the exact same proposition assertion.",
    )
    proposition_id: str = Field(
        ...,
        description="Explicit proposition tracking identifier bound to this audit.",
    )
    proposition_scope_explanation: str = Field(
        ...,
        description="Explanation demonstrating how both independent records substantively address the identical proposition assertion.",
    )

    # Curatorial Metadata
    reviewer_id: str = Field(..., description="Unique identifier of human reviewer who performed the 5-point audit.")
    reviewer_notes: str = Field(..., description="Overall curatorial justification synthesizing the independence determination.")
    audit_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of audit completion.",
    )

    def is_fully_satisfied(self, bound_proposition_id: Optional[str] = None) -> bool:
        """Verify that all five criteria are affirmatively confirmed with substantive documentation."""
        # Criterion 1: Autonomous Data Collection
        if not self.autonomous_data_collection:
            return False
        if not self.data_collection_details or len(self.data_collection_details.strip()) < 10:
            return False

        # Criterion 2: Distinct Underlying Dataset Identity
        if not self.distinct_underlying_datasets:
            return False
        if not self.dataset_a_identity or len(self.dataset_a_identity.strip()) < 3:
            return False
        if not self.dataset_b_identity or len(self.dataset_b_identity.strip()) < 3:
            return False
        if self.dataset_a_identity.strip().lower() == self.dataset_b_identity.strip().lower():
            return False  # Datasets cannot share identical identifier
        if not self.dataset_separation_details or len(self.dataset_separation_details.strip()) < 10:
            return False

        # Criterion 3: Independent Methodology
        if not self.independent_methodology:
            return False
        if not self.methodology_details or len(self.methodology_details.strip()) < 10:
            return False

        # Criterion 4: No Circular Reliance
        if not self.no_circular_reliance:
            return False
        if not self.circular_reliance_explanation or len(self.circular_reliance_explanation.strip()) < 10:
            return False

        # Criterion 5: Exact Proposition Scope
        if not self.exact_proposition_scope:
            return False
        if not self.proposition_id or not self.proposition_id.strip():
            return False
        if bound_proposition_id and self.proposition_id.strip() != bound_proposition_id.strip():
            return False
        if not self.proposition_scope_explanation or len(self.proposition_scope_explanation.strip()) < 10:
            return False

        # Curatorial Metadata Checks
        if not self.reviewer_id or len(self.reviewer_id.strip()) < 3:
            return False
        if not self.reviewer_notes or len(self.reviewer_notes.strip()) < 15:
            return False

        return True


class SourcePairRelationship(BaseModel):
    """Proposition-specific relational link between two evidence records."""

    relationship_id: Optional[int] = Field(default=None, description="Primary key in SQLite table.")
    source_id_a: str = Field(..., description="First evidence ID (subject in directional relationships).")
    source_id_b: str = Field(..., description="Second evidence ID (target in directional relationships).")
    proposition_id: str = Field(..., description="Target proposition tracking identifier (mandatory, non-empty).")
    relationship_type: RelationshipType = Field(default=RelationshipType.UNKNOWN)
    independence_status: IndependenceStatus = Field(default=IndependenceStatus.UNKNOWN)
    is_directional: bool = Field(default=False, description="True for directed provenance edges (CITES, DERIVED).")
    same_publisher_flag: bool = Field(default=False, description="Flag indicating shared canonical domain or publisher.")
    empirical_audit: Optional[EmpiricalIndependenceAudit] = Field(
        default=None,
        description="Documented 5-point audit required for empirical independence."
    )
    reviewer_id: str = Field(..., description="Reviewer who established or verified this relationship.")
    reviewer_notes: str = Field(..., description="Curatorial rationale explaining relationship determination.")
    created_at: Optional[str] = Field(default=None, description="ISO 8601 creation timestamp.")
    updated_at: Optional[str] = Field(default=None, description="ISO 8601 update timestamp.")

    @field_validator("proposition_id")
    @classmethod
    def validate_proposition_id(cls, v: str) -> str:
        trimmed = (v or "").strip()
        if not trimmed:
            raise ValueError("Proposition ID cannot be empty or whitespace.")
        return trimmed

    @field_validator("reviewer_notes")
    @classmethod
    def validate_reviewer_notes(cls, v: str) -> str:
        trimmed = (v or "").strip()
        if len(trimmed) < 10:
            raise ValueError("Reviewer notes must contain at least 10 characters explaining the basis.")
        return trimmed

    @model_validator(mode="after")
    def validate_directionality_and_ordering(self) -> "SourcePairRelationship":
        """Enforce that directionality matches relationship_type and enforce canonical ordering for symmetric pairs."""
        if self.relationship_type in DIRECTIONAL_RELATIONSHIP_TYPES:
            self.is_directional = True
        else:
            self.is_directional = False
            if self.source_id_a > self.source_id_b:
                self.source_id_a, self.source_id_b = self.source_id_b, self.source_id_a
        return self

    @model_validator(mode="after")
    def validate_different_sources(self) -> "SourcePairRelationship":
        """Strictly prohibit self-relationships."""
        if self.source_id_a == self.source_id_b:
            raise ValueError(
                f"Cannot relate a source to itself: source_id_a ('{self.source_id_a}') == source_id_b ('{self.source_id_b}')."
            )
        return self

    @model_validator(mode="after")
    def validate_independent_audit_requirement(self) -> "SourcePairRelationship":
        """Require complete 5-point empirical audit bound to proposition for EVERY independent relationship."""
        if self.relationship_type == RelationshipType.INDEPENDENT or self.independence_status == IndependenceStatus.INDEPENDENT:
            if self.relationship_type != RelationshipType.INDEPENDENT or self.independence_status != IndependenceStatus.INDEPENDENT:
                raise ValueError(
                    f"Inconsistent independence state: relationship_type '{self.relationship_type.value}' "
                    f"and independence_status '{self.independence_status.value}' must both be INDEPENDENT."
                )
            if not self.empirical_audit:
                raise IncompleteEmpiricalAuditError(
                    "Every INDEPENDENT relationship requires all five empirical-independence "
                    "audit criteria to be affirmatively verified and documented."
                )
            if self.empirical_audit.proposition_id in ("AUTO_BIND", ""):
                self.empirical_audit.proposition_id = self.proposition_id
            if self.empirical_audit.reviewer_id in ("AUTO_BIND", ""):
                self.empirical_audit.reviewer_id = self.reviewer_id
            if self.reviewer_id and self.empirical_audit.reviewer_id:
                if self.reviewer_id.strip() != self.empirical_audit.reviewer_id.strip():
                    raise ValueError(
                        f"Reviewer ID mismatch: parent reviewer_id '{self.reviewer_id}' "
                        f"does not match audit reviewer_id '{self.empirical_audit.reviewer_id}'."
                    )

            if not self.empirical_audit.is_fully_satisfied(bound_proposition_id=self.proposition_id):
                raise IncompleteEmpiricalAuditError(
                    f"Empirical independence audit is incomplete, sub-threshold, or mismatched with "
                    f"proposition '{self.proposition_id}'."
                )
        return self


class SourceRelationshipAuditLogEntry(BaseModel):
    """Immutable audit log record for tracking relationship creation and modifications."""

    audit_id: Optional[int] = Field(default=None)
    relationship_id: int = Field(..., description="ID of the modified relationship.")
    source_id_a: str = Field(...)
    source_id_b: str = Field(...)
    proposition_id: str = Field(...)
    previous_relationship_type: Optional[str] = Field(default=None)
    new_relationship_type: str = Field(...)
    previous_independence_status: Optional[str] = Field(default=None)
    new_independence_status: str = Field(...)
    reviewer_id: str = Field(...)
    reviewer_notes: str = Field(...)
    decision_timestamp: str = Field(..., description="ISO 8601 timestamp of curatorial action.")


class AuthorityCluster(BaseModel):
    """Group of mutually dependent evidence records representing one institutional voice."""

    cluster_id: str = Field(..., description="Cluster identifier (e.g. 'cluster-1').")
    member_evidence_ids: List[str] = Field(
        default_factory=list,
        description="Evidence IDs grouped together into this cluster."
    )
    cluster_stance: str = Field(
        default="NEUTRAL",
        description="Directional stance of the cluster: SUPPORTING, CONTRADICTING, CONFLICTING, or NEUTRAL."
    )


class PropositionCorroborationAssessment(BaseModel):
    """Assessment of evidence coverage and independent corroboration for a proposition."""

    proposition_id: str = Field(...)
    total_verified_records: int = Field(default=0)
    independent_clusters_count: int = Field(default=0)
    verified_independent_pairs_count: int = Field(default=0)
    has_two_independent_sources: bool = Field(
        default=False,
        description="True if proposition has >= 2 distinct clusters with verified independent relationship."
    )
    clusters: List[AuthorityCluster] = Field(default_factory=list)
    coverage_status: str = Field(
        default="NO_EVIDENCE",
        description="VERIFIED_SUPPORTED, VERIFIED_CONTRADICTED, CONFLICTING, UNVERIFIED_MATCH_SUPPORTING, etc."
    )
    diagnostic_notes: str = Field(...)
