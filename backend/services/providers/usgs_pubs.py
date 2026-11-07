"""U.S. Geological Survey (USGS) Publications Warehouse Evidence Provider for VERITAS.

Queries the USGS Publications Services API (pubs.usgs.gov/pubs-services/publication)
for peer-reviewed earth science monographs, ecological investigations, hydrological bulletins,
and climate adaptation reports published by the U.S. Geological Survey.

Reliability Rules:
1. Free public endpoint only (no API key, zero cost).
2. Preserves authentic USGS publication IDs, DOIs, canonical URLs, titles, and publication dates.
3. Cleans HTML tags from abstracts and distinguishes abstracts from metadata (is_full_text=False).
4. Government scientific publication alone is NEVER proof of truth (is_verified=False).
5. All retrieved items retain traceability and content hashes.
"""

from datetime import datetime, timezone
import re
from typing import Dict, List, Optional, Tuple
import urllib.parse
from backend.config import settings
from backend.schemas.claim import EvidenceItem
from backend.services.normalization import (
    compute_content_hash,
    normalize_domain,
    normalize_publisher,
)
from backend.services.providers.base import BaseEvidenceProvider


class UsgsPubsProvider(BaseEvidenceProvider):
    """Retrieves geological, ecological, and hydrological reports from the free public USGS API."""

    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(
            name="USGS Publications",
            source_tier="PRIMARY",
            timeout_seconds=timeout_seconds,
        )
        self.api_url = settings.USGS_PUBS_API_URL

    @staticmethod
    def _clean_abstract(raw_abstract: Optional[str]) -> Optional[str]:
        """Strip HTML tags from USGS docAbstract field."""
        if not raw_abstract:
            return None
        cleaned = re.sub(r"<[^>]+>", " ", raw_abstract)
        cleaned = " ".join(cleaned.strip().split())
        return cleaned if cleaned else None

    def search(self, query: str, limit: int = 3) -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search USGS Publications Warehouse for scientific monographs and research articles."""
        if not query or not query.strip():
            return [], "Empty search query"

        encoded_query = urllib.parse.quote(query.strip())
        url = f"{self.api_url}?q={encoded_query}&pageSize={max(1, min(limit, 5))}"

        data, err = self._execute_http_get(url)
        if err:
            return [], f"USGS Pubs error: {err}"

        if not data or "records" not in data:
            return [], "USGS Pubs response contained no 'records' key"

        records_list = data.get("records", [])
        evidence_items: List[EvidenceItem] = []

        for record in records_list:
            pub_id = record.get("id")
            if not pub_id:
                continue

            unique_id = f"usgs-{pub_id}"
            title = record.get("title") or "USGS Scientific Publication"
            title = title.strip().rstrip(".")

            doi = record.get("doi")
            canonical_url = f"https://doi.org/{doi}" if doi else f"https://pubs.usgs.gov/publication/{pub_id}"
            publisher_name = "U.S. Geological Survey (USGS)"

            pub_year = record.get("publicationYear")
            pub_date = f"{pub_year}-01-01" if pub_year else record.get("displayToPublicDate")

            raw_abstract = record.get("docAbstract")
            cleaned_abstract = self._clean_abstract(raw_abstract)

            if cleaned_abstract:
                snippet = f"USGS Abstract: {cleaned_abstract}"
                text_availability = "ABSTRACT"
            else:
                snippet = (
                    f"USGS Publication record for '{title}' ({pub_year or 'year unrecorded'}). "
                    f"USGS ID: {pub_id}. Full-text excerpt not provided in public metadata."
                )
                text_availability = "METADATA_ONLY"

            content_hash = compute_content_hash(snippet)
            domain = normalize_domain(canonical_url) or "pubs.usgs.gov"
            norm_pub = normalize_publisher(publisher_name, domain)

            traceability = {
                "provider": "pubs.usgs.gov/pubs-services",
                "usgs_id": str(pub_id),
                "doi": doi or "N/A",
                "text_availability": text_availability,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "methodology_notice": (
                    "U.S. Geological Survey public research record. Government publication "
                    "alone does not constitute independent verification of factual truth."
                ),
            }

            evidence_items.append(
                EvidenceItem(
                    id=unique_id,
                    title=title,
                    publisher=publisher_name,
                    url=canonical_url,
                    published_date=pub_date,
                    snippet=snippet,
                    stance="NEUTRAL",
                    is_verified=False,
                    source_domain=domain,
                    original_url=canonical_url,
                    canonical_url=canonical_url,
                    canonical_domain=domain,
                    canonical_publisher=norm_pub,
                    source_tier="PRIMARY",
                    source_type="GOVERNMENT_PUBLICATION",
                    text_availability=text_availability,
                    content_sha256=content_hash,
                    is_potential_syndication=False,
                    syndication_notes=None,
                    doi=doi,
                    is_full_text=False,
                    traceability=traceability,
                )
            )

        return evidence_items, None

