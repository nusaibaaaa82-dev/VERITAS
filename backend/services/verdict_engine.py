"""Verdict Assessment Engine for VERITAS.

Synthesizes retrieved evidence and cross-encoder outputs to render calibrated,
standardized verdicts adhering to scientific fact-checking standards.

Five Permitted Verdict Categories:
- TRUE: Factual and fully corroborated by at least 2 independent verified primary/secondary sources.
- FALSE: Demonstrably contradicted by at least 2 independent verified primary/secondary sources.
- PARTIALLY TRUE: Contains accurate factual elements, but omits essential context or overextends scope.
- MISLEADING: Employs authentic figures or quotes in a distorted or deceptive framing.
- UNVERIFIED: Insufficient, duplicate, or inconclusive verified evidence.

Strict Reliability Rules Enforced:
1. Verdict MUST be one of the five permitted categories.
2. Require at least two independent, relevant, verified sources before reaching a conclusive verdict.
3. Do not count duplicate sources as independent (same canonical domain, canonical publisher, or identical snippet SHA-256).
4. Do not count syndicated wire copies (e.g. AP, Reuters, AFP) as independent sources.
5. Wikimedia/tertiary sources are strictly for background/discovery and cannot corroborate conclusive verdicts.
6. Do not treat one source as sufficient proof of a factual claim.
7. Do not automatically label mixed evidence PARTIALLY TRUE without sufficient contextual assessment.
8. Keep MISLEADING separate from PARTIALLY TRUE.
9. Return UNVERIFIED whenever evidence is insufficient or inconclusive.
10. Model agreement must NEVER determine the truth of a claim.
"""

import hashlib
import re
from typing import Dict, List, Set

from backend.config import settings
from backend.schemas.claim import (
    ClaimDecompositionResult,
    ComparisonStatus,
    EvidenceItem,
    ModelInferenceResult,
    VerdictAssessment,
)


