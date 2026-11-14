"""Evidence-to-Proposition Matching and Coverage Service for VERITAS.

Responsible for:
1. Associating retrieved evidence records with individual decomposed propositions.
2. Evaluating proposition-level relevance, polarity, and stance without confusing topic overlap with proof.
3. Calculating granular evidence coverage metrics (SUPPORTED, CONTRADICTED, CONFLICTING, NO_EVIDENCE, UNRESOLVED).
4. Enforcing strict scientific boundaries: coverage metrics are NOT converted into truth verdicts.
"""

import re
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from backend.schemas.claim import (
    ClaimDecompositionResult,
    EvidenceItem,
    PropositionCoverage,
    PropositionEvidenceMatch,
    PropositionItem,
)
from backend.services.relevance_engine import EvidenceRelevanceEngine

if TYPE_CHECKING:
    from backend.services.source_relationship_engine import PropositionCorroborationEngine


class PropositionMatcherService:
    """Matches evidence items to individual propositions and calculates coverage metrics."""

    def __init__(
        self,
        relevance_engine: Optional[EvidenceRelevanceEngine] = None,
        corroboration_engine: Optional["PropositionCorroborationEngine"] = None,
    ):
        self.relevance_engine = relevance_engine or EvidenceRelevanceEngine()
        self.corroboration_engine = corroboration_engine

    def match_propositions(
        self,
        decomposition: ClaimDecompositionResult,
        evidence_items: List[EvidenceItem],
    ) -> ClaimDecompositionResult:
        """Evaluate evidence coverage and matching for all propositions in a claim.

        Reliability Rules:
        - Do not treat general topical similarity as proof of a specific proposition.
        - Preserve full provenance, text availability, and verification status for every match.
        - Do not convert a coverage score into a truth verdict.
        """
        if not decomposition.propositions:
            return decomposition

        coverage_list: List[PropositionCoverage] = []
        verified_supported_count = 0
        verified_contradicted_count = 0
        unverified_supporting_count = 0
        unverified_contradicting_count = 0
        supported_count = 0
        contradicted_count = 0
        conflicting_count = 0
        unresolved_count = 0

        for prop in decomposition.propositions:
            # If proposition was flagged as ambiguous / needs review
            if prop.status == "NEEDS_REVIEW":
                cov = PropositionCoverage(
                    proposition_id=prop.id,
                    proposition_text=prop.text,
                    proposition_type=prop.proposition_type,
                    coverage_status="UNRESOLVED",
                    supporting_count=0,
                    contradicting_count=0,
                    neutral_count=0,
                    verified_supporting_count=0,
                    verified_contradicting_count=0,
                    matches=[],
                    notes="Proposition is ambiguous or subjective; automated evidence matching suspended.",
                )
                coverage_list.append(cov)
                unresolved_count += 1
                continue

            matches_for_prop: List[PropositionEvidenceMatch] = []
            prop_supp = 0
            prop_cont = 0
            prop_neut = 0
            prop_v_supp = 0
            prop_v_cont = 0

            for ev in evidence_items:
                # 1. Rule: Citation metadata-only records cannot evaluate propositional stance
                if ev.text_availability == "METADATA_ONLY" or not ev.snippet:
                    match_record = PropositionEvidenceMatch(
                        proposition_id=prop.id,
                        proposition_text=prop.text,
                        evidence_id=ev.id,
                        evidence_title=ev.title,
                        relevance_status="UNDETERMINED",
                        relevance_score=0.0,
                        stance="NEUTRAL",
                        explanation=(
                            f"Metadata-only record: full text and abstract unindexed. Cannot substantiate "
                            f"specific assertion '{prop.text[:40]}...' without empirical findings."
                        ),
                        source_url=ev.canonical_url or ev.url,
                        publisher=ev.canonical_publisher or ev.publisher,
                        source_tier=ev.source_tier,
                        source_type=ev.source_type,
                        text_availability=ev.text_availability,
                        is_verified=ev.is_verified,
                    )
                    matches_for_prop.append(match_record)
                    prop_neut += 1
                    continue

                # 2. Proposition-specific relevance evaluation
                prop_tokens = self.relevance_engine.extract_content_tokens(prop.text)
                ev_tokens = self.relevance_engine.extract_content_tokens(ev.snippet)
                overlap = prop_tokens.intersection(ev_tokens)
                overlap_ratio = len(overlap) / max(1, len(prop_tokens))

                # Special check for Quantitative propositions: must explicitly mention key numbers/units
                if prop.proposition_type == "QUANTITATIVE":
                    numbers_in_prop = set(n for n in prop.text.split() if any(c.isdigit() for c in n))
                    has_matching_number = any(n.strip(".,;:°%C") in ev.snippet for n in numbers_in_prop if len(n.strip(".,;:°%C")) > 0)
                    if not has_matching_number:
                        # Evidence discusses the general topic, but does NOT corroborate the specific quantitative number!
                        match_record = PropositionEvidenceMatch(
                            proposition_id=prop.id,
                            proposition_text=prop.text,
                            evidence_id=ev.id,
                            evidence_title=ev.title,
                            relevance_status="OFF_TOPIC",
                            relevance_score=round(overlap_ratio * 0.5, 3),
                            stance="NEUTRAL",
                            explanation=(
                                f"Topic alignment on general concepts, but evidence does NOT contain the specific "
                                f"quantitative figure asserted ({', '.join(numbers_in_prop)}). Stance retained as NEUTRAL."
                            ),
                            source_url=ev.canonical_url or ev.url,
                            publisher=ev.canonical_publisher or ev.publisher,
                            source_tier=ev.source_tier,
                            source_type=ev.source_type,
                            text_availability=ev.text_availability,
                            is_verified=ev.is_verified,
                        )
                        matches_for_prop.append(match_record)
                        prop_neut += 1
                        continue

                # Special check for Temporal propositions: must reference specific year or baseline
                if prop.proposition_type == "TEMPORAL":
                    years_in_prop = re.findall(r"\b\d{4}\b", prop.text)
                    if years_in_prop:
                        has_matching_year = any(y in ev.snippet for y in years_in_prop)
                        if not has_matching_year:
                            match_record = PropositionEvidenceMatch(
                                proposition_id=prop.id,
                                proposition_text=prop.text,
                                evidence_id=ev.id,
                                evidence_title=ev.title,
                                relevance_status="OFF_TOPIC",
                                relevance_score=round(overlap_ratio * 0.5, 3),
                                stance="NEUTRAL",
                                explanation=(
                                    f"Evidence discusses related concepts, but does not reference the specific "
                                    f"chronological year or baseline timeframe asserted ({', '.join(years_in_prop)}). "
                                    "Stance retained as NEUTRAL."
                                ),
                                source_url=ev.canonical_url or ev.url,
                                publisher=ev.canonical_publisher or ev.publisher,
                                source_tier=ev.source_tier,
                                source_type=ev.source_type,
                                text_availability=ev.text_availability,
                                is_verified=ev.is_verified,
                            )
                            matches_for_prop.append(match_record)
                            prop_neut += 1
                            continue

                # Special check for Causal propositions: must discuss causal attribution
                if prop.proposition_type == "CAUSAL":
                    causal_tokens = {"caused", "cause", "driver", "driven", "resulting", "due", "human", "anthropogenic", "activity"}
                    has_causal_concept = any(t in ev.snippet.lower() for t in causal_tokens)
                    if not has_causal_concept:
                        match_record = PropositionEvidenceMatch(
                            proposition_id=prop.id,
                            proposition_text=prop.text,
                            evidence_id=ev.id,
                            evidence_title=ev.title,
                            relevance_status="OFF_TOPIC",
                            relevance_score=round(overlap_ratio * 0.5, 3),
                            stance="NEUTRAL",
                            explanation=(
                                "Evidence discusses the observed phenomenon, but does not present observational data "
                                "or attribution regarding the causal driver relationship."
                            ),
                            source_url=ev.canonical_url or ev.url,
                            publisher=ev.canonical_publisher or ev.publisher,
                            source_tier=ev.source_tier,
                            source_type=ev.source_type,
                            text_availability=ev.text_availability,
                            is_verified=ev.is_verified,
                        )
                        matches_for_prop.append(match_record)
                        prop_neut += 1
                        continue

                # General relevance check against proposition
                is_rel = overlap_ratio >= 0.20 or len(overlap) >= 2
                if not is_rel:
                    match_record = PropositionEvidenceMatch(
                        proposition_id=prop.id,
                        proposition_text=prop.text,
                        evidence_id=ev.id,
                        evidence_title=ev.title,
                        relevance_status="IRRELEVANT",
                        relevance_score=round(overlap_ratio, 3),
                        stance="NEUTRAL",
                        explanation=f"Insufficient lexical overlap ({overlap_ratio:.0%}) with proposition '{prop.text[:40]}...'.",
                        source_url=ev.canonical_url or ev.url,
                        publisher=ev.canonical_publisher or ev.publisher,
                        source_tier=ev.source_tier,
                        source_type=ev.source_type,
                        text_availability=ev.text_availability,
                        is_verified=ev.is_verified,
                    )
                    matches_for_prop.append(match_record)
                    continue

                # Evaluate stance using EvidenceRelevanceEngine logic for this specific proposition
                assessed_prop_item = self.relevance_engine.assess_item(claim=prop.text, item=ev)
                
                # Check for verified source status
                if assessed_prop_item.stance == "SUPPORTING":
                    prop_supp += 1
                    if ev.is_verified:
                        prop_v_supp += 1
                elif assessed_prop_item.stance == "CONTRADICTING":
                    prop_cont += 1
                    if ev.is_verified:
                        prop_v_cont += 1
                else:
                    prop_neut += 1

                match_record = PropositionEvidenceMatch(
                    proposition_id=prop.id,
                    proposition_text=prop.text,
                    evidence_id=ev.id,
                    evidence_title=ev.title,
                    relevance_status=assessed_prop_item.relevance_status,
                    relevance_score=assessed_prop_item.relevance_score,
                    stance=assessed_prop_item.stance,
                    explanation=assessed_prop_item.stance_justification or assessed_prop_item.relevance_justification or "Evaluated against proposition.",
                    source_url=ev.canonical_url or ev.url,
                    publisher=ev.canonical_publisher or ev.publisher,
                    source_tier=ev.source_tier,
                    source_type=ev.source_type,
                    text_availability=ev.text_availability,
                    is_verified=ev.is_verified,
                )
                matches_for_prop.append(match_record)

            # If corroboration engine is connected, evaluate Two-Key Gate and authority clusters
            if self.corroboration_engine:
                candidate_evidence = []
                for ev in evidence_items:
                    match_m = next((m for m in matches_for_prop if m.evidence_id == ev.id), None)
                    if match_m and match_m.relevance_status not in ("IRRELEVANT", "OFF_TOPIC"):
                        item_dict = ev.model_dump() if hasattr(ev, "model_dump") else dict(ev)
                        item_dict["stance"] = match_m.stance
                        candidate_evidence.append(item_dict)

                prop_key = getattr(prop, "canonical_id", None) or getattr(prop, "canonical_proposition_hash", None) or prop.id
                assessment = self.corroboration_engine.evaluate_proposition_corroboration(
                    proposition_id=prop_key,
                    candidate_evidence=candidate_evidence,
                    temporal_scope=getattr(prop, "temporal_scope", None) or "PRESENT_OPERATIONAL",
                    reference_period_start=getattr(prop, "reference_period_start", None),
                    reference_period_end=getattr(prop, "reference_period_end", None),
                    temporal_quantification=getattr(prop, "temporal_quantification", None) or "INTERSECTING",
                    proposition_domain=getattr(prop, "domain", None) or "LEGAL",
                )
                cov_status = assessment.coverage_status
                cov_note = assessment.diagnostic_notes or f"Two-Key Gate evaluated: {cov_status}."
                auth_clusters_count = assessment.independent_clusters_count
                v_indep_pairs = assessment.verified_independent_pairs_count
                has_two_indep = assessment.has_two_independent_sources
                indep_corrob = assessment.has_two_independent_sources
                cluster_stances = [c.cluster_stance for c in assessment.clusters]
                cluster_details = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in assessment.clusters]

                if cov_status == "VERIFIED_SUPPORTED":
                    verified_supported_count += 1
                    supported_count += 1
                elif cov_status == "VERIFIED_CONTRADICTED":
                    verified_contradicted_count += 1
                    contradicted_count += 1
                elif cov_status == "UNVERIFIED_MATCH_SUPPORTING":
                    unverified_supporting_count += 1
                    supported_count += 1
                elif cov_status == "UNVERIFIED_MATCH_CONTRADICTING":
                    unverified_contradicting_count += 1
                    contradicted_count += 1
                elif cov_status == "CONFLICTING":
                    conflicting_count += 1
                else:
                    unresolved_count += 1
            else:
                auth_clusters_count = 0
                v_indep_pairs = 0
                has_two_indep = False
                indep_corrob = False
                cluster_stances = []
                cluster_details = []

                # Determine coverage status for this proposition with explicit separation of verified vs unverified matches
                if not matches_for_prop or all(m.relevance_status in ("IRRELEVANT", "OFF_TOPIC") for m in matches_for_prop):
                    cov_status = "NO_EVIDENCE"
                    cov_note = "No usable or relevant evidence items match this specific proposition."
                    unresolved_count += 1
                elif prop_supp > 0 and prop_cont > 0:
                    cov_status = "CONFLICTING"
                    cov_note = f"Conflicting evidence: {prop_supp} supporting ({prop_v_supp} verified) vs {prop_cont} contradicting ({prop_v_cont} verified)."
                    conflicting_count += 1
                elif prop_supp > 0 and prop_cont == 0:
                    if prop_v_supp >= 2:
                        cov_status = "VERIFIED_SUPPORTED"
                        cov_note = f"Independently verified: corroborated by {prop_v_supp} verified independent sources ({prop_supp} total supporting literature records)."
                        verified_supported_count += 1
                    else:
                        cov_status = "UNVERIFIED_MATCH_SUPPORTING"
                        cov_note = (
                            f"Textual literature match: {prop_supp} supporting records ({prop_v_supp} verified). "
                            "Fails the 2-independent-verified-source requirement; cannot be presented as verified fact."
                        )
                        unverified_supporting_count += 1
                    supported_count += 1
                elif prop_cont > 0 and prop_supp == 0:
                    if prop_v_cont >= 2:
                        cov_status = "VERIFIED_CONTRADICTED"
                        cov_note = f"Independently verified contradiction: contradicted by {prop_v_cont} verified independent sources ({prop_cont} total contradicting literature records)."
                        verified_contradicted_count += 1
                    else:
                        cov_status = "UNVERIFIED_MATCH_CONTRADICTING"
                        cov_note = (
                            f"Textual literature dispute: {prop_cont} contradicting records ({prop_v_cont} verified). "
                            "Fails the 2-independent-verified-source requirement; cannot be presented as verified contradiction."
                        )
                        unverified_contradicting_count += 1
                    contradicted_count += 1
                else:
                    cov_status = "UNRESOLVED"
                    cov_note = "Available evidence items discuss the subject descriptively or contextually without establishing stance."
                    unresolved_count += 1

            cov = PropositionCoverage(
                proposition_id=prop.id,
                proposition_text=prop.text,
                proposition_type=prop.proposition_type,
                coverage_status=cov_status,
                supporting_count=prop_supp,
                contradicting_count=prop_cont,
                neutral_count=prop_neut,
                verified_supporting_count=prop_v_supp,
                verified_contradicting_count=prop_v_cont,
                unverified_supporting_count=prop_supp - prop_v_supp,
                unverified_contradicting_count=prop_cont - prop_v_cont,
                matches=matches_for_prop,
                independent_corroboration=indep_corrob,
                authority_clusters_count=auth_clusters_count,
                cluster_stances=cluster_stances,
                cluster_details=cluster_details,
                verified_independent_pairs_count=v_indep_pairs,
                has_two_independent_sources=has_two_indep,
                diagnostic_notes=cov_note,
                notes=cov_note,
            )
            coverage_list.append(cov)

        decomposition.proposition_coverage = coverage_list
        decomposition.total_propositions = len(coverage_list)
        decomposition.verified_supported_count = verified_supported_count
        decomposition.verified_contradicted_count = verified_contradicted_count
        decomposition.unverified_supporting_count = unverified_supporting_count
        decomposition.unverified_contradicting_count = unverified_contradicting_count
        decomposition.supported_propositions_count = supported_count
        decomposition.contradicted_propositions_count = contradicted_count
        decomposition.conflicting_propositions_count = conflicting_count
        decomposition.unresolved_propositions_count = unresolved_count

        summary_msg = (
            f"{len(coverage_list)} propositions evaluated: {verified_supported_count} verified supported, "
            f"{unverified_supporting_count} unverified literature matches, "
            f"{verified_contradicted_count} verified contradicted, "
            f"{unverified_contradicting_count} unverified literature disputes, "
            f"{conflicting_count} conflicting, {unresolved_count} unresolved / no evidence."
        )
        decomposition.coverage_summary = summary_msg

        return decomposition

