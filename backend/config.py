"""VERITAS Configuration Module.

Defines global configuration settings, model identifiers, threshold parameters,
and supported verdicts for the VERITAS fact-checking platform.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Tuple


@dataclass(frozen=True)
class Settings:
    """Core application settings for VERITAS backend services."""

    APP_NAME: str = "VERITAS API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Pipeline Constraints
    MAX_CLAIM_LENGTH: int = 1000
    MAX_EVIDENCE_ITEMS: int = 10

    # Rate Limiting & Abuse Prevention
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 20

    # CORS Configuration
    CORS_ORIGINS: Tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:7860",
        "http://127.0.0.1:7860",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://veritas-frontend-0lhx.onrender.com",
    )

    # Evidence Repository Configuration (Local SQLite + FTS5)
    EVIDENCE_DB_PATH: str = str(Path(__file__).resolve().parent / "data" / "evidence_repository.db")
    ENABLE_FTS5: bool = True

    # Free Public Evidence Providers (Strictly free public endpoints, no keys/subscriptions)
    OPENALEX_API_URL: str = "https://api.openalex.org/works"
    CROSSREF_API_URL: str = "https://api.crossref.org/works"
    WIKIMEDIA_SUMMARY_URL: str = "https://en.wikipedia.org/api/rest_v1/page/summary"
    WIKIMEDIA_SEARCH_URL: str = "https://en.wikipedia.org/w/api.php"
    PUBMED_ESEARCH_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    PUBMED_ESUMMARY_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    NASA_NTRS_API_URL: str = "https://ntrs.nasa.gov/api/citations/search"
    USGS_PUBS_API_URL: str = "https://pubs.usgs.gov/pubs-services/publication"
    WHO_GHO_API_URL: str = "https://ghoapi.azureedge.net/api"
    WHO_IRIS_OAI_URL: str = "https://iris.who.int/oai/request"
    WHO_IRIS_SEARCH_URL: str = "https://iris.who.int/server/api/discover/search/objects"
    WORLDBANK_WDS_API_URL: str = "https://search.worldbank.org/api/v2/wds"
    PROVIDER_TIMEOUT_SECONDS: float = 8.0
    HTTP_USER_AGENT: str = "VERITAS-FactChecker/1.0 (academic research; contact@veritas-project.org)"

    # Model Architecture Identifiers (HuggingFace Hub repositories)
    # 1. XLM-RoBERTa 7-class fact-checking
    XLM_ROBERTA_7CLASS_MODEL_NAME: str = "nusaiba19/xlmr-xfact-7class"
    # 2. XLM-RoBERTa binary fact-checking
    XLM_ROBERTA_BINARY_MODEL_NAME: str = "nusaiba19/xlmr-xfact-binary"
    # Default XLM-RoBERTa model identifier
    XLM_ROBERTA_MODEL_NAME: str = "nusaiba19/xlmr-xfact-7class"

    # 3. RoBERTa immigrant hate-speech classifier (Safety/Content Risk - NOT a fact-checking classifier)
    ROBERTA_HATE_SPEECH_MODEL_NAME: str = "nusaiba19/roberta-immigrant-hate-speech"
    ROBERTA_MODEL_NAME: str = "nusaiba19/roberta-immigrant-hate-speech"

    # Standardized 5-Verdict Classification Taxonomy
    PERMITTED_VERDICTS: FrozenSet[str] = frozenset(
        {
            "TRUE",
            "FALSE",
            "PARTIALLY TRUE",
            "MISLEADING",
            "UNVERIFIED",
        }
    )

    VERDICTS_ORDERED: Tuple[str, ...] = (
        "TRUE",
        "FALSE",
        "PARTIALLY TRUE",
        "MISLEADING",
        "UNVERIFIED",
    )

    # Minimum number of INDEPENDENT verified sources required for a conclusive verdict
    # Rule: One source is never sufficient proof of a factual claim.
    MIN_INDEPENDENT_EVIDENCE_SOURCES: int = 2


settings = Settings()
