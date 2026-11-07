"""Base class for free public evidence providers in VERITAS.

Enforces zero-cost API constraints:
1. Free public endpoints only (no paid APIs, API keys, or subscriptions).
2. Strict timeouts, request limits, and polite User-Agent headers.
3. Resilient error handling (HTTP errors, timeouts, malformed JSON).
4. Full provenance tracking without fabricating missing fields.
"""

from abc import ABC, abstractmethod
import json
from typing import Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
from backend.config import settings
from backend.schemas.claim import EvidenceItem


class BaseEvidenceProvider(ABC):
    """Abstract base provider for free public evidence discovery."""

    def __init__(
        self,
        name: str,
        source_tier: str,
        timeout_seconds: Optional[float] = None,
    ):
        self.name = name
        self.source_tier = source_tier  # PRIMARY, SECONDARY, or TERTIARY
        self.timeout_seconds = timeout_seconds or settings.PROVIDER_TIMEOUT_SECONDS
        self.user_agent = settings.HTTP_USER_AGENT

    def _execute_http_get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[dict], Optional[str]]:
        """Safely execute an HTTP GET request with timeouts and error trapping.

        Returns (response_data_dict, error_message).
        """
        req_headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, headers=req_headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status != 200:
                    return None, f"HTTP Error {response.status}: {response.reason}"
                payload = response.read().decode("utf-8")
                data = json.loads(payload)
                return data, None
        except urllib.error.HTTPError as http_err:
            return None, f"HTTP {http_err.code}: {http_err.reason}"
        except urllib.error.URLError as url_err:
            return None, f"Network/Connection error: {str(url_err.reason)}"
        except TimeoutError:
            return None, f"Request timed out after {self.timeout_seconds} seconds"
        except json.JSONDecodeError:
            return None, "Failed to parse API JSON response"
        except Exception as exc:
            return None, f"Unexpected retrieval failure: {str(exc)}"

    @abstractmethod
    def search(self, query: str, limit: int = 3) -> Tuple[List[EvidenceItem], Optional[str]]:
        """Search the public provider for relevant evidence records.

        Returns:
            Tuple of (list_of_evidence_items, error_or_diagnostic_message)
        """
        pass
