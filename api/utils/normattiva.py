"""Fetch live del testo vigente da normattiva.it.

Funzione principale:
    fetch_testo_vigente(url_normattiva, timeout=10) -> dict

Restituisce:
    {
      "url": str,                  # URL canonico usato
      "testo": str,                # Testo estratto (pulito, max ~8000 char)
      "fonte": str,                # "normattiva" | "cache" | "fallback"
      "aggiornato_al": str | None, # Data ultima modifica se presente
      "errore": str | None,        # Messaggio errore se fetch fallito
    }

Cache in-process (LRU semplice a 64 voci) per evitare fetch ripetuti
nella stessa istanza serverless Vercel.
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from html.parser import HTMLParser
from typing import Optional

# ── Cache in-process ──────────────────────────────────────────────────────────
_CACHE_MAX = 64
_CACHE_TTL = 3600  # secondi — 1 ora
_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()


def _cache_get(key: str) -> Optional[dict]:
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            _cache.move_to_end(key)
            return val
        del _cache[key]
    return None


def _cache_set(key: str, val: dict) -> None:
    if key in _cache:
        _cache.move_to_end(key)
    _cache[key] = (time.time(), val)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


# ── Parser HTML minimale (no dipendenze esterne) ──────────────────────────────
class _TextExtractor(HTMLParser):
    """Estrae testo pulito da HTML, saltando script/style/nav."""
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript",
                 "meta", "link", "head", "button", "form", "input"}
    BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5",
                  "h6", "article", "section", "span", "br", "td", "th"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._skip_tag: Optional[str] = None
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._skip_depth > 0:
            self._skip_depth += 1
            return
        if tag in self.SKIP_TAGS:
            self._skip_depth = 1
            self._skip_tag = tag
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self.parts.append(data)

    def get_text(self) -> str:
        raw = " ".join(self.parts)
        # Comprime whitespace multipli
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        # Fallback regex grezzo
        return re.sub(r"<[^>]+>", " ", html).strip()


def _estrai_data_vigenza(html: str) -> Optional[str]:
    """Cerca pattern 'vigente al', 'aggiornato al', 'in vigore dal' nel testo."""
    patterns = [
        r"vigente\s+al\s+([\d/]{8,10})",
        r"aggiornato\s+al\s+([\d/]{8,10})",
        r"in\s+vigore\s+dal\s+([\d/]{8,10})",
        r"(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for p in patterns:
        m = re.search(p, html[:5000], re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _truncate_testo(testo: str, max_chars: int = 8000) -> str:
    if len(testo) <= max_chars:
        return testo
    # Tronca all'ultimo punto prima del limite
    trunc = testo[:max_chars]
    last_dot = trunc.rfind(".")
    if last_dot > max_chars // 2:
        return trunc[:last_dot + 1] + " [...]"
    return trunc + " [...]"


# ── Funzione pubblica principale ──────────────────────────────────────────────
def fetch_testo_vigente(
    url_normattiva: str,
    timeout: int = 10,
) -> dict:
    """Recupera il testo vigente da normattiva.it.

    Args:
        url_normattiva: URL canonico NIR, es:
            'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2023-03-31;36'
        timeout: timeout HTTP in secondi

    Returns:
        dict con chiavi: url, testo, fonte, aggiornato_al, errore
    """
    if not url_normattiva or not url_normattiva.startswith("http"):
        return {
            "url": url_normattiva,
            "testo": "",
            "fonte": "fallback",
            "aggiornato_al": None,
            "errore": "URL non valido o mancante",
        }

    # Controlla cache
    cached = _cache_get(url_normattiva)
    if cached is not None:
        result = cached.copy()
        result["fonte"] = "cache"
        return result

    try:
        req = urllib.request.Request(
            url_normattiva,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; NormativaBot/1.0; "
                    "+https://normattiva.vercel.app)"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "it-IT,it;q=0.9",
            },
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html_bytes = resp.read()
            # Normattiva usa latin-1 o utf-8 — prova entrambi
            try:
                html = html_bytes.decode("utf-8")
            except UnicodeDecodeError:
                html = html_bytes.decode("latin-1", errors="replace")

        testo = _html_to_text(html)
        aggiornato_al = _estrai_data_vigenza(html)

        # Filtra il testo: elimina intestazioni boilerplate di normattiva
        boilerplate_markers = [
            "Normattiva", "COOKIES", "Accessibilità",
            "salta al contenuto", "mappa del sito",
        ]
        lines = testo.splitlines()
        filtered_lines = []
        body_started = False
        for line in lines:
            stripped = line.strip()
            if not body_started:
                # Inizia a raccogliere dopo il titolo del provvedimento
                if any(kw in stripped for kw in ["decreto", "legge", "d.lgs",
                                                  "DECRETO", "LEGGE", "Legge",
                                                  "Art.", "art.", "Articolo"]):
                    body_started = True
                continue
            if stripped and not any(bp.lower() in stripped.lower()
                                    for bp in boilerplate_markers):
                filtered_lines.append(stripped)

        testo_pulito = _truncate_testo("\n".join(filtered_lines))

        result = {
            "url": url_normattiva,
            "testo": testo_pulito,
            "fonte": "normattiva",
            "aggiornato_al": aggiornato_al,
            "errore": None,
        }
        _cache_set(url_normattiva, result)
        return result

    except urllib.error.HTTPError as e:
        return {
            "url": url_normattiva,
            "testo": "",
            "fonte": "fallback",
            "aggiornato_al": None,
            "errore": f"HTTP {e.code}: {e.reason}",
        }
    except Exception as exc:
        return {
            "url": url_normattiva,
            "testo": "",
            "fonte": "fallback",
            "aggiornato_al": None,
            "errore": f"{type(exc).__name__}: {exc}",
        }


def fetch_testo_batch(
    norme: list[dict],
    max_fetch: int = 3,
    timeout: int = 8,
) -> dict[str, dict]:
    """Fetch parallelo (sequenziale con early-stop) per le prime `max_fetch` norme.

    Args:
        norme: lista di norme (dict con campo 'id' e 'url_normattiva')
        max_fetch: numero massimo di norme da fetchare (top-N per rilevanza)
        timeout: timeout per singola richiesta HTTP

    Returns:
        dict {norma_id: risultato_fetch}
    """
    results: dict[str, dict] = {}
    fetched = 0
    for norma in norme:
        if fetched >= max_fetch:
            break
        norma_id = norma.get("id", "")
        url = norma.get("url_normattiva", "")
        if not norma_id or not url:
            continue
        # Skip se già in cache (conta lo stesso)
        res = fetch_testo_vigente(url, timeout=timeout)
        results[norma_id] = res
        fetched += 1
        # Log minimal
        import sys
        fonte = res.get("fonte", "?")
        errore = res.get("errore")
        testo_len = len(res.get("testo", ""))
        print(
            f"[NORMATTIVA FETCH] id={norma_id} | fonte={fonte} | "
            f"chars={testo_len} | errore={errore}",
            flush=True,
            file=sys.stdout,
        )
    return results
