"""VERITAS Evidence Source Registry.

Maintains the authoritative registry of evidence discovery sources across domains:
- Health
- Climate and Environment
- Immigration and Governance
- General Science

Enforces strict authority classifications, zero-cost public access policies,
language limitations, and independence safeguards.

Rules:
- Do not classify think tanks (e.g. Cato Institute) or universities/independent academies
  (e.g. NASEM, Stanford University, NBER) as government agencies.
- Think tanks are classified as THINK_TANK_ADVOCACY.
- Independent academies and universities are classified as ACADEMIC_SCHOLARLY.
- Executive and federal departments are classified as GOVERNMENT_PRIMARY.
- International treaty bodies are classified as INTERGOVERNMENTAL_PRIMARY.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class AuthorityClassification(str, Enum):
    """Authority tier classification for evidence discovery sources."""
    GOVERNMENT_PRIMARY = "GOVERNMENT_PRIMARY"
    INTERGOVERNMENTAL_PRIMARY = "INTERGOVERNMENTAL_PRIMARY"
    ACADEMIC_SCHOLARLY = "ACADEMIC_SCHOLARLY"
    THINK_TANK_ADVOCACY = "THINK_TANK_ADVOCACY"
    SCHOLARLY_PEER_REVIEWED = "SCHOLARLY_PEER_REVIEWED"
    SCHOLARLY_INDEX = "SCHOLARLY_INDEX"
    TERTIARY_ENCYCLOPEDIC = "TERTIARY_ENCYCLOPEDIC"
    OFFICIAL_LEGAL_STATUTE = "OFFICIAL_LEGAL_STATUTE"
    HYBRID_MULTI_TIER = "HYBRID_MULTI_TIER"


class DomainType(str, Enum):
    """Target verification domain."""
    HEALTH = "HEALTH"
    CLIMATE = "CLIMATE"
    IMMIGRATION = "IMMIGRATION"
    GENERAL_SCIENCE = "GENERAL_SCIENCE"
    CROSS_DOMAIN = "CROSS_DOMAIN"


@dataclass
class SourceRegistryEntry:
    """Descriptor for an integrated or audited evidence source in VERITAS."""
    provider_id: str
    display_name: str
    domains: List[DomainType]
    source_tier: str  # PRIMARY, SECONDARY, TERTIARY
    authority_classification: AuthorityClassification
    official_api_url: Optional[str]
    is_integrated: bool
    authentication_required: bool
    free_usage_conditions: str
    rate_limits: str
    retrieval_capabilities: List[str]
    languages_supported: List[str]
    text_availability: List[str]  # FULL_TEXT, ABSTRACT, EXCERPT, METADATA_ONLY
    provenance_requirements: List[str]
    independence_rules: str
    limitations_notes: str


SOURCE_REGISTRY: Dict[str, SourceRegistryEntry] = {
    # -------------------------------------------------------------------------
    # SCHOLARLY & INTERGOVERNMENTAL APIS (INTEGRATED)
    # -------------------------------------------------------------------------
    "pubmed": SourceRegistryEntry(
        provider_id="pubmed",
        display_name="NCBI PubMed E-Utilities",
        domains=[DomainType.HEALTH],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.SCHOLARLY_PEER_REVIEWED,
        official_api_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Free public service of the U.S. National Library of Medicine; zero cost.",
        rate_limits="Up to 3 requests/sec unauthenticated; 10 requests/sec with optional API key.",
        retrieval_capabilities=["MeSH headings", "Abstract full-text", "Boolean search", "Author/Date filter"],
        languages_supported=["en", "multilingual_abstracts"],
        text_availability=["ABSTRACT", "METADATA_ONLY"],
        provenance_requirements=["PMID", "DOI", "Journal Title", "Publication Date", "SHA-256"],
        independence_rules="Multiple papers citing the exact same clinical trial or dataset are linked to that trial.",
        limitations_notes="Paywalled full text; evaluates abstracts; low coverage of non-biomedical claims.",
    ),
    "who_gho": SourceRegistryEntry(
        provider_id="who_gho",
        display_name="WHO Global Health Observatory (GHO)",
        domains=[DomainType.HEALTH],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.INTERGOVERNMENTAL_PRIMARY,
        official_api_url="https://ghoapi.azureedge.net/api/",
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Free public OData REST service of the World Health Organization.",
        rate_limits="Polite access (~5 requests/sec).",
        retrieval_capabilities=["OData filter contains()", "Indicator search", "Dimension breakdowns"],
        languages_supported=["en"],
        text_availability=["ABSTRACT", "METADATA_ONLY"],
        provenance_requirements=["Indicator Code", "Indicator Name", "WHO Canonical URL", "Timestamp", "SHA-256"],
        independence_rules="Represents official WHO intergovernmental epidemiological consensus.",
        limitations_notes="Structured indicator metrics rather than narrative medical literature.",
    ),
    "who_iris": SourceRegistryEntry(
        provider_id="who_iris",
        display_name="WHO Institutional Repository for Information Sharing (IRIS)",
        domains=[DomainType.HEALTH],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.INTERGOVERNMENTAL_PRIMARY,
        official_api_url="https://iris.who.int/oai/request",
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Free public OAI-PMH 2.0 and DSpace REST service of the World Health Organization.",
        rate_limits="Polite automated access (1-3 requests/sec); supports resumptionToken pagination.",
        retrieval_capabilities=["OAI-PMH Dublin Core", "DSpace 7 Discover REST", "Handle URLs", "Multilingual guidelines (EN, ES, HI, BN)"],
        languages_supported=["en", "es", "hi", "bn", "fr", "ar", "ru", "zh"],
        text_availability=["ABSTRACT", "EXCERPT", "METADATA_ONLY"],
        provenance_requirements=["Handle Identifier", "WHO Publication Date", "Language", "Original Document URL", "Parent Identifier", "SHA-256"],
        independence_rules="Official WHO guidelines, technical reports, and regional factsheets. Translated copies link to parent study and collapse into 1 source vote.",
        limitations_notes="Full text is available in PDF format; provider extracts Dublin Core metadata and substantive abstracts.",
    ),
    "world_bank": SourceRegistryEntry(
        provider_id="world_bank",
        display_name="World Bank Documents & Reports (WDS)",
        domains=[DomainType.IMMIGRATION, DomainType.HEALTH, DomainType.CLIMATE, DomainType.GENERAL_SCIENCE],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.INTERGOVERNMENTAL_PRIMARY,
        official_api_url="https://search.worldbank.org/api/v2/wds",
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Free public REST API provided by the World Bank Group; zero cost; no API key required.",
        rate_limits="Polite automated access (standard public web limits ~5 requests/sec).",
        retrieval_capabilities=[
            "Full-text/Abstract search via qterm",
            "Report type filtering (Working Papers, Economic Reports, Policy Research)",
            "Language filtering and exact match (EN, ES, HI, BN)",
            "Multi-language edition tracking (available_in, fullavailablein)",
            "Project ID and Report Number canonical metadata",
        ],
        languages_supported=["en", "es", "hi", "bn", "fr", "ar", "ru", "zh"],
        text_availability=["ABSTRACT", "EXCERPT", "METADATA_ONLY"],
        provenance_requirements=[
            "Document ID",
            "Report Number",
            "Project ID",
            "Canonical Curated URL",
            "Publication Date",
            "Official Language",
            "SHA-256",
        ],
        independence_rules=(
            "Official World Bank Group intergovernmental research and project documents. "
            "Translated copies link to parent project/report (underlying_source_id) and collapse into 1 source vote. "
            "Administrative loan and project appraisal documents must not be treated as independent verification of natural science or medical clinical claims."
        ),
        limitations_notes=(
            "API returns metadata and abstracts (or cdata snippet); full PDFs require external download. "
            "Non-English holdings vary widely (e.g. 96 Hindi and 29 Bengali documents cataloged vs hundreds of thousands in English/Spanish). "
            "Loan agreements and administrative documents must be filtered for proposition relevance."
        ),
    ),
    "nasa_ntrs": SourceRegistryEntry(
        provider_id="nasa_ntrs",
        display_name="NASA Technical Reports Server (NTRS)",
        domains=[DomainType.CLIMATE, DomainType.GENERAL_SCIENCE],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.GOVERNMENT_PRIMARY,
        official_api_url="https://ntrs.nasa.gov/api/citations/search",
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Free public access to U.S. aerospace, Earth science, and atmospheric research.",
        rate_limits="Standard public web limits (~5 requests/sec).",
        retrieval_capabilities=["Full-text and abstract keyword search", "Earth observations", "Author/Date filter"],
        languages_supported=["en"],
        text_availability=["ABSTRACT", "METADATA_ONLY"],
        provenance_requirements=["NTRS Citation ID", "NASA Center", "Report Number", "SHA-256"],
        independence_rules="Direct primary research from NASA mission scientists and instrument observations.",
        limitations_notes="English-only technical documents; domain-restricted to aerospace and Earth observations.",
    ),
    "usgs_pubs": SourceRegistryEntry(
        provider_id="usgs_pubs",
        display_name="USGS Publications Warehouse",
        domains=[DomainType.CLIMATE, DomainType.GENERAL_SCIENCE],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.GOVERNMENT_PRIMARY,
        official_api_url="https://pubs.er.usgs.gov/service/documentation/products",
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Free public access to U.S. Geological Survey research monographs and reports.",
        rate_limits="Standard polite request rate (~5 requests/sec).",
        retrieval_capabilities=["Keyword search", "Hydrological and geological series", "Subseries filtering"],
        languages_supported=["en"],
        text_availability=["ABSTRACT", "METADATA_ONLY"],
        provenance_requirements=["USGS Report ID", "Series Name", "Publication Year", "SHA-256"],
        independence_rules="Primary government geological, hydrological, and seismic monographs.",
        limitations_notes="U.S.-focused geography; English only; no sociological or health coverage.",
    ),
    "openalex": SourceRegistryEntry(
        provider_id="openalex",
        display_name="OpenAlex Scholarly Works Catalog",
        domains=[DomainType.HEALTH, DomainType.CLIMATE, DomainType.IMMIGRATION, DomainType.GENERAL_SCIENCE],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.SCHOLARLY_INDEX,
        official_api_url="https://api.openalex.org/works",
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Free open catalog under CC0 license; polite pool with email in User-Agent.",
        rate_limits="Up to 10 requests/sec with polite User-Agent.",
        retrieval_capabilities=["Inverted abstract reconstruction", "Multilingual keyword search", "DOI lookup", "Concept filters"],
        languages_supported=["en", "es", "hi", "bn", "multilingual"],
        text_availability=["ABSTRACT", "METADATA_ONLY"],
        provenance_requirements=["OpenAlex Work ID", "DOI", "Primary Location", "Publication Year", "SHA-256"],
        independence_rules="Tracks primary DOIs; multiple records with identical DOIs collapsed into one source.",
        limitations_notes="Abstracts reconstructed from inverted index; non-English coverage uneven; paywalled full text.",
    ),
    "crossref": SourceRegistryEntry(
        provider_id="crossref",
        display_name="Crossref DOI Metadata Registry",
        domains=[DomainType.HEALTH, DomainType.CLIMATE, DomainType.IMMIGRATION, DomainType.GENERAL_SCIENCE],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.SCHOLARLY_INDEX,
        official_api_url="https://api.crossref.org/works",
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Free public bibliographic API; polite pool with mailto in User-Agent.",
        rate_limits="50 requests/sec in polite pool.",
        retrieval_capabilities=["DOI resolution", "Title and author bibliographic query", "Publisher verification"],
        languages_supported=["en", "multilingual_metadata"],
        text_availability=["METADATA_ONLY"],
        provenance_requirements=["DOI", "Publisher Name", "ISSN", "Deposited Date", "SHA-256"],
        independence_rules="Used for authority verification and DOI resolution; cannot corroborate factual propositions alone.",
        limitations_notes="Metadata-only (no abstracts or full texts); must be paired with substantive sources.",
    ),
    "wikimedia": SourceRegistryEntry(
        provider_id="wikimedia",
        display_name="Wikimedia REST API",
        domains=[DomainType.CROSS_DOMAIN],
        source_tier="TERTIARY",
        authority_classification=AuthorityClassification.TERTIARY_ENCYCLOPEDIC,
        official_api_url="https://en.wikipedia.org/w/rest.php/v1/search/page",
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Free public API under Wikimedia API Etiquette policy.",
        rate_limits="Polite rate limits (~10-20 requests/sec).",
        retrieval_capabilities=["Full-text search", "Lead extract summary", "Language-specific wikis (en, es, hi, bn)"],
        languages_supported=["en", "es", "hi", "bn"],
        text_availability=["EXCERPT"],
        provenance_requirements=["Wikipedia Page ID", "Language Code", "Article Revision URL", "SHA-256"],
        independence_rules="Strictly tertiary; never satisfies the 2-source primary corroboration rule.",
        limitations_notes="Crowdsourced secondary/tertiary synthesis; vulnerable to editing disputes; not primary research.",
    ),
    "local_repository": SourceRegistryEntry(
        provider_id="local_repository",
        display_name="VERITAS Local Evidence Repository (SQLite + FTS5)",
        domains=[DomainType.IMMIGRATION, DomainType.HEALTH, DomainType.CLIMATE, DomainType.GENERAL_SCIENCE],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.HYBRID_MULTI_TIER,
        official_api_url=None,
        is_integrated=True,
        authentication_required=False,
        free_usage_conditions="Local embedded zero-cost storage; no network latency or external rate limits.",
        rate_limits="Unlimited local SQLite queries.",
        retrieval_capabilities=["FTS5 full-text search", "Exact SHA-256 deduplication", "Multilingual indexing", "Verified tag filter"],
        languages_supported=["en", "es", "hi", "bn"],
        text_availability=["FULL_TEXT", "ABSTRACT", "EXCERPT"],
        provenance_requirements=["Canonical URL", "Source Domain", "Publisher", "Content SHA-256", "Provenance JSON"],
        independence_rules="Enforces strict wire syndication, shared-DOI discounting, and parent study linking.",
        limitations_notes="Corpus bounded by pre-cached and newly harvested verified records.",
    ),

    # -------------------------------------------------------------------------
    # AUDITED INSTITUTIONAL & GOVERNMENT SOURCES
    # -------------------------------------------------------------------------
    "census_bureau": SourceRegistryEntry(
        provider_id="census_bureau",
        display_name="U.S. Census Bureau (ACS / Decennial)",
        domains=[DomainType.IMMIGRATION],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.GOVERNMENT_PRIMARY,
        official_api_url="https://api.census.gov/data/",
        is_integrated=False,
        authentication_required=True,
        free_usage_conditions="Free registration required for API key; unauthenticated calls return Missing Key error.",
        rate_limits="500 requests/day unauthenticated; 50 requests/sec with key.",
        retrieval_capabilities=["Tabular demographic variables (B05001, B05002)", "No natural language full-text search"],
        languages_supported=["en"],
        text_availability=["FULL_TEXT", "METADATA_ONLY"],
        provenance_requirements=["Table Code", "Geography", "Release Year", "Census Table URL"],
        independence_rules="Authoritative U.S. Federal Government primary statistical agency (Department of Commerce).",
        limitations_notes="Requires API key; structured variable mapping only (cannot process free-text queries).",
    ),
    "nasem": SourceRegistryEntry(
        provider_id="nasem",
        display_name="National Academies of Sciences, Engineering, and Medicine (NASEM)",
        domains=[DomainType.IMMIGRATION, DomainType.HEALTH, DomainType.CLIMATE, DomainType.GENERAL_SCIENCE],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.ACADEMIC_SCHOLARLY,
        official_api_url="https://nap.nationalacademies.org/",
        is_integrated=False,
        authentication_required=False,
        free_usage_conditions="Open-access consensus study reports published by National Academies Press.",
        rate_limits="Standard web access.",
        retrieval_capabilities=["Consensus study monographs", "Expert committee reports", "DOI indexing"],
        languages_supported=["en"],
        text_availability=["FULL_TEXT", "ABSTRACT"],
        provenance_requirements=["DOI", "ISBN", "National Academies Press URL", "Consensus Committee"],
        independence_rules="Independent, non-profit academic research institution (chartered 1863; NOT a government agency).",
        limitations_notes="Monographic consensus volumes published periodically; not a dynamic daily API.",
    ),
    "nber_stanford": SourceRegistryEntry(
        provider_id="nber_stanford",
        display_name="National Bureau of Economic Research (NBER) / Stanford University",
        domains=[DomainType.IMMIGRATION],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.ACADEMIC_SCHOLARLY,
        official_api_url="https://www.nber.org/papers/",
        is_integrated=False,
        authentication_required=False,
        free_usage_conditions="Academic working paper series and microdata archives.",
        rate_limits="Standard polite web access.",
        retrieval_capabilities=["Working paper search", "Author/Date search", "Microdata analysis"],
        languages_supported=["en"],
        text_availability=["ABSTRACT", "FULL_TEXT"],
        provenance_requirements=["NBER Working Paper Number", "DOI", "Author Affiliations"],
        independence_rules="Private, non-profit academic research organization and private university (NOT a government agency).",
        limitations_notes="Working papers represent author findings prior to formal journal publication.",
    ),
    "cato_institute": SourceRegistryEntry(
        provider_id="cato_institute",
        display_name="Cato Institute (Center for Global Liberty and Prosperity)",
        domains=[DomainType.IMMIGRATION],
        source_tier="SECONDARY",
        authority_classification=AuthorityClassification.THINK_TANK_ADVOCACY,
        official_api_url="https://www.cato.org/research",
        is_integrated=False,
        authentication_required=False,
        free_usage_conditions="Public policy research publications freely available under standard copyright.",
        rate_limits="Standard web access.",
        retrieval_capabilities=["Policy analysis briefs", "Immigration research reports"],
        languages_supported=["en"],
        text_availability=["FULL_TEXT", "ABSTRACT"],
        provenance_requirements=["Policy Analysis Number", "Canonical URL", "Author Attribution"],
        independence_rules="Independent 501(c)(3) public policy think tank / advocacy organization (NOT a government agency, NOT an academic university). Must be linked to primary administrative datasets (e.g. Texas DPS records) when analyzing government data.",
        limitations_notes="Policy research perspective; secondary analysis of primary government administrative data.",
    ),
    "congress_gov": SourceRegistryEntry(
        provider_id="congress_gov",
        display_name="Congress.gov API",
        domains=[DomainType.IMMIGRATION],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.OFFICIAL_LEGAL_STATUTE,
        official_api_url="https://api.congress.gov/v3/",
        is_integrated=False,
        authentication_required=True,
        free_usage_conditions="Free registration required via api.data.gov; returns 403 Forbidden without key.",
        rate_limits="1,000 requests/hour with API key.",
        retrieval_capabilities=["Bill search", "Amendment text", "Congressional record"],
        languages_supported=["en"],
        text_availability=["FULL_TEXT", "METADATA_ONLY"],
        provenance_requirements=["Bill Number", "Congress", "Statute ID"],
        independence_rules="Official legislative primary text of the United States Congress.",
        limitations_notes="Blocked by 403 Forbidden without API key.",
    ),
    "noaa_cdo": SourceRegistryEntry(
        provider_id="noaa_cdo",
        display_name="NOAA Climate Data Online (CDO) API",
        domains=[DomainType.CLIMATE],
        source_tier="PRIMARY",
        authority_classification=AuthorityClassification.GOVERNMENT_PRIMARY,
        official_api_url="https://www.ncdc.noaa.gov/cdo-web/api/v2/",
        is_integrated=False,
        authentication_required=True,
        free_usage_conditions="Mandatory user registration token required in HTTP headers.",
        rate_limits="5 requests/sec, 10,000 requests/day with token.",
        retrieval_capabilities=["Station measurements", "GHCND climate normals", "Daily temperature data"],
        languages_supported=["en"],
        text_availability=["METADATA_ONLY"],
        provenance_requirements=["Station ID", "Dataset ID", "Observation Date"],
        independence_rules="Authoritative NOAA primary observational meteorological agency (U.S. Department of Commerce).",
        limitations_notes="Requires token registration; tabular temperature values rather than claim-evaluating papers.",
    ),
}


def get_source_registry() -> Dict[str, SourceRegistryEntry]:
    """Return the complete dictionary of registered and audited evidence sources."""
    return SOURCE_REGISTRY


def get_providers_for_domain(domain: DomainType, integrated_only: bool = True) -> List[SourceRegistryEntry]:
    """Retrieve registered providers for a specific domain, respecting integration status."""
    results: List[SourceRegistryEntry] = []
    for entry in SOURCE_REGISTRY.values():
        if integrated_only and not entry.is_integrated:
            continue
        if domain in entry.domains or DomainType.CROSS_DOMAIN in entry.domains:
            results.append(entry)
    return results
