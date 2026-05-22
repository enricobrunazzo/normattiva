"""Endpoint /api/search — ricerca normativa su Normattiva."""
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse

import httpx
from bs4 import BeautifulSoup

# ── Costanti soglie (D.Lgs. 36/2023) ──────────────────────────────────────────
SEMI_THRESHOLD   = 5_000
DIRECT_THRESHOLD = 140_000
NEGO_THRESHOLD   = 215_000

TIPO_ATTO_KEYWORDS = {
    "determina": ["determinazione dirigenziale", "determina a contrarre", "D.Lgs. 36/2023"],
    "delibera":  ["deliberazione", "delibera giunta", "delibera consiglio"],
    "ordinanza": ["ordinanza sindacale", "ordinanza dirigenziale"],
    "decreto":   ["decreto", "atto di indirizzo"],
    "contratto": ["contratto pubblico", "accordo", "convenzione"],
}

SEMANTIC_MAP = {
    "acquisto":    ["codice contratti pubblici", "D.Lgs. 36/2023"],
    "software":    ["digitalizzazione", "CAD", "D.Lgs. 82/2005", "AgID"],
    "cloud":       ["cloud computing PA", "AgID", "PNRR digitalizzazione"],
    "hardware":    ["codice contratti pubblici", "D.Lgs. 36/2023"],
    "servizi":     ["affidamento servizi", "D.Lgs. 36/2023"],
    "manutenzione":["contratto manutenzione", "D.Lgs. 36/2023"],
    "consulenza":  ["incarico professionale", "D.Lgs. 165/2001", "articolo 7 TUPI"],
    "formazione":  ["formazione dipendenti PA", "D.Lgs. 165/2001"],
    "privacy":     ["GDPR", "D.Lgs. 196/2003", "Regolamento UE 2016/679"],
    "dati":        ["protezione dati", "GDPR", "D.Lgs. 196/2003"],
    "trasparenza": ["D.Lgs. 33/2013", "amministrazione trasparente", "FOIA"],
    "anticorruzione":["L. 190/2012", "ANAC", "piano anticorruzione"],
    "gara":        ["D.Lgs. 36/2023", "bando di gara", "CIG"],
    "appalto":     ["D.Lgs. 36/2023", "appalto pubblico", "CIG", "RUP"],
    "fornitore":   ["albo fornitori", "MEPA", "Consip"],
    "mepa":        ["MEPA", "mercato elettronico PA", "Consip"],
    "consip":      ["Consip", "convenzioni Consip", "acquisti centralizzati"],
    "lavori":      ["lavori pubblici", "D.Lgs. 36/2023", "progettazione"],
    "sicurezza":   ["D.Lgs. 81/2008", "sicurezza lavoro", "DUVRI"],
    "personale":   ["D.Lgs. 165/2001", "TUPI", "personale PA"],
    "bilancio":    ["D.Lgs. 118/2011", "armonizzazione contabile"],
    "pnrr":        ["PNRR", "Piano Nazionale Ripresa Resilienza"],
    "comune":      ["TUEL", "D.Lgs. 267/2000", "enti locali"],
    "regione":     ["legge regionale", "autonomia regionale"],
    "fondo":       ["fondi strutturali", "PNRR"],
}

STOP_WORDS = {
    "il","lo","la","i","gli","le","un","uno","una",
    "di","del","della","degli","dei","delle",
    "a","al","alla","ai","agli","alle",
    "da","dal","dalla","dai","dagli","dalle",
    "in","nel","nella","nei","negli","nelle",
    "con","su","per","tra","fra","che","chi","cui",
    "non","ma","se","ho","ha","hanno","devo","deve",
    "voglio","fare","sono","e","o","come","quando","dove",
}

BASE_URL   = "https://www.normattiva.it"
SEARCH_URL = f"{BASE_URL}/ricerca/semplice"
HEADERS = {
    "User-Agent": "NormativaSearchBot/1.0 (+https://github.com/enricobrunazzo/normattiva)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "it-IT,it;q=0.9",
}


# ── Keyword extraction ─────────────────────────────────────────────────────────
def _importo_keywords(importo_str: str) -> list:
    try:
        val = float(importo_str.replace(".", "").replace(",", ".").replace("€", "").strip())
    except (ValueError, AttributeError):
        return []
    if val <= SEMI_THRESHOLD:
        return ["affidamento diretto", "microprocurement", "articolo 50 codice contratti"]
    elif val <= DIRECT_THRESHOLD:
        return ["affidamento diretto", "articolo 50 codice contratti", "determina a contrarre"]
    elif val <= NEGO_THRESHOLD:
        return ["procedura negoziata", "articolo 72 codice contratti", "CIG", "RUP"]
    else:
        return ["procedura aperta", "bando di gara", "articolo 71 codice contratti", "RUP", "CIG"]


