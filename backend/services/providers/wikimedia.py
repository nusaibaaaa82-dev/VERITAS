"""Wikimedia Public Evidence Provider for VERITAS.

Queries the Wikimedia / Wikipedia REST API (en.wikipedia.org/api/rest_v1)
and Search API for background encyclopedic context and claim entity discovery.

Crucial Scientific Constraints:
1. Free public endpoints only (no API key, zero cost).
2. Wikimedia results are strictly for discovery and background context,
   NOT primary-source factual corroboration (source_tier='TERTIARY').
3. Wikipedia articles alone are NEVER treated as proof that a claim is true (is_verified=False).
4. Preserves authentic article URLs, titles, revision timestamps, and excerpts.
"""

from datetime import datetime, timezone
import re
from typing import List, Optional, Tuple
import urllib.parse
from backend.config import settings
from backend.schemas.claim import EvidenceItem
from backend.services.normalization import compute_content_hash, normalize_domain, normalize_publisher
from backend.services.providers.base import BaseEvidenceProvider


class WikimediaProvider(BaseEvidenceProvider):
    """Retrieves encyclopedic background summaries from the Wikimedia REST API."""

    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(
            name="Wikimedia REST API",
            source_tier="TERTIARY",
            timeout_seconds=timeout_seconds,
        )
        self.search_url = settings.WIKIMEDIA_SEARCH_URL
        self.summary_url = settings.WIKIMEDIA_SUMMARY_URL

    def search(self, query: str, limit: int = 3, language: str = "en") -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search Wikipedia for encyclopedic pages matching claim topics and extract summaries."""
        if not query or not query.strip():
            return [], "Empty search query"

        # Determine target localized Wikipedia sub-domain (en, es, hi, bn)
        lang_code = language.strip().lower() if language and len(language.strip()) in (2, 3) else "en"
        if lang_code not in ("en", "es", "hi", "bn", "fr", "de"):
            lang_code = "en"

        search_url = f"https://{lang_code}.wikipedia.org/w/api.php"
        summary_url = f"https://{lang_code}.wikipedia.org/api/rest_v1/page/summary"

        # Step 1: Query Wikipedia Search API for top matching article titles
        encoded_query = urllib.parse.quote(query.strip())
        search_endpoint = (
            f"{search_url}?action=query&list=search"
            f"&srsearch={encoded_query}&utf8=1&format=json&srlimit={max(1, min(limit, 5))}"
        )

        search_data, err = self._execute_http_get(search_endpoint)
        if err:
            return [], f"Wikimedia search error ({lang_code}): {err}"

        if not search_data or "query" not in search_data or "search" not in search_data.get("query", {}):
            return [], f"Wikimedia search response ({lang_code}) contained no 'search' results"

        search_results = search_data["query"]["search"]
        evidence_items: List[EvidenceItem] = []

        # Step 2: Fetch clean summary extracts from Page Summary REST API for each title
        for entry in search_results:
            raw_title = entry.get("title") or ""
            if not raw_title:
                continue

            page_id = entry.get("pageid", "0")
            unique_id = f"wiki-{lang_code}-{page_id}"

            # Query REST API for summary extract
            title_quoted = urllib.parse.quote(raw_title.replace(" ", "_"))
            summary_endpoint = f"{summary_url}/{title_quoted}"
            summary_data, summary_err = self._execute_http_get(summary_endpoint)

            if summary_data and "extract" in summary_data:
                title = summary_data.get("title") or raw_title
                extract = summary_data.get("extract") or ""
                url = (
                    summary_data.get("content_urls", {}).get("desktop", {}).get("page")
                    or f"https://{lang_code}.wikipedia.org/wiki/{title_quoted}"
                )
                pub_date = summary_data.get("timestamp")
            else:
                # Fallback to search snippet with stripped HTML
                title = raw_title
                snippet_raw = entry.get("snippet") or ""
                extract = re.sub(r"<[^>]+>", "", snippet_raw)
                url = f"https://{lang_code}.wikipedia.org/wiki/{title_quoted}"
                pub_date = entry.get("timestamp")

            if not extract:
                continue

            snippet = f"Wikipedia ({lang_code.upper()}) background summary: {extract}"
            content_hash = compute_content_hash(snippet)
            domain = normalize_domain(url) or f"{lang_code}.wikipedia.org"
            norm_pub = normalize_publisher("Wikimedia Foundation", domain)

            traceability = {
                "provider": f"{lang_code}.wikipedia.org/api/rest_v1",
                "page_id": str(page_id),
                "language": lang_code,
                "work_type": "encyclopedic_summary",
                "text_availability": "EXCERPT",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "methodology_notice": (
                    f"Tertiary encyclopedic background ({lang_code.upper()}). Wikimedia consensus records "
                    "provide discovery context and entity framing, NOT primary-source factual corroboration."
                ),
            }

            evidence_items.append(
                EvidenceItem(
                    id=unique_id,
                    title=title,
                    publisher="Wikimedia Foundation",
                    url=url,
                    published_date=pub_date,
                    snippet=snippet,
                    stance="NEUTRAL",
                    # Tertiary encyclopedic content alone is NEVER treated as proof of truth
                    is_verified=False,
                    source_domain=domain,
                    original_url=url,
                    canonical_url=url,
                    canonical_domain=domain,
                    canonical_publisher=norm_pub,
                    source_tier="TERTIARY",
                    source_type="ENCYCLOPEDIC_SUMMARY",
                    text_availability="EXCERPT",
                    content_sha256=content_hash,
                    is_potential_syndication=False,
                    syndication_notes=None,
                    doi=None,
                    is_full_text=False,
                    traceability=traceability,
                )
            )

        return evidence_items, None

