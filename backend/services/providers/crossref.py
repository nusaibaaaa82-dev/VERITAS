"""Crossref Public Evidence Provider for VERITAS.

Queries the free Crossref REST API (api.crossref.org) to discover official
Digital Object Identifier (DOI) records, peer-reviewed journal papers,
and academic metadata.

Requirements:
1. Free public endpoint only (no API key, zero cost).
2. Preserves real DOIs, canonical URLs, titles, publication dates, and publishers.
3. Cleans XML/JATS abstract tags when present.
4. Distinguishes metadata from full-text evidence (is_full_text=False).
5. Academic publication alone is NEVER proof of truth (is_verified=False).
"""

from datetime import datetime, timezone
import re
from typing import List, Optional, Tuple
import urllib.parse
from backend.config import settings
from backend.schemas.claim import EvidenceItem
from backend.services.normalization import (
    classify_source,
    compute_content_hash,
    normalize_domain,
    normalize_publisher,
)
from backend.services.providers.base import BaseEvidenceProvider


class CrossrefProvider(BaseEvidenceProvider):
    """Retrieves scholarly DOI records from the free public Crossref REST API."""

    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(
            name="Crossref DOI Registry",
            source_tier="PRIMARY",
            timeout_seconds=timeout_seconds,
        )
        self.api_url = settings.CROSSREF_API_URL

    @staticmethod
    def _clean_abstract(raw_abstract: Optional[str]) -> Optional[str]:
        """Strip JATS / XML markup tags from Crossref abstract fields."""
        if not raw_abstract:
            return None
        # Remove XML/HTML tags (e.g. <jats:p>, </jats:sec>)
        cleaned = re.sub(r"<[^>]+>", " ", raw_abstract)
        cleaned = " ".join(cleaned.strip().split())
        return cleaned if cleaned else None

    @staticmethod
    def _format_date(date_parts: Optional[List[List[int]]]) -> Optional[str]:
        """Format Crossref date-parts array [[YYYY, MM, DD]] into ISO format."""
        if not date_parts or not isinstance(date_parts, list) or not date_parts[0]:
            return None
        parts = date_parts[0]
        try:
            year = parts[0]
            month = parts[1] if len(parts) > 1 else 1
            day = parts[2] if len(parts) > 2 else 1
            return f"{year:04d}-{month:02d}-{day:02d}"
        except Exception:
            return str(parts[0]) if parts else None

    def search(self, query: str, limit: int = 3) -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search Crossref for official DOI academic publications."""
        if not query or not query.strip():
            return [], "Empty search query"

        encoded_query = urllib.parse.quote(query.strip())
        select_fields = "DOI,title,publisher,published,URL,abstract,type"
        url = f"{self.api_url}?query={encoded_query}&rows={max(1, min(limit, 5))}&select={select_fields}"

        data, err = self._execute_http_get(url)
        if err:
            return [], f"Crossref error: {err}"

        if not data or "message" not in data or "items" not in data.get("message", {}):
            return [], "Crossref response contained no 'items' key"

        items_list = data["message"]["items"]
        evidence_items: List[EvidenceItem] = []

        for item in items_list:
            doi = item.get("DOI") or ""
            if not doi:
                continue

            clean_id = f"crossref-{doi.replace('/', '_')}"

            # Extract title (Crossref returns title as a list of strings)
            raw_title = item.get("title")
            title = raw_title[0] if isinstance(raw_title, list) and raw_title else (raw_title or "Scholarly Publication")

            canonical_url = f"https://doi.org/{doi}"
            publisher_name = item.get("publisher") or "Scholarly Publisher"
            pub_date = self._format_date(item.get("published", {}).get("date-parts"))

            cleaned_abstract = self._clean_abstract(item.get("abstract"))
            if cleaned_abstract:
                snippet = f"Abstract: {cleaned_abstract}"
                is_full = False
            else:
                snippet = (
                    f"Crossref DOI record for '{title}' published by '{publisher_name}' ({pub_date or 'date unrecorded'}). "
                    f"DOI: {doi}. Full-text excerpt not provided in public metadata."
                )
                is_full = False

            content_hash = compute_content_hash(snippet)
            domain = normalize_domain(canonical_url) or "doi.org"
            norm_pub = normalize_publisher(publisher_name, domain)

            # Accurate source classification: distinguish original research, reviews, and encyclopedias
            raw_work_type = item.get("type")
            source_tier, source_type, text_availability = classify_source(
                provider_name="Crossref",
                raw_type=raw_work_type,
                publisher=publisher_name,
                domain=domain,
                title=title,
                has_abstract=bool(cleaned_abstract),
                is_full_text=False,
            )

            traceability = {
                "provider": "api.crossref.org",
                "doi": doi,
                "work_type": raw_work_type or "unspecified",
                "text_availability": text_availability,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "methodology_notice": (
                    "Scholarly DOI registry record. Existence of a published paper or abstract "
                    "does not constitute verified proof of factual truth."
                ),
            }

            evidence_items.append(
                EvidenceItem(
                    id=clean_id,
                    title=title,
                    publisher=publisher_name,
                    url=canonical_url,
                    published_date=pub_date,
                    snippet=snippet,
                    stance="NEUTRAL",
                    # Academic existence alone is not proof of truth
                    is_verified=False,
                    source_domain=domain,
                    original_url=canonical_url,
                    canonical_url=canonical_url,
                    canonical_domain=domain,
                    canonical_publisher=norm_pub,
                    source_tier=source_tier,
                    source_type=source_type,
                    text_availability=text_availability,
                    content_sha256=content_hash,
                    is_potential_syndication=False,
                    syndication_notes=None,
                    doi=doi,
                    is_full_text=is_full,
                    traceability=traceability,
                )
            )

        return evidence_items, None

