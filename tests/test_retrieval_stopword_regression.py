"""Regression test suite for VERITAS Evidence Retrieval and FTS5 Stopword Filtering.

Verifies:
1. FTS5 query sanitization of "The Earth revolves around the Sun." excludes stopwords ("The", "around", "the").
2. High-frequency grammatical stopwords are strictly prevented from generating wildcard OR terms.
3. Empty and stopword-only queries fail closed and return empty results safely.
4. Astronomical queries do not retrieve unrelated photosynthesis, labor, or immigration records.
5. Multilingual concept mapping and query behavior are preserved across languages.
6. Legitimate short terms and legal citations continue to be indexed and retrieved.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.schemas.claim import EvidenceItem
from backend.services.evidence_repository import EvidenceRepository, FTS_STOPWORDS
from backend.services.evidence_retrieval import EvidenceRetrievalService
from backend.services.relevance_engine import STOPWORDS


class TestRetrievalStopwordRegression(unittest.TestCase):
    """Test suite for retrieval fallback logic and FTS5 stopword sanitization."""

    @classmethod
    def setUpClass(cls):
        cls.repository = EvidenceRepository()
        cls.retrieval_service = EvidenceRetrievalService(repository=cls.repository)

    def test_01_sanitization_of_earth_revolves_sun(self):
        """Test 1: Sanitization of 'The Earth revolves around the Sun.' excludes stopwords."""
        raw_query = "The Earth revolves around the Sun."
        sanitized = EvidenceRepository.sanitize_fts_query(raw_query)

        # Expected: '"Earth"* OR "revolves"* OR "Sun"*'
        self.assertEqual(sanitized, '"Earth"* OR "revolves"* OR "Sun"*')

        # Strictly verify that common stopwords are not present in wildcard terms
        self.assertNotIn('"The"*', sanitized)
        self.assertNotIn('"the"*', sanitized)
        self.assertNotIn('"around"*', sanitized)

    def test_02_stopwords_excluded_from_wildcards(self):
        """Test 2: High-frequency grammatical stopwords do not generate wildcard OR matches."""
        target_stopwords = [
            "the", "a", "an", "around", "of", "to", "and", "or", "is",
            "in", "on", "at", "by", "for", "with", "about", "against"
        ]
        for sw in target_stopwords:
            self.assertIn(sw, FTS_STOPWORDS, f"Stopword '{sw}' must be in FTS_STOPWORDS")
            sanitized = EvidenceRepository.sanitize_fts_query(sw)
            self.assertEqual(sanitized, "", f"Single stopword '{sw}' must produce empty sanitized FTS string")

        # Test composite stopword query
        composite = "The a an around of to and or is in on at by for with"
        self.assertEqual(EvidenceRepository.sanitize_fts_query(composite), "")

    def test_03_empty_and_stopword_only_queries_fail_closed(self):
        """Test 3: Empty and stopword-only queries safely return empty results."""
        # Empty string
        self.assertEqual(EvidenceRepository.sanitize_fts_query(""), "")
        self.assertEqual(EvidenceRepository.sanitize_fts_query("   "), "")
        self.assertEqual(self.repository.search_evidence(""), [])
        self.assertEqual(self.repository.search_evidence("   "), [])

        # Stopword-only queries
        stopword_query = "The of and around is a an or to"
        self.assertEqual(EvidenceRepository.sanitize_fts_query(stopword_query), "")
        results = self.repository.search_evidence(stopword_query)
        self.assertEqual(results, [], "Stopword-only query must fail closed and return 0 records")

    def test_04_astronomical_query_does_not_retrieve_unrelated_records(self):
        """Test 4: Astronomical query does not match photosynthesis, immigration, or labor records."""
        query = "The Earth revolves around the Sun."
        results = self.repository.search_evidence(query=query, limit=20)

        retrieved_ids = {item.id for item in results}

        # Unrelated records that must NEVER match merely due to common words like 'the' or 'around'
        prohibited_ids = {
            "flsa-immigrant-coverage-overview",
            "dol-whd-factsheet-48-immigrant-workers",
            "dol-whd-retaliation-guidance-flsa",
            "ca8-lucas-v-jerusalem-cafe-721-f3d-927",
            "us-code-29-usc-215-anti-retaliation",
            "nasem-immigration-fiscal-2017",
            "cato-texas-dps-crime-rates",
            "nber-w31422-immigrant-crime",
            "photosynthesis-light-dependent-reactions",
            "ipcc-ar6-wg1-spm-headline-a1",
        }

        intersection = retrieved_ids.intersection(prohibited_ids)
        self.assertEqual(
            intersection,
            set(),
            f"Astronomical query retrieved prohibited unrelated records: {intersection}"
        )

        # Confirm legitimate astronomical/geodetic records ARE retrieved
        self.assertIn("de440-jpl-planetary-ephemeris", retrieved_ids)

    def test_05_retrieval_service_fallback_logic(self):
        """Test 5: Retrieval service uses meaningful concept/native keywords rather than raw unprocessed claim."""
        claim = "The Earth revolves around the Sun."
        native_q = self.retrieval_service.formulate_native_query(claim)
        concept_q = self.retrieval_service.formulate_concept_mapped_query(claim, language="en")

        # Native query must have stopwords removed
        self.assertEqual(native_q, "earth revolves sun")
        self.assertEqual(concept_q, "earth revolves sun")

        # End-to-end service candidate retrieval
        candidates = self.retrieval_service.retrieve_evidence(claim)
        candidate_ids = {c.id for c in candidates}

        # None of the candidates should be unrelated immigration or photosynthesis records
        for cid in candidate_ids:
            self.assertNotIn("immigrant", cid.lower())
            self.assertNotIn("flsa", cid.lower())
            self.assertNotIn("photosynthesis", cid.lower())

    def test_06_multilingual_stopword_and_concept_behavior(self):
        """Test 6: Multilingual concept mapping and stopword filtering are preserved."""
        # Spanish claim with stopwords
        es_claim = "Los trabajadores indocumentados no pueden denunciar el robo de salario."
        es_native = self.retrieval_service.formulate_native_query(es_claim)
        # Should filter 'los', 'no', 'el', 'de'
        self.assertNotIn("los", es_native.split())
        self.assertNotIn("el", es_native.split())
        self.assertNotIn("de", es_native.split())
        self.assertIn("trabajadores", es_native)
        self.assertIn("salario", es_native)

        # Bengali claim
        bn_claim = "টিকা কি অটিজম সৃষ্টি করে?"
        bn_native = self.retrieval_service.formulate_native_query(bn_claim)
        self.assertIn("টিকা", bn_native)
        self.assertIn("অটিজম", bn_native)

    def test_07_legitimate_searches_preserved(self):
        """Test 7: Legitimate queries with specific keywords and numbers continue to work."""
        legitimate_queries = [
            ("Hoffman Plastics", "dol-whd-factsheet-48-immigrant-workers"),
            ("Jerusalem Cafe", "ca8-lucas-v-jerusalem-cafe-721-f3d-927"),
            ("Planetary Ephemerides", "de440-jpl-planetary-ephemeris"),
            ("altimetry geoid", "jgr-ocean-satellite-geoid-curvature"),
            ("World Geodetic System", "wgs84-tr8350-geodetic-datum"),
        ]
        for query_str, expected_id in legitimate_queries:
            results = self.repository.search_evidence(query=query_str, limit=10)
            result_ids = {r.id for r in results}
            self.assertIn(
                expected_id,
                result_ids,
                f"Legitimate query '{query_str}' failed to retrieve expected record '{expected_id}'"
            )


if __name__ == "__main__":
    unittest.main()
