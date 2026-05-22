"""Endpoint /api/search — ricerca normativa PA con ranking Groq/Llama."""
from http.server import BaseHTTPRequestHandler
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

# ── Defensive startup log (eseguito al cold start, visibile nei Runtime Logs) ──
_GROQ_API_KEY_PRESENT = bool(os.environ.get("GROQ_API_KEY", ""))
print(
    f"[INIT] GROQ_API_KEY present: {_GROQ_API_KEY_PRESENT} "
    f"| len={len(os.environ.get('GROQ_API_KEY', ''))}",
    flush=True,
)
if not _GROQ_API_KEY_PRESENT:
    print(
        "[INIT] WARNING: GROQ_API_KEY non trovata nell'ambiente. "
        "Verifica Settings → Environment Variables su Vercel e fai un nuovo deploy (non redeploy da cache).",
        flush=True,
    )

# ── Soglie D.Lgs. 36/2023 ─────────────────────────────────────────────────────
SEMI_THRESHOLD   = 5_000
DIRECT_THRESHOLD = 140_000
NEGO_THRESHOLD   = 215_000

# ── Numero massimo di candidati passati a Groq ────────────────────────────────
GROQ_MAX_CANDIDATES = 15

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
    # ── NUOVE NORME ──────────────────────────────────────────────────────────────
    {
        "id": "l_241_1990",
        "titolo": "Legge sul procedimento amministrativo",
        "estremi": "L. 7 agosto 1990, n. 241",
        "descrizione": "Regola il procedimento amministrativo in tutte le sue fasi: avvio, istruttoria, partecipazione dei privati, motivazione degli atti, silenzio-assenso, accesso agli atti. È il riferimento trasversale per la legittimità di qualsiasi provvedimento della PA, incluse determine e delibere.",
        "articoli_chiave": [
            "art. 1 — principi generali (efficacia, economicità, imparzialità)",
            "art. 3 — obbligo di motivazione del provvedimento",
            "art. 7 — comunicazione avvio del procedimento",
            "art. 21-octies — annullabilità del provvedimento",
            "art. 22 — accesso agli atti amministrativi",
        ],
        "tags": ["determina", "delibera", "ordinanza", "procedimento", "motivazione", "accesso", "comune", "provincia", "appalto", "acquisto"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1990-08-07;241",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+241+1990+procedimento+amministrativo",
    },
    {
        "id": "dlgs_50_2016",
        "titolo": "Codice dei contratti pubblici 2016 (previgente)",
        "estremi": "D.Lgs. 18 aprile 2016, n. 50",
        "descrizione": "Codice appalti previgente, abrogato dal D.Lgs. 36/2023 ma ancora applicabile ai contratti aggiudicati prima del 1° luglio 2023 e ai procedimenti in corso. Rilevante per contestare o gestire appalti storici, proroghe e collaudi di contratti avviati sotto la vecchia disciplina.",
        "articoli_chiave": [
            "art. 36 — contratti sotto soglia (affidamento diretto, procedura negoziata)",
            "art. 63 — procedura negoziata senza bando",
            "art. 95 — criteri di aggiudicazione",
            "art. 106 — modifica dei contratti in corso",
        ],
        "tags": ["appalto", "gara", "acquisto", "affidamento", "contratto", "proroga", "servizi", "lavori", "cig"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2016-04-18;50",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+50+2016+codice+contratti+pubblici",
    },
    {
        "id": "l_296_2006_consip",
        "titolo": "Obbligo Consip / MEPA (L. Finanziaria 2007)",
        "estremi": "L. 27 dicembre 2006, n. 296, art. 1 co. 449-450",
        "descrizione": "Obbliga le amministrazioni statali ad approvvigionarsi tramite convenzioni Consip o a utilizzarne i parametri come prezzi di riferimento (benchmark). Le PA non statali (Comuni, Province, ASL) devono comunque ricorrere al MEPA o giustificare la convenienza economica di procedure autonome. Il mancato rispetto espone il RUP a responsabilità erariale.",
        "articoli_chiave": [
            "art. 1 co. 449 — obbligo adesione convenzioni Consip per PA statali",
            "art. 1 co. 450 — obbligo MEPA per acquisti sotto soglia comunitaria",
            "art. 1 co. 452 — benchmark prezzi Consip per PA non statali",
        ],
        "tags": ["mepa", "consip", "acquisto", "appalto", "fornitore", "determina", "cig", "affidamento", "benchmark"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2006-12-27;296",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+296+2006+finanziaria+consip+mepa+449",
    },
    {
        "id": "dlgs_231_2001",
        "titolo": "Responsabilità amministrativa degli enti (D.Lgs. 231)",
        "estremi": "D.Lgs. 8 giugno 2001, n. 231",
        "descrizione": "Disciplina la responsabilità amministrativa delle persone giuridiche private per reati commessi nell'interesse o a vantaggio dell'ente. Rilevante negli appalti pubblici: la PA deve verificare che il fornitore privato sia dotato di Modello Organizzativo 231 (MOG) per prevenire reati di corruzione, frode e riciclaggio.",
        "articoli_chiave": [
            "art. 5 — responsabilità dell'ente per reati dei propri soggetti",
            "art. 6 — esimenti: adozione ed efficace attuazione del MOG",
            "art. 24 — reati contro la PA (corruzione, concussione, frode)",
            "art. 25 — peculato, corruzione e induzione indebita",
        ],
        "tags": ["anticorruzione", "appalto", "fornitore", "contratto", "gara", "conflitto", "determina"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2001-06-08;231",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+231+2001+responsabilita+amministrativa+enti",
    },
    {
        "id": "circ_agid_cloud_2021",
        "titolo": "Qualificazione cloud PA — Linee guida AgID / ACN",
        "estremi": "Circolare AgID n. 2/2018 + Determinazione AgID 628/2021 + Regolamento ACN 2022",
        "descrizione": "Definisce i requisiti di qualificazione per i servizi cloud acquistabili dalla PA (IaaS, PaaS, SaaS). Solo i servizi presenti nel Catalogo Cloud PA (marketplace.cloud.gov.it) possono essere acquisiti. Classifica i servizi in tre livelli: PSN, Cloud qualificato, SaaS qualificato. Rilevante per ogni acquisto cloud, anche tramite MEPA.",
        "articoli_chiave": [
            "Determinazione 628/2021 — qualificazione servizi SaaS per PA",
            "Regolamento ACN 2022 — classificazione dati e servizi cloud",
            "Circolare AgID 2/2018 — criteri qualificazione CSP e SaaS",
        ],
        "tags": ["cloud", "software", "saas", "agid", "digitalizzazione", "pnrr", "ict", "acquisto", "mepa"],
        "url_normattiva": "https://www.agid.gov.it/it/infrastrutture/cloud-pa",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=AgID+qualificazione+cloud+PA+628+2021",
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
    "software":      ["software", "digitalizzazione", "dati", "privacy", "saas"],
    "cloud":         ["cloud", "pnrr", "software", "saas", "agid"],
    "hardware":      ["acquisto", "appalto"],
    "servizi":       ["appalto", "acquisto", "sicurezza", "cig"],
    "manutenzione":  ["appalto", "sicurezza"],
    "consulenza":    ["consulenza", "personale"],
    "formazione":    ["formazione", "personale"],
    "privacy":       ["privacy", "dati", "software"],
    "dati":          ["dati", "privacy", "software"],
    "gdpr":          ["privacy", "dati"],
    "trasparenza":   ["trasparenza", "anticorruzione"],
    "anticorruzione": ["anticorruzione", "trasparenza"],
    "gara":          ["gara", "appalto", "acquisto", "cig"],
    "appalto":       ["appalto", "gara", "sicurezza", "cig"],
    "fornitore":     ["fornitore", "acquisto", "appalto"],
    "mepa":          ["mepa", "acquisto", "cig", "consip"],
    "consip":        ["mepa", "acquisto", "consip"],
    "lavori":        ["lavori", "sicurezza", "appalto"],
    "sicurezza":     ["sicurezza", "appalto"],
    "personale":     ["personale", "consulenza"],
    "bilancio":      ["bilancio", "comune"],
    "pnrr":          ["pnrr", "cloud", "software", "cup"],
    "comune":        ["comune", "determina", "bilancio"],
    "regione":       ["comune"],
    "provincia":     ["comune", "bilancio"],
    "incarico":      ["consulenza", "personale"],
    "digitale":      ["software", "cloud", "pnrr", "agid"],
    "ict":           ["software", "cloud", "agid"],
    "gestionale":    ["software", "dati"],
    "licenza":       ["software"],
    "abbonamento":   ["software", "acquisto"],
    "saas":          ["software", "cloud", "privacy", "agid"],
    "agid":          ["software", "cloud", "pnrr", "agid"],
    "cig":           ["cig", "acquisto", "appalto"],
    "cup":           ["cup", "cig", "pnrr"],
    "tracciabilita": ["cig", "tracciabilità"],
    "affidamento":   ["acquisto", "appalto", "cig", "affidamento"],
    "conflitto":     ["anticorruzione", "conflitto"],
    # nuove chiavi semantiche
    "procedimento":  ["procedimento", "motivazione", "determina"],
    "motivazione":   ["motivazione", "procedimento", "determina"],
    "accesso":       ["accesso", "trasparenza"],
    "proroga":       ["proroga", "contratto", "appalto"],
    "benchmark":     ["benchmark", "mepa", "consip"],
    "mog":           ["anticorruzione", "fornitore", "appalto"],
    "231":           ["anticorruzione", "fornitore", "appalto"],
    "qualificazione": ["cloud", "agid", "saas"],
    "marketplace":   ["cloud", "agid", "mepa"],
    "psn":           ["cloud", "agid", "pnrr"],
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


# ── Helpers importo ────────────────────────────────────────────────────────────
def _parse_importo(importo_str: str) -> float | None:
    try:
        return float(importo_str.replace(".", "").replace(",", ".").replace("€", "").strip())
    except (ValueError, AttributeError):
        return None


def _importo_tags(importo_str: str, convenzione: bool = False) -> list:
    val = _parse_importo(importo_str)
    if val is None:
        return []
    if convenzione:
        return ["acquisto", "mepa", "consip", "cig"]
    if val <= SEMI_THRESHOLD:
        return ["acquisto"]
    elif val <= DIRECT_THRESHOLD:
        return ["acquisto", "appalto", "cig"]
    elif val <= NEGO_THRESHOLD:
        return ["appalto", "gara", "cig"]
    else:
        return ["appalto", "gara", "lavori", "cig"]


def _importo_label(importo_str: str, convenzione: bool = False) -> str:
    val = _parse_importo(importo_str)
    if val is None:
        return ""
    if convenzione:
        return (
            f"€{val:,.0f} — Adesione a convenzione Consip / Ordine su MEPA "
            f"(art. 1 co. 449 L. 296/2006 e art. 26 L. 488/1999)"
        )
    if val <= SEMI_THRESHOLD:
        return f"€{val:,.0f} — Affidamento diretto semplificato (art. 50 co. 1, D.Lgs. 36/2023)"
    elif val <= DIRECT_THRESHOLD:
        return f"€{val:,.0f} — Affidamento diretto (art. 50, D.Lgs. 36/2023)"
    elif val <= NEGO_THRESHOLD:
        return f"€{val:,.0f} — Procedura negoziata (art. 72, D.Lgs. 36/2023)"
    else:
        return f"€{val:,.0f} — Procedura aperta (art. 71, D.Lgs. 36/2023)"


# ── Motore tag (pre-filtro) ────────────────────────────────────────────────────
def _tag_search(testo: str, tipo_atto: str, oggetto: str, importo: str,
                convenzione: bool = False) -> list:
    """Pre-filtro: restituisce norme candidate ordinate per score tag."""
    matched: dict = {}

    def _add(nid, score=1):
        matched[nid] = matched.get(nid, 0) + score

    if tipo_atto and tipo_atto.lower() in TIPO_ATTO_TAGS:
        for tag in TIPO_ATTO_TAGS[tipo_atto.lower()]:
            for nid in TAG_INDEX.get(tag, []):
                _add(nid, 2)

    for tag in _importo_tags(importo, convenzione):
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

    if convenzione:
        for boost_id in ("l_136_2010", "dlgs_33_2013", "dlgs_267_2000", "l_296_2006_consip"):
            if boost_id in NORME_BY_ID:
                _add(boost_id, 4)

    sorted_ids = sorted(matched.items(), key=lambda x: x[1], reverse=True)
    results = []
    for nid, score in sorted_ids:
        norma = NORME_BY_ID[nid].copy()
        norma["score"] = score
        norma["ai_motivation"] = ""
        results.append(norma)
    return results


def _extract_json(raw: str) -> dict:
    """Estrae il primo oggetto JSON valido da una stringa, anche con testo attorno."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    m = re.search(r"(\{[\s\S]*\})", raw)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Nessun JSON valido trovato. Raw: {raw[:300]!r}")


# ── Groq ranking (Llama 3.3 70B — free tier) ──────────────────────────────────
def _groq_rank(testo: str, tipo_atto: str, oggetto: str, importo: str,
               candidates: list, convenzione: bool = False) -> list:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("[GROQ] SKIP — GROQ_API_KEY assente a runtime", flush=True)
        return candidates

    groq_candidates = candidates[:GROQ_MAX_CANDIDATES]
    remaining = candidates[GROQ_MAX_CANDIDATES:]

    key_preview = f"{api_key[:8]}...{api_key[-4:]}"
    print(f"[GROQ] Calling Groq API | key={key_preview} | candidates={len(groq_candidates)} (capped from {len(candidates)}) | convenzione={convenzione}", flush=True)
    t0 = time.time()

    try:
        norme_list = "\n".join(
            f"- ID: {n['id']} | {n['estremi']} — {n['titolo']}"
            for n in groq_candidates
        )
        importo_info = f"Importo: {importo}" if importo else "Importo: non specificato"

        convenzione_info = (
            "- Modalità di acquisto: CONVENZIONE CONSIP / ORDINE SU MEPA "
            "(non è richiesta gara autonoma; la procedura è già assolta dalla convenzione quadro)\n"
            if convenzione else ""
        )

        prompt = (
            "Sei un esperto di diritto amministrativo italiano.\n"
            "Un funzionario della PA deve redigere il seguente atto:\n"
            f"- Tipo atto: {tipo_atto or 'non specificato'}\n"
            f"- Oggetto: {oggetto or 'non specificato'}\n"
            f"- {importo_info}\n"
            f"{convenzione_info}"
            f"- Descrizione esigenza: {testo}\n\n"
            "Queste sono le norme candidate trovate dal sistema:\n"
            f"{norme_list}\n\n"
            "Restituisci un oggetto JSON con questa struttura:\n"
            "{\"ranked\": [{\"id\": \"<id_norma>\", \"motivation\": \"<1-2 frasi perché rilevante>\"}]}\n"
            "Ordina dalla più rilevante alla meno rilevante. "
            "Includi TUTTE le norme elencate, anche quelle meno pertinenti (motivation breve). "
            "Non omettere nessuna norma dalla lista."
        )

        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2048,
        }).encode()

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode())

        elapsed = time.time() - t0
        print(f"[GROQ] OK | elapsed={elapsed:.2f}s", flush=True)

        raw_content = body["choices"][0]["message"]["content"]
        ranked_data = _extract_json(raw_content)
        ranked_list = ranked_data.get("ranked", [])

        ranked_map = {item["id"]: item.get("motivation", "") for item in ranked_list}
        reranked = []
        for item in ranked_list:
            nid = item["id"]
            if nid in NORME_BY_ID:
                norma = NORME_BY_ID[nid].copy()
                norma["score"] = 100 - len(reranked)
                norma["ai_motivation"] = ranked_map.get(nid, "")
                reranked.append(norma)

        seen = {n["id"] for n in reranked}
        for n in groq_candidates:
            if n["id"] not in seen:
                n["ai_motivation"] = ""
                reranked.append(n)

        return reranked + remaining

    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")[:500]
        print(f"[GROQ ERROR] HTTP {e.code} | {err_body}", flush=True)
        return candidates
    except Exception as exc:
        print(f"[GROQ ERROR] {type(exc).__name__}: {exc}", flush=True)
        return candidates


# ── Handler HTTP ───────────────────────────────────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        testo      = params.get("q", [""])[0].strip()
        tipo_atto  = params.get("tipo_atto", [""])[0].strip().lower()
        oggetto    = params.get("oggetto", [""])[0].strip()
        importo    = params.get("importo", [""])[0].strip()
        convenzione = params.get("convenzione", ["false"])[0].strip().lower() in ("true", "1", "yes")

        t_start = time.time()

        candidates = _tag_search(testo, tipo_atto, oggetto, importo, convenzione)
        results    = _groq_rank(testo, tipo_atto, oggetto, importo, candidates, convenzione)

        importo_label = _importo_label(importo, convenzione)

        output = {
            "query": testo,
            "tipo_atto": tipo_atto,
            "oggetto": oggetto,
            "importo_label": importo_label,
            "convenzione": convenzione,
            "results": results,
            "elapsed_ms": round((time.time() - t_start) * 1000),
        }

        body = json.dumps(output, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
