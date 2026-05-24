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


# ── Estrazione blocco normativo da HTML Normattiva ───────────────────────────
# Normattiva struttura il testo normativo dentro contenitori specifici:
#   <div id="corpo-atto">...</div>   (layout moderno)
#   <div id="testo-articoli">...</div>
#   <div class="bodyTesto">...</div> (layout legacy)
# Se non trovato, si fa il fallback sul testo completo filtrato.

_BLOCK_SELECTORS = [
    # id esatti
    r'<div[^>]+id=["\']corpo-atto["\'][^>]*>',
    r'<div[^>]+id=["\']testo-articoli["\'][^>]*>',
    r'<div[^>]+id=["\']atto-content["\'][^>]*>',
    r'<div[^>]+id=["\']contenuto-atto["\'][^>]*>',
    # class
    r'<div[^>]+class=["\'][^"\']*(bodyTesto|corpo-atto|testo-norma)[^"\']* *["\'][^>]*>',
]


def _extract_normativo_block(html: str) -> str:
    """
    Cerca il blocco normativo principale nell'HTML di Normattiva.
    Restituisce l'HTML del blocco se trovato, altrimenti stringa vuota.
    """
    for pattern in _BLOCK_SELECTORS:
        m = re.search(pattern, html, re.IGNORECASE)
        if not m:
            continue
        start = m.start()
        # Trova il </div> di chiusura bilanciato
        pos = m.end()
        depth = 1
        while pos < len(html) and depth > 0:
            open_m = re.search(r'<div', html[pos:pos + 200], re.IGNORECASE)
            close_m = re.search(r'</div>', html[pos:pos + 200], re.IGNORECASE)
            if close_m and (not open_m or close_m.start() < open_m.start()):
                depth -= 1
                pos += close_m.end()
            elif open_m:
                depth += 1
                pos += open_m.end()
            else:
                # Salta avanti per non bloccarsi
                pos += 200
        if depth == 0:
            return html[start:pos]
    return ""


# ── Parser HTML minimale (no dipendenze esterne) ──────────────────────────────
class _TextExtractor(HTMLParser):
    """Estrae testo pulito da HTML, saltando script/style/nav."""
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript",
                 "meta", "link", "head", "button", "form", "input",
                 "select", "textarea", "iframe", "svg", "canvas"}
    BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5",
                  "h6", "article", "section", "span", "br", "td", "th"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._skip_depth > 0:
            self._skip_depth += 1
            return
        if tag in self.SKIP_TAGS:
            self._skip_depth = 1
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.parts.append(stripped)

    def get_text(self) -> str:
        raw = "\n".join(self.parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()


# Parole che segnalano testo boilerplate di navigazione Normattiva
_BOILERPLATE_PATTERNS = re.compile(
    r"(presidenza del consiglio|accessibilit|mappa del sito"
    r"|normattiva|cookies|privacy policy|salta al contenuto"
    r"|torna all.inizio|stampa la pagina|note legali"
    r"|versione stampabile|cerca nel sito|aiuto|help)",
    re.IGNORECASE,
)


def _clean_testo(testo: str) -> str:
    """Rimuove righe di boilerplate e normalizza il testo estratto."""
    lines = []
    for line in testo.splitlines():
        s = line.strip()
        if not s:
            continue
        if len(s) < 4:  # righe troppo corte (es. "ITA", "|", "-")
            continue
        if _BOILERPLATE_PATTERNS.search(s):
            continue
        lines.append(s)
    return "\n".join(lines)


def _estrai_data_vigenza(html: str) -> Optional[str]:
    """Cerca pattern 'vigente al', 'aggiornato al', 'in vigore dal' nel testo."""
    patterns = [
        r"vigente\s+al\s+([\d/]{8,10})",
        r"aggiornato\s+al\s+([\d/]{8,10})",
        r"in\s+vigore\s+dal\s+([\d/]{8,10})",
    ]
    for p in patterns:
        m = re.search(p, html[:8000], re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _truncate_testo(testo: str, max_chars: int = 8000) -> str:
    if len(testo) <= max_chars:
        return testo
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
    """Recupera il testo vigente da normattiva.it."""
    if not url_normattiva or not url_normattiva.startswith("http"):
        return {
            "url": url_normattiva,
            "testo": "",
            "fonte": "fallback",
            "aggiornato_al": None,
            "errore": "URL non valido o mancante",
        }

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
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_bytes = resp.read()
            try:
                html = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                html = raw_bytes.decode("latin-1", errors="replace")

        aggiornato_al = _estrai_data_vigenza(html)

        # 1. Prova a estrarre il blocco normativo specifico
        block_html = _extract_normativo_block(html)
        if block_html:
            testo_raw = _html_to_text(block_html)
            print(f"[NORMATTIVA] blocco estratto ({len(testo_raw)} chars)", flush=True)
        else:
            # 2. Fallback: testo completo della pagina
            testo_raw = _html_to_text(html)
            print(f"[NORMATTIVA] fallback testo completo ({len(testo_raw)} chars)", flush=True)

        testo_pulito = _clean_testo(testo_raw)
        testo_finale = _truncate_testo(testo_pulito)

        result = {
            "url": url_normattiva,
            "testo": testo_finale,
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
    """Fetch parallelo (sequenziale con early-stop) per le prime `max_fetch` norme."""
    import sys
    results: dict[str, dict] = {}
    fetched = 0
    for norma in norme:
        if fetched >= max_fetch:
            break
        norma_id = norma.get("id", "")
        url = norma.get("url_normattiva", "")
        if not norma_id or not url:
            continue
        res = fetch_testo_vigente(url, timeout=timeout)
        results[norma_id] = res
        fetched += 1
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
