"""Minimal client (standard library only) for the Jolpica-F1 API, the successor of Ergast.

Designed for reproducibility and to respect the API limits (~4 req/s burst, ~500 req/h sustained):
  * Every response is cached on disk (RAW_DIR); a second run downloads nothing again.
  * The download can be interrupted and resumed: cached pages are reused.
  * On 429/5xx it retries with increasing waits (honoring Retry-After).
  * Offline mode: reads only the cache and fails with a clear message if something is missing.
"""
from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

PAGE_SIZE = 100          # maximum page size the API accepts
MIN_INTERVAL_S = 0.3     # pause between real requests (~3 req/s)
MAX_RETRIES = 40        # with a 120 s max wait this survives the API's hourly cap (429)


class JolpicaError(RuntimeError):
    pass


class JolpicaClient:
    def __init__(self, base_url: str, cache_dir: Path, offline: bool = False, refresh: bool = False):
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.offline = offline
        self.refresh = refresh
        self._last_request = 0.0
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ low level
    def _cache_file(self, path: str, offset: int) -> Path:
        safe = path.strip("/").replace("/", "__")
        return self.cache_dir / f"{safe}__offset{offset}.json"

    def _http_get(self, url: str) -> dict:
        wait = 5.0
        for attempt in range(1, MAX_RETRIES + 1):
            since = time.monotonic() - self._last_request
            if since < MIN_INTERVAL_S:
                time.sleep(MIN_INTERVAL_S - since)
            req = urllib.request.Request(url, headers={"User-Agent": "tp-sql-agent/1.0 (academic use)"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self._last_request = time.monotonic()
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                self._last_request = time.monotonic()
                if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                    retry_after = e.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else wait
                    print(f"  HTTP {e.code} for {url}; retry {attempt}/{MAX_RETRIES} in {delay:.0f}s",
                          file=sys.stderr)
                    time.sleep(delay)
                    wait = min(wait * 2, 120)
                    continue
                raise JolpicaError(f"HTTP {e.code} requesting {url}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < MAX_RETRIES:
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                    continue
                raise JolpicaError(f"Network error requesting {url}: {e}") from e
        raise JolpicaError(f"Retries exhausted for {url}")

    # ------------------------------------------------------------------ public API
    def page(self, path: str, offset: int = 0) -> dict:
        """Returns the 'MRData' object of a page, from cache or network."""
        cache = self._cache_file(path, offset)
        if cache.exists() and not self.refresh:
            return json.loads(cache.read_text(encoding="utf-8"))["MRData"]
        if self.offline:
            raise JolpicaError(f"Offline mode: {cache.name} is missing from the cache. "
                               "Run without --offline to download it.")
        url = f"{self.base_url}/{path.strip('/')}.json?limit={PAGE_SIZE}&offset={offset}"
        data = self._http_get(url)
        tmp = cache.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(cache)  # atomic write: a half-written page can never be left behind
        return data["MRData"]

    def pages(self, path: str) -> Iterator[dict]:
        """Iterates over all pages of an endpoint, printing progress."""
        first = self.page(path, 0)
        total = int(first["total"])
        limit = int(first["limit"])
        n_pages = max(1, math.ceil(total / limit))
        print(f"  {path}: {total} rows in {n_pages} page(s)", file=sys.stderr)
        yield first
        for i in range(1, n_pages):
            yield self.page(path, i * limit)
