"""HTTP client with retries, backoff and polite rate limiting."""

from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class HttpClient:
    """Small wrapper that never hammers a host.

    ``min_interval`` is enforced between *all* requests made by the instance.
    """

    def __init__(
        self,
        min_interval: float = 1.0,
        timeout: int = 25,
        retries: int = 4,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-GB,en;q=0.9",
            }
        )
        if headers:
            self.session.headers.update(headers)
        self.min_interval = min_interval
        self.timeout = timeout
        self.retries = retries
        self._last_request = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed + random.uniform(0, 0.25))
        self._last_request = time.monotonic()

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> requests.Response:
        last_error: Optional[Exception] = None
        for attempt in range(self.retries):
            self._wait()
            try:
                response = self.session.get(url, params=params, timeout=self.timeout, **kwargs)
                if response.status_code in (429, 503):
                    time.sleep(min(60, 5 * (2**attempt)))
                    continue
                response.raise_for_status()
                return response
            except requests.RequestException as exc:  # pragma: no cover - network dependent
                last_error = exc
                time.sleep(min(30, 2**attempt))
        raise RuntimeError(f"GET failed after {self.retries} attempts: {url} ({last_error})")

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        return self.get(url, params=params, **kwargs).json()

    def get_text(self, url: str, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> str:
        return self.get(url, params=params, **kwargs).text
