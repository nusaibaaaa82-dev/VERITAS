"""OpenAlex Public Evidence Provider for VERITAS.

Queries OpenAlex (api.openalex.org), a free and open catalog of 250M+ global
scholarly research works, journal articles, and peer-reviewed papers.

Requirements:
1. Free public endpoint only (no API key, zero cost).
2. Preserves real DOIs, titles, publication dates, and journal publishers.
3. Reconstructs abstracts from inverted index when available.
4. Distinguishes abstract metadata from full-text evidence (is_full_text=False).
5. Academic paper existence or abstract alone is NEVER proof of truth (is_verified=False).
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
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


class OpenAlexProvider(BaseEvidenceProvider):
    """Retrieves primary scholarly works from the free public OpenAlex API."""

    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(
            name="OpenAlex Scholarly Index",
            source_tier="PRIMARY",
            timeout_seconds=timeout_seconds,
        )
        self.api_url = settings.OPENALEX_API_URL

    @staticmethod
    def _reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
        """Reconstruct plain-text abstract from OpenAlex inverted index structure."""
        if not inverted_index or not isinstance(inverted_index, dict):
            return None
        try:
            position_words: List[Tuple[int, str]] = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    position_words.append((pos, word))
            position_words.sort(key=lambda x: x[0])
            reconstructed = " ".join(word for _, word in position_words)
            return reconstructed.strip() if reconstructed else None
        except Exception:
            return None

    def search(self, query: str, limit: int = 3) -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search OpenAlex works for peer-reviewed literature matching claim query."""
        if not query or not query.strip():
            return [], "Empty search query"

        encoded_query = urllib.parse.quote(query.strip())
        select_fields = "id,doi,title,publication_year,publication_date,type,primary_location,abstract_inverted_index,cited_by_count"
        url = f"{self.api_url}?search={encoded_query}&per-page={max(1, min(limit, 5))}&select={select_fields}"

        data, err = self._execute_http_get(url)
        if err:
            return [], f"OpenAlex error: {err}"

        if not data or "results" not in data:
            return [], "OpenAlex response contained no 'results' key"

        results_list = data.get("results", [])
        evidence_items: List[EvidenceItem] = []

        for work in results_list:
            work_id_raw = work.get("id") or ""
            work_id_clean = work_id_raw.split("/")[-1] if "/" in work_id_raw else work_id_raw
            unique_id = f"openalex-{work_id_clean}"

            title = work.get("title") or "Untitled Scholarly Work"
            doi = work.get("doi")
            canonical_url = doi or work.get("id") or ""

            # Extract primary journal / source publisher
            primary_loc = work.get("primary_location") or {}
            source_info = primary_loc.get("source") or {}
            publisher_name = source_info.get("display_name") or source_info.get("publisher") or "Academic Publisher"

            pub_date = work.get("publication_date")
            if not pub_date and work.get("publication_year"):
                pub_date = f"{work.get('publication_year')}-01-01"

            # Reconstruct abstract or formulate transparent metadata summary
            abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))
            if abstract:
                snippet = f"Abstract: {abstract}"
                is_full = False
            else:
                snippet = (
                    f"Scholarly metadata record for '{title}' published in '{publisher_name}' ({pub_date or 'date unrecorded'}). "
                    "Full-text abstract not indexed in OpenAlex public metadata."
                )
                is_full = False

            # Hash and normalize
            content_hash = compute_content_hash(snippet)
            domain = normalize_domain(canonical_url) or "doi.org"
            norm_pub = normalize_publisher(publisher_name, domain)

            # Accurate source classification: do not automatically classify all records as PRIMARY
            raw_work_type = work.get("type")
            source_tier, source_type, text_availability = classify_source(
                provider_name="OpenAlex",
                raw_type=raw_work_type,
                publisher=publisher_name,
                domain=domain,
                title=title,
                has_abstract=bool(abstract),
                is_full_text=False,
            )

            traceability = {
                "provider": "api.openalex.org",
                "openalex_id": work_id_raw,
                "doi": doi or "N/A",
                "work_type": raw_work_type or "unspecified",
                "text_availability": text_availability,
                "cited_by_count": str(work.get("cited_by_count", 0)),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "methodology_notice": (
                    "Scholarly index record. Existence of a published paper or abstract "
                    "does not constitute verified proof of factual truth."
                ),
            }

            item = EvidenceItem(
                id=unique_id,
                title=title,
                publisher=publisher_name,
                url=canonical_url,
                published_date=pub_date,
                snippet=snippet,
                stance="NEUTRAL",
                # Academic paper existence alone is NOT proof that claim is verified true
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
            evidence_items.append(item)

        return evidence_items, None

