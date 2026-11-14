"""Claim Decomposition Service for VERITAS.

Responsible for:
1. Identifying distinct factual sub-propositions within complex/compound claims.
2. Segmenting causal drivers, temporal baselines, quantitative measurements, and entity assertions.
3. Detecting ambiguous, speculative, or subjective statements that require human review (NEEDS_REVIEW).
4. Providing transparent, traceable extraction rationales.

Scientific Integrity Notice:
Heuristic decomposition uses rule-based syntactic and semantic pattern extraction.
It is an analytical aid and is not claimed to be a fully validated scientific NLP parse.
"""

import re
from typing import List, Optional, Tuple
from backend.schemas.claim import ClaimDecompositionResult, PropositionItem
from backend.services.proposition_identity import (
    compute_assertion_digest,
    generate_stable_proposition_id,
    normalize_assertion_text,
)


class ClaimDecompositionService:
    """Decomposes submitted claims into self-contained factual propositions."""

    # Subjective, speculative, or non-factual modal markers indicating ambiguous claims
    AMBIGUOUS_MARKERS: List[str] = [
        "maybe",
        "perhaps",
        "i think",
        "i feel",
        "in my opinion",
        "it seems",
        "it might be",
        "probably",
        "could be good",
        "could be bad",
        "some people say",
        "some say",
        "who knows",
        "supposedly",
        "allegedly",
    ]

    # Causal conjunction and preposition patterns
    CAUSAL_PATTERNS = [
        re.compile(r"\b(?:because of|due to|caused by|resulting from|as a result of)\s+([^,\.;]+)", re.IGNORECASE),
        re.compile(r"\bbecause\s+([^,\.;]+)", re.IGNORECASE),
    ]

    # Conditional statement patterns that indicate hypothetical or dependent claims
    CONDITIONAL_PATTERNS = [
        re.compile(r"^(?:if|provided that|assuming that)\b", re.IGNORECASE),
        re.compile(r"\bif\s+.*,\s*.*\b(?:will|would|could|decreased|increased|shall|can)\b", re.IGNORECASE),
        re.compile(r",\s*if\b", re.IGNORECASE),
    ]

    # Double negation or complex negation patterns
    DOUBLE_NEGATION_PATTERNS = [
        re.compile(r"\bnot\s+(?:untrue|unlikely|uncommon|impossible|unproven|ineffective|insignificant|without)\b", re.IGNORECASE),
        re.compile(r"\bno\s+evidence\s+that\s+.*\b(?:not|no|untrue|ineffective)\b", re.IGNORECASE),
        re.compile(r"\b(?:neither|nor)\b", re.IGNORECASE),
        re.compile(r"\bnot\b.{1,35}\b(?:not|no)\b", re.IGNORECASE),
    ]

    # Temporal baseline patterns (e.g. "since 1900", "in 2020", "from 1850 to 1900")
    TEMPORAL_PATTERNS = [
        (re.compile(r"\b(?:since|starting in|from)\s+(\d{4})\b", re.IGNORECASE), "The comparison baseline starts in {0}."),
        (re.compile(r"\b(?:between|from)\s+(\d{4})\s+(?:and|to)\s+(\d{4})\b", re.IGNORECASE), "The observation timeframe is from {0} to {1}."),
        (re.compile(r"\bin\s+(\d{4})\b", re.IGNORECASE), "The reported event or measurement occurred in {0}."),
    ]

    # Quantitative measurement patterns (e.g. "by 2°C", "by 1.5 degrees", "by approximately 15%", "by over 15%")
    QUANTITATIVE_PATTERNS = [
        re.compile(
            r"\bby\s+(?:approximately|approx\.|about|around|over|nearly|almost|at least|more than|roughly)?\s*(\d+[\.,]?\d*\s*(?:°c|degrees(?:\s+celsius)?|c|%|percent|billion|million|trillion|meters|km|ppm)?)(?=[,\.;\s]|$)",
            re.IGNORECASE,
        ),
        re.compile(r"\bby\s+(\d+[\.,]?\d*)(?=[,\.;\s]|$)", re.IGNORECASE),
    ]

    def _enrich_proposition(self, prop: PropositionItem, original_claim: str) -> PropositionItem:
        """Enrich extracted proposition with deterministic IDs, domain classification, and temporal bounds."""
        p_text = prop.text
        # 1. Deterministic canonical ID & assertion hash
        try:
            norm = normalize_assertion_text(p_text)
            prop.canonical_proposition_hash = compute_assertion_digest(norm, length=16)
            prop.canonical_id = generate_stable_proposition_id(original_claim, p_text, decomp_version="v1")
        except Exception:
            prop.canonical_proposition_hash = None
            prop.canonical_id = None

        # 2. Epistemic domain & temporal scope inference
        text_lower = (original_claim + " " + p_text).lower()
        empirical_keywords = ("temperature", "climate", "warming", "degrees", "carbon", "dioxide", "planet", "orbit", "mercury", "sun", "earth", "ephemeris", "astronomy", "hadcrut", "copernicus")
        if any(k in text_lower for k in empirical_keywords) and not any(k in text_lower for k in ("wage", "flsa", "immigrant", "noncitizen", "undocumented", "right", "rights", "law")):
            prop.domain = "EMPIRICAL_NON_LEGAL"
            prop.temporal_scope = "EMPIRICAL_NON_LEGAL"
        else:
            prop.domain = "LEGAL"
            hist_years = [int(y) for y in re.findall(r"\b(18\d{2}|19\d{2}|20[0-1]\d)\b", p_text)]
            if hist_years:
                prop.temporal_scope = "HISTORICAL_LEGAL"
            else:
                prop.temporal_scope = "PRESENT_OPERATIONAL"

        # 3. Temporal parameters extraction
        m_range = re.search(r"\b(?:between|from)\s+(\d{4})\s+(?:and|to)\s+(\d{4})\b", p_text, re.IGNORECASE)
        if m_range:
            prop.reference_period_start = m_range.group(1)
            prop.reference_period_end = m_range.group(2)
            prop.temporal_quantification = "CONTINUOUS_FULL_PERIOD" if "between" in m_range.group(0).lower() or "throughout" in text_lower else "INTERSECTING"
        else:
            m_since = re.search(r"\b(?:since|starting in)\s+(\d{4})\b", p_text, re.IGNORECASE)
            if m_since:
                prop.reference_period_start = m_since.group(1)
                prop.reference_period_end = "2026"
                prop.temporal_quantification = "CONTINUOUS_FULL_PERIOD"
            else:
                m_in = re.search(r"\bin\s+(\d{4})\b", p_text, re.IGNORECASE)
                if m_in:
                    prop.reference_period_start = m_in.group(1)
                    prop.reference_period_end = m_in.group(1)
                    prop.temporal_quantification = "POINT_IN_TIME"

        return prop

    def decompose_claim(self, claim: str, claim_id: str) -> ClaimDecompositionResult:
        """Analyze and decompose a submitted claim into structured propositions.

        Reliability Rules:
        - Do not invent propositions when a claim is ambiguous.
        - Return explicit status NEEDS_REVIEW or AMBIGUOUS for subjective/vague claims.
        - Preserve every proposition with a distinct tracking ID linked to claim_id.
        """
        cleaned_claim = claim.strip()
        claim_lower = cleaned_claim.lower()

        # Step 1: Ambiguity and subjectivity evaluation
        words = cleaned_claim.split()
        is_too_short = len(words) < 3
        has_ambiguous_marker = any(m in claim_lower for m in self.AMBIGUOUS_MARKERS)

        if is_too_short or has_ambiguous_marker:
            ambig_prop = PropositionItem(
                id=f"{claim_id}-p1",
                claim_id=claim_id,
                text=cleaned_claim,
                proposition_type="AMBIGUOUS",
                status="NEEDS_REVIEW",
                notes=(
                    "Claim statement contains subjective, speculative, or ambiguous phrasing. "
                    "Per VERITAS scientific guidelines, automated decomposition is suspended and flagged for review."
                ),
            )
            ambig_prop = self._enrich_proposition(ambig_prop, cleaned_claim)
            return ClaimDecompositionResult(
                claim_id=claim_id,
                original_claim=cleaned_claim,
                status="NEEDS_REVIEW",
                propositions=[ambig_prop],
                proposition_coverage=[],
                total_propositions=1,
                supported_propositions_count=0,
                contradicted_propositions_count=0,
                conflicting_propositions_count=0,
                unresolved_propositions_count=1,
                coverage_summary="Decomposition suspended: claim is ambiguous or lacks verifiable factual framing.",
                decomposition_notes="Flagged as NEEDS_REVIEW: subjective or ambiguous statement.",
            )

        # Check for conditional or counterfactual claims (e.g. "If policy X was introduced, unemployment decreased.")
        has_conditional = any(p.search(cleaned_claim) for p in self.CONDITIONAL_PATTERNS)
        if has_conditional:
            cond_prop = PropositionItem(
                id=f"{claim_id}-p1",
                claim_id=claim_id,
                text=cleaned_claim,
                proposition_type="CONDITIONAL",
                status="NEEDS_REVIEW",
                notes=(
                    "Conditional or hypothetical statement detected ('if ...'). In formal logic, "
                    "a conditional statement (P -> Q) cannot be heuristically split into independent "
                    "unconditional facts without distorting the claim; flagged as NEEDS_REVIEW."
                ),
            )
            cond_prop = self._enrich_proposition(cond_prop, cleaned_claim)
            return ClaimDecompositionResult(
                claim_id=claim_id,
                original_claim=cleaned_claim,
                status="NEEDS_REVIEW",
                propositions=[cond_prop],
                proposition_coverage=[],
                total_propositions=1,
                supported_propositions_count=0,
                contradicted_propositions_count=0,
                conflicting_propositions_count=0,
                unresolved_propositions_count=1,
                coverage_summary="Decomposition suspended: conditional statements require contextual epistemological review.",
                decomposition_notes="Flagged as NEEDS_REVIEW: conditional hypothesis.",
            )

        # Check for complex or double negation (e.g. "It is not untrue that...", "not ineffective")
        has_double_neg = any(p.search(cleaned_claim) for p in self.DOUBLE_NEGATION_PATTERNS)
        if has_double_neg:
            neg_prop = PropositionItem(
                id=f"{claim_id}-p1",
                claim_id=claim_id,
                text=cleaned_claim,
                proposition_type="AMBIGUOUS",
                status="NEEDS_REVIEW",
                notes=(
                    "Complex or double negation detected. Automated heuristic parsing risks inverting polarity "
                    "or generating distorted sub-propositions. Per VERITAS safety guidelines, flagged as NEEDS_REVIEW."
                ),
            )
            neg_prop = self._enrich_proposition(neg_prop, cleaned_claim)
            return ClaimDecompositionResult(
                claim_id=claim_id,
                original_claim=cleaned_claim,
                status="NEEDS_REVIEW",
                propositions=[neg_prop],
                proposition_coverage=[],
                total_propositions=1,
                supported_propositions_count=0,
                contradicted_propositions_count=0,
                conflicting_propositions_count=0,
                unresolved_propositions_count=1,
                coverage_summary="Decomposition suspended: complex/double negation requires human fact-checker review.",
                decomposition_notes="Flagged as NEEDS_REVIEW: complex or double negation.",
            )

        extracted_props: List[PropositionItem] = []
        prop_idx = 1

        # Step 2: Causal Decomposition (Leading and Trailing)
        # Leading causal clause: e.g. "Because of human activity, global temperatures increased by 2°C since 1900."
        leading_causal_pattern = re.compile(
            r"^(?:because of|due to|caused by|resulting from|as a result of|owing to)\s+([^,]+),\s*(.+)",
            re.IGNORECASE,
        )
        leading_match = leading_causal_pattern.match(cleaned_claim)

        causal_driver_text = None
        candidate_core_statement = cleaned_claim

        if leading_match:
            causal_driver_text = leading_match.group(1).strip()
            candidate_core_statement = leading_match.group(2).strip()
        else:
            # Trailing causal patterns: e.g. "Global temperatures have increased ... because of human activity"
            for pattern in self.CAUSAL_PATTERNS:
                match = pattern.search(cleaned_claim)
                if match:
                    causal_driver_text = match.group(1).strip()
                    candidate_core_statement = cleaned_claim[:match.start()].strip()
                    break

        # Step 3: Temporal Baseline Decomposition (e.g. "since 1900")
        temporal_match = None
        temporal_statement = None
        for pattern, template in self.TEMPORAL_PATTERNS:
            match = pattern.search(cleaned_claim)
            if match:
                temporal_match = match
                groups = match.groups()
                temporal_statement = template.format(*groups)
                break

        # Step 4: Quantitative Magnitude Decomposition (e.g. "by 2°C", "by approximately 15%")
        quantitative_match = None
        quantitative_statement = None
        for pattern in self.QUANTITATIVE_PATTERNS:
            match = pattern.search(cleaned_claim)
            if match:
                quantitative_match = match
                val = match.group(0).strip()
                clean_val = re.sub(r"^by\s+", "", val, flags=re.IGNORECASE).strip()
                if any(k in clean_val.lower() for k in ("approximately", "approx.", "about", "over", "nearly", "almost", "at least", "more than", "roughly")):
                    quantitative_statement = f"The reported magnitude or increase is {clean_val}."
                else:
                    quantitative_statement = f"The reported magnitude or increase is approximately {clean_val}."
                break

        # Step 5: Core Entity Assertion (Strip secondary clauses to isolate primary predicate)
        core_statement = candidate_core_statement
        if temporal_match:
            for pattern, _ in self.TEMPORAL_PATTERNS:
                core_statement = pattern.sub("", core_statement)
        if quantitative_match:
            for pattern in self.QUANTITATIVE_PATTERNS:
                core_statement = pattern.sub("", core_statement)

        # Clean trailing and leading punctuation and whitespace
        core_statement = re.sub(r"\s+", " ", core_statement).strip(" ,;.")
        if core_statement:
            if not core_statement.endswith("."):
                core_statement += "."
            extracted_props.append(
                PropositionItem(
                    id=f"{claim_id}-p{prop_idx}",
                    claim_id=claim_id,
                    text=core_statement[0].upper() + core_statement[1:],
                    proposition_type="ENTITY_ASSERTION" if (causal_driver_text or temporal_statement or quantitative_statement) else "ATOMIC",
                    status="VALID",
                    notes="Primary factual assertion isolated from claim.",
                )
            )
            prop_idx += 1

        # Add Quantitative Proposition if extracted
        if quantitative_statement:
            extracted_props.append(
                PropositionItem(
                    id=f"{claim_id}-p{prop_idx}",
                    claim_id=claim_id,
                    text=quantitative_statement,
                    proposition_type="QUANTITATIVE",
                    status="VALID",
                    notes="Quantitative measurement assertion extracted from claim.",
                )
            )
            prop_idx += 1

        # Add Temporal Proposition if extracted
        if temporal_statement:
            extracted_props.append(
                PropositionItem(
                    id=f"{claim_id}-p{prop_idx}",
                    claim_id=claim_id,
                    text=temporal_statement,
                    proposition_type="TEMPORAL",
                    status="VALID",
                    notes="Temporal baseline or chronological frame extracted from claim.",
                )
            )
            prop_idx += 1

        # Add Causal Proposition if extracted
        if causal_driver_text:
            causal_prop_text = f"{causal_driver_text.capitalize()} caused the reported effect or increase."
            if not causal_prop_text.endswith("."):
                causal_prop_text += "."
            extracted_props.append(
                PropositionItem(
                    id=f"{claim_id}-p{prop_idx}",
                    claim_id=claim_id,
                    text=causal_prop_text,
                    proposition_type="CAUSAL",
                    status="VALID",
                    notes="Causal driver relationship extracted from claim.",
                )
            )
            prop_idx += 1

        # Step 6: Conjunction splitting for multi-clause claims without causal/temporal patterns
        # e.g., "The Earth orbits the Sun, Paris is the capital of France, and water boils at 100°C."
        if len(extracted_props) == 1 and (
            " and " in cleaned_claim or " while " in cleaned_claim or ", " in cleaned_claim
        ):
            parts = re.split(r",?\s+(?:and|while)\s+|,\s*", cleaned_claim, flags=re.IGNORECASE)
            valid_parts = [p.strip().rstrip(".,;") for p in parts if len(p.split()) >= 3]
            if len(valid_parts) >= 2:
                extracted_props = []
                for p_i, part in enumerate(valid_parts, 1):
                    p_text = part
                    if not p_text.endswith("."):
                        p_text += "."
                    extracted_props.append(
                        PropositionItem(
                            id=f"{claim_id}-p{p_i}",
                            claim_id=claim_id,
                            text=p_text[0].upper() + p_text[1:],
                            proposition_type="ATOMIC",
                            status="VALID",
                            notes=f"Conjunctive sub-clause {p_i} extracted from compound statement.",
                        )
                    )

        # Step 7: Fallback to single atomic proposition if no compound sub-clauses
        if not extracted_props:
            extracted_props.append(
                PropositionItem(
                    id=f"{claim_id}-p1",
                    claim_id=claim_id,
                    text=cleaned_claim if cleaned_claim.endswith(".") else f"{cleaned_claim}.",
                    proposition_type="ATOMIC",
                    status="VALID",
                    notes="Atomic single proposition; no compound syntactic boundaries detected.",
                )
            )

        extracted_props = [self._enrich_proposition(p, cleaned_claim) for p in extracted_props]

        status = "COMPLETED" if len(extracted_props) > 1 else "SINGLE_PROPOSITION"
        notes = (
            f"Extracted {len(extracted_props)} factual propositions using rule-based syntactic parsing. "
            "Heuristic decomposition is an analytical aid and does not replace human fact-checker review."
        )

        return ClaimDecompositionResult(
            claim_id=claim_id,
            original_claim=cleaned_claim,
            status=status,
            propositions=extracted_props,
            proposition_coverage=[],
            total_propositions=len(extracted_props),
            supported_propositions_count=0,
            contradicted_propositions_count=0,
            conflicting_propositions_count=0,
            unresolved_propositions_count=len(extracted_props),
            coverage_summary=f"{len(extracted_props)} propositions extracted ({status}). Evidence matching pending.",
            decomposition_notes=notes,
        )

