"""World Health Organization (WHO) Institutional Repository for Information Sharing (IRIS) Provider.

Queries WHO IRIS (iris.who.int), the digital repository of the World Health Organization,
providing open-access access to WHO published technical documents, guidelines, resolutions,
meeting reports, and regional publications (including SEARO Hindi and Bengali documents).

Protocols Supported:
1. OAI-PMH 2.0 endpoint (iris.who.int/oai/request) with metadataPrefix=oai_dc (Dublin Core).
2. DSpace 7 Discover REST Search API (iris.who.int/server/api/discover/search/objects).

Reliability & Verification Safeguards:
1. Free public endpoints only (no API keys, zero subscriptions).
2. Official intergovernmental primary source tier (INTERGOVERNMENTAL_PRIMARY).
3. Preserves official document identifiers (Handles), publication dates, publishers, and original URLs.
4. Distinguishes ABSTRACT, EXCERPT, and METADATA_ONLY (never claims full-text access for metadata/abstracts).
5. Tracks translation provenance: translated documents link to their parent publication identifier
   (underlying_source_id) and are marked TRANSLATION_COPY so they collapse into 1 source vote.
6. Does NOT mark records as verified merely because they originate from WHO (is_verified=False).
7. Non-invented language metadata: missing or ambiguous language is preserved as 'und' (undetermined).
"""

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Dict, List, Optional, Set, Tuple
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from backend.config import settings
from backend.schemas.claim import EvidenceItem
from backend.services.normalization import (
    compute_content_hash,
    normalize_domain,
    normalize_publisher,
)
from backend.services.providers.base import BaseEvidenceProvider
from backend.services.source_registry import AuthorityClassification


# Standard XML Namespaces for OAI-PMH and Dublin Core
OAI_NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# Language normalization dictionary for WHO IRIS records
WHO_LANGUAGE_MAP: Dict[str, str] = {
    "english": "en",
    "en": "en",
    "eng": "en",
    "español": "es",
    "es": "es",
    "spa": "es",
    "spanish": "es",
    "hindi": "hi",
    "hi": "hi",
    "hin": "hi",
    "हिन्दी": "hi",
    "bengali": "bn",
    "bn": "bn",
    "ben": "bn",
    "বাংলা": "bn",
    "français": "fr",
    "french": "fr",
    "fr": "fr",
    "fra": "fr",
    "russian": "ru",
    "ru": "ru",
    "rus": "ru",
    "русский": "ru",
    "arabic": "ar",
    "ar": "ar",
    "ara": "ar",
    "chinese": "zh",
    "zh": "zh",
    "zho": "zh",
    "中文": "zh",
    "português": "pt",
    "portuguese": "pt",
    "pt": "pt",
}


