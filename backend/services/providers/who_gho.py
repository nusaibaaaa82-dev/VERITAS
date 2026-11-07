"""World Health Organization (WHO) Global Health Observatory (GHO) Public Evidence Provider.

Queries the WHO GHO OData API (ghoapi.azureedge.net/api) to discover official global
health statistics, immunization coverage indicators, disease surveillance, and mortality estimates.

Reliability Rules:
1. Free public endpoint only (no API key, zero cost).
2. Official intergovernmental primary source data (World Health Organization).
3. Preserves official indicator codes, names, definitions, and canonical URLs.
4. Distinguishes official statistics from peer-reviewed secondary literature.
5. All retrieved items retain traceability and content SHA-256 hashes.
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


class WhoGhoProvider(BaseEvidenceProvider):
    """Retrieves authoritative global health indicators from the World Health Organization GHO OData API."""

    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(
            name="WHO Global Health Observatory",
            source_tier="PRIMARY",
            timeout_seconds=timeout_seconds,
        )
        self.base_url = "https://ghoapi.azureedge.net/api"

    def search(self, query: str, limit: int = 3) -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search WHO GHO indicators for relevant public health statistics matching query."""
        if not query or not query.strip():
            return [], "Empty search query"

        # Sanitize query for OData contains() function
        clean_terms = [t for t in query.strip().split() if len(t) > 3][:3]
        if not clean_terms:
            clean_terms = [query.strip()]
        
        search_term = clean_terms[0].replace("'", "''")
        filter_clause = f"contains(IndicatorName, '{search_term}')"
        encoded_filter = urllib.parse.quote(filter_clause)
        
        url = f"{self.base_url}/Indicator?$filter={encoded_filter}&$top={max(1, min(limit, 5))}"

        data, err = self._execute_http_get(url)
        if err:
            return [], f"WHO GHO search error: {err}"

        if not data or "value" not in data:
            return [], "WHO GHO response contained no 'value' array"

        indicators = data["value"]
        if not indicators:
            return [], None

        evidence_items: List[EvidenceItem] = []

        for ind in indicators:
            ind_code = ind.get("IndicatorCode") or "UNKNOWN"
            ind_name = ind.get("IndicatorName") or "WHO Global Health Indicator"
            lang = ind.get("Language") or "EN"

            canonical_url = f"https://www.who.int/data/gho/data/indicators/indicator-details/GHO/{ind_code}"
            title = f"WHO Global Health Indicator: {ind_name}"

            # Fetch a sample data point if available to provide substantive context
            data_sample_note = ""
            data_url = f"{self.base_url}/{ind_code}?$top=1"
            val_data, val_err = self._execute_http_get(data_url)
            if not val_err and val_data and "value" in val_data and val_data["value"]:
                sample_item = val_data["value"][0]
                val_num = sample_item.get("NumericValue") or sample_item.get("Value")
                val_year = sample_item.get("TimeDim") or sample_item.get("TimeDimensionValue")
                loc = sample_item.get("SpatialDim") or sample_item.get("ParentLocation") or "Global"
                if val_num is not None:
                    data_sample_note = f" Reported indicator value: {val_num} ({loc}, {val_year or 'latest series'})."

            snippet = (
                f"Official World Health Organization Global Health Observatory metric. "
                f"Indicator '{ind_name}' (Code: {ind_code}).{data_sample_note} "
                f"Published by WHO Division of Data, Analytics and Delivery for Impact."
            )

            text_availability = "ABSTRACT"
            content_hash = compute_content_hash(snippet)
            domain = "who.int"
            norm_pub = "World Health Organization"

            traceability = {
                "provider": "ghoapi.azureedge.net",
                "indicator_code": ind_code,
                "authority_classification": "INTERGOVERNMENTAL_PRIMARY",
                "source_tier": "PRIMARY",
                "source_type": "GOVERNMENT_PUBLICATION",
                "text_availability": text_availability,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "methodology_notice": (
                    "Official World Health Organization primary statistical indicator. "
                    "Represents intergovernmental epidemiological consensus and surveillance."
                ),
            }

            evidence_items.append(
                EvidenceItem(
                    id=f"who-gho-{ind_code.lower()}",
                    title=title,
                    publisher=norm_pub,
                    url=canonical_url,
                    published_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
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
                    doi=None,
                    is_full_text=False,
                    traceability=traceability,
                )
            )

        return evidence_items, None

