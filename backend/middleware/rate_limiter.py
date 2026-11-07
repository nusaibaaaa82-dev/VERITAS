"""In-memory Sliding Window Rate Limiter Middleware for VERITAS.

Protects VERITAS backend and external public providers (OpenAlex, PubMed, World Bank, etc.)
from automated request floods and denial-of-service attempts without requiring Redis or paid services.

Policy:
- Enforces requests-per-minute per client IP (default: 20 req/min).
- Targets expensive pipeline operations (POST /api/verify and POST /api/claims) while keeping /health, /, and static assets unthrottled.
- Returns HTTP 429 Too Many Requests with standard 'Retry-After' header and JSON error details.

Proxy & Deployment Architecture Considerations:
1. Reverse Proxy & IP Spoofing Prevention:
   - Hugging Face Spaces uses Cloudflare / HAProxy edge reverse proxies.
   - Attackers can forge an 'X-Forwarded-For: fake_ip' header. To mitigate spoofing,
     the resolver checks trusted proxy headers in priority:
     a) 'cf-connecting-ip' (Cloudflare edge client IP; cannot be forged if traffic passes through Cloudflare)
     b) 'x-real-ip' (Set by reverse proxy to direct downstream client)
     c) 'x-forwarded-for' (Appended by proxies; rightmost IP is the proxy-verified peer)
     d) request.client.host (Direct socket address fallback)
2. Ephemeral In-Memory State across Restarts:
   - On Hugging Face Spaces free-tier instances, the container goes to sleep after 48h of inactivity or restarts on rebuilds.
   - The sliding-window records are held in Python memory. Upon container restart, all rate-limiting records reset.
   - This provides safe DoS mitigation without introducing costly external Redis databases.
3. Single-Worker Constraint:
   - In-memory rate limiting is process-local. If multiple Uvicorn worker processes are launched,
     each worker maintains an independent rate limit window.
   - Running with a single worker (--workers 1) is required for strict limit enforcement and prevents
     PyTorch neural model memory duplication on CPU (keeping RAM under 1.4 GB).
"""

from collections import defaultdict
import logging
import time
from typing import Dict, List, Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """Extract real client IP address safely behind edge reverse proxies.

    Prioritizes headers set by trusted edge layers (Cloudflare, HAProxy) before
    falling back to direct socket client. Avoids relying blindly on the leftmost
    X-Forwarded-For element which an untrusted client can manipulate.
    """
    # 1. Cloudflare edge header (Hugging Face Spaces edge termination)
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip and cf_ip.strip():
        return cf_ip.strip()

    # 2. X-Real-IP header (standard reverse proxy)
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    # 3. X-Forwarded-For header
    # When behind a reverse proxy, the proxy appends the remote client IP to the end of the chain.
    # The rightmost entry is the most trustworthy proxy-appended address.
    xff = request.headers.get("x-forwarded-for")
    if xff and xff.strip():
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]

    # 4. Direct socket client host fallback
    if request.client and request.client.host:
        return request.client.host

    return "unknown"


class SlidingWindowRateLimiter(BaseHTTPMiddleware):
    """Sliding-window IP rate limiter middleware."""

    def __init__(
        self,
        app,
        requests_per_minute: int = 20,
        enabled: bool = True,
    ):
        super().__init__(app)
        self.requests_per_minute = max(1, requests_per_minute)
        self.enabled = enabled
        self.client_records: Dict[str, List[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        # Apply rate limiting specifically to resource-intensive verification pipeline calls
        if request.method == "POST" and request.url.path in ("/api/verify", "/api/claims"):
            client_ip = get_client_ip(request)

            now = time.time()
            cutoff = now - 60.0

            # Evict timestamps older than 60 seconds
            timestamps = [t for t in self.client_records[client_ip] if t > cutoff]

            if len(timestamps) >= self.requests_per_minute:
                oldest = timestamps[0]
                retry_after = max(1, int(60.0 - (now - oldest)))
                logger.warning(
                    "Rate limit exceeded for IP %s (%d requests in last 60s). Throttling for %ds.",
                    client_ip,
                    len(timestamps),
                    retry_after,
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": "Rate Limit Exceeded",
                        "message": (
                            f"Too many verification requests from your IP. "
                            f"Limit is {self.requests_per_minute} requests per minute. "
                            f"Please wait {retry_after} seconds before retrying."
                        ),
                        "retry_after": retry_after,
                        "status": "rate_limited",
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            timestamps.append(now)
            self.client_records[client_ip] = timestamps

            # Housekeeping: periodically purge inactive client records every 5 minutes
            if now - self._last_cleanup > 300.0:
                self.client_records = defaultdict(
                    list,
                    {
                        ip: times
                        for ip, times in self.client_records.items()
                        if any(t > cutoff for t in times)
                    },
                )
                self._last_cleanup = now

        return await call_next(request)
