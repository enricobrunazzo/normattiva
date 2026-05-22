"""Endpoint /api/search — ricerca normativa PA con ranking Groq/Llama."""
from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.parse
import urllib.request

# ── Soglie D.Lgs. 36/2023 ─────────────────────────────────────────────────────
SEMI_THRESHOLD   = 5_000
DIRECT_THRESHOLD = 140_000
NEGO_THRESHOLD   = 215_000

# ── Database normativo locale ──────────────────────────────────────────────────
NORMATIVE_DB = [
    {
        "id": "dlgs_36_2023",
        "titolo": "Codice dei contratti pubblici",
        "estremi": "D.Lgs. 31 marzo 2023, n. 36",
        "descrizione": "Disciplina l'affidamento e l'esecuzione di appalti pubblici e concessioni. Regolamenta le soglie per affidamento diretto (art. 50), procedura negoziata (art. 72) e procedura aperta (art. 71). Obbliga alla nomina del RUP e all'acquisizione del CIG.",
        "articoli_chiave": ["art. 50 — affidamento diretto", "art. 51 — procedura negoziata semplificata", "art. 71 — procedura aperta", "art. 72 — procedura negoziata", "art. 15 — RUP"],
        "tags": ["acquisto", "appalto", "gara", "fornitore", "mepa", "consip", "lavori", "servizi", "manutenzione", "hardware", "software", "cloud", "determina", "cig", "cup", "rup"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2023-03-31;36",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+36+2023+codice+contratti+pubblici",
    },
    {
        "id": "dlgs_82_2005",
        "titolo": "Codice dell'Amministrazione Digitale (CAD)",
        "estremi": "D.Lgs. 7 marzo 2005, n. 82",
        "descrizione": "Regola la digitalizzazione della PA, l'uso di software, cloud computing e servizi ICT. Stabilisce l'obbligo di preferenza per soluzioni open source (art. 68) e il riuso del software (art. 69).",
        "articoli_chiave": ["art. 68 — analisi comparativa soluzioni", "art. 69 — riuso del software", "art. 50 — disponibilità dei dati"],
        "tags": ["software", "cloud", "digitalizzazione", "ict", "dati", "agid"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2005-03-07;82",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=codice+amministrazione+digitale+CAD+82+2005",
    },
    {
        "id": "dlgs_33_2013",
        "titolo": "Trasparenza e accesso civico",
        "estremi": "D.Lgs. 14 marzo 2013, n. 33",
        "descrizione": "Obbliga le PA alla pubblicazione su 'Amministrazione Trasparente' di dati su contratti, affidamenti e spese. Ogni determina di acquisto rilevante deve essere pubblicata. Disciplina anche il FOIA (art. 5).",
        "articoli_chiave": ["art. 23 — obblighi pubblicazione provvedimenti", "art. 37 — pubblicazione contratti e appalti", "art. 5 — accesso civico"],
        "tags": ["trasparenza", "acquisto", "appalto", "determina", "delibera", "anticorruzione"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2013-03-14;33",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+33+2013+trasparenza+amministrativa",
    },
    {
        "id": "l_190_2012",
        "titolo": "Legge Anticorruzione",
        "estremi": "L. 6 novembre 2012, n. 190",
        "descrizione": "Introduce misure per la prevenzione della corruzione nella PA. Obbliga gli enti al PTPCT. L'art. 1 co. 41 richiede l'attestazione di assenza di conflitto d'interessi in ogni provvedimento.",
        "articoli_chiave": ["art. 1 — PTPCT", "art. 1 co. 9 — misure obbligatorie", "art. 1 co. 41 — conflitto d'interessi"],
        "tags": ["anticorruzione", "trasparenza", "acquisto", "appalto", "determina", "conflitto"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2012-11-06;190",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+190+2012+anticorruzione",
    },
    {
        "id": "dlgs_267_2000",
        "titolo": "Testo Unico Enti Locali (TUEL)",
        "estremi": "D.Lgs. 18 agosto 2000, n. 267",
        "descrizione": "Disciplina l'organizzazione di Comuni e Province. Regolamenta competenze degli organi, forma degli atti (delibere, determine) e gestione finanziaria. Riferimento primario per ogni atto amministrativo di ente locale.",
        "articoli_chiave": ["art. 107 — competenze dirigenziali", "art. 192 — determinazione a contrarre", "art. 183 — assunzione impegno di spesa"],
        "tags": ["comune", "provincia", "determina", "delibera", "ordinanza", "acquisto", "appalto", "bilancio"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2000-08-18;267",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=testo+unico+enti+locali+TUEL+267+2000",
    },
    {
        "id": "dlgs_165_2001",
        "titolo": "Testo Unico Pubblico Impiego (TUPI)",
        "estremi": "D.Lgs. 30 marzo 2001, n. 165",
        "descrizione": "Disciplina il rapporto di lavoro dei dipendenti PA. Regola incarichi, consulenze esterne (art. 7), formazione e organizzazione degli uffici.",
        "articoli_chiave": ["art. 7 — gestione risorse e incarichi", "art. 19 — incarichi dirigenziali", "art. 36 — utilizzo flessibile"],
        "tags": ["personale", "consulenza", "formazione", "determina", "incarico"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2001-03-30;165",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=testo+unico+pubblico+impiego+165+2001",
    },
    {
        "id": "dlgs_196_2003",
        "titolo": "Codice Privacy + GDPR",
        "estremi": "D.Lgs. 30 giugno 2003, n. 196 (mod. dal Reg. UE 2016/679)",
        "descrizione": "Disciplina il trattamento dei dati personali. Il GDPR è direttamente applicabile. Rilevante per acquisti di software, cloud e qualsiasi trattamento dati personali da parte della PA.",
        "articoli_chiave": ["art. 13 GDPR — informativa", "art. 28 GDPR — responsabile trattamento", "art. 32 GDPR — sicurezza trattamento"],
        "tags": ["privacy", "dati", "software", "cloud", "gdpr"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003-06-30;196",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=codice+privacy+196+2003+GDPR",
    },
    {
        "id": "dlgs_81_2008",
        "titolo": "Testo Unico Sicurezza sul Lavoro",
        "estremi": "D.Lgs. 9 aprile 2008, n. 81",
        "descrizione": "Disciplina la sicurezza nei luoghi di lavoro. Negli appalti richiede il DUVRI e la verifica dei requisiti di sicurezza del fornitore.",
        "articoli_chiave": ["art. 26 — obblighi connessi ai contratti d'appalto (DUVRI)", "art. 17 — obblighi non delegabili"],
        "tags": ["sicurezza", "appalto", "lavori", "servizi", "contratto"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2008-04-09;81",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=testo+unico+sicurezza+lavoro+81+2008",
    },
    {
        "id": "dlgs_118_2011",
        "titolo": "Armonizzazione contabile enti locali",
        "estremi": "D.Lgs. 23 giugno 2011, n. 118",
        "descrizione": "Disciplina i sistemi contabili e gli schemi di bilancio di Regioni, Province e Comuni. Regolamenta la corretta imputazione delle spese e gli impegni di bilancio.",
        "articoli_chiave": ["art. 56 — principi contabili applicati", "Allegato 4/2 — principio della competenza finanziaria"],
        "tags": ["bilancio", "fondo", "comune", "provincia", "determina", "acquisto"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2011-06-23;118",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+118+2011+armonizzazione+contabile",
    },
    {
        "id": "pnrr_missione1",
        "titolo": "PNRR — Missione 1: Digitalizzazione PA",
        "estremi": "Piano Nazionale di Ripresa e Resilienza, Missione 1",
        "descrizione": "Definisce gli investimenti per la transizione digitale della PA. Gli acquisti ICT finanziati dal PNRR devono rispettare le linee guida AgID e i requisiti cloud.",
        "articoli_chiave": ["Componente 1.1 — Infrastrutture digitali", "Componente 1.2 — Abilitazione migrazione al cloud"],
        "tags": ["pnrr", "cloud", "software", "digitalizzazione", "agid", "fondo"],
        "url_normattiva": "https://www.normattiva.it/ricerca/semplice?query=PNRR+piano+nazionale+ripresa+resilienza+digitalizzazione",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=PNRR+piano+nazionale+ripresa+resilienza+digitalizzazione",
    },
    {
        "id": "l_136_2010",
        "titolo": "Tracciabilità dei flussi finanziari (CIG/CUP)",
        "estremi": "L. 13 agosto 2010, n. 136",
        "descrizione": "Obbliga le stazioni appaltanti a utilizzare conti dedicati e strumenti tracciabili. Ogni contratto pubblico deve riportare il CIG e, se finanziato con fondi pubblici, il CUP. La mancata indicazione nelle determine costituisce violazione.",
        "articoli_chiave": ["art. 3 — obblighi di tracciabilità dei flussi finanziari", "art. 3 co. 5 — obbligo CIG e CUP", "art. 6 — sanzioni per violazione tracciabilità"],
        "tags": ["cig", "cup", "tracciabilità", "acquisto", "appalto", "fornitore", "contratto", "determina", "gara", "rup"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2010-08-13;136",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+136+2010+tracciabilita+flussi+finanziari+CIG",
    },
]

# Indice tag → norm_id
TAG_INDEX: dict = {}
for _n in NORMATIVE_DB:
    for _t in _n["tags"]:
        TAG_INDEX.setdefault(_t, []).append(_n["id"])
NORME_BY_ID = {n["id"]: n for n in NORMATIVE_DB}

TIPO_ATTO_TAGS = {
    "determina":  ["determina", "acquisto", "cig"],
    "delibera":   ["delibera", "comune"],
    "ordinanza":  ["ordinanza"],
    "decreto":    ["determina"],
    "contratto":  ["contratto", "appalto", "cig"],
}

SEMANTIC_MAP = {
    "acquisto":      ["acquisto", "appalto", "cig"],
    "software":      ["software", "digitalizzazione", "dati", "privacy"],
    "cloud":         ["cloud", "pnrr", "software"],
    "hardware":      ["acquisto", "appalto"],
    "servizi":       ["appalto", "acquisto", "sicurezza", "cig"],
    "manutenzione":  ["appalto", "sicurezza"],
    "consulenza":    ["consulenza", "personale"],
    "formazione":    ["formazione", "personale"],
    "privacy":       ["privacy", "dati", "software"],
    "dati":          ["dati", "privacy", "software"],
    "gdpr":          ["privacy", "dati"],
    "trasparenza":   ["trasparenza", "anticorruzione"],
    "anticorruzione":["anticorruzione", "trasparenza"],
    "gara":          ["gara", "appalto", "acquisto", "cig"],
    "appalto":       ["appalto", "gara", "sicurezza", "cig"],
    "fornitore":     ["fornitore", "acquisto", "appalto"],
    "mepa":          ["mepa", "acquisto", "cig"],
    "consip":        ["mepa", "acquisto"],
    "lavori":        ["lavori", "sicurezza", "appalto"],
    "sicurezza":     ["sicurezza", "appalto"],
    "personale":     ["personale", "consulenza"],
    "bilancio":      ["bilancio", "comune"],
    "pnrr":          ["pnrr", "cloud", "software", "cup"],
    "comune":        ["comune", "determina", "bilancio"],
    "regione":       ["comune"],
    "provincia":     ["comune", "bilancio"],
    "incarico":      ["consulenza", "personale"],
    "digitale":      ["software", "cloud", "pnrr"],
    "ict":           ["software", "cloud"],
    "gestionale":    ["software", "dati"],
    "licenza":       ["software"],
    "abbonamento":   ["software", "acquisto"],
    "saas":          ["software", "cloud", "privacy"],
    "agid":          ["software", "cloud", "pnrr"],
    "cig":           ["cig", "acquisto", "appalto"],
    "cup":           ["cup", "cig", "pnrr"],
    "tracciabilita": ["cig", "tracciabilità"],
    "affidamento":   ["acquisto", "appalto", "cig"],
    "conflitto":     ["anticorruzione", "conflitto"],
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
    "questo","questa","questi","queste","also","such",
}


# ── Motore tag (pre-filtro) ────────────────────────────────────────────────────
def _importo_tags(importo_str: str) -> list:
    try:
        val = float(importo_str.replace(".", "").replace(",", ".").replace("€", "").strip())
    except (ValueError, AttributeError):
        return []
    if val <= SEMI_THRESHOLD:
        return ["acquisto"]
    elif val <= DIRECT_THRESHOLD:
        return ["acquisto", "appalto", "cig"]
    elif val <= NEGO_THRESHOLD:
        return ["appalto", "gara", "cig"]
    else:
        return ["appalto", "gara", "lavori", "cig"]


def _importo_label(importo_str: str) -> str:
    try:
        val = float(importo_str.replace(".", "").replace(",", ".").replace("€", "").strip())
    except (ValueError, AttributeError):
        return ""
    if val <= SEMI_THRESHOLD:
        return f"€{val:,.0f} — Affidamento diretto semplificato (art. 50 co. 1, D.Lgs. 36/2023)"
    elif val <= DIRECT_THRESHOLD:
        return f"€{val:,.0f} — Affidamento diretto (art. 50, D.Lgs. 36/2023)"
    elif val <= NEGO_THRESHOLD:
        return f"€{val:,.0f} — Procedura negoziata (art. 72, D.Lgs. 36/2023)"
    else:
        return f"€{val:,.0f} — Procedura aperta (art. 71, D.Lgs. 36/2023)"


def _tag_search(testo: str, tipo_atto: str, oggetto: str, importo: str) -> list:
    """Pre-filtro: restituisce norme candidate ordinate per score tag."""
    matched: dict = {}

    def _add(nid, score=1):
        matched[nid] = matched.get(nid, 0) + score

    if tipo_atto and tipo_atto.lower() in TIPO_ATTO_TAGS:
        for tag in TIPO_ATTO_TAGS[tipo_atto.lower()]:
            for nid in TAG_INDEX.get(tag, []):
                _add(nid, 2)

    for tag in _importo_tags(importo):
        for nid in TAG_INDEX.get(tag, []):
            _add(nid, 3)

    full_text = f"{testo} {oggetto}".lower()
    tokens = full_text.replace(",", " ").replace(".", " ").replace("/", " ").split()
    for token in tokens:
        token = token.strip("'\"()[]")
        if token in STOP_WORDS or len(token) < 4:
            continue
        for nid in TAG_INDEX.get(token, []):
            _add(nid, 2)
        for sem_tag in SEMANTIC_MAP.get(token, []):
            for nid in TAG_INDEX.get(sem_tag, []):
                _add(nid, 1)

    sorted_ids = sorted(matched.items(), key=lambda x: x[1], reverse=True)
    results = []
    for nid, score in sorted_ids:
        norma = NORME_BY_ID[nid].copy()
        norma["score"] = score
        norma["ai_motivation"] = ""
        results.append(norma)
    return results


# ── Groq ranking (Llama 3.3 70B — free tier) ──────────────────────────────────
def _groq_rank(testo: str, tipo_atto: str, oggetto: str, importo: str,
               candidates: list) -> list:
    """
    Chiama Groq (Llama 3.3 70B) per riordinare i candidati e aggiungere motivazione.
    Free tier: 14.400 req/giorno, nessuna carta di credito.
    Usa solo urllib della stdlib — zero dipendenze esterne.
    Restituisce la lista arricchita, o i candidati originali in caso di errore.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return candidates

    try:
        norme_list = "\n".join(
            f"- ID: {n['id']} | {n['estremi']} — {n['titolo']}"
            for n in candidates
        )
        importo_info = f"Importo: {importo}" if importo else "Importo: non specificato"
        prompt = (
            "Sei un esperto di diritto amministrativo italiano.\n"
            "Un funzionario della PA deve redigere il seguente atto:\n"
            f"- Tipo atto: {tipo_atto or 'non specificato'}\n"
            f"- Oggetto: {oggetto or 'non specificato'}\n"
            f"- {importo_info}\n"
            f"- Descrizione esigenza: {testo}\n\n"
            "Queste sono le norme candidate trovate dal sistema:\n"
            f"{norme_list}\n\n"
            "Restituisci SOLO un oggetto JSON valido (nessun testo prima o dopo) con questa struttura:\n"
            "{\n"
            '  "ranked": [\n'
            '    {"id": "<id_norma>", "motivation": "<1-2 frasi in italiano: perché questa norma è rilevante per questo specifico atto>"},\n'
            "    ...\n"
            "  ]\n"
            "}\n"
            "Ordina dalla più rilevante alla meno rilevante. "
            "Includi solo le norme effettivamente applicabili. Ometti quelle non pertinenti."
        )

        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1024,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        resp = urllib.request.urlopen(req, timeout=20)
        data = json.loads(resp.read().decode("utf-8"))
        raw = data["choices"][0]["message"]["content"].strip()

        # Estrai JSON anche se il modello aggiunge backtick
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        ranked_data = json.loads(raw)

        by_id = {n["id"]: n for n in candidates}
        result = []
        ranked_ids = set()
        for item in ranked_data.get("ranked", []):
            nid = item["id"]
            if nid in by_id:
                norma = by_id[nid].copy()
                norma["ai_motivation"] = item.get("motivation", "")
                result.append(norma)
                ranked_ids.add(nid)

        # Aggiunge eventuali norme non restituite dal modello in fondo
        for n in candidates:
            if n["id"] not in ranked_ids:
                n["ai_motivation"] = ""
                result.append(n)

        return result

    except Exception:
        # Qualsiasi errore → fallback motore classico
        return candidates


# ── Entry point ────────────────────────────────────────────────────────────────
def find_norme(testo: str, tipo_atto: str = "", oggetto: str = "", importo: str = "") -> dict:
    candidates = _tag_search(testo, tipo_atto, oggetto, importo)
    results = _groq_rank(testo, tipo_atto, oggetto, importo, candidates)

    # Keywords per frontend
    full_text = f"{testo} {oggetto}".lower()
    tokens = full_text.replace(",", " ").replace(".", " ").replace("/", " ").split()
    kw_set = set()
    for token in tokens:
        token = token.strip("'\"()[]")
        if token not in STOP_WORDS and len(token) >= 4 and (
            token in TAG_INDEX or token in SEMANTIC_MAP
        ):
            kw_set.add(token)

    ai_active = bool(os.environ.get("GROQ_API_KEY", ""))

    return {
        "keywords": list(kw_set)[:10],
        "importo_label": _importo_label(importo) if importo else "",
        "results": results,
        "total": len(results),
        "ai_active": ai_active,
    }


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
                self._send_json({"error": "Inserisci almeno una descrizione o un oggetto"}, 400)
                return
            data = find_norme(testo, tipo_atto, oggetto, importo)
            self._send_json(data)
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
