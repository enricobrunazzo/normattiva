"""Estrazione parole chiave da esigenza amministrativa."""

# Dizionario tipo atto → keywords normative di base
TIPO_ATTO_KEYWORDS = {
    "determina": ["determinazione dirigenziale", "determine", "atto amministrativo"],
    "delibera": ["deliberazione", "delibera giunta", "delibera consiglio"],
    "ordinanza": ["ordinanza sindacale", "ordinanza dirigenziale"],
    "decreto": ["decreto", "atto di indirizzo"],
    "contratto": ["contratto pubblico", "accordo", "convenzione"],
}

# Soglie per acquisti pubblici (D.Lgs. 36/2023 aggiornate)
SEMI_THRESHOLD = 5_000       # affidamento diretto semplificato
DIRECT_THRESHOLD = 140_000   # affidamento diretto
NEGO_THRESHOLD = 215_000     # procedura negoziata

# Keywords per categoria di importo
def _importo_keywords(importo_str: str) -> list[str]:
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


# Keywords semplificate estratte dal testo libero
_STOP_WORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
    "di", "del", "della", "degli", "dei", "delle",
    "a", "al", "alla", "ai", "agli", "alle",
    "da", "dal", "dalla", "dai", "dagli", "dalle",
    "in", "nel", "nella", "nei", "negli", "nelle",
    "con", "su", "per", "tra", "fra",
    "che", "chi", "cui", "non", "ma", "se",
    "ho", "ha", "hanno", "devo", "deve", "voglio", "fare",
    "sono", "è", "e", "o", "come", "quando", "dove",
}

# Dizionario sintetico testo → normativa
_SEMANTIC_MAP = {
    "acquisto": ["codice contratti pubblici", "D.Lgs. 36/2023"],
    "software": ["digitalizzazione", "CAD", "D.Lgs. 82/2005", "AgID"],
    "cloud": ["cloud computing PA", "AgID", "PNRR digitalizzazione"],
    "hardware": ["codice contratti pubblici", "D.Lgs. 36/2023"],
    "servizi": ["servizi pubblici", "affidamento servizi", "D.Lgs. 36/2023"],
    "manutenzione": ["manutenzione", "contratto manutenzione", "D.Lgs. 36/2023"],
    "consulenza": ["incarico professionale", "D.Lgs. 165/2001", "articolo 7 TUPI"],
    "formazione": ["formazione dipendenti PA", "D.Lgs. 165/2001"],
    "privacy": ["GDPR", "D.Lgs. 196/2003", "codice privacy", "Regolamento UE 2016/679"],
    "dati": ["protezione dati", "GDPR", "D.Lgs. 196/2003"],
    "trasparenza": ["D.Lgs. 33/2013", "amministrazione trasparente", "FOIA"],
    "anticorruzione": ["L. 190/2012", "ANAC", "piano anticorruzione"],
    "gara": ["D.Lgs. 36/2023", "codice contratti", "bando di gara", "CIG"],
    "appalto": ["D.Lgs. 36/2023", "appalto pubblico", "CIG", "RUP"],
    "fornitore": ["albo fornitori", "MEPA", "Consip"],
    "mepa": ["MEPA", "mercato elettronico PA", "Consip", "D.Lgs. 36/2023"],
    "consip": ["Consip", "convenzioni Consip", "acquisti centralizzati"],
    "lavori": ["lavori pubblici", "D.Lgs. 36/2023", "progettazione"],
    "sicurezza": ["D.Lgs. 81/2008", "sicurezza lavoro", "DUVRI"],
    "personale": ["D.Lgs. 165/2001", "TUPI", "personale PA"],
    "bilancio": ["D.Lgs. 118/2011", "armonizzazione contabile", "piano dei conti"],
    "fondo": ["fondo", "fondi strutturali", "PNRR"],
    "pnrr": ["PNRR", "Piano Nazionale Ripresa Resilienza", "missione digitalizzazione"],
    "comune": ["TUEL", "D.Lgs. 267/2000", "enti locali"],
    "regione": ["legge regionale", "autonomia regionale"],
    "provincia": ["TUEL", "D.Lgs. 267/2000", "province"],
}


def extract_keywords(testo: str, tipo_atto: str = "", oggetto: str = "", importo: str = "") -> list[str]:
    """Restituisce lista di parole chiave per la ricerca normativa."""
    keywords: list[str] = []

    # 1. Parole chiave dal tipo atto
    if tipo_atto and tipo_atto.lower() in TIPO_ATTO_KEYWORDS:
        keywords.extend(TIPO_ATTO_KEYWORDS[tipo_atto.lower()])

    # 2. Parole chiave da importo
    if importo:
        keywords.extend(_importo_keywords(importo))

    # 3. Mappatura semantica dal testo + oggetto
    full_text = f"{testo} {oggetto}".lower()
    tokens = full_text.replace(",", " ").replace(".", " ").split()
    for token in tokens:
        token = token.strip("'\"()[]")
        if token in _STOP_WORDS or len(token) < 4:
            continue
        if token in _SEMANTIC_MAP:
            keywords.extend(_SEMANTIC_MAP[token])

    # Deduplication mantenendo ordine
    seen = set()
    result = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            result.append(k)

    # Fallback: usa le parole significative del testo come query grezza
    if not result:
        significant = [t for t in tokens if t not in _STOP_WORDS and len(t) >= 4]
        result = list(dict.fromkeys(significant[:8]))

    return result[:12]  # max 12 keywords
