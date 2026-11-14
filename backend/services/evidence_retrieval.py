"""Evidence Retrieval Service for VERITAS with Local SQLite Repository and Public Providers.

Responsible for discovering, verifying, and indexing primary source documentation,
peer-reviewed records, and background knowledge.

Components:
1. Local SQLite Evidence Repository (sqlite3 + FTS5 full-text search).
2. Zero-cost Public Evidence Providers:
   - OpenAlex (api.openalex.org) - Academic literature and inverted index abstracts.
   - Crossref (api.crossref.org) - Scholarly DOIs, metadata, and abstracts.
   - Wikimedia REST API (en.wikipedia.org) - Background discovery (tertiary tier).

Strict Reliability Rules Enforced:
1. Never invent sources or synthesize fake evidence.
2. Return an empty evidence list when no matching records exist in the repository.
3. An academic paper's existence or abstract alone is NOT proof of truth (is_verified=False).
4. Wikimedia results are strictly tertiary discovery context, not primary corroboration.
5. Do not count syndicated or duplicate records as independent sources.
6. Report provider failures honestly without masking errors.
"""

from datetime import datetime, timezone
import hashlib
import logging
import re
from typing import Dict, List, Optional, Set
import unicodedata
from urllib.parse import urlparse

from backend.config import settings
from backend.schemas.claim import EvidenceItem
from backend.services.evidence_repository import EvidenceRepository
from backend.services.providers.base import BaseEvidenceProvider
from backend.services.providers.crossref import CrossrefProvider
from backend.services.providers.dol_whd import DolWhdProvider
from backend.services.providers.ecfr import EcfrProvider
from backend.services.providers.nasa_ntrs import NasaNtrsProvider
from backend.services.providers.openalex import OpenAlexProvider
from backend.services.providers.pubmed import PubMedProvider
from backend.services.providers.usgs_pubs import UsgsPubsProvider
from backend.services.providers.who_gho import WhoGhoProvider
from backend.services.providers.who_iris import WhoIrisProvider
from backend.services.providers.wikimedia import WikimediaProvider
from backend.services.providers.world_bank import WorldBankProvider
from backend.services.source_registry import get_source_registry, AuthorityClassification, DomainType
from backend.services.relevance_engine import (
    EvidenceRelevanceEngine,
    CONCEPT_EQUIVALENTS,
    STOPWORDS,
)
from backend.services.normalization import compute_text_similarity

logger = logging.getLogger(__name__)


