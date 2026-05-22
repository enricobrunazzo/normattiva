"""Client per la ricerca su Normattiva."""
import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.normattiva.it"
SEARCH_URL = f"{BASE_URL}/ricerca/semplice"

HEADERS = {
    "User-Agent": "NormativaSearchBot/1.0 (ricerca normativa PA; +https://github.com/enricobrunazzo/normattiva)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "it-IT,it;q=0.9",
}


def search_normattiva(keywords: list[str], max_results: int = 10) -> list[dict]:
    """Interroga Normattiva con le parole chiave e restituisce lista di norme trovate."""
    results = []
    seen_urns = set()

    for keyword in keywords[:5]:  # max 5 query distinte per evitare rate limiting
        try:
            batch = _query(keyword, max_results=5)
            for item in batch:
                urn = item.get("urn", "")
                if urn and urn not in seen_urns:
                    seen_urns.add(urn)
                    item["source_keyword"] = keyword
                    results.append(item)
        except Exception:
            continue  # skip keyword problematica

        if len(results) >= max_results:
            break

    return results[:max_results]


def _query(keyword: str, max_results: int = 5) -> list[dict]:
    """Singola query verso Normattiva."""
    params = {
        "query": keyword,
        "tipologiaDoc": "",
        "tipoVigenza": "VIGENTE",
    }

    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        resp = client.get(SEARCH_URL, params=params, headers=HEADERS)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    items = []

    # Normattiva risultati in lista #risultatiRicerca
    result_list = soup.select("#risultatiRicerca .risultato-ricerca, .risultato, li.atto")

    for el in result_list[:max_results]:
        item = _parse_result(el)
        if item:
            items.append(item)

    # Fallback: prova selettori alternativi se la pagina cambia struttura
    if not items:
        items = _parse_fallback(soup, keyword)

    return items


def _parse_result(el) -> dict | None:
    """Estrae dati da un singolo elemento risultato."""
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

        # Prova a estrarre URN Normattiva dall'href
        urn = ""
        if "/atto/" in href:
            urn = href.split("/atto/")[-1].split("?")[0]

        if not title and not href:
            return None

        return {
            "title": title,
            "estremi": estremi,
            "snippet": snippet,
            "url": url,
            "urn": urn,
        }
    except Exception:
        return None


def _parse_fallback(soup: BeautifulSoup, keyword: str) -> list[dict]:
    """Fallback parser se la struttura della pagina è cambiata."""
    items = []
    # Cerca tutti i link che puntano ad atti normativi
    for a in soup.select("a[href*='/atto/']")[:5]:
        href = a["href"]
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        title = a.get_text(strip=True)
        if title and len(title) > 5:
            items.append({
                "title": title,
                "estremi": "",
                "snippet": f"Risultato trovato per: {keyword}",
                "url": url,
                "urn": href.split("/atto/")[-1].split("?")[0],
            })
    return items
