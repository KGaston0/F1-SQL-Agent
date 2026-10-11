"""Cliente mínimo (solo librería estándar) de la API Jolpica-F1, sucesora de Ergast.

Características pensadas para reproducibilidad y para respetar los límites de la API
(~4 req/s en ráfaga, ~500 req/h sostenido):
  * Cada respuesta se guarda en disco (RAW_DIR); una segunda ejecución no vuelve a descargar nada.
  * La descarga se puede interrumpir y retomar: lo ya cacheado se reutiliza.
  * Ante 429/5xx reintenta con espera creciente (respetando Retry-After).
  * Modo offline: solo lee la caché y falla con un mensaje claro si falta algo.
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

PAGE_SIZE = 100          # máximo que acepta la API por página
MIN_INTERVAL_S = 0.3     # pausa entre requests reales (≈3 req/s)
MAX_RETRIES = 40        # con espera máx. de 120 s tolera el tope horario de la API (429)


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

    # ------------------------------------------------------------------ bajo nivel
    def _cache_file(self, path: str, offset: int) -> Path:
        safe = path.strip("/").replace("/", "__")
        return self.cache_dir / f"{safe}__offset{offset}.json"

    def _http_get(self, url: str) -> dict:
        wait = 5.0
        for attempt in range(1, MAX_RETRIES + 1):
            since = time.monotonic() - self._last_request
            if since < MIN_INTERVAL_S:
                time.sleep(MIN_INTERVAL_S - since)
            req = urllib.request.Request(url, headers={"User-Agent": "tp-agente-sql/1.0 (uso academico)"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    self._last_request = time.monotonic()
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                self._last_request = time.monotonic()
                if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                    retry_after = e.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else wait
                    print(f"  HTTP {e.code} en {url}; reintento {attempt}/{MAX_RETRIES} en {delay:.0f}s",
                          file=sys.stderr)
                    time.sleep(delay)
                    wait = min(wait * 2, 120)
                    continue
                raise JolpicaError(f"HTTP {e.code} al pedir {url}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < MAX_RETRIES:
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                    continue
                raise JolpicaError(f"Error de red al pedir {url}: {e}") from e
        raise JolpicaError(f"Se agotaron los reintentos para {url}")

    # ------------------------------------------------------------------ API pública
    def page(self, path: str, offset: int = 0) -> dict:
        """Devuelve el objeto 'MRData' de una página, desde caché o red."""
        cache = self._cache_file(path, offset)
        if cache.exists() and not self.refresh:
            return json.loads(cache.read_text(encoding="utf-8"))["MRData"]
        if self.offline:
            raise JolpicaError(f"Modo offline: falta en caché {cache.name}. "
                               "Ejecutá sin --offline para descargarlo.")
        url = f"{self.base_url}/{path.strip('/')}.json?limit={PAGE_SIZE}&offset={offset}"
        data = self._http_get(url)
        tmp = cache.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(cache)  # escritura atómica: nunca queda una página a medio escribir
        return data["MRData"]

    def pages(self, path: str) -> Iterator[dict]:
        """Itera todas las páginas de un endpoint, mostrando progreso."""
        first = self.page(path, 0)
        total = int(first["total"])
        limit = int(first["limit"])
        n_pages = max(1, math.ceil(total / limit))
        print(f"  {path}: {total} filas en {n_pages} página(s)", file=sys.stderr)
        yield first
        for i in range(1, n_pages):
            yield self.page(path, i * limit)