class EvidenceRetrievalService:
    """Service handling multi-source evidence extraction, provenance, and local repository storage."""

    HEALTH_KEYWORDS: Set[str] = {
        # English
        "vaccine", "vaccines", "vaccination", "health", "disease", "diseases",
        "cancer", "infection", "infections", "infectious", "virus", "viral",
        "medical", "hospital", "treatment", "mortality", "drug", "drugs",
        "covid", "cholera", "syndrome", "clinical", "illness", "illnesses",
        # Spanish
        "salud", "vacuna", "vacunas", "vacunación", "enfermedad", "enfermedades",
        "infección", "infecciones", "infecciosa", "infecciosas", "médico", "médica",
        "médicos", "médicas", "sanitario", "sanitaria", "tratamiento", "tratamientos",
        "virus", "hospital", "hospitales",
        # Hindi
        "टीका", "टीके", "टीकाकरण", "संक्रामक", "संक्रमण", "बीमारी", "बीमारियों",
        "रोग", "दवा", "दवाएं", "स्वास्थ्य", "इलाज", "वायरस", "अस्पताल",
        # Bengali
        "টিকা", "টিকাদান", "সংক্রামক", "সংক্রমণ", "রোগ", "অসুখ",
        "স্বাস্থ্য", "চিকিৎসা", "ওষুধ", "ঔষধ", "জীবাণু", "ভাইরাস",
    }

    CLIMATE_KEYWORDS: Set[str] = {
        # English
        "climate", "temperature", "temperatures", "warming", "emissions", "carbon",
        "co2", "atmosphere", "atmospheric", "sea level", "ocean", "oceans",
        "arctic", "ice", "drought", "geology", "earthquake", "flood",
        "water", "weather",
        # Spanish
        "clima", "climático", "climática", "climáticos", "climáticas",
        "calentamiento", "temperatura", "temperaturas", "sequía", "inundación",
        "inundaciones", "emisión", "emisiones", "medioambiente", "planeta",
        "océano", "océanos", "glaciares", "glaciar",
        # Hindi
        "तापमान", "जलवायु", "ग्लोबल", "वार्मिंग", "मौसम", "पर्यावरण",
        "उत्सर्जन", "प्रदूषण", "समुद्र", "बाढ़", "सूखा", "ग्लेशियर",
        # Bengali
        "তাপমাত্রা", "জলবায়ু", "উষ্ণায়ন", "আবহাওয়া", "পরিবেশ",
        "নির্গমন", "বন্যা", "খরা", "সমুদ্রপৃষ্ঠ", "হিমবাহ",
    }

    IMMIGRATION_KEYWORDS: Set[str] = {
        # English
        "immigrant", "immigrants", "immigration", "migrant", "migrants", "migration",
        "border", "asylum", "refugee", "refugees", "deportation", "undocumented",
        "citizens", "incarceration", "crime", "taxes",
        # Spanish
        "inmigrante", "inmigrantes", "inmigración", "migrante", "migrantes", "migración",
        "frontera", "asilo", "refugiado", "refugiados", "deportación", "delincuencia", "impuestos",
        # Hindi
        "प्रवासी", "अप्रवासी", "आव्रजन", "शरणार्थी", "निर्वासन", "कामगार",
        # Bengali
        "অভিবাসী", "প্রবাসী", "অভিবাসন", "শরণার্থী", "বহিষ্কার", "রেমিট্যান্স",
    }

    EMPLOYMENT_KEYWORDS: Set[str] = {
        # English
        "wage", "wages", "salary", "salaries", "overtime", "theft", "paycheck",
        "workplace", "worker", "workers", "employee", "employees", "employer",
        "employers", "labor", "labour", "employment", "minimum wage", "flsa",
        "osha", "subminimum", "working conditions", "retaliate", "retaliation",
        # Spanish
        "salario", "salarios", "sueldo", "sueldos", "robo de salario", "robo",
        "horas extras", "lugar de trabajo", "trabajador", "trabajadores",
        "empleado", "empleados", "empleador", "empleadores", "laboral", "empleo",
        "salario mínimo", "represalia", "represalias",
        # Hindi
        "मजदूरी", "वेतन", "मजदूरी चोरी", "वेतन चोरी", "कार्यस्थल", "ओवरटाइम",
        "श्रमिक", "मजदूर", "कर्मचारी", "नियोक्ता", "श्रम", "रोजगार", "न्यूनतम मजदूरी",
        # Bengali
        "মজুরি", "বেতন", "মজুরি চুরি", "কর্মক্ষেত্র", "ওভারটাইম", "শ্রমিক",
        "কর্মী", "কর্মচারী", "নিয়োগকর্তা", "শ্রম", "কর্মসংস্থান", "ন্যূনতম মজুরি",
    }

    @staticmethod
    def tokenize_unicode_words(text: str) -> List[str]:
        """Extract word tokens from text preserving Unicode letters, numbers, and combining marks (Mn, Mc, Me).

        Unlike [^\\W_]+, which breaks words at nonspacing and combining vowel signs (matras)
        in Devanagari and Bengali, this tokenizer preserves base characters together with
        all associated combining diacritics and signs.
        """
        if not text:
            return []
        tokens: List[str] = []
        current_chars: List[str] = []
        for ch in text.lower():
            cat = unicodedata.category(ch)
            # Letter (L*), Number (N*), or Combining Mark (Mn, Mc, Me)
            if cat.startswith("L") or cat.startswith("N") or cat.startswith("M"):
                current_chars.append(ch)
            else:
                if current_chars:
                    tokens.append("".join(current_chars))
                    current_chars = []
        if current_chars:
            tokens.append("".join(current_chars))
        return tokens

    @classmethod
    def formulate_native_query(cls, text: str) -> str:
        """Extract substantive key concept tokens from text, filtering stopwords and punctuation."""
        if not text:
            return ""
        tokens = [t for t in cls.tokenize_unicode_words(text) if t not in STOPWORDS]
        return " ".join(tokens[:16])

    @classmethod
    def formulate_concept_mapped_query(cls, text: str, language: str = "en") -> str:
        """Formulate targeted concept search query using domain concept mappings across languages.

        Preserves the user's submitted claim unchanged while enabling semantic and
        cross-lingual discovery in literature catalogs and the local evidence repository.
        """
        if not text:
            return ""

        tokens = cls.tokenize_unicode_words(text)
        mapped_concepts: List[str] = []
        for t in tokens:
            if t in CONCEPT_EQUIVALENTS:
                eqs = [e for e in CONCEPT_EQUIVALENTS[t] if any(ord(c) < 128 for c in e)]
                if eqs:
                    mapped_concepts.extend(sorted(eqs, key=len)[:2])
        if mapped_concepts:
            seen: Set[str] = set()
            dedup: List[str] = []
            for m in mapped_concepts:
                if m not in seen and m not in STOPWORDS:
                    seen.add(m)
                    dedup.append(m)
            return " ".join(dedup[:15])
        return cls.formulate_native_query(text)

    @staticmethod
    def _rank_and_deduplicate_evidence(
        records: List[EvidenceItem],
        clean_claim: str,
        relevance_engine: EvidenceRelevanceEngine,
    ) -> List[EvidenceItem]:
        """Rank and deduplicate retrieved evidence candidates.

        Safeguards enforced:
        1. Prioritize records with substantive text availability (ABSTRACT, EXCERPT, FULL_TEXT)
           over METADATA_ONLY citations.
        2. Deduplicate exact duplicate snippet SHA-256 hashes.
        3. Flag and cluster high-similarity (>= 75%) syndicated wire reprints.
        4. Sort by substantive text > relevance status (RELEVANT > UNDETERMINED > IRRELEVANT) > relevance score.
        """
        seen_hashes: Set[str] = set()
        seen_urls: Set[str] = set()
        unique_evaluated: List[EvidenceItem] = []

        for raw_item in records:
            assessed = relevance_engine.assess_item(claim=clean_claim, item=raw_item)

            c_hash = assessed.content_sha256 or hashlib.sha256(assessed.snippet.strip().encode("utf-8")).hexdigest()
            canon_url = (assessed.canonical_url or assessed.url or "").strip().lower()

            if c_hash in seen_hashes:
                continue
            seen_hashes.add(c_hash)

            if canon_url and canon_url in seen_urls:
                continue
            if canon_url:
                seen_urls.add(canon_url)

            # Check syndication against already accepted items
            for prior in unique_evaluated:
                sim = compute_text_similarity(assessed.snippet, prior.snippet)
                if sim >= 0.75:
                    assessed.is_potential_syndication = True
                    assessed.syndication_notes = f"High textual overlap ({sim:.1%}) with item {prior.id}"
                    break

            unique_evaluated.append(assessed)

        def ranking_key(it: EvidenceItem):
            has_substantive_text = 1 if it.text_availability in ("ABSTRACT", "EXCERPT", "FULL_TEXT") else 0
            rel_rank = 0
            if it.relevance_status == "RELEVANT":
                if it.stance in ("SUPPORTING", "CONTRADICTING"):
                    rel_rank = 3
                else:
                    rel_rank = 2
            elif it.relevance_status == "UNDETERMINED":
                rel_rank = 1
            else:
                rel_rank = 0
            rel_score = it.relevance_score or 0.0
            tier_rank = 2 if it.source_tier == "PRIMARY" else (1 if it.source_tier == "SECONDARY" else 0)
            return (rel_rank, has_substantive_text, rel_score, tier_rank)

        # Safeguard: When relevant records exist, do not present irrelevant records as evidence
        relevant_candidates = [it for it in unique_evaluated if it.relevance_status != "IRRELEVANT"]
        if relevant_candidates:
            relevant_candidates.sort(key=ranking_key, reverse=True)
            return relevant_candidates[:10]

        unique_evaluated.sort(key=ranking_key, reverse=True)
        return unique_evaluated[:10]

    def __init__(self, repository: Optional[EvidenceRepository] = None, relevance_engine: Optional[EvidenceRelevanceEngine] = None):
        self.repository = repository or EvidenceRepository()
        self.relevance_engine = relevance_engine or EvidenceRelevanceEngine()
        self.providers: Dict[str, BaseEvidenceProvider] = {
            "pubmed": PubMedProvider(),
            "nasa_ntrs": NasaNtrsProvider(),
            "usgs_pubs": UsgsPubsProvider(),
            "openalex": OpenAlexProvider(),
            "crossref": CrossrefProvider(),
            "wikimedia": WikimediaProvider(),
            "who_gho": WhoGhoProvider(),
            "who_iris": WhoIrisProvider(),
            "world_bank": WorldBankProvider(),
            "dol_whd": DolWhdProvider(),
            "ecfr": EcfrProvider(),
        }
        self.is_connected: bool = True
        self.retrieval_backend: str = "sqlite_fts5" if self.repository.fts5_available else "sqlite_like"
        self.last_routing_info: Dict[str, object] = {}

    def detect_claim_domain(self, claim: str) -> str:
        """Categorize claim into EMPLOYMENT_RIGHTS, HEALTH, CLIMATE, IMMIGRATION, or GENERAL_SCIENCE for targeted evidence routing.

        Reliability Rule:
        Identify employment and wage-theft claims before routing them to generic immigration or biomedical providers.
        """
        if not claim or not claim.strip():
            return "GENERAL_SCIENCE"
        words = set(self.tokenize_unicode_words(claim))
        claim_lower = claim.lower()

        # Step 2: Prioritize employment and wage-theft claims
        if words.intersection(self.EMPLOYMENT_KEYWORDS) or any(
            phrase in claim_lower for phrase in (
                "wage theft", "wage", "wages", "minimum wage", "overtime",
                "workplace", "unpaid wages", "robo de salario", "robo de sueldo",
                "मजदूरी चोरी", "वेतन चोरी", "মজুরি চুরি"
            )
        ):
            return "EMPLOYMENT_RIGHTS"

        if words.intersection(self.HEALTH_KEYWORDS):
            return "HEALTH"
        if words.intersection(self.CLIMATE_KEYWORDS):
            return "CLIMATE"
        if words.intersection(self.IMMIGRATION_KEYWORDS):
            return "IMMIGRATION"
        return "GENERAL_SCIENCE"

    def retrieve_evidence(self, claim: str, language: Optional[str] = None) -> List[EvidenceItem]:
        """Retrieve relevant source documentation from local repository and live external providers.

        Reliability & Routing Rules:
        - Never invent evidence.
        - Check local SQLite repository first.
        - Assess whether local records provide substantive topical coverage (>= 2 relevant records).
        - If local relevant records are insufficient, query domain-prioritized external public providers.
        - Enforce strict maximum of TWO scholarly providers per claim.
        - Keep Wikimedia separate as optional tertiary background discovery (tier='TERTIARY').
        - Domain-Routing Design:
          * HEALTH: PubMed and OpenAlex (scholarly, max 2).
          * CLIMATE: NASA NTRS and USGS Publications for English; OpenAlex as alternative for non-English (scholarly, max 2).
          * GENERAL_SCIENCE: OpenAlex and Crossref (scholarly, max 2).
        - Log reasons for provider selection or omission.
        - All newly retrieved external records are stored in SQLite (is_verified=False) with SHA-256 hashes.
        - Assess relevance and stance dynamically relative to the submitted claim.
        """
        if not claim or not claim.strip():
            return []

        clean_claim = claim.strip()
        lang_code = (language or "en").strip().lower()

        # Query formulation: extract native content keywords and cross-lingual concept mapped query
        native_q = self.formulate_native_query(clean_claim)
        concept_q = self.formulate_concept_mapped_query(clean_claim, language=lang_code)

        # Step 1: Query local SQLite repository (searching cross-lingual concepts and native terms)
        if concept_q and native_q:
            local_search_q = f"{concept_q} {native_q}".strip() if concept_q != native_q else concept_q
        elif concept_q or native_q:
            local_search_q = (concept_q or native_q).strip()
        else:
            local_search_q = clean_claim
        local_records = self.repository.search_evidence(
            query=local_search_q,
            limit=15,
            verified_only=False,
        )

        # Step 2: Determine domain classification and target provider configuration
        domain = self.detect_claim_domain(clean_claim)
        scholarly_providers: List[str] = []
        skipped_providers: Dict[str, str] = {}
        routing_reason: str = ""

        if domain == "EMPLOYMENT_RIGHTS":
            scholarly_providers = ["dol_whd", "ecfr"]
            skipped_providers = {
                "pubmed": "Domain mismatch (Biomedical clinical trials, not labor standards or wage protections)",
                "nasa_ntrs": "Domain mismatch (Aerospace / Earth observations, not employment law)",
                "usgs_pubs": "Domain mismatch (Geology & hydrology, not labor rights)",
                "who_gho": "Domain mismatch (International health indicators, not U.S. employment law)",
                "world_bank": "Domain mismatch (Global macroeconomic development, not U.S. worker wage rights)",
                "openalex": "Provider limit: official federal labor agencies prioritized (DOL WHD + eCFR selected)",
                "crossref": "Provider limit: official federal labor agencies prioritized",
            }
            routing_reason = (
                "Selected official employment rights providers: U.S. Department of Labor Wage and Hour Division (WHD) "
                "and Electronic Code of Federal Regulations (eCFR Title 29 - Labor). "
                "Prioritized direct federal enforcement guidance and statutory labor protections. "
                "Skipped biomedical (PubMed), planetary (NASA, USGS), and international development (World Bank) providers. "
                "Enforced maximum 2 official providers. Tertiary discovery: Wikimedia."
            )
        elif domain == "HEALTH":
            is_gho_specific = any(k in clean_claim.lower() for k in ("gho", "global health observatory", "global surveillance", "immunization coverage"))
            is_iris_specific = any(k in clean_claim.lower() for k in ("iris", "searo", "guidelines", "technical report", "factsheet", "বিশ্ব স্বাস্থ্য", "विश्व स्वास्थ्य"))
            if is_gho_specific:
                scholarly_providers = ["pubmed", "who_gho"]
                skipped_providers = {
                    "openalex": "WHO GHO selected for official intergovernmental health indicator surveillance",
                    "who_iris": "WHO GHO prioritized for quantitative indicator metrics",
                    "nasa_ntrs": "Domain mismatch (Earth observations / aerospace, not health)",
                    "usgs_pubs": "Domain mismatch (Geology & hydrology, not health)",
                    "crossref": "Provider limit: max 2 providers (PubMed + WHO GHO selected)",
                }
                routing_reason = (
                    "Selected providers: PubMed (biomedical research) and WHO GHO (intergovernmental health surveillance). "
                    "Skipped NASA NTRS and USGS Pubs due to domain specialization. "
                    "Enforced maximum 2 scholarly providers. Tertiary discovery: Wikimedia."
                )
            elif is_iris_specific or lang_code in ("hi", "bn"):
                scholarly_providers = ["who_iris", "openalex"]
                skipped_providers = {
                    "pubmed": "PubMed lacks native South Asian literature (9 Hindi, 0 Bengali citations); WHO IRIS prioritized",
                    "who_gho": "WHO IRIS prioritized for clinical and epidemiological guidelines",
                    "nasa_ntrs": "Domain mismatch (Aerospace, not health)",
                    "usgs_pubs": "Domain mismatch (Geology, not health)",
                    "crossref": "Provider limit: max 2 providers",
                }
                routing_reason = (
                    "Selected providers: WHO IRIS (multilingual SEARO health documents) and OpenAlex (scholarly index). "
                    "Skipped PubMed due to lack of native Hindi/Bengali indexing. "
                    "Enforced maximum 2 scholarly providers. Tertiary discovery: Wikimedia."
                )
            else:
                scholarly_providers = ["pubmed", "openalex"]
                skipped_providers = {
                    "who_iris": "General biomedical query: PubMed and OpenAlex prioritized",
                    "who_gho": "General biomedical query: PubMed and OpenAlex prioritized",
                    "nasa_ntrs": "Domain mismatch (Earth observations / aerospace, not health)",
                    "usgs_pubs": "Domain mismatch (Geology & hydrology, not health)",
                    "crossref": "Provider limit: max 2 scholarly providers (PubMed + OpenAlex selected)",
                }
                routing_reason = (
                    "Selected scholarly providers: PubMed (biomedical & clinical trials) and OpenAlex (scholarly index). "
                    "Skipped NASA NTRS and USGS Pubs due to domain specialization. "
                    "Enforced maximum 2 scholarly providers. Tertiary discovery: Wikimedia."
                )
        elif domain == "CLIMATE":
            if lang_code in ("hi", "bn", "es"):
                scholarly_providers = ["nasa_ntrs", "openalex"]
                skipped_providers = {
                    "usgs_pubs": "Catalog is English-focused; OpenAlex selected as multilingual scholarly alternative",
                    "pubmed": "Domain mismatch (Biomedical, not climate)",
                    "crossref": "Provider limit: max 2 scholarly providers (NASA NTRS + OpenAlex selected)",
                }
                routing_reason = (
                    "Selected scholarly providers: NASA NTRS (Earth observations & atmospheric measurements) and OpenAlex (scholarly index with multilingual works). "
                    "OpenAlex utilized as appropriate scholarly alternative for non-English climate query. "
                    "Enforced maximum 2 scholarly providers. Tertiary discovery: Wikimedia."
                )
            else:
                scholarly_providers = ["nasa_ntrs", "usgs_pubs"]
                skipped_providers = {
                    "pubmed": "Domain mismatch (Biomedical, not climate)",
                    "openalex": "Provider limit: max 2 scholarly providers (NASA NTRS + USGS selected)",
                    "crossref": "Provider limit: max 2 scholarly providers",
                }
                routing_reason = (
                    "Selected scholarly providers: NASA NTRS (Earth observations & atmospheric measurements) and USGS Publications (geological & hydrological monographs). "
                    "Skipped PubMed (domain mismatch) and OpenAlex (enforced 2 scholarly provider ceiling). Tertiary discovery: Wikimedia."
                )
        elif domain == "IMMIGRATION":
            scholarly_providers = ["world_bank", "openalex"]
            skipped_providers = {
                "pubmed": "Domain mismatch (Biomedical, not immigration / demographics / economics)",
                "nasa_ntrs": "Domain mismatch (Earth observations / aerospace, not immigration)",
                "usgs_pubs": "Domain mismatch (Geology & hydrology, not immigration)",
                "crossref": "Provider limit: max 2 scholarly providers (World Bank + OpenAlex selected)",
            }
            routing_reason = (
                "Selected scholarly providers: World Bank WDS (official intergovernmental migration, remittance, & economic research) and OpenAlex (scholarly index). "
                "Skipped domain-specific NASA, USGS, and PubMed. "
                "Enforced maximum 2 scholarly providers. Tertiary discovery: Wikimedia."
            )
        else:
            scholarly_providers = ["openalex", "crossref"]
            skipped_providers = {
                "pubmed": "Domain mismatch (General science, not specialized health)",
                "nasa_ntrs": "Domain mismatch (General science, not specialized aerospace/climate)",
                "usgs_pubs": "Domain mismatch (General science, not specialized geology/hydrology)",
            }
            routing_reason = (
                "Selected scholarly providers: OpenAlex (broad interdisciplinary literature) and Crossref (DOI registry). "
                "Skipped domain-specific NASA, USGS, and PubMed. "
                "Enforced maximum 2 scholarly providers. Tertiary discovery: Wikimedia."
            )

        # Enforce strict maximum of 2 scholarly providers
        scholarly_providers = scholarly_providers[:2]

        # Check if local records contain substantive topical coverage
        relevant_local_count = 0
        for item in local_records:
            assessed = self.relevance_engine.assess_item(claim=clean_claim, item=item)
            if assessed.relevance_status in ("RELEVANT", "SUPPORTING", "CONTRADICTING"):
                relevant_local_count += 1

        self.last_routing_info = {
            "claim": clean_claim,
            "language": lang_code,
            "domain": domain,
            "native_query": native_q,
            "concept_query": concept_q,
            "scholarly_providers": scholarly_providers,
            "tertiary_provider": "wikimedia",
            "skipped_providers": skipped_providers,
            "routing_reason": routing_reason,
            "relevant_local_count": relevant_local_count,
            "live_retrieval_triggered": relevant_local_count < 2,
        }

        # Step 3: Live targeted external retrieval if local relevant records are insufficient (< 2 records)
        if relevant_local_count < 2:
            logger.info(f"Domain: {domain} | {routing_reason}")

            # Query selected scholarly providers (max 2)
            for p_key in scholarly_providers:
                provider = self.providers.get(p_key)
                if not provider:
                    continue
                # For non-English claims or English-focused catalogs, use targeted concept query
                query_for_provider = concept_q if (lang_code != "en" and concept_q) else (native_q or clean_claim)
                try:
                    items, err = provider.search(query_for_provider, limit=2)
                    if err:
                        logger.warning(f"Live retrieval from scholarly provider '{p_key}' returned note: {err}")
                    for item in items:
                        self.repository.store_evidence_item(item)
                except Exception as exc:
                    logger.warning(f"Live retrieval from scholarly provider '{p_key}' skipped: {exc}")

            # Query tertiary discovery provider (Wikimedia with native query and language)
            wiki_provider = self.providers.get("wikimedia")
            if wiki_provider:
                wiki_q = native_q or clean_claim
                try:
                    wiki_items, wiki_err = wiki_provider.search(wiki_q, limit=2, language=lang_code)
                    if wiki_err:
                        logger.warning(f"Tertiary discovery from Wikimedia returned note: {wiki_err}")
                    for item in wiki_items:
                        self.repository.store_evidence_item(item)
                except Exception as exc:
                    logger.warning(f"Tertiary discovery from Wikimedia skipped: {exc}")

            # Re-query local repository to fetch the newly indexed items alongside existing ones
            local_records = self.repository.search_evidence(
                query=local_search_q,
                limit=20,
                verified_only=False,
            )

        # Step 3: Assess relevance, stance, deduplicate, and rank evidence (abstracts first)
        evaluated_records = self._rank_and_deduplicate_evidence(
            records=local_records,
            clean_claim=clean_claim,
            relevance_engine=self.relevance_engine,
        )

        return evaluated_records

    def fetch_and_index_external_evidence(
        self, query: str, limit_per_provider: int = 2
    ) -> Dict[str, object]:
        """Query free public external providers and index retrieved items into the local repository.

        This method is used for evidence discovery and testing without fabricating data.
        All retrieved items are stored with their real provenance, content hash, and source tier.
        """
        results: Dict[str, object] = {
            "query": query,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "providers": {},
            "total_retrieved": 0,
            "total_stored": 0,
            "duplicates_detected": 0,
        }

        total_retrieved = 0
        total_stored = 0
        duplicates_detected = 0

        for provider_name, provider in self.providers.items():
            provider_status = {
                "provider": provider.name,
                "success": False,
                "items_retrieved": 0,
                "items_stored": 0,
                "duplicates": 0,
                "error": None,
                "sample_titles": [],
            }

            try:
                items, err = provider.search(query, limit=limit_per_provider)
                if err:
                    provider_status["error"] = err
                provider_status["success"] = True if items else (err is None)
                provider_status["items_retrieved"] = len(items)
                total_retrieved += len(items)

                for item in items:
                    provider_status["sample_titles"].append(item.title)
                    stored, note = self.repository.store_evidence_item(item)
                    if stored:
                        provider_status["items_stored"] += 1
                        total_stored += 1
                    else:
                        provider_status["duplicates"] += 1
                        duplicates_detected += 1

            except Exception as e:
                logger.error(f"Error querying provider {provider_name}: {e}")
                provider_status["error"] = str(e)

            results["providers"][provider_name] = provider_status

        results["total_retrieved"] = total_retrieved
        results["total_stored"] = total_stored
        results["duplicates_detected"] = duplicates_detected
        results["current_repository_records"] = self.repository.get_record_count()

        return results

    def get_retrieval_status(self) -> Dict[str, object]:
        """Return the current operational status of the evidence repository and providers."""
        record_count = self.repository.get_record_count()
        return {
            "is_connected": self.is_connected,
            "backend": self.retrieval_backend,
            "fts5_enabled": self.repository.fts5_available,
            "db_path": self.repository.db_path,
            "stored_records_count": record_count,
            "configured_providers": list(self.providers.keys()),
            "message": (
                f"Local SQLite Evidence Repository active ({self.retrieval_backend}) with "
                f"{record_count} stored records. Free public evidence providers configured "
                "for verified evidence discovery."
            ),
        }

    @staticmethod
    def extract_source_domain(url: Optional[str]) -> Optional[str]:
        """Extract normalized root domain from a source URL for independent source validation."""
        if not url:
            return None
        try:
            parsed = urlparse(url.strip())
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain if domain else None
        except Exception:
            return None

    def create_evidence_item(
        self,
        id: str,
        title: str,
        snippet: str,
        url: Optional[str] = None,
        publisher: Optional[str] = None,
        stance: str = "NEUTRAL",
        published_date: Optional[str] = None,
        is_verified: bool = False,
    ) -> EvidenceItem:
        """Construct an EvidenceItem preserving actual provenance information.

        Reliability Rule:
        - Do not claim that evidence is verified merely because it has a URL or SHA-256 hash.
        - is_verified is strictly controlled and defaults to False.
        """
        domain = self.extract_source_domain(url)

        # Deterministic SHA-256 digest of snippet content for integrity checking
        content_hash = hashlib.sha256(snippet.encode("utf-8")).hexdigest()

        traceability_info = {
            "content_sha256": content_hash,
            "source_domain": domain or "unknown",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "verification_note": (
                "Verified by independent primary fact-check authority."
                if is_verified
                else "Unverified source record: presence of URL/hash does not constitute proof of authenticity."
            ),
        }

        return EvidenceItem(
            id=id,
            title=title,
            publisher=publisher,
            url=url,
            published_date=published_date,
            snippet=snippet,
            stance=stance.upper(),
            is_verified=is_verified,
            source_domain=domain,
            original_url=url,
            canonical_url=url,
            canonical_domain=domain,
            canonical_publisher=publisher,
            source_tier="SECONDARY",
            content_sha256=content_hash,
            is_potential_syndication=False,
            syndication_notes=None,
            doi=None,
            is_full_text=False,
            traceability=traceability_info,
        )