class VerdictEngine:
    """Evaluates evidence corroboration to produce transparent, auditable verdicts."""

    @staticmethod
    def deduplicate_independent_sources(evidence: List[EvidenceItem]) -> List[EvidenceItem]:
        """Filter evidence to retain only independent sources.

        Reliability Rules:
        - Duplicate sources from the same publisher, canonical domain, or wire agency are not independent.
        - Identical content SHA-256 hashes across different domains indicate copied/syndicated text.
        - Potential wire syndications sharing the same wire agency are grouped as a single source.
        """
        seen_domains: Set[str] = set()
        seen_publishers: Set[str] = set()
        seen_hashes: Set[str] = set()
        seen_wires: Set[str] = set()
        seen_dois: Set[str] = set()
        seen_underlying: Set[str] = set()
        independent: List[EvidenceItem] = []

        for item in evidence:
            trace = item.traceability or {}

            # 1. Exact content hash deduplication across any domain
            content_hash = item.content_sha256 or (
                hashlib.sha256(item.snippet.encode("utf-8")).hexdigest() if item.snippet else None
            )
            if content_hash:
                if content_hash in seen_hashes:
                    continue
                seen_hashes.add(content_hash)

            # 2. Wire syndication grouping (e.g. AP wire distributed across multiple local outlets)
            if item.is_potential_syndication and item.syndication_notes:
                wire_match = re.search(r"identified wire:\s*([^),]+)", item.syndication_notes, re.IGNORECASE)
                wire_name = wire_match.group(1).lower().strip() if wire_match else "wire_syndicated"
                if wire_name in seen_wires:
                    continue
                seen_wires.add(wire_name)

            # 3. Shared underlying DOI deduplication (e.g. distinct news portals citing the same primary study)
            raw_doi = (item.doi or trace.get("doi") or "").lower().strip()
            if raw_doi:
                clean_doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", raw_doi)
                if clean_doi in seen_dois:
                    continue
                seen_dois.add(clean_doi)

            # 4. Shared underlying source / parent study deduplication (e.g. translation copies of same report)
            underlying_id = (item.underlying_source_id or trace.get("underlying_source_id") or "").lower().strip()
            if underlying_id:
                if underlying_id in seen_underlying:
                    continue
                seen_underlying.add(underlying_id)

            # 5. Canonical domain and publisher deduplication
            norm_dom = (item.canonical_domain or item.source_domain or "").lower().strip()
            norm_pub = (item.canonical_publisher or item.publisher or "").lower().strip()

            if norm_dom and norm_dom in seen_domains:
                continue
            if norm_pub and norm_pub in seen_publishers:
                continue

            if norm_dom:
                seen_domains.add(norm_dom)
            if norm_pub:
                seen_publishers.add(norm_pub)

            independent.append(item)

        return independent

    def assess_verdict(
        self,
        claim: str,
        evidence: List[EvidenceItem],
        model_results: Dict[str, ModelInferenceResult],
        comparison_status: ComparisonStatus,
        decomposition: Optional[ClaimDecompositionResult] = None,
    ) -> VerdictAssessment:
        """Formulate the standardized verdict based strictly on verified independent evidence.

        Reliability Rules:
        - If evidence is insufficient (< 2 independent verified sources), return UNVERIFIED.
        - Model agreement must NEVER determine the truth of a claim.
        - Multi-proposition claims require verification across all essential sub-propositions.
        - Do not allow one proposition's evidence to establish the truth of the entire claim.
        - Do not convert a coverage score into a truth verdict.
        - Wikimedia/tertiary sources cannot satisfy primary corroboration requirements.
        - Must be one of: TRUE, FALSE, PARTIALLY TRUE, MISLEADING, UNVERIFIED.
        """
        evidence_count = len(evidence)

        # Deduplicate sources to count only independent entities
        independent_sources = self.deduplicate_independent_sources(evidence)
        independent_sources_count = len(independent_sources)

        # Filter strictly for verified, relevant, non-tertiary, non-metadata sources
        # (Presence of URL or hash alone does NOT constitute verified)
        # Wikimedia/tertiary sources and metadata-only records are strictly background context.
        verified_independent = [
            item
            for item in independent_sources
            if item.is_verified
            and item.source_tier not in ("TERTIARY", "METADATA_ONLY")
            and item.relevance_status != "IRRELEVANT"
            and item.independence_status != "UNKNOWN"
            and (item.traceability or {}).get("independence_status") != "UNKNOWN"
        ]
        verified_independent_count = len(verified_independent)

        # Base methodology notes
        methodology_notes = [
            "Model agreement is never treated as proof of truth.",
            "Model predictions provide auxiliary analytical signals and are never mapped directly to final verdicts.",
            "The two XLM-RoBERTa checkpoints share the xlm-roberta-base architecture and do not constitute independent models.",
            f"Conclusive verdicts require at least {settings.MIN_INDEPENDENT_EVIDENCE_SOURCES} independent verified sources.",
            "Multi-proposition claims require independent corroboration across all essential sub-propositions.",
            "Evidence for one sub-clause never establishes the factual truth of the entire statement.",
            "Proposition coverage scores are never converted directly into truth verdicts.",
            "Wikimedia summaries and metadata-only citations serve as discovery context and do not count toward primary corroboration.",
            "Presence of a URL or cryptographic hash does not constitute proof of authenticity.",
        ]

        # Rule: If sufficient verified evidence is unavailable (< 2 independent verified sources), return UNVERIFIED
        if verified_independent_count < settings.MIN_INDEPENDENT_EVIDENCE_SOURCES:
            return VerdictAssessment(
                verdict="UNVERIFIED",
                justification=(
                    f"Insufficient verified evidence: found {verified_independent_count} independent verified sources "
                    f"(minimum {settings.MIN_INDEPENDENT_EVIDENCE_SOURCES} required). "
                    "VERITAS strictly withholds definitive truth determinations without corroborating primary evidence."
                ),
                evidence_count=evidence_count,
                independent_sources_count=independent_sources_count,
                has_sufficient_evidence=False,
                methodology_notes=methodology_notes,
            )

        # Safety Rule: If claim has multiple decomposed propositions, one proposition's evidence
        # must NEVER establish the truth of the entire claim!
        if decomposition and decomposition.total_propositions > 1:
            not_verified_supported = [
                cov for cov in decomposition.proposition_coverage
                if cov.coverage_status != "VERIFIED_SUPPORTED"
            ]
            if not_verified_supported or decomposition.unresolved_propositions_count > 0 or decomposition.contradicted_propositions_count > 0:
                unverified_match_count = sum(
                    1 for cov in not_verified_supported
                    if cov.coverage_status in ("UNVERIFIED_MATCH_SUPPORTING", "UNVERIFIED_MATCH_CONTRADICTING")
                )
                return VerdictAssessment(
                    verdict="UNVERIFIED",
                    justification=(
                        f"Incomplete proposition corroboration: claim decomposed into {decomposition.total_propositions} factual "
                        f"sub-propositions, but {len(not_verified_supported)} propositions lack independent verification "
                        f"({unverified_match_count} have unverified literature matches, "
                        f"{decomposition.unresolved_propositions_count} lack evidence, "
                        f"{decomposition.contradicted_propositions_count} are contradicted). "
                        "Evidence for one sub-clause cannot establish the truth of the compound statement as a whole."
                    ),
                    evidence_count=evidence_count,
                    independent_sources_count=independent_sources_count,
                    has_sufficient_evidence=False,
                    methodology_notes=methodology_notes,
                )

        # Analyze stances among verified independent sources
        supporting = [e for e in verified_independent if e.stance == "SUPPORTING"]
        contradicting = [e for e in verified_independent if e.stance == "CONTRADICTING"]

        # Rule: Both supporting and contradicting without detailed contextual assessment
        # Do NOT automatically label mixed evidence PARTIALLY TRUE.
        if len(supporting) > 0 and len(contradicting) > 0:
            verdict = "UNVERIFIED"
            justification = (
                f"Conflicting evidence detected across independent verified sources ({len(supporting)} supporting, "
                f"{len(contradicting)} contradicting). Without contextual resolution or scholarly consensus, "
                "the claim remains UNVERIFIED."
            )
        elif len(supporting) >= settings.MIN_INDEPENDENT_EVIDENCE_SOURCES and len(contradicting) == 0:
            verdict = "TRUE"
            justification = (
                f"The claim is corroborated by {len(supporting)} independent verified sources "
                "with no contradictory evidence identified."
            )
        elif len(contradicting) >= settings.MIN_INDEPENDENT_EVIDENCE_SOURCES and len(supporting) == 0:
            verdict = "FALSE"
            justification = (
                f"The claim is demonstrably contradicted by {len(contradicting)} independent verified sources."
            )
        else:
            verdict = "UNVERIFIED"
            justification = (
                "Available independent verified sources are neutral, inconclusive, or insufficient to establish truth."
            )

        # Validate that the formulated verdict is strictly in PERMITTED_VERDICTS
        assert verdict in settings.PERMITTED_VERDICTS, f"Invalid verdict: {verdict}"

        return VerdictAssessment(
            verdict=verdict,
            justification=justification,
            evidence_count=evidence_count,
            independent_sources_count=independent_sources_count,
            has_sufficient_evidence=True,
            methodology_notes=methodology_notes,
        )
