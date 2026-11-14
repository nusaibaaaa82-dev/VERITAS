"""Claim schemas and verification data models for VERITAS.

This module defines Pydantic request and response models used throughout
the verification pipeline, ensuring strict type safety, input validation,
and auditable documentation.
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from backend.config import settings

# Canonical Curation Types
CurationStatus = Literal[
    "UNREVIEWED",
    "UNDER_REVIEW",
    "APPROVED_VERIFIED",
    "REJECTED_IRRELEVANT",
    "REJECTED_UNRELIABLE",
    "SUPERSEDED",
]

ReviewerConfirmedStance = Literal["SUPPORTING", "CONTRADICTING", "NEUTRAL"]
TextProvenance = Literal["VERBATIM", "SUMMARY", "INTERPRETATION", "UNAVAILABLE"]
RetrievalMethod = Literal["LIVE", "OFFLINE_FALLBACK", "UNKNOWN"]


class LanguageInfo(BaseModel):
    """Detailed language identification outcome."""

    code: str = Field(
        ...,
        description="ISO 639-1 or 639-2 code, or 'und' for undetermined.",
        examples=["en", "ru", "es", "und"],
    )
    name: str = Field(
        ...,
        description="Descriptive name of the identified language or script family.",
        examples=["English", "Cyrillic Script (Russian / Slavic)", "Undetermined Latin-script"],
    )
    is_reliable: bool = Field(
        ...,
        description="True if identification was confirmed with high confidence; False if uncertain.",
    )
    method: str = Field(
        ...,
        description="Detection method used (e.g. 'user_hint', 'script_analysis', 'lexical_analysis', 'undetermined').",
    )
    note: Optional[str] = Field(
        default=None,
        description="Methodology note regarding identification certainty.",
    )


class ClaimRequest(BaseModel):
    """Request schema for submitting a claim statement to VERITAS."""

    claim: str = Field(
        ...,
        max_length=settings.MAX_CLAIM_LENGTH,
        description="The statement or proposition to verify (maximum 1,000 characters).",
        examples=["Global surface temperatures have increased by 1.1°C compared to 1850–1900 averages."],
    )
    language: Optional[str] = Field(
        default=None,
        description="Optional ISO language code hint (e.g. 'en', 'es', 'ru').",
        examples=["en"],
    )

    @field_validator("claim")
    @classmethod
    def validate_claim_not_empty_or_whitespace(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Claim cannot be empty or contain only whitespace.")
        if len(value) > settings.MAX_CLAIM_LENGTH:
            raise ValueError(f"Claim cannot exceed {settings.MAX_CLAIM_LENGTH} characters.")
        return trimmed


class ClaimReceiptResponse(BaseModel):
    """Initial confirmation response indicating the claim was received."""

    success: bool = Field(True, description="Indicates if the claim was received successfully.")
    message: str = Field(
        "Claim received. Verification services are not connected yet.",
        description="Status message regarding current pipeline connectivity.",
    )
    claim: str = Field(..., description="The submitted claim text.")
    status: str = Field("pending", description="Current lifecycle status of the claim.")


class EvidenceItem(BaseModel):
    """Represents a retrieved source document or excerpt for factual verification.

    Reliability Rule:
    An evidence item is NOT verified merely because it has a URL or hash.
    It requires verified status from trusted, independent investigative sources.
    """

    id: str = Field(..., description="Unique identifier for the evidence passage.")
    title: str = Field(..., description="Title or headline of the source record.")
    publisher: Optional[str] = Field(
        default=None,
        description="Publishing entity, institution, journal, or news organization.",
    )
    url: Optional[str] = Field(
        default=None,
        description="Canonical URL to the primary source material.",
    )
    published_date: Optional[str] = Field(
        default=None,
        description="Publication date of the record.",
    )
    snippet: str = Field(..., description="Exact textual excerpt used for claim evaluation.")
    stance: str = Field(
        default="NEUTRAL",
        description="Stance relative to the claim: SUPPORTING, CONTRADICTING, or NEUTRAL.",
    )
    is_verified: bool = Field(
        default=False,
        description="Whether this source has been independently confirmed as authentic and accurate.",
    )
    source_domain: Optional[str] = Field(
        default=None,
        description="Normalized root domain used for independent source deduplication.",
    )
    original_url: Optional[str] = Field(
        default=None,
        description="Original submitted or scraped URL prior to canonicalization.",
    )
    canonical_url: Optional[str] = Field(
        default=None,
        description="Canonical URL to the primary source material.",
    )
    canonical_domain: Optional[str] = Field(
        default=None,
        description="Normalized root domain without subdomains (e.g. 'bbc.co.uk').",
    )
    canonical_publisher: Optional[str] = Field(
        default=None,
        description="Normalized publisher entity (e.g. 'BBC', 'Reuters', 'Associated Press').",
    )
    source_tier: str = Field(
        default="SECONDARY",
        description="Source categorization: 'PRIMARY' (direct archive/DOI), 'SECONDARY' (press/fact-check), 'TERTIARY' (encyclopedia), or 'METADATA_ONLY'.",
    )
    source_type: str = Field(
        default="OTHER",
        description="Granular source classification: 'ORIGINAL_RESEARCH', 'REVIEW_PAPER', 'GOVERNMENT_PUBLICATION', 'METADATA_RECORD', 'ENCYCLOPEDIC_SUMMARY', 'NEWS_REPORT', 'WIRE_DISPATCH', 'PREPRINT', or 'OTHER'.",
    )
    text_availability: str = Field(
        default="METADATA_ONLY",
        description="Text availability: 'METADATA_ONLY', 'ABSTRACT', 'EXCERPT', or 'FULL_TEXT'. Never claim full text if only abstract or metadata is available.",
    )
    text_provenance: TextProvenance = Field(
        default="UNAVAILABLE",
        description="Text provenance classification: 'VERBATIM' (exact source quotation), 'SUMMARY' (faithful summary/paraphrase), 'INTERPRETATION' (legal/editorial analysis or synthesis), or 'UNAVAILABLE' (no body text).",
    )
    retrieval_method: RetrievalMethod = Field(
        default="UNKNOWN",
        description="Retrieval method origin: 'LIVE' (retrieved directly via live network request), 'OFFLINE_FALLBACK' (loaded from offline catalog fallback / cache), or 'UNKNOWN' (unspecified).",
    )
    relevance_status: str = Field(
        default="UNDETERMINED",
        description="Relevance to submitted claim: 'RELEVANT', 'IRRELEVANT', 'OFF_TOPIC', or 'UNDETERMINED'.",
    )
    relevance_score: Optional[float] = Field(
        default=None,
        description="Quantitative entity and lexical overlap score (0.0 to 1.0).",
    )
    relevance_justification: Optional[str] = Field(
        default=None,
        description="Detailed explanation of topical alignment or thematic mismatch.",
    )
    stance_justification: Optional[str] = Field(
        default=None,
        description="Detailed justification for SUPPORTING, CONTRADICTING, NEUTRAL, or UNKNOWN stance assignment.",
    )
    duplicate_reason: Optional[str] = Field(
        default=None,
        description="Detailed provenance reasoning for exact duplicate detection or syndication grouping decision.",
    )
    content_sha256: Optional[str] = Field(
        default=None,
        description="SHA-256 cryptographic digest of normalized snippet content.",
    )
    is_potential_syndication: bool = Field(
        default=False,
        description="True if article appears to be a syndicated wire copy from a third-party agency (AP, Reuters, AFP).",
    )
    syndication_notes: Optional[str] = Field(
        default=None,
        description="Details regarding wire service syndication or duplicate content origin.",
    )
    doi: Optional[str] = Field(
        default=None,
        description="Digital Object Identifier (DOI) for scholarly literature (e.g. '10.1029/2010rg000345').",
    )
    is_full_text: bool = Field(
        default=False,
        description="True if excerpt is from full-text article; False if derived from abstract or metadata summary.",
    )
    underlying_source_id: Optional[str] = Field(
        default=None,
        description="Parent study or dataset identifier for translations, reprints, or syndicated records.",
    )
    independence_status: str = Field(
        default="INDEPENDENT",
        description="Independence classification: 'INDEPENDENT', 'TRANSLATION_COPY', 'SYNDICATED_COPY', or 'UNKNOWN'.",
    )
    is_machine_translated: bool = Field(
        default=False,
        description="True if snippet was generated via automated machine translation rather than author text.",
    )
    translation_engine: Optional[str] = Field(
        default=None,
        description="Identifier of machine translation system or organizational translation agency.",
    )
    original_language: Optional[str] = Field(
        default=None,
        description="ISO 639-1 code of original publication language before translation, or 'und' if undetermined.",
    )
    traceability: Optional[Dict[str, str]] = Field(
        default=None,
        description="Traceability metadata including retrieval timestamp, archival record, and content hash.",
    )
    curation_status: CurationStatus = Field(
        default="UNREVIEWED",
        description="Reviewer curation status: 'UNREVIEWED', 'UNDER_REVIEW', 'APPROVED_VERIFIED', 'REJECTED_IRRELEVANT', 'REJECTED_UNRELIABLE', or 'SUPERSEDED'.",
    )
    reviewer_id: Optional[str] = Field(
        default=None,
        description="Identifier of the human reviewer who performed curation.",
    )
    review_timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp when curation was conducted.",
    )
    reviewer_notes: Optional[str] = Field(
        default=None,
        description="Reviewer rationale, verification methodology, and scientific justification.",
    )
    reviewer_confirmed_stance: Optional[ReviewerConfirmedStance] = Field(
        default=None,
        description="Human confirmed stance relative to the claim ('SUPPORTING', 'CONTRADICTING', or 'NEUTRAL').",
    )
    peer_review_confirmed: bool = Field(
        default=False,
        description="Whether publication in a peer-reviewed scientific journal or authoritative agency archive was confirmed by reviewer.",
    )
    operational_status: str = Field(
        default="UNKNOWN",
        description="Administrative and legal operational vitality ('CURRENT_OPERATIVE', 'ARCHIVED_DISCONTINUED', 'REPEALED_VACATED', 'SUPERSEDED', 'HISTORICAL_ONLY', 'UNKNOWN', 'NOT_APPLICABLE').",
    )
    domain: str = Field(
        default="EMPIRICAL_NON_LEGAL",
        description="Epistemological domain of evidence ('LEGAL', 'EMPIRICAL_NON_LEGAL', 'EMPIRICAL_POLICY_CONTEXT').",
    )
    effective_from_date: Optional[str] = Field(
        default=None,
        description="ISO 8601 date (YYYY-MM-DD, YYYY-MM, or YYYY) when authority became legally effective.",
    )
    effective_to_date: Optional[str] = Field(
        default=None,
        description="ISO 8601 date when authority was repealed, vacated, superseded, or sunset.",
    )
    enactment_date: Optional[str] = Field(
        default=None,
        description="ISO 8601 date when legislation was signed or passed.",
    )
    textual_epoch: Optional[str] = Field(
        default=None,
        description="Chronological authenticity of text ('HISTORICAL_CONTEMPORARY', 'CODIFIED_RETROSPECTIVE', 'CURRENT_CONSOLIDATED').",
    )


class CurationReviewDecision(BaseModel):
    """Structured decision submitted by a human reviewer for an evidence record."""

    evidence_id: str = Field(..., description="Unique ID of the evidence record being curated.")
    claim_id: Optional[str] = Field(default=None, description="Optional associated claim ID if review is claim-specific.")
    curation_status: CurationStatus = Field(..., description="Target curation status.")
    reviewer_id: str = Field(..., description="Unique identifier or username of the reviewer.")
    reviewer_notes: Optional[str] = Field(default=None, description="Detailed reasoning and justification for the decision.")
    reviewer_confirmed_stance: Optional[ReviewerConfirmedStance] = Field(
        default=None,
        description="Reviewer-confirmed stance relative to the claim ('SUPPORTING', 'CONTRADICTING', or 'NEUTRAL').",
    )
    peer_review_confirmed: bool = Field(
        default=False,
        description="Whether publication in a peer-reviewed scientific journal or authoritative agency archive was confirmed by reviewer.",
    )
    # CurationReviewDecision operational status
    operational_status: Optional[str] = Field(
        default=None,
        description="Optional reviewer-assigned operational status ('CURRENT_OPERATIVE', 'ARCHIVED_DISCONTINUED', 'REPEALED_VACATED', 'SUPERSEDED', 'HISTORICAL_ONLY', 'UNKNOWN', 'NOT_APPLICABLE').",
    )
    text_provenance: Optional[TextProvenance] = Field(
        default=None,
        description="Reviewer-confirmed text provenance classification ('VERBATIM', 'SUMMARY', 'INTERPRETATION', or 'UNAVAILABLE').",
    )

    @field_validator("reviewer_id")
    @classmethod
    def validate_reviewer_id_not_empty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Reviewer ID cannot be empty or whitespace.")
        return trimmed

    @model_validator(mode="after")
    def validate_approved_verified_stance(self) -> "CurationReviewDecision":
        """Enforce that APPROVED_VERIFIED requires an explicit decisive stance (SUPPORTING or CONTRADICTING)."""
        if self.curation_status == "APPROVED_VERIFIED":
            if not self.reviewer_confirmed_stance:
                raise ValueError(
                    "APPROVED_VERIFIED status requires an explicit reviewer-confirmed stance ('SUPPORTING' or 'CONTRADICTING'). "
                    "Cannot approve evidence without confirmed decisive stance."
                )
            if self.reviewer_confirmed_stance not in ("SUPPORTING", "CONTRADICTING"):
                raise ValueError(
                    f"APPROVED_VERIFIED status requires a decisive stance ('SUPPORTING' or 'CONTRADICTING'), "
                    f"got '{self.reviewer_confirmed_stance}'. Neutral evidence cannot be approved as verified."
                )
        return self


class CurationAuditLogEntry(BaseModel):
    """Audit log entry representing a historical curation decision."""

    audit_id: int = Field(..., description="Auto-incremented audit log ID.")
    evidence_id: str = Field(..., description="Unique ID of the evidence record.")
    claim_id: Optional[str] = Field(default=None, description="Optional associated claim ID.")
    previous_status: str = Field(..., description="Previous curation status.")
    new_status: str = Field(..., description="New curation status.")
    previous_stance: Optional[str] = Field(default=None, description="Previous stance before review.")
    new_stance: Optional[str] = Field(default=None, description="New reviewer-confirmed stance.")
    reviewer_id: str = Field(..., description="Identifier of the reviewer.")
    reviewer_notes: Optional[str] = Field(default=None, description="Reviewer rationale and notes.")
    decision_timestamp: str = Field(..., description="ISO 8601 timestamp of the decision.")


class CurationQueueResponse(BaseModel):
    """Response model for paginated curation queue queries."""

    total_count: int = Field(..., description="Total number of evidence records matching query criteria.")
    items: List[EvidenceItem] = Field(..., description="List of evidence items in the current page.")


class ModelInferenceResult(BaseModel):
    """Inference output from an individual neural transformer model.

    Reliability Rules:
    - Never invent predictions or confidence scores.
    - An unavailable or unimplemented model can NEVER return is_available=True.
    - A hate-speech classifier must not be treated as a fact-checking classifier.
    - Model predictions must never be mapped directly to final verdicts.
    """

    model_name: str = Field(..., description="Name of the model (e.g. XLM-RoBERTa or RoBERTa).")
    is_available: bool = Field(
        default=False,
        description="Whether model weights are loaded and active. False if weights are not loaded.",
    )
    prediction: Optional[str] = Field(
        default=None,
        description="Model prediction. Strictly None when weights are not loaded.",
    )
    status: str = Field(..., description="Operational status: 'model_not_loaded', 'active', or 'error'.")
    details: Optional[str] = Field(
        default=None,
        description="Contextual details regarding the model adapter state.",
    )
    task: Optional[str] = Field(
        default=None,
        description="Specific task domain (e.g. 'fact_checking_7class', 'fact_checking_binary', 'immigrant_hate_speech').",
    )
    repository: Optional[str] = Field(
        default=None,
        description="HuggingFace model repository identifier.",
    )
    classification_type: Optional[str] = Field(
        default=None,
        description="Category: 'fact_checking' (XLM-RoBERTa) vs 'content_safety' (RoBERTa hate speech).",
    )
    architecture: Optional[str] = Field(
        default=None,
        description="Underlying base transformer architecture (e.g. 'xlm-roberta-base' or 'roberta-base').",
    )
    label_mapping: Optional[Dict[int, str]] = Field(
        default=None,
        description="Audited id2label dictionary matching Hugging Face config.json.",
    )
    language_support: Optional[str] = Field(
        default=None,
        description="Status of language compatibility for this model.",
    )
    raw_class_id: Optional[int] = Field(
        default=None,
        description="Raw integer class identifier returned by the model head argmax.",
    )
    confidence: Optional[float] = Field(
        default=None,
        description="Softmax probability associated with the predicted class (0.0 to 1.0). None when not loaded.",
    )
    inference_time_ms: Optional[float] = Field(
        default=None,
        description="Latency of the model forward pass in milliseconds.",
    )
    device: Optional[str] = Field(
        default=None,
        description="Computation device ('mps', 'cuda', 'cpu') utilized for inference.",
    )


class ModelControlRequest(BaseModel):
    """Request payload for on-demand neural model loading or unloading."""

    model_name: Optional[str] = Field(
        default="all",
        description="Target model identifier ('xlm_roberta_7class', 'xlm_roberta_binary', 'roberta_hate_speech', or 'all').",
    )


class ComparisonStatus(BaseModel):
    """Summary of cross-model evaluation status.

    Reliability Rules:
    - A future scientifically valid dual-model fact-checking comparison requires compatible fact-checking outputs.
    - RoBERTa (nusaiba19/roberta-immigrant-hate-speech) is an immigrant hate-speech classifier, NOT a fact-checking model.
    - Incompatible classification labels must never be combined to claim independent truth verification.
    - If compatible models or weights are unavailable, is_complete MUST be False.
    """

    is_complete: bool = Field(
        ...,
        description="True ONLY if compatible fact-checking models were fully evaluated. False if either is unavailable or incompatible.",
    )
    models_evaluated: List[str] = Field(
        default_factory=list,
        description="List of models that successfully completed inference.",
    )
    status_message: str = Field(..., description="Explanation of model comparison availability.")


class VerdictAssessment(BaseModel):
    """Evidence-based verdict determination.

    Reliability Rules:
    - Verdict MUST be one of the five permitted categories.
    - Requires at least two independent, relevant, verified sources before a conclusive verdict.
    - If evidence is insufficient, returns UNVERIFIED.
    - Model agreement is NEVER treated as proof of truth.
    """

    verdict: str = Field(
        default="UNVERIFIED",
        description="Standardized verdict: TRUE, FALSE, PARTIALLY TRUE, MISLEADING, or UNVERIFIED.",
    )
    justification: str = Field(..., description="Evidence-anchored justification for the verdict.")
    evidence_count: int = Field(default=0, description="Total number of evidence items retrieved.")
    independent_sources_count: int = Field(
        default=0,
        description="Count of distinct, independent publishers or domains (duplicates excluded).",
    )
    has_sufficient_evidence: bool = Field(
        default=False,
        description="True if minimum independent verified source threshold (>= 2) was met.",
    )
    methodology_notes: List[str] = Field(
        default_factory=list,
        description="Core scientific guidelines and boundaries applied during this evaluation.",
    )

    @field_validator("verdict")
    @classmethod
    def validate_permitted_verdict(cls, value: str) -> str:
        if value not in settings.PERMITTED_VERDICTS:
            raise ValueError(
                f"Invalid verdict '{value}'. Must be one of: {', '.join(settings.VERDICTS_ORDERED)}"
            )
        return value


class PropositionItem(BaseModel):
    """An individual factual proposition extracted from a compound claim."""

    id: str = Field(..., description="Unique tracking identifier for this sub-proposition (e.g. 'prop-1').")
    claim_id: str = Field(..., description="Reference ID of the parent claim statement.")
    text: str = Field(..., description="The self-contained factual proposition statement.")
    proposition_type: str = Field(
        default="ATOMIC",
        description="Type of assertion: 'ATOMIC', 'ENTITY_ASSERTION', 'QUANTITATIVE', 'TEMPORAL', 'CAUSAL', or 'AMBIGUOUS'.",
    )
    status: str = Field(
        default="VALID",
        description="Extraction validity status: 'VALID', 'NEEDS_REVIEW', or 'AMBIGUOUS'.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Analytical rationale for proposition boundary identification.",
    )
    temporal_scope: Optional[str] = Field(
        default="PRESENT_OPERATIONAL",
        description="Temporal frame of reference for assertion ('PRESENT_OPERATIONAL', 'HISTORICAL', 'HISTORICAL_LEGAL', 'TIME_INVARIANT_LEGAL_RULE', 'TIME_INVARIANT_LEGAL_MAXIM', 'EMPIRICAL_NON_LEGAL', 'UNKNOWN').",
    )
    reference_period_start: Optional[str] = Field(
        default=None,
        description="ISO 8601 date (YYYY-MM-DD, YYYY-MM, or YYYY) start of claimed event/scope.",
    )
    reference_period_end: Optional[str] = Field(
        default=None,
        description="ISO 8601 date (YYYY-MM-DD, YYYY-MM, or YYYY) end of claimed event/scope.",
    )
    temporal_quantification: Optional[str] = Field(
        default="INTERSECTING",
        description="Temporal quantification modality ('INTERSECTING', 'CONTINUOUS_FULL_PERIOD', 'POINT_IN_TIME').",
    )
    canonical_id: Optional[str] = Field(
        default=None,
        description="Deterministic semantic proposition identifier (prop_{decomp_version}_{claim_hash}_{prop_hash}).",
    )
    canonical_proposition_hash: Optional[str] = Field(
        default=None,
        description="Deterministic SHA-256 digest of normalized proposition assertion.",
    )
    domain: Optional[str] = Field(
        default="LEGAL",
        description="Epistemological domain of proposition ('LEGAL', 'EMPIRICAL_NON_LEGAL', 'EMPIRICAL_POLICY_CONTEXT').",
    )


class PropositionEvidenceMatch(BaseModel):
    """Association and stance evaluation of an evidence record against a specific proposition."""

    proposition_id: str = Field(..., description="ID of the evaluated proposition.")
    proposition_text: str = Field(..., description="Text of the proposition being evaluated.")
    evidence_id: str = Field(..., description="ID of the matched evidence record.")
    evidence_title: str = Field(..., description="Title or headline of the evidence record.")
    relevance_status: str = Field(
        default="UNDETERMINED",
        description="Relevance to this specific proposition: 'RELEVANT', 'IRRELEVANT', 'OFF_TOPIC', or 'UNDETERMINED'.",
    )
    relevance_score: Optional[float] = Field(
        default=None,
        description="Lexical/entity overlap score relative to this specific proposition (0.0 to 1.0).",
    )
    stance: str = Field(
        default="NEUTRAL",
        description="Directional stance for this proposition: 'SUPPORTING', 'CONTRADICTING', 'NEUTRAL', or 'UNDETERMINED'.",
    )
    explanation: str = Field(..., description="Traceable explanation for the relevance and stance determination.")
    source_url: Optional[str] = Field(default=None, description="Canonical source URL of the evidence item.")
    publisher: Optional[str] = Field(default=None, description="Publishing entity or media outlet.")
    source_tier: str = Field(default="SECONDARY", description="Source classification tier (PRIMARY, SECONDARY, TERTIARY).")
    source_type: str = Field(default="OTHER", description="Granular source type.")
    text_availability: str = Field(default="METADATA_ONLY", description="Availability: METADATA_ONLY, ABSTRACT, EXCERPT, FULL_TEXT.")
    is_verified: bool = Field(default=False, description="Whether the evidence item is independently verified.")


class PropositionCoverage(BaseModel):
    """Evidence coverage and balance summary for an individual proposition."""

    proposition_id: str = Field(..., description="ID of the proposition.")
    proposition_text: str = Field(..., description="Text of the proposition.")
    proposition_type: str = Field(default="ATOMIC", description="Proposition category.")
    coverage_status: str = Field(
        default="NO_EVIDENCE",
        description=(
            "Coverage status: 'VERIFIED_SUPPORTED' (>= 2 verified independent sources), "
            "'UNVERIFIED_MATCH_SUPPORTING' (text match in unverified literature), "
            "'VERIFIED_CONTRADICTED' (>= 2 verified independent sources), "
            "'UNVERIFIED_MATCH_CONTRADICTING' (text match in unverified literature), "
            "'CONFLICTING', 'NO_EVIDENCE', or 'UNRESOLVED'."
        ),
    )
    supporting_count: int = Field(default=0, description="Total supporting evidence items (verified + unverified).")
    contradicting_count: int = Field(default=0, description="Total contradicting evidence items (verified + unverified).")
    neutral_count: int = Field(default=0, description="Total neutral / descriptive evidence items.")
    verified_supporting_count: int = Field(default=0, description="Total verified independent supporting evidence items.")
    verified_contradicting_count: int = Field(default=0, description="Total verified independent contradicting evidence items.")
    unverified_supporting_count: int = Field(default=0, description="Total unverified supporting literature items.")
    unverified_contradicting_count: int = Field(default=0, description="Total unverified contradicting literature items.")
    matches: List[PropositionEvidenceMatch] = Field(
        default_factory=list,
        description="List of detailed evidence match records associated with this proposition.",
    )
    independent_corroboration: bool = Field(
        default=False,
        description="True if proposition is corroborated by >= 2 independent verified clusters.",
    )
    authority_clusters_count: int = Field(
        default=0,
        description="Count of distinct independent authority clusters formed for this proposition.",
    )
    cluster_stances: List[str] = Field(
        default_factory=list,
        description="Stances assigned to formed authority clusters ('SUPPORTING', 'CONTRADICTING', 'CONFLICTING', etc.).",
    )
    cluster_details: Optional[List[Dict]] = Field(
        default=None,
        description="Detailed authority cluster breakdowns including member evidence IDs and stances.",
    )
    verified_independent_pairs_count: int = Field(
        default=0,
        description="Count of verified independent cross-cluster relationship pairs.",
    )
    has_two_independent_sources: bool = Field(
        default=False,
        description="Whether the Two-Key Gate threshold is satisfied (>= 2 independent clusters and >= 1 verified independent pair).",
    )
    diagnostic_notes: Optional[str] = Field(
        default=None,
        description="Detailed diagnostic notes from proposition corroboration evaluation.",
    )
    notes: Optional[str] = Field(default=None, description="Diagnostic coverage notes.")


class ClaimDecompositionResult(BaseModel):
    """Complete claim decomposition and multi-proposition evidence coverage breakdown."""

    claim_id: str = Field(..., description="Tracking identifier of the analyzed claim.")
    original_claim: str = Field(..., description="Original submitted claim statement.")
    status: str = Field(
        default="COMPLETED",
        description="Decomposition status: 'COMPLETED', 'SINGLE_PROPOSITION', 'NEEDS_REVIEW', or 'AMBIGUOUS'.",
    )
    propositions: List[PropositionItem] = Field(
        default_factory=list,
        description="Individual factual propositions extracted from the claim.",
    )
    proposition_coverage: List[PropositionCoverage] = Field(
        default_factory=list,
        description="Evidence coverage and match details for each proposition.",
    )
    total_propositions: int = Field(default=0, description="Total number of extracted propositions.")
    verified_supported_count: int = Field(
        default=0,
        description="Count of propositions supported by >= 2 independent verified sources.",
    )
    verified_contradicted_count: int = Field(
        default=0,
        description="Count of propositions contradicted by >= 2 independent verified sources.",
    )
    unverified_supporting_count: int = Field(
        default=0,
        description="Count of propositions with unverified literature match support.",
    )
    unverified_contradicting_count: int = Field(
        default=0,
        description="Count of propositions with unverified literature match contradiction.",
    )
    supported_propositions_count: int = Field(
        default=0,
        description="Total supported propositions (verified + unverified matches).",
    )
    contradicted_propositions_count: int = Field(
        default=0,
        description="Total contradicted propositions (verified + unverified matches).",
    )
    conflicting_propositions_count: int = Field(
        default=0,
        description="Propositions with conflicting evidence.",
    )
    unresolved_propositions_count: int = Field(
        default=0,
        description="Propositions with no usable or unresolved evidence.",
    )
    coverage_summary: str = Field(..., description="Summary statement of proposition evidence coverage.")
    decomposition_notes: Optional[str] = Field(
        default=None,
        description="Methodology and boundary notes regarding heuristic decomposition.",
    )


class VerificationResultResponse(BaseModel):
    """Structured response representing the complete verification pipeline output."""

    claim_id: str = Field(..., description="Unique tracking identifier for this verification request.")
    claim: str = Field(..., description="The normalized claim statement under evaluation.")
    language: str = Field(..., description="ISO language code or 'und' for undetermined.")
    language_info: LanguageInfo = Field(..., description="Detailed language identification data.")
    comparison_status: ComparisonStatus = Field(
        ...,
        description="Status of cross-model evaluation. Reflects fact-checking compatibility constraints.",
    )
    models: Dict[str, ModelInferenceResult] = Field(
        ...,
        description="Operational outputs for registered models (XLM-RoBERTa 7-class, XLM-RoBERTa binary, RoBERTa hate-speech).",
    )
    evidence: List[EvidenceItem] = Field(
        default_factory=list,
        description="Authoritative evidence sources retrieved (empty when retrieval engine is disconnected).",
    )
    evidence_retrieval_status: str = Field(
        default="disconnected",
        description="Status of the evidence retrieval engine (e.g. 'disconnected', 'connected').",
    )
    decomposition: Optional[ClaimDecompositionResult] = Field(
        default=None,
        description="Decomposed sub-propositions and evidence matching breakdown.",
    )
    verdict_assessment: VerdictAssessment = Field(
        ...,
        description="Final evidence-based verdict determination.",
    )
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of pipeline execution.")
