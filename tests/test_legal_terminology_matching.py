"""Regression and Negative Test Suite for Legal Terminology Matching in RelevanceEngine.

Verifies:
1. Bidirectional concept mapping for legal and statutory terminology:
   - undocumented <-> unauthorized
   - immigrant / immigrants <-> alien / aliens (with domain-mismatch protection)
   - minimum wage <-> FLSA Section 206(a)
   - wages <-> statutory minimum wage / damages
   - workers <-> work / employees
2. Regression: Lucas v. Jerusalem Cafe (721 F.3d 927) is assessed as RELEVANT (score >= 0.25)
   and successfully retrieved by EvidenceRetrievalService for the target claim:
   "Undocumented immigrant workers are entitled to minimum wage under the Fair Labor Standards Act."
3. Negative Tests:
   - General criminal justice / incarceration records remain strictly IRRELEVANT (Texas DPS, NBER)
   - Planetary / astronomical records remain strictly IRRELEVANT (JPL DE440 ephemeris)
   - Extraterrestrial "alien" search papers remain strictly IRRELEVANT (SETI / exoplanetary biosignatures)
   - Extraterrestrial claims do not match human immigration/statutory labor documents
4. Pipeline Safety: Target claim produces honest UNVERIFIED verdict with unreviewed sources.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.schemas.claim import EvidenceItem, ClaimRequest
from backend.services.evidence_retrieval import EvidenceRetrievalService
from backend.services.relevance_engine import EvidenceRelevanceEngine, CONCEPT_EQUIVALENTS
from backend.services.verification import VerificationPipeline


TARGET_CLAIM = "Undocumented immigrant workers are entitled to minimum wage under the Fair Labor Standards Act."


def test_token_extraction_and_bad_chars():
    print("\n[TEST 1] Token Extraction & Legal Symbol Cleansing...")
    engine = EvidenceRelevanceEngine()
    snippet = "FLSA, 29 U.S.C. §§ 206(a), 207(a), 216(b), statutory damages"
    tokens = engine.extract_content_tokens(snippet)
    assert "§§" not in tokens, "Section symbol '§§' should be stripped from tokens"
    assert "206a" in tokens, "'206a' should be cleanly extracted"
    assert "207a" in tokens, "'207a' should be cleanly extracted"
    assert "216b" in tokens, "'216b' should be cleanly extracted"
    assert "statutory" in tokens, "'statutory' should be extracted"
    assert "damages" in tokens, "'damages' should be extracted"
    print("  [PASS] Token extraction cleans legal section symbols and extracts statutory provisions.")


def test_concept_equivalents_structure():
    print("\n[TEST 2] Legal Concept Equivalents Mappings...")
    assert "unauthorized" in CONCEPT_EQUIVALENTS.get("undocumented", set())
    assert "undocumented" in CONCEPT_EQUIVALENTS.get("unauthorized", set())
    assert "aliens" in CONCEPT_EQUIVALENTS.get("immigrant", set())
    assert "alien" in CONCEPT_EQUIVALENTS.get("immigrants", set())
    assert "immigrant" in CONCEPT_EQUIVALENTS.get("alien", set())
    assert "206a" in CONCEPT_EQUIVALENTS.get("wage", set())
    assert "wage" in CONCEPT_EQUIVALENTS.get("206a", set())
    assert "work" in CONCEPT_EQUIVALENTS.get("workers", set())
    assert "flsa" in CONCEPT_EQUIVALENTS.get("standards", set())
    print("  [PASS] Bidirectional legal concept mappings confirmed.")


def test_lucas_relevance_regression():
    print("\n[TEST 3] Lucas Decision Relevance Regression...")
    engine = EvidenceRelevanceEngine()
    lucas_item = EvidenceItem(
        id="ca8-lucas-v-jerusalem-cafe-721-f3d-927",
        title="Lucas v. Jerusalem Cafe, LLC, 721 F.3d 927 (8th Cir. 2013)",
        snippet="For these reasons, we hold that unauthorized aliens may sue under the FLSA, 29 U.S.C. §§ 206(a), 207(a), 216(b), to recover statutory damages for work actually performed.",
        source_tier="TIER_1",
        text_availability="EXCERPT",
        is_verified=False,
        curation_status="UNREVIEWED",
        stance="NEUTRAL",
    )
    assessed = engine.assess_item(TARGET_CLAIM, lucas_item)
    print(f"  Lucas Status: {assessed.relevance_status}")
    print(f"  Lucas Score: {assessed.relevance_score}")
    print(f"  Lucas Justification: {assessed.relevance_justification}")
    print(f"  Lucas Stance: {assessed.stance}")

    assert assessed.relevance_status == "RELEVANT", f"Expected RELEVANT, got {assessed.relevance_status}"
    assert assessed.relevance_score >= 0.25, f"Expected score >= 0.25, got {assessed.relevance_score}"
    assert assessed.relevance_score >= 0.6, f"Expected score >= 0.6 with full legal mappings, got {assessed.relevance_score}"
    assert assessed.stance == "NEUTRAL", f"Expected NEUTRAL stance without curation, got {assessed.stance}"
    print("  [PASS] Lucas decision achieves RELEVANT status with score >= 0.6.")


def test_retrieval_service_includes_both_sources():
    print("\n[TEST 4] Evidence Retrieval Service Candidate Ingestion...")
    service = EvidenceRetrievalService()
    candidates = service.retrieve_evidence(TARGET_CLAIM)

    candidate_ids = {c.id for c in candidates}
    print(f"  Retrieved candidate IDs: {candidate_ids}")

    assert "ca8-lucas-v-jerusalem-cafe-721-f3d-927" in candidate_ids, "Lucas must be present in retrieved candidates"
    assert "dol-whd-factsheet-48-immigrant-workers" in candidate_ids, "DOL Fact Sheet #48 must be present in retrieved candidates"

    # Confirm both remain unverified
    for item in candidates:
        if item.id in ("ca8-lucas-v-jerusalem-cafe-721-f3d-927", "dol-whd-factsheet-48-immigrant-workers"):
            assert item.is_verified is False, f"Item {item.id} must remain unverified"
            assert item.relevance_status == "RELEVANT", f"Item {item.id} must be RELEVANT"

    print("  [PASS] Both DOL Fact Sheet #48 and Lucas decision retrieved and assessed RELEVANT.")


def test_negative_crime_and_incarceration():
    print("\n[TEST 5] Negative Tests: Unrelated Criminal Justice / Incarceration Records...")
    engine = EvidenceRelevanceEngine()

    # Texas DPS Crime Report
    texas_dps = EvidenceItem(
        id="cato-texas-dps-crime-rates",
        title="Comparing Crime Rates Between Undocumented Immigrants, Legal Immigrants, and Native-Born Citizens in Texas",
        snippet="Longitudinal analysis of Texas Department of Public Safety (DPS) arrest and conviction records. Findings confirm that undocumented immigrants have lower felony conviction rates.",
        source_tier="TIER_1",
        text_availability="EXCERPT",
        is_verified=False,
        curation_status="UNREVIEWED",
        stance="NEUTRAL",
    )
    assessed_dps = engine.assess_item(TARGET_CLAIM, texas_dps)
    print(f"  Texas DPS Status: {assessed_dps.relevance_status} | Score: {assessed_dps.relevance_score}")
    assert assessed_dps.relevance_status == "IRRELEVANT", f"Texas DPS must be IRRELEVANT, got {assessed_dps.relevance_status}"
    assert assessed_dps.relevance_score == 0.0, f"Expected 0.0 score, got {assessed_dps.relevance_score}"

    # NBER Incarceration Gap
    nber = EvidenceItem(
        id="nber-w31422-immigrant-crime",
        title="Law-Abiding Immigrants: The Incarceration Gap Over 150 Years",
        snippet="Stanford University and NBER empirical demographic analysis of U.S. Census microdata from 1870 to 2020. The study demonstrates that immigrant men are 60% less likely to be incarcerated than native-born citizens. This incarceration gap has widened steadily since 1960.",
        source_tier="TIER_1",
        text_availability="EXCERPT",
        is_verified=False,
        curation_status="UNREVIEWED",
        stance="NEUTRAL",
    )
    assessed_nber = engine.assess_item(TARGET_CLAIM, nber)
    print(f"  NBER Status: {assessed_nber.relevance_status} | Score: {assessed_nber.relevance_score}")
    assert assessed_nber.relevance_status == "IRRELEVANT", f"NBER must be IRRELEVANT, got {assessed_nber.relevance_status}"
    print("  [PASS] Unrelated criminal justice and incarceration records strictly marked IRRELEVANT.")


def test_negative_extraterrestrial_and_astronomy():
    print("\n[TEST 6] Negative Tests: Extraterrestrial 'Alien' and Astronomical Records...")
    engine = EvidenceRelevanceEngine()

    # JPL Ephemeris
    ephemeris = EvidenceItem(
        id="de440-jpl-planetary-ephemeris",
        title="The Planetary and Lunar Ephemerides DE440 and DE441",
        snippet="High-precision dynamical ephemerides for the Moon and major planets created by numerical integration.",
        source_tier="TIER_1",
        text_availability="EXCERPT",
        is_verified=False,
        curation_status="UNREVIEWED",
        stance="NEUTRAL",
    )
    assessed_eph = engine.assess_item(TARGET_CLAIM, ephemeris)
    print(f"  Ephemeris Status: {assessed_eph.relevance_status} | Score: {assessed_eph.relevance_score}")
    assert assessed_eph.relevance_status == "IRRELEVANT"
    assert assessed_eph.relevance_score == 0.0

    # Extraterrestrial "Alien" Biosignature Paper (High overlap with words: alien, standards, act)
    seti = EvidenceItem(
        id="seti-alien-standards-exoplanet",
        title="Search for Alien Life: Methodological Standards and Act of Astrobiology",
        snippet="Spectroscopic search for extraterrestrial aliens, technosignatures, and atmospheric biosignatures in nearby exoplanets adhering to astrobiology observation standards and the Space Act.",
        source_tier="TIER_1",
        text_availability="EXCERPT",
        is_verified=False,
        curation_status="UNREVIEWED",
        stance="NEUTRAL",
    )
    assessed_seti = engine.assess_item(TARGET_CLAIM, seti)
    print(f"  SETI/Alien Status: {assessed_seti.relevance_status} | Score: {assessed_seti.relevance_score}")
    print(f"  SETI Justification: {assessed_seti.relevance_justification}")
    assert assessed_seti.relevance_status == "IRRELEVANT"
    assert assessed_seti.relevance_score == 0.0
    assert "Domain mismatch" in assessed_seti.relevance_justification

    # Reverse: Extraterrestrial claim evaluated against human labor/immigration evidence
    et_claim = "Extraterrestrial alien life has been confirmed under statutory observational FLSA standards."
    lucas_item = EvidenceItem(
        id="ca8-lucas-v-jerusalem-cafe-721-f3d-927",
        title="Lucas v. Jerusalem Cafe, LLC, 721 F.3d 927 (8th Cir. 2013)",
        snippet="For these reasons, we hold that unauthorized aliens may sue under the FLSA, 29 U.S.C. §§ 206(a), 207(a), 216(b), to recover statutory damages for work actually performed.",
        source_tier="TIER_1",
        text_availability="EXCERPT",
        is_verified=False,
        curation_status="UNREVIEWED",
        stance="NEUTRAL",
    )
    assessed_et = engine.assess_item(et_claim, lucas_item)
    print(f"  ET Claim against Lucas Status: {assessed_et.relevance_status} | Score: {assessed_et.relevance_score}")
    print(f"  ET Claim Justification: {assessed_et.relevance_justification}")
    assert assessed_et.relevance_status == "IRRELEVANT"
    assert assessed_et.relevance_score == 0.0
    assert "Domain mismatch" in assessed_et.relevance_justification
    print("  [PASS] Extraterrestrial / astronomical documents and claims strictly isolated via domain guards.")


def test_pipeline_verdict_integrity():
    print("\n[TEST 7] Pipeline Verdict Integrity...")
    pipeline = VerificationPipeline()
    req = ClaimRequest(claim=TARGET_CLAIM)
    res = pipeline.verify_claim(req)

    print(f"  Verdict: {res.verdict_assessment.verdict}")
    print(f"  Justification: {res.verdict_assessment.justification}")
    print(f"  Evidence count: {len(res.evidence)}")

    assert res.verdict_assessment.verdict == "UNVERIFIED", (
        f"Verdict must remain UNVERIFIED because candidate sources are not yet verified. Got: {res.verdict_assessment.verdict}"
    )
    assert not res.verdict_assessment.has_sufficient_evidence, "Must report insufficient verified evidence"

    # Confirm both target sources are in response evidence
    response_ids = {e.id for e in res.evidence}
    assert "ca8-lucas-v-jerusalem-cafe-721-f3d-927" in response_ids
    assert "dol-whd-factsheet-48-immigrant-workers" in response_ids
    print("  [PASS] Honest UNVERIFIED verdict generated with full evidence transparency.")


def main():
    print("=" * 75)
    print("VERITAS LEGAL TERMINOLOGY MATCHING & DOMAIN ISOLATION REGRESSION SUITE")
    print("=" * 75)
    test_token_extraction_and_bad_chars()
    test_concept_equivalents_structure()
    test_lucas_relevance_regression()
    test_retrieval_service_includes_both_sources()
    test_negative_crime_and_incarceration()
    test_negative_extraterrestrial_and_astronomy()
    test_pipeline_verdict_integrity()
    print("\n" + "=" * 75)
    print("ALL 7 REGRESSION & NEGATIVE TESTS PASSED SUCCESSFULLY!")
    print("=" * 75)


if __name__ == "__main__":
    main()
