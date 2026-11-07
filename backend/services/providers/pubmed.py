"""NCBI PubMed Public Evidence Provider for VERITAS.

Queries the National Center for Biotechnology Information (NCBI) PubMed E-utilities API
(eutils.ncbi.nlm.nih.gov) to discover peer-reviewed biomedical research, clinical trials,
and systematic reviews across 36M+ biomedical citations.

Reliability Rules:
1. Free public endpoint only (no API key, zero cost).
2. Preserves real PMIDs, DOIs, canonical URLs, titles, publication dates, and journal publishers.
3. Distinguishes peer-reviewed abstracts from metadata-only citations (is_full_text=False).
4. Academic publication or abstract alone is NEVER proof of truth (is_verified=False).
5. All retrieved items retain traceability and content hashes.
"""

from datetime import datetime, timezone
import re
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


class PubMedProvider(BaseEvidenceProvider):
    """Retrieves biomedical research and review papers from the free NCBI PubMed API."""

    def __init__(self, timeout_seconds: Optional[float] = None):
        super().__init__(
            name="NCBI PubMed",
            source_tier="PRIMARY",
            timeout_seconds=timeout_seconds,
        )
        self.search_url = settings.PUBMED_ESEARCH_URL
        self.summary_url = settings.PUBMED_ESUMMARY_URL
        self.fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def _fetch_abstract(self, pmid: str) -> Optional[str]:
        """Fetch plain-text abstract for a specific PubMed ID using efetch."""
        fetch_endpoint = f"{self.fetch_url}?db=pubmed&id={pmid}&rettype=abstract&retmode=text"
        try:
            req = urllib.request.Request(
                fetch_endpoint,
                headers={"User-Agent": self.user_agent, "Accept": "text/plain"},
            )
            with urllib.request.urlopen(req, timeout=min(5.0, self.timeout_seconds)) as response:
                if response.status == 200:
                    text = response.read().decode("utf-8", errors="replace")
                    # Extract abstract text block (after author information)
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    # Look for paragraph after Author information or DOI header
                    abstract_paragraphs = []
                    recording = False
                    for line in lines:
                        if line.startswith("Author information:") or line.startswith("DOI:"):
                            recording = True
                            continue
                        if recording:
                            if line.startswith("PMID:") or line.startswith("PMCID:") or line.startswith("Conflict of interest"):
                                break
                            # Filter out email lines or short affiliation lines
                            if not line.startswith("(") and len(line) > 30 and "@" not in line:
                                abstract_paragraphs.append(line)
                    if abstract_paragraphs:
                        clean_abstract = " ".join(abstract_paragraphs)
                        return clean_abstract if len(clean_abstract) >= 60 else None
        except Exception:
            return None
        return None

    def search(self, query: str, limit: int = 3) -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search PubMed for peer-reviewed biomedical literature matching claim query."""
        if not query or not query.strip():
            return [], "Empty search query"

        encoded_query = urllib.parse.quote(query.strip())
        search_endpoint = f"{self.search_url}?db=pubmed&term={encoded_query}&retmode=json&retmax={max(1, min(limit, 5))}"

        data, err = self._execute_http_get(search_endpoint)
        if err:
            return [], f"PubMed search error: {err}"

        if not data or "esearchresult" not in data or "idlist" not in data["esearchresult"]:
            return [], "PubMed response contained no 'idlist'"

        id_list = data["esearchresult"]["idlist"]
        if not id_list:
            return [], None

        id_str = ",".join(id_list)
        summary_endpoint = f"{self.summary_url}?db=pubmed&id={id_str}&retmode=json"
        sum_data, sum_err = self._execute_http_get(summary_endpoint)
        if sum_err or not sum_data or "result" not in sum_data:
            return [], f"PubMed summary error: {sum_err or 'No result key'}"

        evidence_items: List[EvidenceItem] = []
        result_dict = sum_data["result"]

        for pmid in id_list:
            doc = result_dict.get(pmid)
            if not doc:
                continue

            unique_id = f"pubmed-{pmid}"
            title = doc.get("title") or "Biomedical Research Publication"
            # Strip trailing period from title
            title = title.rstrip(".")

            journal = doc.get("source") or "National Library of Medicine"
            pub_date = doc.get("pubdate") or doc.get("epubdate")

            # Extract DOI if present in articleids
            doi = None
            for aid in doc.get("articleids", []):
                if aid.get("idtype") == "doi":
                    doi = aid.get("value")
                    break

            canonical_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            if doi:
                doi_url = f"https://doi.org/{doi}"
            else:
                doi_url = canonical_url

            # Attempt to fetch abstract
            abstract = self._fetch_abstract(pmid)
            if abstract:
                snippet = f"Abstract: {abstract}"
                text_availability = "ABSTRACT"
            else:
                snippet = (
                    f"PubMed biomedical record for '{title}' published in '{journal}' ({pub_date or 'date unrecorded'}). "
                    f"PMID: {pmid}. Full-text abstract not indexed in public summary."
                )
                text_availability = "METADATA_ONLY"

            content_hash = compute_content_hash(snippet)
            domain = normalize_domain(canonical_url) or "pubmed.ncbi.nlm.nih.gov"
            norm_pub = normalize_publisher(journal, domain)

            # Classify source tier and type
            is_review = "review" in title.lower() or "meta-analysis" in title.lower()
            source_type = "REVIEW_PAPER" if is_review else ("ORIGINAL_RESEARCH" if abstract else "METADATA_RECORD")
            source_tier = "SECONDARY" if is_review else ("PRIMARY" if abstract else "METADATA_ONLY")

            traceability = {
                "provider": "eutils.ncbi.nlm.nih.gov",
                "pmid": pmid,
                "doi": doi or "N/A",
                "journal": journal,
                "text_availability": text_availability,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "methodology_notice": (
                    "NCBI PubMed biomedical index record. Publication of an abstract alone "
                    "does not constitute independent verification of factual truth."
                ),
            }

            evidence_items.append(
                EvidenceItem(
                    id=unique_id,
                    title=title,
                    publisher=journal,
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
                    source_tier=source_tier,
                    source_type=source_type,
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