def extract_keywords(testo: str, tipo_atto: str = "", oggetto: str = "", importo: str = "") -> list:
    keywords = []
    if tipo_atto and tipo_atto.lower() in TIPO_ATTO_KEYWORDS:
        keywords.extend(TIPO_ATTO_KEYWORDS[tipo_atto.lower()])
    if importo:
        keywords.extend(_importo_keywords(importo))
    full_text = f"{testo} {oggetto}".lower()
    tokens = full_text.replace(",", " ").replace(".", " ").split()
    for token in tokens:
        token = token.strip("'\"()[]")
        if token in STOP_WORDS or len(token) < 4:
            continue
        if token in SEMANTIC_MAP:
            keywords.extend(SEMANTIC_MAP[token])
    seen = set()
    result = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            result.append(k)
    if not result:
        significant = [t for t in tokens if t not in STOP_WORDS and len(t) >= 4]
        result = list(dict.fromkeys(significant[:8]))
    return result[:12]


# ── Normattiva client ──────────────────────────────────────────────────────────
def _parse_result(el):
    try:
        title_el = el.select_one(".titolo, h3, h4, .titolo-atto")
        title = title_el.get_text(strip=True) if title_el else ""
        link_el = el.select_one("a[href]")
        href = link_el["href"] if link_el else ""
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        estremi_el = el.select_one(".estremi, .data-atto, .numero-atto")
        estremi = estremi_el.get_text(strip=True) if estremi_el else ""
        snippet_el = el.select_one(".sommario, .abstract, .descrizione, p")
        snippet = snippet_el.get_text(strip=True)[:300] if snippet_el else ""
        urn = href.split("/atto/")[-1].split("?")[0] if "/atto/" in href else ""
        if not title and not href:
            return None
        return {"title": title, "estremi": estremi, "snippet": snippet, "url": url, "urn": urn}
    except Exception:
        return None


def _parse_fallback(soup, keyword: str) -> list:
    items = []
    for a in soup.select("a[href*='/atto/']")[:5]:
        href = a["href"]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        title = a.get_text(strip=True)
        if title and len(title) > 5:
            items.append({
                "title": title, "estremi": "",
                "snippet": f"Risultato per: {keyword}",
                "url": url,
                "urn": href.split("/atto/")[-1].split("?")[0],
            })
    return items


def _query(keyword: str, max_results: int = 5) -> list:
    params = {"query": keyword, "tipologiaDoc": "", "tipoVigenza": "VIGENTE"}
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        resp = client.get(SEARCH_URL, params=params, headers=HEADERS)
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    items = []
    result_list = soup.select("#risultatiRicerca .risultato-ricerca, .risultato, li.atto")
    for el in result_list[:max_results]:
        item = _parse_result(el)
        if item:
            items.append(item)
    if not items:
        items = _parse_fallback(soup, keyword)
    return items


def search_normattiva(keywords: list, max_results: int = 10) -> list:
    results = []
    seen_urns = set()
    for keyword in keywords[:5]:
        try:
            batch = _query(keyword, max_results=5)
            for item in batch:
                urn = item.get("urn", "")
                if urn and urn not in seen_urns:
                    seen_urns.add(urn)
                    item["source_keyword"] = keyword
                    results.append(item)
                elif not urn:
                    item["source_keyword"] = keyword
                    results.append(item)
        except Exception:
            continue
        if len(results) >= max_results:
            break
    return results[:max_results]


# ── Handler Vercel ─────────────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            testo     = params.get("testo",     [""])[0].strip()
            tipo_atto = params.get("tipo_atto", [""])[0].strip()
            oggetto   = params.get("oggetto",   [""])[0].strip()
            importo   = params.get("importo",   [""])[0].strip()
            if not testo and not oggetto:
                self._send_json({"error": "Parametro 'testo' obbligatorio"}, 400)
                return
            keywords = extract_keywords(testo, tipo_atto, oggetto, importo)
            results  = search_normattiva(keywords)
            self._send_json({"keywords": keywords, "results": results, "total": len(results)})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
