"""Proposition identity and versioning service for VERITAS.

Implements deterministic, semantic proposition identification, conservative text
normalization, duplicate detection, and explicit, human-reviewed supersession
registries to prevent historical curation decisions from silently attaching
to modified or displaced proposition assertions.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import re
from typing import Dict, List, Optional, Set, Tuple
import unicodedata
from pydantic import BaseModel, Field, field_validator


class SupersessionStatus(str, Enum):
    """Status of an explicit human-reviewed proposition supersession."""

    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED_SUPERSEDED = "CONFIRMED_SUPERSEDED"
    REJECTED = "REJECTED"


class PropositionSupersessionRecord(BaseModel):
    """Explicit, auditable mapping between an old and a superseded proposition.

    STRICT INVARIANT:
    Independence relationships and curation approvals are NEVER automatically
    transferred from previous_proposition_id to new_proposition_id.
    Transfer requires explicit human verification and affirmative documentation.
    """

    supersession_id: str = Field(..., description="Unique tracking identifier for this supersession mapping.")
    previous_proposition_id: str = Field(..., description="Stable ID of the deprecated or modified proposition.")
    new_proposition_id: str = Field(..., description="Stable ID of the replacement proposition.")
    previous_assertion_text: str = Field(..., description="Exact assertion text of the previous proposition.")
    new_assertion_text: str = Field(..., description="Exact assertion text of the new replacement proposition.")
    reviewer_id: str = Field(..., description="Accountable human reviewer recording this mapping.")
    reviewer_notes: str = Field(..., description="Substantive reasoning explaining why the proposition changed.")
    status: SupersessionStatus = Field(default=SupersessionStatus.PENDING_REVIEW)
    allow_relationship_transfer: bool = Field(
        default=False,
        description="Whether relationships may be transferred. Defaults to False; requires explicit reviewer override."
    )
    transfer_justification: Optional[str] = Field(
        default=None,
        description="Mandatory documentation required if allow_relationship_transfer is set to True."
    )
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

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
            raise ValueError("Reviewer notes must contain at least 15 characters explaining the basis.")
        return trimmed

    @field_validator("transfer_justification")
    @classmethod
    def validate_transfer_justification(cls, v: Optional[str], info) -> Optional[str]:
        data = info.data
        if data.get("allow_relationship_transfer"):
            trimmed = (v or "").strip()
            if len(trimmed) < 20:
                raise ValueError(
                    "Transferring relationships across supersession boundaries requires explicit justification "
                    "containing at least 20 characters explaining why the evidentiary scope remains identical."
                )
            return trimmed
        return v


def normalize_assertion_text(text: str) -> str:
    """Normalize proposition text using conservative, semantics-preserving rules.

    Conservative Normalization Rules:
    1. Unicode Canonical Decomposition & Composition (NFC): standardizes accented and composite characters.
    2. Case Normalization: standardizes case to lowercase.
    3. Whitespace Normalization: collapses multiple spaces, tabs, and newlines to a single space; trims ends.
    4. Terminal Punctuation: strips terminal periods, semicolons, commas, or exclamation marks that do not alter core assertion.
    5. Unit and Symbol Standardization: preserves symbols (% , °, $, §) while canonicalizing common verbal equivalents.
    6. SEMANTIC PRESERVATION:
       - Preserves ALL numbers, decimals, and dates (e.g., 7.25, 2023, 1900).
       - Preserves ALL negation tokens ('not', 'no', 'never', 'neither', 'nor', 'cannot', 'without').
       - Preserves statutory/legal references (e.g., '29 U.S.C. § 206', 'FLSA', 'Title VII').
       - NO aggressive stemming or lemmatization that alters grammatical parts of speech or legal terms of art.
    """
    if not text:
        return ""

    # 1. Unicode NFC
    norm = unicodedata.normalize("NFC", text.strip())

    # 2. Lowercase for case-insensitivity
    norm = norm.lower()

    # 3. Standardize common symbol/unit variants while strictly preserving numbers and symbols
    # e.g., "degrees celsius" -> "°c", "percent" -> "%"
    norm = re.sub(r"\bdegrees?\s+celsius\b", "°c", norm)
    norm = re.sub(r"\bpercent\b", "%", norm)
    # Statutory section references: "section § 215", "sec. § 215", "section 215", "sec. 215" -> "§ 215"
    norm = re.sub(r"\b(?:section|sec\.)\s*§\s*", "§ ", norm)
    norm = re.sub(r"\b(?:section|sec\.)\s+(?=\d)", "§ ", norm)

    # 4. Collapse contiguous whitespace, tabs, and newlines
    norm = re.sub(r"[\s\t\r\n]+", " ", norm).strip()

    # 5. Strip non-semantic trailing punctuation
    norm = norm.rstrip(".,;:!?")

    return norm


def compute_assertion_digest(normalized_text: str, length: int = 16) -> str:
    """Compute deterministic SHA-256 digest of normalized proposition assertion text."""
    if not normalized_text:
        raise ValueError("Cannot compute digest of empty normalized assertion text.")
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:length]


def generate_stable_proposition_id(
    claim_text: str,
    proposition_text: str,
    decomp_version: str = "v1",
) -> str:
    """Generate a deterministic, semantic, order-independent proposition identifier.

    Format:
        prop_{decomp_version}_{norm_claim_hash}_{norm_prop_hash}

    Components:
    - decomp_version: algorithm version (e.g. 'v1') isolating heuristic updates.
    - norm_claim_hash: 12-char SHA-256 digest of the normalized parent claim.
    - norm_prop_hash: 16-char SHA-256 digest of the normalized proposition assertion text.

    Epistemological Properties:
    - Order Independent: Proposition index position in decomposition output does not affect the ID.
    - Displacement Immune: If proposition wording changes, norm_prop_hash changes, preventing silent re-binding.
    - Negation Sensitive: Negation changes norm_prop_hash completely.
    - Number & Unit Sensitive: Any difference in numbers or units produces a distinct ID.
    """
    norm_claim = normalize_assertion_text(claim_text)
    norm_prop = normalize_assertion_text(proposition_text)

    if not norm_claim:
        raise ValueError("Claim text cannot be empty or whitespace-only.")
    if not norm_prop:
        raise ValueError("Proposition text cannot be empty or whitespace-only.")

    claim_hash = compute_assertion_digest(norm_claim, length=12)
    prop_hash = compute_assertion_digest(norm_prop, length=16)

    return f"prop_{decomp_version}_{claim_hash}_{prop_hash}"


def detect_duplicate_propositions(
    propositions: List[str],
) -> Tuple[List[str], Dict[str, List[int]]]:
    """Identify duplicate propositions within a decomposed claim using normalized semantic text.

    Returns:
    - unique_propositions: list of distinct normalized propositions in first-seen order.
    - duplicate_map: mapping from normalized text to list of original zero-based indices.
    """
    seen: Dict[str, List[int]] = {}
    for idx, prop in enumerate(propositions):
        norm = normalize_assertion_text(prop)
        if norm:
            seen.setdefault(norm, []).append(idx)

    unique_propositions = list(seen.keys())
    duplicate_map = {norm: indices for norm, indices in seen.items() if len(indices) > 1}
    return unique_propositions, duplicate_map


class PropositionSupersessionRegistry:
    """In-memory or repository-backed registry for tracking proposition revisions and supersessions."""

    def __init__(self):
        self._records: Dict[str, PropositionSupersessionRecord] = {}

    def register_supersession(
        self,
        previous_proposition_id: str,
        new_proposition_id: str,
        previous_assertion_text: str,
        new_assertion_text: str,
        reviewer_id: str,
        reviewer_notes: str,
        allow_relationship_transfer: bool = False,
        transfer_justification: Optional[str] = None,
    ) -> PropositionSupersessionRecord:
        """Register a human-confirmed supersession record."""
        if previous_proposition_id == new_proposition_id:
            raise ValueError("Previous proposition ID and new proposition ID cannot be identical.")

        supersession_id = f"super_{previous_proposition_id}_to_{new_proposition_id}"
        record = PropositionSupersessionRecord(
            supersession_id=supersession_id,
            previous_proposition_id=previous_proposition_id,
            new_proposition_id=new_proposition_id,
            previous_assertion_text=previous_assertion_text,
            new_assertion_text=new_assertion_text,
            reviewer_id=reviewer_id,
            reviewer_notes=reviewer_notes,
            status=SupersessionStatus.CONFIRMED_SUPERSEDED,
            allow_relationship_transfer=allow_relationship_transfer,
            transfer_justification=transfer_justification,
        )
        self._records[supersession_id] = record
        return record

    def get_supersession(self, previous_proposition_id: str) -> Optional[PropositionSupersessionRecord]:
        """Find if a proposition has an active supersession mapping."""
        for rec in self._records.values():
            if rec.previous_proposition_id == previous_proposition_id and rec.status == SupersessionStatus.CONFIRMED_SUPERSEDED:
                return rec
        return None

    def can_transfer_relationships(self, previous_proposition_id: str) -> bool:
        """Strict guard checking whether relationship transfer was explicitly authorized by human reviewer."""
        rec = self.get_supersession(previous_proposition_id)
        if not rec:
            return False
        return rec.allow_relationship_transfer is True