class WhoIrisProvider(BaseEvidenceProvider):
    """Retrieves authoritative WHO publications from the WHO IRIS digital repository."""

    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(
            name="WHO Institutional Repository (IRIS)",
            source_tier="PRIMARY",
            timeout_seconds=timeout_seconds,
        )
        self.oai_base_url: str = getattr(settings, "WHO_IRIS_OAI_URL", "https://iris.who.int/oai/request")
        self.search_api_url: str = "https://iris.who.int/server/api/discover/search/objects"

    @staticmethod
    def normalize_language_code(raw_langs: List[str], text_sample: str = "") -> str:
        """Map raw language strings to ISO 639-1, avoiding speculative guesses.
        
        If language is missing, ambiguous, or undetermined, returns 'und'.
        """
        if raw_langs:
            for l in raw_langs:
                cleaned = l.strip().lower()
                if cleaned in WHO_LANGUAGE_MAP:
                    return WHO_LANGUAGE_MAP[cleaned]
                # Check Devanagari or Bengali literal
                if "हिन्दी" in l or "hindi" in cleaned:
                    return "hi"
                if "বাংলা" in l or "bengali" in cleaned:
                    return "bn"

        # Check script of text sample if language metadata was absent
        if text_sample:
            has_hi = any(0x0900 <= ord(c) <= 0x097F for c in text_sample if c != "।")
            has_bn = any(0x0980 <= ord(c) <= 0x09FF for c in text_sample)
            if has_bn:
                return "bn"
            if has_hi:
                return "hi"

        return "und"

    @staticmethod
    def extract_parent_study_handle(
        relations: List[str],
        title: str,
        current_handle: str = "",
    ) -> Optional[str]:
        """Extract parent study Handle identifier for translations and versions."""
        if relations:
            for rel in relations:
                # e.g., 'Related document (main document): https://iris.who.int/handle/10665/385625'
                handle_match = re.search(r"10665/(\d+)", rel)
                if handle_match:
                    h = f"10665/{handle_match.group(1)}"
                    if h != current_handle:
                        return h

        # Check for translation / version markers in title
        # e.g., 'Title [Hindi translation of WHO/EPI/2021]' or 'Title = French Title'
        parent_match = re.search(r"(?:translation of|isversionof|version of|parent)\s*[:=]?\s*([A-Za-z0-9_/-]+)", title, re.IGNORECASE)
        if parent_match:
            return parent_match.group(1).strip()

        return None

    def _execute_http_get_raw(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Execute HTTP GET returning raw string payload (for XML or JSON)."""
        req_headers = {"User-Agent": self.user_agent}
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status != 200:
                    return None, f"HTTP Error {response.status}: {response.reason}"
                payload = response.read().decode("utf-8", errors="replace")
                return payload, None
        except urllib.error.HTTPError as http_err:
            return None, f"HTTP {http_err.code}: {http_err.reason}"
        except urllib.error.URLError as url_err:
            return None, f"Network/Connection error: {str(url_err.reason)}"
        except TimeoutError:
            return None, f"Request timed out after {self.timeout_seconds}s"
        except Exception as exc:
            return None, f"Unexpected error: {str(exc)}"

    def parse_oai_dc_record(self, record_element: ET.Element) -> Optional[EvidenceItem]:
        """Parse a single OAI-PMH record element containing oai_dc:dc metadata."""
        header = record_element.find("{http://www.openarchives.org/OAI/2.0/}header")
        if header is None:
            return None
        
        # Check if record is deleted
        if header.attrib.get("status") == "deleted":
            return None

        oai_id = header.findtext("{http://www.openarchives.org/OAI/2.0/}identifier") or ""
        handle_match = re.search(r"10665/(\d+)", oai_id)
        raw_handle = f"10665/{handle_match.group(1)}" if handle_match else oai_id.replace(":", "_").replace("/", "_")

        dc_elem = record_element.find(".//{http://www.openarchives.org/OAI/2.0/oai_dc/}dc")
        if dc_elem is None:
            return None

        # Extract titles
        titles = [e.text.strip() for e in dc_elem.findall("{http://purl.org/dc/elements/1.1/}title") if e.text]
        title = titles[0] if titles else "Untitled WHO Publication"

        # Extract publishers
        publishers = [e.text.strip() for e in dc_elem.findall("{http://purl.org/dc/elements/1.1/}publisher") if e.text]
        publisher = publishers[0] if publishers else "World Health Organization"
        canonical_pub = "World Health Organization"

        # Extract dates
        dates = [e.text.strip() for e in dc_elem.findall("{http://purl.org/dc/elements/1.1/}date") if e.text]
        published_date = None
        for d in dates:
            # Prefer YYYY-MM-DD or YYYY
            date_m = re.search(r"\b(\d{4}(?:-\d{2}-\d{2})?)\b", d)
            if date_m:
                published_date = date_m.group(1)
                break

        # Extract descriptions / abstracts
        descriptions = [e.text.strip() for e in dc_elem.findall("{http://purl.org/dc/elements/1.1/}description") if e.text]
        # Filter out purely pagination descriptions (e.g. '12 p.', '484 p.')
        substantive_desc = [d for d in descriptions if len(d) > 30 and not re.match(r"^\d+\s*p\.?$", d.strip())]
        abstract = substantive_desc[0] if substantive_desc else (descriptions[0] if descriptions else None)

        # Extract identifiers / URLs
        identifiers = [e.text.strip() for e in dc_elem.findall("{http://purl.org/dc/elements/1.1/}identifier") if e.text]
        handle_url = next((i for i in identifiers if "handle/10665" in i), f"https://iris.who.int/handle/{raw_handle}")

        # Extract languages
        languages = [e.text.strip() for e in dc_elem.findall("{http://purl.org/dc/elements/1.1/}language") if e.text]
        doc_lang = self.normalize_language_code(languages, text_sample=f"{title} {abstract or ''}")

        # Extract relations (for parent study and translation tracking)
        relations = [e.text.strip() for e in dc_elem.findall("{http://purl.org/dc/elements/1.1/}relation") if e.text]
        parent_handle = self.extract_parent_study_handle(relations, title, current_handle=raw_handle)

        # Classify text availability and build snippet
        if abstract and len(abstract) > 50:
            text_avail = "ABSTRACT"
            snippet = f"WHO IRIS Abstract: {abstract}"
        elif abstract:
            text_avail = "EXCERPT"
            snippet = f"WHO IRIS Excerpt: {abstract}"
        else:
            text_avail = "METADATA_ONLY"
            snippet = (
                f"WHO IRIS document record: '{title}' ({published_date or 'date unrecorded'}). "
                f"Published by {publisher}. Full-text report indexed at {handle_url}."
            )

        # Translation and Independence Status
        is_translation = False
        underlying_source_id = None
        ind_status = "INDEPENDENT"
        original_lang = doc_lang

        if parent_handle:
            is_translation = True
            underlying_source_id = f"who-iris-{parent_handle.replace('/', '_')}"
            ind_status = "TRANSLATION_COPY"
            original_lang = "en"  # Most parent WHO reports are published in English first
        elif doc_lang in ("hi", "bn") and any(k in title.lower() for k in ("translation", "translated", "version")):
            is_translation = True
            ind_status = "TRANSLATION_COPY"
            underlying_source_id = f"who-iris-parent-{raw_handle.replace('/', '_')}"
            original_lang = "en"

        clean_item_id = f"who-iris-{raw_handle.replace('/', '_')}"
        content_hash = hashlib.sha256(snippet.encode("utf-8")).hexdigest()

        return EvidenceItem(
            id=clean_item_id,
            title=title,
            publisher=publisher,
            canonical_publisher=canonical_pub,
            url=handle_url,
            canonical_url=handle_url,
            published_date=published_date,
            snippet=snippet,
            stance="NEUTRAL",
            is_verified=False,  # Invariant: external dynamic records are NEVER pre-verified
            source_domain="iris.who.int",
            canonical_domain="who.int",
            source_tier="PRIMARY",
            source_type="GOVERNMENT_PUBLICATION",
            text_availability=text_avail,
            is_full_text=False,  # Invariant: metadata/abstract is never full text
            content_sha256=content_hash,
            underlying_source_id=underlying_source_id,
            independence_status=ind_status,
            is_machine_translated=False,
            translation_engine="WHO Official Translation" if is_translation else None,
            original_language=original_lang,
            traceability={
                "provider": "who_iris",
                "handle": raw_handle,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "authority_classification": AuthorityClassification.INTERGOVERNMENTAL_PRIMARY,
                "underlying_source_id": underlying_source_id or "",
                "independence_status": ind_status,
                "detected_language": doc_lang,
            },
        )

    def parse_dspace_json_item(self, item_dict: dict) -> Optional[EvidenceItem]:
        """Parse a single indexableObject from DSpace 7 Discover REST API."""
        if not isinstance(item_dict, dict):
            return None

        handle = item_dict.get("handle") or item_dict.get("id") or "unknown"
        clean_handle = handle.replace("/", "_")
        name = item_dict.get("name") or "Untitled WHO Publication"
        metadata = item_dict.get("metadata", {})

        # Title
        title_objs = metadata.get("dc.title", [])
        title = title_objs[0].get("value") if title_objs else name

        # Publisher
        pub_objs = metadata.get("dc.publisher", [])
        publisher = pub_objs[0].get("value") if pub_objs else "World Health Organization"

        # Date issued
        date_objs = metadata.get("dc.date.issued", [])
        raw_date = date_objs[0].get("value") if date_objs else None
        pub_date = None
        if raw_date:
            date_m = re.search(r"\b(\d{4}(?:-\d{2}-\d{2})?)\b", raw_date)
            pub_date = date_m.group(1) if date_m else raw_date

        # Abstract
        abs_objs = metadata.get("dc.description.abstract", [])
        abstract = abs_objs[0].get("value") if abs_objs else None

        # Identifier URI / Canonical URL
        uri_objs = metadata.get("dc.identifier.uri", [])
        url = uri_objs[0].get("value") if uri_objs else f"https://iris.who.int/handle/{handle}"

        # Languages
        lang_objs = metadata.get("dc.language.iso", []) or metadata.get("dc.language", [])
        raw_langs = [l.get("value") for l in lang_objs if isinstance(l, dict) and l.get("value")]
        doc_lang = self.normalize_language_code(raw_langs, text_sample=f"{title} {abstract or ''}")

        # Relations (parent study)
        rel_objs = metadata.get("dc.relation.isversionof", []) or metadata.get("dc.relation", [])
        raw_rels = [r.get("value") for r in rel_objs if isinstance(r, dict) and r.get("value")]
        parent_handle = self.extract_parent_study_handle(raw_rels, title, current_handle=handle)

        # Text availability
        if abstract and len(abstract) > 50:
            text_avail = "ABSTRACT"
            snippet = f"WHO IRIS Abstract: {abstract.strip()}"
        elif abstract:
            text_avail = "EXCERPT"
            snippet = f"WHO IRIS Excerpt: {abstract.strip()}"
        else:
            text_avail = "METADATA_ONLY"
            snippet = (
                f"WHO IRIS document record: '{title}' ({pub_date or 'date unrecorded'}). "
                f"Published by {publisher}. Full-text report indexed at {url}."
            )

        # Translation provenance
        is_translation = False
        underlying_source_id = None
        ind_status = "INDEPENDENT"
        original_lang = doc_lang

        if parent_handle:
            is_translation = True
            underlying_source_id = f"who-iris-{parent_handle.replace('/', '_')}"
            ind_status = "TRANSLATION_COPY"
            original_lang = "en"
        elif doc_lang in ("hi", "bn") and any(k in title.lower() for k in ("translation", "translated", "version")):
            is_translation = True
            ind_status = "TRANSLATION_COPY"
            underlying_source_id = f"who-iris-parent-{clean_handle}"
            original_lang = "en"

        clean_id = f"who-iris-{clean_handle}"
        content_hash = hashlib.sha256(snippet.encode("utf-8")).hexdigest()

        return EvidenceItem(
            id=clean_id,
            title=title,
            publisher=publisher,
            canonical_publisher="World Health Organization",
            url=url,
            canonical_url=url,
            published_date=pub_date,
            snippet=snippet,
            stance="NEUTRAL",
            is_verified=False,
            source_domain="iris.who.int",
            canonical_domain="who.int",
            source_tier="PRIMARY",
            source_type="GOVERNMENT_PUBLICATION",
            text_availability=text_avail,
            is_full_text=False,
            content_sha256=content_hash,
            underlying_source_id=underlying_source_id,
            independence_status=ind_status,
            is_machine_translated=False,
            translation_engine="WHO Official Translation" if is_translation else None,
            original_language=original_lang,
            traceability={
                "provider": "who_iris",
                "handle": handle,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "authority_classification": AuthorityClassification.INTERGOVERNMENTAL_PRIMARY,
                "underlying_source_id": underlying_source_id or "",
                "independence_status": ind_status,
                "detected_language": doc_lang,
            },
        )

    def search(
        self,
        query: str,
        limit: int = 3,
        language: Optional[str] = None,
    ) -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search WHO IRIS for official WHO health publications.
        
        Attempts the DSpace 7 Discover REST API first; falls back to OAI-PMH
        harvesting if needed. Traps and reports network/endpoint errors honestly.
        """
        if not query or not query.strip():
            return [], "Empty search query"

        clean_q = query.strip()
        encoded_query = urllib.parse.quote(clean_q)
        target_size = max(1, min(limit, 5))

        search_url = f"{self.search_api_url}?query={encoded_query}&size={target_size}"
        raw_json, err = self._execute_http_get_raw(
            search_url,
            headers={"Accept": "application/json"},
        )

        if err:
            return [], f"WHO IRIS REST search error: {err}"

        if not raw_json:
            return [], "Empty response from WHO IRIS"

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return [], "Malformed JSON response from WHO IRIS REST search"

        search_res = data.get("_embedded", {}).get("searchResult", {})
        objects = search_res.get("_embedded", {}).get("objects", [])

        if not objects:
            return [], None

        items: List[EvidenceItem] = []
        for obj in objects:
            idx_obj = obj.get("_embedded", {}).get("indexableObject", {})
            parsed = self.parse_dspace_json_item(idx_obj)
            if parsed:
                items.append(parsed)

        return items[:limit], None

    def get_oai_record(self, handle_or_identifier: str) -> Tuple[Optional[EvidenceItem], Optional[str]]:
        """Fetch a specific publication by Handle or OAI identifier via OAI-PMH GetRecord."""
        if not handle_or_identifier or not handle_or_identifier.strip():
            return None, "Empty identifier"

        clean_id = handle_or_identifier.strip()
        if not clean_id.startswith("oai:iris.who.int:"):
            # Normalize handle (e.g. '10665/378497') to OAI identifier
            clean_id = f"oai:iris.who.int:{clean_id.replace('https://iris.who.int/handle/', '')}"

        req_url = f"{self.oai_base_url}?verb=GetRecord&identifier={urllib.parse.quote(clean_id)}&metadataPrefix=oai_dc"
        raw_xml, err = self._execute_http_get_raw(req_url, headers={"Accept": "text/xml"})

        if err:
            return None, f"WHO IRIS OAI-PMH error: {err}"

        if not raw_xml:
            return None, "Empty response from WHO IRIS OAI-PMH"

        try:
            root = ET.fromstring(raw_xml)
            record_elem = root.find(".//{http://www.openarchives.org/OAI/2.0/}record")
            if record_elem is None:
                # Check for OAI error element
                err_elem = root.find(".//{http://www.openarchives.org/OAI/2.0/}error")
                err_msg = err_elem.text if err_elem is not None else "Record not found in WHO IRIS OAI-PMH"
                return None, f"OAI-PMH error: {err_msg}"
            
            parsed_item = self.parse_oai_dc_record(record_elem)
            return parsed_item, None
        except ET.ParseError as pe:
            return None, f"XML Parse error on WHO IRIS OAI response: {pe}"
        except Exception as exc:
            return None, f"Unexpected error parsing WHO IRIS OAI record: {exc}"

