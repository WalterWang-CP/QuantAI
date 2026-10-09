"""SEC public data client. Shared throttling/cache are per Python process."""
import json
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime

import httpx

from app.core.config import settings
from app.providers.errors import ProviderRateLimitError, ProviderRequestError, ProviderTemporaryError


@dataclass(frozen=True)
class SECResponse:
    url: str
    body: bytes
    content_type: str | None
    fetched_at: datetime


def normalize_cik(value: str) -> str:
    value = str(value).strip()
    if not value.isascii() or not value.isdigit() or not 1 <= len(value) <= 10 or int(value) == 0:
        raise ValueError("CIK must contain 1-10 digits and be nonzero")
    return value.zfill(10)


def decode_sec_json(response: SECResponse) -> dict:
    try:
        payload = json.loads(response.body.decode("utf-8-sig"), parse_float=Decimal)
    except (ValueError, UnicodeError) as error:
        raise ProviderTemporaryError("SEC returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ProviderTemporaryError("SEC returned a non-object JSON response")
    return payload


class SECClient:
    _lock = threading.Lock()
    _next_request = 0.0
    _cache = OrderedDict()
    _cache_limit = 16

    def __init__(self, *, user_agent=None):
        self.user_agent = (user_agent if user_agent is not None else settings.sec_user_agent) or ""
        if "@" not in self.user_agent or "\n" in self.user_agent or "\r" in self.user_agent:
            raise ProviderRequestError("Set SEC_USER_AGENT to an application name and real contact email")

    def _wait_for_slot(self):
        # Hold the lock during the short wait so concurrent callers cannot burst.
        with SECClient._lock:
            delay = SECClient._next_request - time.monotonic()
            if delay > 30:
                raise ProviderRateLimitError("SEC cooldown is active; retry later")
            if delay > 0:
                time.sleep(delay)
            SECClient._next_request = time.monotonic() + settings.sec_request_interval_seconds

    def _fetch(self, url):
        now = time.monotonic()
        with SECClient._lock:
            cached = SECClient._cache.get(url)
            if cached and settings.sec_cache_ttl_seconds and now - cached[0] < settings.sec_cache_ttl_seconds:
                SECClient._cache.move_to_end(url)
                return cached[1]
        for attempt in range(settings.sec_max_attempts):
            self._wait_for_slot()
            response = None
            try:
                response = httpx.get(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                                     timeout=settings.sec_timeout_seconds, follow_redirects=False)
                status = response.status_code
                if status == 429:
                    error = ProviderRateLimitError("SEC request rate limited; retry later")
                elif status >= 500:
                    error = ProviderTemporaryError(f"SEC temporarily unavailable (HTTP {status})")
                elif status != 200:
                    raise ProviderRequestError(f"SEC request failed (HTTP {status}); check CIK and User-Agent")
                else:
                    result = SECResponse(url, response.content, response.headers.get("content-type"),
                                         datetime.now(timezone.utc))
                    decode_sec_json(result)
                    with SECClient._lock:
                        SECClient._cache[url] = (time.monotonic(), result)
                        SECClient._cache.move_to_end(url)
                        while len(SECClient._cache) > SECClient._cache_limit:
                            SECClient._cache.popitem(last=False)
                    return result
            except (httpx.RequestError, ProviderTemporaryError) as exception:
                error = ProviderTemporaryError("Unable to retrieve a valid SEC response")
                error.__cause__ = exception
            retry_after = response.headers.get("retry-after", "") if response is not None else ""
            try:
                delay = float(retry_after) if retry_after.isdigit() else max(
                    0, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                )
            except (TypeError, ValueError, OverflowError):
                delay = 0
            if isinstance(error, ProviderRateLimitError):
                delay = max(delay, 2 ** attempt)
                with SECClient._lock:
                    SECClient._next_request = max(SECClient._next_request, time.monotonic() + delay)
            if attempt + 1 == settings.sec_max_attempts or delay > 30:
                raise error
            time.sleep(max(delay, 2 ** attempt))
        raise ProviderTemporaryError("SEC request failed")

    def fetch_submissions(self, cik):
        return self._fetch(f"https://data.sec.gov/submissions/CIK{normalize_cik(cik)}.json")

    def fetch_company_facts(self, cik):
        return self._fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalize_cik(cik)}.json")

    def fetch_history_file(self, cik, filename):
        cik = normalize_cik(cik)
        if not re.fullmatch(rf"CIK{cik}-submissions-\d+\.json", filename):
            raise ProviderRequestError("Unexpected SEC submissions history filename")
        return self._fetch(f"https://data.sec.gov/submissions/{filename}")
