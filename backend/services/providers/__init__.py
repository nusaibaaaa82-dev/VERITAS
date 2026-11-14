"""Evidence source providers for VERITAS.

Free, public evidence providers:
- OpenAlexProvider: Academic works, papers, DOI metadata, inverted index abstracts.
- CrossrefProvider: Scholarly DOIs, publishers, titles, publication dates.
- WikimediaProvider: Background discovery, Wikipedia summaries (tertiary tier).
- PubMedProvider: NCBI biomedical and clinical trials literature.
- NasaNtrsProvider: NASA Earth science and atmospheric technical reports.
- UsgsPubsProvider: USGS geological and hydrological publications.
- WhoGhoProvider: World Health Organization Global Health Observatory indicators.
- WhoIrisProvider: World Health Organization Institutional Repository for Information Sharing.
- WorldBankProvider: World Bank Documents & Reports (WDS) economic and migration research.
"""

from backend.services.providers.base import BaseEvidenceProvider
from backend.services.providers.crossref import CrossrefProvider
from backend.services.providers.dol_whd import DolWhdProvider
from backend.services.providers.ecfr import EcfrProvider
from backend.services.providers.nasa_ntrs import NasaNtrsProvider
from backend.services.providers.openalex import OpenAlexProvider
from backend.services.providers.pubmed import PubMedProvider
from backend.services.providers.usgs_pubs import UsgsPubsProvider
from backend.services.providers.who_gho import WhoGhoProvider
from backend.services.providers.who_iris import WhoIrisProvider
from backend.services.providers.wikimedia import WikimediaProvider
from backend.services.providers.world_bank import WorldBankProvider

__all__ = [
    "BaseEvidenceProvider",
    "OpenAlexProvider",
    "CrossrefProvider",
    "WikimediaProvider",
    "PubMedProvider",
    "NasaNtrsProvider",
    "UsgsPubsProvider",
    "WhoGhoProvider",
    "WhoIrisProvider",
    "WorldBankProvider",
    "DolWhdProvider",
    "EcfrProvider",
]
