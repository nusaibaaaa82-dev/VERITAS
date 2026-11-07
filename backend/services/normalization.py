"""Domain, publisher, and syndication normalization utilities for VERITAS.

Ensures strict source independence validation by:
1. Canonicalizing domain names across subdomains and multi-part ccTLDs.
2. Mapping publisher variations to canonical publishing organizations.
3. Detecting wire service syndication (AP, Reuters, AFP) across secondary distributors.
4. Computing deterministic content digests for cross-domain duplicate detection.
"""

import hashlib
import re
from typing import Optional, Set, Tuple
import unicodedata
from urllib.parse import urlparse

# Multi-part ccTLDs where the domain name is the third-to-last component
MULTI_PART_TLDS: Set[str] = {
    "co.uk",
    "gov.uk",
    "org.uk",
    "ac.uk",
    "com.au",
    "gov.au",
    "edu.au",
    "org.au",
    "co.nz",
    "co.jp",
    "com.br",
    "co.in",
    "gov.in",
    "org.in",
    "com.mx",
    "co.za",
}

# Known Wire Services and their signature patterns in body text or bylines
WIRE_SERVICE_SIGNATURES = [
    (
        "Associated Press",
        re.compile(
            r"(?:\bAssociated Press\b|\(AP\)|(?:\b|\()AP\s*[-—–]|\bBy\s+[A-Za-z\s]+,\s*Associated Press\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "Reuters",
        re.compile(
            r"(?:\bReuters\b|\(Reuters\)|(?:\b|\()Reuters\s*[-—–]|\bBy\s+[A-Za-z\s]+,\s*Reuters\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "Agence France-Presse",
        re.compile(
            r"(?:\bAgence France-Presse\b|\(AFP\)|(?:\b|\()AFP\s*[-—–])",
            re.IGNORECASE,
        ),
    ),
    (
        "Bloomberg",
        re.compile(
            r"(?:\bBloomberg(?:\s+News)?\b|\(Bloomberg\)|(?:\b|\()Bloomberg\s*[-—–])",
            re.IGNORECASE,
        ),
    ),
    (
        "PR Newswire",
        re.compile(
            r"(?:\bPR Newswire\b|\bPRNewswire\b|\(PR Newswire\))",
            re.IGNORECASE,
        ),
    ),
]

# Canonical mapping for major news agencies, academic publishers, and fact-checkers
CANONICAL_PUBLISHER_MAP = {
    "bbc": "BBC",
    "bbc news": "BBC",
    "british broadcasting corporation": "BBC",
    "bbc.co.uk": "BBC",
    "bbc.com": "BBC",
    "reuters": "Reuters",
    "thomson reuters": "Reuters",
    "reuters.com": "Reuters",
    "associated press": "Associated Press",
    "the associated press": "Associated Press",
    "ap": "Associated Press",
    "ap news": "Associated Press",
    "apnews.com": "Associated Press",
    "agence france-presse": "Agence France-Presse",
    "agence france presse": "Agence France-Presse",
    "afp": "Agence France-Presse",
    "afp.com": "Agence France-Presse",
    "the new york times": "The New York Times",
    "new york times": "The New York Times",
    "nytimes.com": "The New York Times",
    "the washington post": "The Washington Post",
    "washington post": "The Washington Post",
    "washingtonpost.com": "The Washington Post",
    "the guardian": "The Guardian",
    "guardian": "The Guardian",
    "theguardian.com": "The Guardian",
    "nature": "Nature Publishing Group",
    "nature publishing group": "Nature Publishing Group",
    "nature.com": "Nature Publishing Group",
    "science": "AAAS / Science",
    "science.org": "AAAS / Science",
    "american association for the advancement of science": "AAAS / Science",
    "politifact": "PolitiFact",
    "politifact.com": "PolitiFact",
    "factcheck.org": "FactCheck.org",
    "factcheck": "FactCheck.org",
    "snopes": "Snopes",
    "snopes.com": "Snopes",
    "wikimedia foundation": "Wikimedia Foundation",
    "wikipedia": "Wikimedia Foundation",
    "openalex": "OpenAlex / OurResearch",
    "crossref": "Crossref",
}


def normalize_domain(url: Optional[str]) -> Optional[str]:
    """Extract canonical root domain from a source URL.

    Handles subdomains (e.g. 'news.bbc.co.uk' -> 'bbc.co.uk'),
    prefixes ('www.', 'm.', 'amp.'), and multi-part ccTLDs.
    """
    if not url:
        return None

    try:
        parsed = urlparse(url.strip())
        netloc = parsed.netloc.lower()
        if not netloc:
            # Handle URLs passed without scheme (e.g. 'reuters.com/article')
            if "/" in url:
                netloc = url.split("/")[0].lower()
            else:
                netloc = url.strip().lower()

        # Strip standard port if present
        if ":" in netloc:
            netloc = netloc.split(":")[0]

        parts = netloc.split(".")
        if len(parts) <= 1:
            return netloc

        # Check for multi-part ccTLDs (e.g. 'co.uk', 'com.au')
        if len(parts) >= 3:
            potential_tld = f"{parts[-2]}.{parts[-1]}"
            if potential_tld in MULTI_PART_TLDS:
                # Return the SLD + multi-part TLD (e.g. 'bbc.co.uk')
                return f"{parts[-3]}.{potential_tld}"

        # Standard TLD: return domain.tld (strip leading subdomains like www, news, m, amp)
        if len(parts) >= 2:
            return f"{parts[-2]}.{parts[-1]}"

        return netloc
    except Exception:
        return None


def normalize_publisher(
    publisher: Optional[str],
    domain: Optional[str] = None,
) -> Optional[str]:
    """Normalize publisher names across stylistic variations and domains."""
    if not publisher and not domain:
        return None

    # Check publisher string
    if publisher:
        clean_pub = publisher.strip().lower()
        if clean_pub in CANONICAL_PUBLISHER_MAP:
            return CANONICAL_PUBLISHER_MAP[clean_pub]

    # Check domain
    if domain:
        clean_dom = domain.strip().lower()
        if clean_dom.startswith("www."):
            clean_dom = clean_dom[4:]
        if clean_dom in CANONICAL_PUBLISHER_MAP:
            return CANONICAL_PUBLISHER_MAP[clean_dom]

    # Fallback to cleaned title case publisher or domain
    if publisher:
        return publisher.strip()
    return domain.strip() if domain else None


# Known Government and Intergovernmental Organizations (IGOs)
GOVERNMENT_ENTITIES = {
    "nasa",
    "u.s. geological survey",
    "usgs",
    "noaa",
    "national oceanic and atmospheric administration",
    "world health organization",
    "who",
    "centers for disease control and prevention",
    "cdc",
    "united nations",
    "un",
    "world bank",
    "european union",
    "ipcc",
    "intergovernmental panel on climate change",
    "national institute of standards and technology",
    "nist",
    "department of energy",
    "doe",
}

GOVERNMENT_TLDS_DOMAINS = {
    ".gov",
    ".gov.uk",
    ".gov.au",
    ".mil",
    "who.int",
    "un.org",
    "worldbank.org",
    "nasa.gov",
    "usgs.gov",
    "noaa.gov",
    "cdc.gov",
    "nih.gov",
}

# Known Reference and Encyclopedic Publishers
REFERENCE_PUBLISHERS = {
    "wikimedia foundation",
    "wikipedia",
    "encyclopaedia britannica",
    "britannica",
    "sage publications",
    "sage reference",
    "oxford reference",
    "routledge encyclopedia",
}


def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 digest of normalized snippet content."""
    normalized_text = " ".join(text.strip().split())
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def _extract_similarity_tokens(text: str) -> Set[str]:
    """Extract Unicode word tokens (Latin, Devanagari, Bengali, etc.) for similarity comparison."""
    if not text:
        return set()
    tokens: Set[str] = set()
    curr: List[str] = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("N") or cat.startswith("M"):
            curr.append(ch)
        else:
            if curr:
                w = "".join(curr)
                if len(w) >= 3 or (len(w) >= 2 and any(ord(c) >= 128 for c in w)):
                    tokens.add(w)
                curr = []
    if curr:
        w = "".join(curr)
        if len(w) >= 3 or (len(w) >= 2 and any(ord(c) >= 128 for c in w)):
            tokens.add(w)
    return tokens


def compute_text_similarity(text1: str, text2: str) -> float:
    """Compute token Jaccard similarity between two texts for duplicate/syndication analysis.

    Unicode-aware: correctly extracts tokens from Latin, Devanagari, Bengali, and other scripts
    preserving combining vowel signs and diacritics.
    """
    if not text1 or not text2:
        return 0.0

    tokens1 = _extract_similarity_tokens(text1)
    tokens2 = _extract_similarity_tokens(text2)

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def classify_source(
    provider_name: str,
    raw_type: Optional[str] = None,
    publisher: Optional[str] = None,
    domain: Optional[str] = None,
    title: Optional[str] = None,
    has_abstract: bool = False,
    is_full_text: bool = False,
) -> Tuple[str, str, str]:
    """Classify evidence source tier, granular source type, and text availability.

    Reliability Rules:
    - Never classify all OpenAlex or Crossref records as PRIMARY.
    - Distinguish original research, review papers, metadata records, government publications, and encyclopedias.
    - Clearly distinguish metadata, abstracts, excerpts, and full text.
    - Never claim to have read full text when only metadata or an abstract is available.

    Returns:
    (source_tier, source_type, text_availability)
    """
    clean_pub = (publisher or "").strip().lower()
    clean_dom = (domain or "").strip().lower()
    clean_type = (raw_type or "").strip().lower()
    clean_title = (title or "").strip().lower()

    # 1. Determine Text Availability
    if is_full_text:
        text_availability = "FULL_TEXT"
    elif has_abstract:
        text_availability = "ABSTRACT"
    elif provider_name.lower() in ("wikimedia", "wikipedia") or "wikipedia.org" in clean_dom:
        text_availability = "EXCERPT"
    else:
        text_availability = "METADATA_ONLY"

    # 2. If only citation metadata is available (no abstract or text)
    if text_availability == "METADATA_ONLY":
        return "METADATA_ONLY", "METADATA_RECORD", text_availability

    # 3. Check for Government / IGO publications
    is_gov = (
        clean_pub in GOVERNMENT_ENTITIES
        or any(clean_pub.startswith(gov) for gov in GOVERNMENT_ENTITIES)
        or any(clean_dom.endswith(tld) or tld in clean_dom for tld in GOVERNMENT_TLDS_DOMAINS)
    )
    if is_gov:
        # Government observational datasets or scientific bulletins are PRIMARY; policy overviews are SECONDARY
        tier = "PRIMARY" if "data" in clean_type or "report" in clean_type else "SECONDARY"
        return tier, "GOVERNMENT_PUBLICATION", text_availability

    # 4. Check for Encyclopedic / Reference Summaries
    is_encyclopedia = (
        provider_name.lower() in ("wikimedia", "wikipedia")
        or "wikipedia.org" in clean_dom
        or clean_type in ("reference-entry", "book-chapter")
        or any(ref_pub in clean_pub for ref_pub in REFERENCE_PUBLISHERS)
    )
    if is_encyclopedia:
        return "TERTIARY", "ENCYCLOPEDIC_SUMMARY", text_availability

    # 5. Check for Review Papers / Meta-Analyses
    review_markers = ["systematic review", "meta-analysis", "a review of", "literature review", "scoping review"]
    is_review = clean_type == "review" or any(marker in clean_title for marker in review_markers)
    if is_review:
        return "SECONDARY", "REVIEW_PAPER", text_availability

    # 6. Check for Preprints
    preprint_domains = ["arxiv.org", "biorxiv.org", "medrxiv.org", "preprints.org"]
    is_preprint = clean_type == "posted-content" or any(p_dom in clean_dom for p_dom in preprint_domains)
    if is_preprint:
        return "SECONDARY", "PREPRINT", text_availability

    # 7. Check for Direct Wire Dispatches
    is_direct_wire = any(wire[0].lower() in clean_pub or wire[0].lower() in clean_dom for wire in WIRE_SERVICE_SIGNATURES)
    if is_direct_wire:
        return "PRIMARY", "WIRE_DISPATCH", text_availability

    # 8. Check for Original Research Journal Articles
    is_journal_article = clean_type in ("article", "journal-article", "proceedings-article") or (
        has_abstract and provider_name in ("OpenAlex Scholarly Index", "Crossref DOI Registry", "OpenAlex", "Crossref")
    )
    if is_journal_article:
        return "PRIMARY", "ORIGINAL_RESEARCH", text_availability

    # 9. Default Journalistic News Reporting or Secondary Source
    return "SECONDARY", "NEWS_REPORT", text_availability


def detect_syndication(
    snippet: str,
    publisher: Optional[str] = None,
    domain: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Detect potential wire service syndication (AP, Reuters, AFP, Bloomberg).

    Returns:
    (is_potential_syndication, syndication_notes, wire_agency)
    """
    if not snippet:
        return False, None, None

    norm_pub = (normalize_publisher(publisher, domain) or "").lower()
    norm_dom = (normalize_domain(domain) or "").lower()

    for wire_name, pattern in WIRE_SERVICE_SIGNATURES:
        if pattern.search(snippet):
            wire_lower = wire_name.lower()
            # If the article itself is published directly by the wire agency, it's the primary dispatch
            if wire_lower in norm_pub or wire_lower in norm_dom:
                return False, f"Primary dispatch published by {wire_name}", wire_name

            # Republished on a third-party domain -> Syndicated wire report
            distributor = publisher or domain or "secondary publisher"
            notes = (
                f"Potential syndicated wire report: contains {wire_name} dispatch signature (identified wire: {wire_name}), "
                f"republished by '{distributor}'. Does not constitute independent corroboration from {wire_name}."
            )
            return True, notes, wire_name

    return False, None, None
