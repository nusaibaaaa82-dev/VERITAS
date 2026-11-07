"""NASA Technical Reports Server (NTRS) Public Evidence Provider for VERITAS.

Queries the National Aeronautics and Space Administration (NASA) NTRS API
(ntrs.nasa.gov/api/citations/search) for authoritative Earth science observations,
atmospheric measurements, climate reports, and aerospace scientific research.

Reliability Rules:
1. Free public endpoint only (no API key, zero cost).
2. Preserves authentic NASA report IDs, DOIs, canonical URLs, titles, publication dates, and center publishers.
3. Distinguishes peer-reviewed government report abstracts from metadata-only records (is_full_text=False).
4. Government scientific publication alone is NEVER proof of truth (is_verified=False).
5. All retrieved items retain traceability and content hashes.
"""

from datetime import datetime, timezone
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


class NasaNtrsProvider(BaseEvidenceProvider):
    """Retrieves Earth science and aerospace reports from the free public NASA NTRS API."""

    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(
            name="NASA NTRS",
            source_tier="PRIMARY",
            timeout_seconds=timeout_seconds,
        )
        self.api_url = settings.NASA_NTRS_API_URL

    def search(self, query: str, limit: int = 3) -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search NASA NTRS for scientific publications and technical reports matching claim query."""
        if not query or not query.strip():
            return [], "Empty search query"

        encoded_query = urllib.parse.quote(query.strip())
        url = f"{self.api_url}?q={encoded_query}&size={max(1, min(limit, 5))}"

        data, err = self._execute_http_get(url)
        if err:
            return [], f"NASA NTRS error: {err}"

        if not data or "results" not in data:
            return [], "NASA NTRS response contained no 'results' key"

        results_list = data.get("results", [])
        evidence_items: List[EvidenceItem] = []

        for record in results_list:
            record_id = record.get("id") or record.get("submissionId")
            if not record_id:
                continue

            unique_id = f"nasa-{record_id}"
            title = record.get("title") or "NASA Technical Report"
            title = title.strip().rstrip(".")

            abstract = record.get("abstract")
            canonical_url = f"https://ntrs.nasa.gov/citations/{record_id}"
            publisher_name = "National Aeronautics and Space Administration (NASA)"

            pub_date = record.get("publicationDate")
            if not pub_date and record.get("published"):
                pub_date = str(record.get("published"))

            # DOI extraction
            doi = None
            if record.get("doi"):
                doi = record.get("doi")

            if abstract:
                snippet = f"NASA Report Abstract: {abstract.strip()}"
                text_availability = "ABSTRACT"
            else:
                snippet = (
                    f"NASA Technical Report record for '{title}' ({pub_date or 'date unrecorded'}). "
                    f"NASA ID: {record_id}. Full-text excerpt not provided in public metadata."
                )
                text_availability = "METADATA_ONLY"

            content_hash = compute_content_hash(snippet)
            domain = normalize_domain(canonical_url) or "ntrs.nasa.gov"
            norm_pub = normalize_publisher(publisher_name, domain)

            traceability = {
                "provider": "ntrs.nasa.gov/api",
                "nasa_id": str(record_id),
                "doi": doi or "N/A",
                "text_availability": text_availability,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "methodology_notice": (
                    "NASA Technical Reports Server public record. Government publication "
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

