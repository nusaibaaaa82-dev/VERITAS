"""World Bank Documents & Reports (WDS) Evidence Provider.

Queries the World Bank Documents & Reports API (search.worldbank.org/api/v2/wds),
providing authoritative open access to World Bank economic research, policy research
working papers, country economic memorandums, project appraisal documents,
and demographic / migration reports across English, Spanish, Hindi, and Bengali.

Reliability & Verification Safeguards:
1. Zero-cost public REST endpoint only (no API keys, subscriptions, or paywalls).
2. Official intergovernmental primary source tier (INTERGOVERNMENTAL_PRIMARY).
3. Preserves official document IDs, report numbers, project IDs, publication dates,
   authors, publishers, official languages, and permanent curated URLs.
4. Distinguishes ABSTRACT, EXCERPT, and METADATA_ONLY (never claims full-text access
   since API snippets are abstracts; full PDFs require external download).
5. Inspects document's actual 'lang' field; NEVER assumes language from query text.
6. Translation provenance tracking: translated editions (e.g. Hindi/Bengali project
   briefs with English parent studies) are linked via underlying_source_id and flagged
   as TRANSLATION_COPY so they collapse into 1 independent source vote.
7. Does NOT mark records as verified merely because they originate from the World Bank
   (is_verified=False until human/expert confirmation).
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
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

logger = logging.getLogger(__name__)

# Language normalization mapping from World Bank WDS language names to ISO 639-1
WORLDBANK_LANGUAGE_MAP: Dict[str, str] = {
    "english": "en",
    "en": "en",
    "eng": "en",
    "spanish": "es",
    "español": "es",
    "es": "es",
    "spa": "es",
    "hindi": "hi",
    "हिन्दी": "hi",
    "hi": "hi",
    "hin": "hi",
    "bengali": "bn",
    "বাংলা": "bn",
    "bn": "bn",
    "ben": "bn",
    "french": "fr",
    "français": "fr",
    "fr": "fr",
    "fra": "fr",
    "arabic": "ar",
    "ar": "ar",
    "ara": "ar",
    "russian": "ru",
    "русский": "ru",
    "ru": "ru",
    "rus": "ru",
    "chinese": "zh",
    "中文": "zh",
    "zh": "zh",
    "zho": "zh",
    "portuguese": "pt",
    "português": "pt",
    "pt": "pt",
}

# Reverse mapping for API lang_exact query parameter
API_LANG_EXACT_MAP: Dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "hi": "Hindi",
    "bn": "Bengali",
    "fr": "French",
    "ar": "Arabic",
    "ru": "Russian",
    "zh": "Chinese",
    "pt": "Portuguese",
}


class WorldBankProvider(BaseEvidenceProvider):
    """Retrieves authoritative economic, migration, and development publications from World Bank WDS."""

    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(
            name="World Bank Documents & Reports (WDS)",
            source_tier="PRIMARY",
            timeout_seconds=timeout_seconds,
        )
        self.api_url: str = getattr(
            settings,
            "WORLDBANK_WDS_API_URL",
            "https://search.worldbank.org/api/v2/wds",
        )

    @staticmethod
    def normalize_language_code(raw_lang: Optional[str]) -> str:
        """Normalize raw World Bank language string into ISO 639-1 code.

        Returns 'und' (undetermined) if unknown, rather than guessing.
        """
        if not raw_lang:
            return "und"
        # Check first comma-separated token if multiple languages listed
        tokens = [t.strip().lower() for t in raw_lang.replace("/", ",").split(",") if t.strip()]
        for t in tokens:
            if t in WORLDBANK_LANGUAGE_MAP:
                return WORLDBANK_LANGUAGE_MAP[t]
        return "und"

    @staticmethod
    def extract_authors(raw_authors: object) -> str:
        """Extract clean author string from World Bank authors dictionary or string."""
        if not raw_authors:
            return "World Bank Group"
        if isinstance(raw_authors, dict):
            extracted: List[str] = []
            # Authors dict is keyed by index strings '0', '1', etc.
            for k in sorted(raw_authors.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                val = raw_authors[k]
                if isinstance(val, dict) and "author" in val:
                    extracted.append(str(val["author"]).strip())
                elif isinstance(val, str):
                    extracted.append(val.strip())
            if extracted:
                return ", ".join(extracted)
        elif isinstance(raw_authors, str):
            return " ".join(raw_authors.split())
        return "World Bank Group"

    @classmethod
    def parse_wds_json_dict(cls, data: dict) -> List[EvidenceItem]:
        """Parse World Bank WDS JSON API response into standardized EvidenceItem objects.

        Hermetic pure parser suitable for both live retrieval and unit testing with mock fixtures.
        """
        if not data or not isinstance(data, dict):
            return []

        docs_container = data.get("documents")
        if not docs_container or not isinstance(docs_container, dict):
            return []

        items: List[EvidenceItem] = []

        for doc_key, doc in docs_container.items():
            # Skip non-document metadata entries like 'facets'
            if doc_key == "facets" or not isinstance(doc, dict):
                continue

            doc_id = str(doc.get("id") or "").strip()
            if not doc_id:
                continue

            # 1. Clean Title
            raw_title = doc.get("display_title") or doc.get("docty") or f"World Bank Document {doc_id}"
            title = " ".join(str(raw_title).split())

            # 2. Document Date
            raw_date = doc.get("docdt") or doc.get("datestored") or doc.get("disclosure_date") or ""
            pub_date = str(raw_date)[:10] if raw_date else None

            # 3. Authors
            authors = cls.extract_authors(doc.get("authors"))

            # 4. Canonical & Direct URLs
            canonical_url = doc.get("url") or doc.get("url_friendly_title") or ""
            if canonical_url and canonical_url.startswith("http://"):
                canonical_url = "https://" + canonical_url[7:]
            pdf_url = doc.get("pdfurl") or ""
            if pdf_url and pdf_url.startswith("http://"):
                pdf_url = "https://" + pdf_url[7:]
            primary_url = canonical_url or pdf_url or f"https://documents.worldbank.org/curated/en/{doc_id}"

            # 5. Extract Abstract / Excerpt Snippet
            raw_abstract = doc.get("abstracts")
            snippet_text = ""
            if isinstance(raw_abstract, dict):
                snippet_text = str(raw_abstract.get("cdata!", "")).strip()
            elif isinstance(raw_abstract, str):
                snippet_text = raw_abstract.strip()

            snippet_text = " ".join(snippet_text.split())

            # Determine text availability accurately
            if len(snippet_text) >= 60:
                text_availability = "ABSTRACT"
                display_snippet = snippet_text
            elif len(snippet_text) > 0:
                text_availability = "EXCERPT"
                display_snippet = snippet_text
            else:
                text_availability = "METADATA_ONLY"
                # For metadata records, provide an honest descriptive summary without claiming full text
                doc_type = doc.get("docty") or "Document"
                rep_nb = doc.get("repnb") or "N/A"
                display_snippet = (
                    f"World Bank {doc_type} (Report No: {rep_nb}). "
                    f"Title: {title}. Authors: {authors}. Published: {pub_date or 'Undated'}. "
                    "Abstract text is not indexed in public catalog metadata."
                )

            # 6. Language Detection & Normalization (Never assume from query)
            raw_lang = doc.get("lang") or ""
            normalized_lang = cls.normalize_language_code(str(raw_lang))

            # 7. Translation & Independence Linkage
            # World Bank documents link multi-language editions via 'available_in', 'fullavailablein',
            # project ID ('projectid'), and report number ('repnb').
            available_in_str = str(doc.get("available_in") or "")
            fullavailable_list = doc.get("fullavailablein") or []
            project_id = str(doc.get("projectid") or "").strip()
            rep_nb = str(doc.get("repnb") or "").strip()

            is_translation = False
            parent_link_id = None

            # If document is non-English (e.g. Hindi, Bengali, Spanish) and an English edition exists
            if normalized_lang != "en" and (
                "english" in available_in_str.lower()
                or any(
                    isinstance(fa, dict) and fa.get("lang", "").lower() == "english"
                    for fa in fullavailable_list
                )
            ):
                is_translation = True
                # Parent identifier ties back to shared project ID, report number, or root node
                root_ref = project_id or rep_nb or doc.get("guid") or doc_id
                parent_link_id = f"worldbank-{root_ref}"

            independence_status = "TRANSLATION_COPY" if is_translation else "INDEPENDENT"
            translation_engine = "World Bank Official Translation" if is_translation else None
            original_lang = "en" if is_translation else (normalized_lang if normalized_lang != "und" else "en")

            # Content hash
            content_sha256 = compute_content_hash(display_snippet)

            # Traceability dictionary
            traceability = {
                "provider": "world_bank",
                "document_id": doc_id,
                "project_id": project_id or "N/A",
                "report_number": rep_nb or "N/A",
                "authors": authors,
                "guid": str(doc.get("guid") or ""),
                "cataloged_language": str(raw_lang),
                "normalized_language": normalized_lang,
                "available_in": available_in_str,
                "is_translation": str(is_translation),
                "underlying_source_id": parent_link_id or f"worldbank-{doc_id}",
                "independence_status": independence_status,
                "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
                "content_sha256": content_sha256,
            }

            evidence_item = EvidenceItem(
                id=f"worldbank-{doc_id}",
                title=title,
                publisher="World Bank Group",
                url=primary_url,
                published_date=pub_date,
                snippet=display_snippet,
                stance="NEUTRAL",
                is_verified=False,  # Unverified until human/expert confirmation
                source_domain="worldbank.org",
                original_url=primary_url,
                canonical_url=canonical_url or primary_url,
                canonical_domain="worldbank.org",
                canonical_publisher="World Bank Group",
                source_tier="PRIMARY",
                source_type="GOVERNMENT_PUBLICATION",
                text_availability=text_availability,
                is_full_text=False,  # API snippets are abstracts; full text is in external PDF
                content_sha256=content_sha256,
                underlying_source_id=parent_link_id,
                independence_status=independence_status,
                is_machine_translated=False,
                translation_engine=translation_engine,
                original_language=original_lang,
                traceability=traceability,
            )
            items.append(evidence_item)

        return items

    def search(
        self,
        query: str,
        limit: int = 3,
        language: Optional[str] = None,
    ) -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search World Bank Documents & Reports for relevant primary publications.

        Parameters:
            query: The thematic or keyword search phrase.
            limit: Maximum number of records to return (default 3).
            language: Optional ISO 639-1 language filter hint ('en', 'es', 'hi', 'bn').

        Returns:
            Tuple of (list_of_evidence_items, error_or_diagnostic_message).
        """
        if not query or not query.strip():
            return [], "Query cannot be empty"

        clean_query = query.strip()

        # Build query parameters
        params = {
            "format": "json",
            "qterm": clean_query,
            "rows": max(1, min(limit, 20)),
        }

        # If a specific language is explicitly requested and mapped in World Bank catalog
        if language:
            norm_hint = language.strip().lower()
            if norm_hint in API_LANG_EXACT_MAP:
                params["lang_exact"] = API_LANG_EXACT_MAP[norm_hint]

        url = f"{self.api_url}?{urllib.parse.urlencode(params)}"

        data, err = self._execute_http_get(url)
        if err:
            return [], f"World Bank WDS API error: {err}"

        if not data or not isinstance(data, dict):
            return [], "Invalid or empty response from World Bank WDS"

        total_records = data.get("total", 0)
        try:
            total_records = int(total_records)
        except (ValueError, TypeError):
            total_records = 0

        if total_records == 0:
            return [], f"No documents found matching query '{clean_query}'"

        items = self.parse_wds_json_dict(data)
        if not items:
            return [], f"No parseable document records returned for query '{clean_query}'"

        return items[:limit], None
