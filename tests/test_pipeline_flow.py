"""
Test the end-to-end VerificationPipeline on the local repository.
STRICTLY READ-ONLY against the database.
"""
import json
import os
from pathlib import Path
import sys

# Ensure root is on path independently of working directory
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.schemas.claim import ClaimRequest
from backend.services.verification import VerificationPipeline

def run_tests():
    pipeline = VerificationPipeline()

    # Test 1: Random unsupported claim
    claim1 = "Bananas are purple and grow underwater."
    print(f"\n=== Test 1: Unsupported Claim: '{claim1}' ===")
    req1 = ClaimRequest(claim=claim1)
    res1 = pipeline.verify_claim(req1)
    print(f"Verdict: {res1.verdict_assessment.verdict}")
    print(f"Justification: {res1.verdict_assessment.justification}")
    print(f"Independent sources count: {res1.verdict_assessment.independent_sources_count}")
    print(f"Evidence retrieved: {len(res1.evidence)}")
    assert res1.verdict_assessment.verdict == "UNVERIFIED", f"Expected UNVERIFIED, got {res1.verdict_assessment.verdict}"
    print("PASS: Unsupported claim correctly returned UNVERIFIED.")

    # Test 2: Target claim
    claim2 = "Undocumented immigrant workers are entitled to minimum wage under the Fair Labor Standards Act."
    print(f"\n=== Test 2: Target Claim: '{claim2}' ===")
    req2 = ClaimRequest(claim=claim2)
    res2 = pipeline.verify_claim(req2)
    print(f"Verdict: {res2.verdict_assessment.verdict}")
    print(f"Justification: {res2.verdict_assessment.justification}")
    print(f"Independent sources count: {res2.verdict_assessment.independent_sources_count}")
    print(f"Evidence retrieved: {len(res2.evidence)}")
    for i, ev in enumerate(res2.evidence):
        print(f"  [{i+1}] {ev.id} | verified={ev.is_verified} | stance={ev.stance} | tier={ev.source_tier}")
        print(f"      Title: {ev.title}")
        print(f"      URL: {ev.url or ev.canonical_url}")
    if res2.decomposition:
        print(f"Propositions: {len(res2.decomposition.propositions)}")

    # Since neither DOL nor Lucas is verified yet (both is_verified=False),
    # the verdict engine MUST return UNVERIFIED.
    assert res2.verdict_assessment.verdict == "UNVERIFIED", f"Expected UNVERIFIED for uncurated evidence, got {res2.verdict_assessment.verdict}"
    print("PASS: Target claim correctly returned UNVERIFIED because candidate sources are not yet human-verified.")

if __name__ == "__main__":
    run_tests()
