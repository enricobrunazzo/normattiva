"""Endpoint /api/search — ricerca normativa PA con ranking Groq/Llama."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler
from html import unescape
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from api.utils.supabase_search import supabase_vector_search, log_query_to_supabase

# ── Defensive startup log ────────────────────────────────────────────────────────
_GROQ_API_KEY_PRESENT = bool(os.environ.get("GROQ_API_KEY", ""))
_SUPABASE_CONFIGURED = bool(os.environ.get("SUPABASE_URL", "") and os.environ.get("SUPABASE_KEY", ""))
print(
    f"[INIT] GROQ_API_KEY present: {_GROQ_API_KEY_PRESENT} "
    f"| len={len(os.environ.get('GROQ_API_KEY', ''))} "
    f"| SUPABASE configured: {_SUPABASE_CONFIGURED}",
    flush=True,
)
if not _GROQ_API_KEY_PRESENT:
    print(
        "[INIT] WARNING: GROQ_API_KEY non trovata nell'ambiente. "
        "Verifica Settings → Environment Variables su Vercel e fai un nuovo deploy.",
        flush=True,
    )
if not _SUPABASE_CONFIGURED:
    print(
        "[INIT] WARNING: SUPABASE_URL / SUPABASE_KEY non trovate. "
        "Userò il fallback locale su tag.",
        flush=True,
    )

# ── Soglie D.Lgs. 36/2023 ─────────────────────────────────────────────────────
SEMI_THRESHOLD   = 5_000
DIRECT_THRESHOLD = 140_000
NEGO_THRESHOLD   = 215_000

# ── Numero massimo di candidati passati a Groq (ranking) ─────────────────────
GROQ_MAX_CANDIDATES = 12

# ── Score minimo per entrare nel pool Groq ────────────────────────────────────
MIN_SCORE_FOR_GROQ = 2

# ── Modelli Groq ──────────────────────────────────────────────────────────────
MODEL_EXPAND = "openai/gpt-oss-20b"
MODEL_RANK   = "openai/gpt-oss-120b"

# ── Cache in memoria per il testo vigente da Normattiva ───────────────────────
_NORM_TEXT_CACHE: dict = {}
_CACHE_TTL = 60 * 60 * 6

# ── Fetch live ────────────────────────────────────────────────────────────────
K_FETCH_LIVE            = 3
FETCH_TIMEOUT_PER_NORMA = 3
FETCH_BUDGET_TOTAL      = 4

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
        "tags": ["software", "cloud", "digitalizzazione", "ict", "dati", "agid", "open-source", "riuso"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2005-03-07;82",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=codice+amministrazione+digitale+CAD+82+2005",
    },
    {
        "id": "dlgs_33_2013",
        "titolo": "Trasparenza e accesso civico",
        "estremi": "D.Lgs. 14 marzo 2013, n. 33",
        "descrizione": "Obbliga le PA alla pubblicazione su 'Amministrazione Trasparente' di dati su contratti, affidamenti e spese. Ogni determina di acquisto rilevante deve essere pubblicata. Disciplina anche il FOIA (art. 5).",
        "articoli_chiave": ["art. 23 — obblighi pubblicazione provvedimenti", "art. 37 — pubblicazione contratti e appalti", "art. 5 — accesso civico"],
        "tags": ["trasparenza", "anticorruzione", "foia", "pubblicazione", "accesso", "determina"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2013-03-14;33",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+33+2013+trasparenza+amministrativa",
    },
    {
        "id": "l_190_2012",
        "titolo": "Legge Anticorruzione",
        "estremi": "L. 6 novembre 2012, n. 190",
        "descrizione": "Introduce misure per la prevenzione della corruzione nella PA. Obbliga gli enti al PTPCT. L'art. 1 co. 41 richiede l'attestazione di assenza di conflitto d'interessi in ogni provvedimento.",
        "articoli_chiave": ["art. 1 — PTPCT", "art. 1 co. 9 — misure obbligatorie", "art. 1 co. 41 — conflitto d'interessi"],
        "tags": ["anticorruzione", "trasparenza", "conflitto", "ptpct", "corruzione"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2012-11-06;190",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+190+2012+anticorruzione",
    },
    {
        "id": "dlgs_267_2000",
        "titolo": "Testo Unico Enti Locali (TUEL)",
        "estremi": "D.Lgs. 18 agosto 2000, n. 267",
        "descrizione": "Disciplina l'organizzazione di Comuni e Province. Regolamenta competenze degli organi, forma degli atti (delibere, determine) e gestione finanziaria. Riferimento primario per ogni atto amministrativo di ente locale.",
        "articoli_chiave": ["art. 107 — competenze dirigenziali", "art. 192 — determinazione a contrarre", "art. 183 — assunzione impegno di spesa"],
        "tags": ["comune", "provincia", "delibera", "ordinanza", "bilancio", "determina", "ente-locale", "dirigente"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2000-08-18;267",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=testo+unico+enti+locali+TUEL+267+2000",
    },
    {
        "id": "dlgs_165_2001",
        "titolo": "Testo Unico Pubblico Impiego (TUPI)",
        "estremi": "D.Lgs. 30 marzo 2001, n. 165",
        "descrizione": "Disciplina il rapporto di lavoro dei dipendenti PA. Regola incarichi, consulenze esterne (art. 7), formazione e organizzazione degli uffici.",
        "articoli_chiave": ["art. 7 — gestione risorse e incarichi", "art. 19 — incarichi dirigenziali", "art. 36 — utilizzo flessibile"],
        "tags": ["personale", "consulenza", "formazione", "incarico", "dipendente", "dirigente", "lavoro"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2001-03-30;165",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=testo+unico+pubblico+impiego+165+2001",
    },
    {
        "id": "dlgs_196_2003",
        "titolo": "Codice Privacy + GDPR",
        "estremi": "D.Lgs. 30 giugno 2003, n. 196 (mod. dal Reg. UE 2016/679)",
        "descrizione": "Disciplina il trattamento dei dati personali. Il GDPR è direttamente applicabile. Rilevante per acquisti di software, cloud e qualsiasi trattamento dati personali da parte della PA.",
        "articoli_chiave": ["art. 13 GDPR — informativa", "art. 28 GDPR — responsabile trattamento", "art. 32 GDPR — sicurezza trattamento"],
        "tags": ["privacy", "dati", "gdpr", "trattamento", "personali", "software", "cloud"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003-06-30;196",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=codice+privacy+196+2003+GDPR",
    },
    {
        "id": "dlgs_81_2008",
        "titolo": "Testo Unico Sicurezza sul Lavoro",
        "estremi": "D.Lgs. 9 aprile 2008, n. 81",
        "descrizione": "Disciplina la sicurezza nei luoghi di lavoro. Negli appalti richiede il DUVRI e la verifica dei requisiti di sicurezza del fornitore.",
        "articoli_chiave": ["art. 26 — obblighi connessi ai contratti d'appalto (DUVRI)", "art. 17 — obblighi non delegabili"],
        "tags": ["sicurezza", "lavori", "contratto", "duvri", "appalto", "cantiere"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2008-04-09;81",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=testo+unico+sicurezza+lavoro+81+2008",
    },
    {
        "id": "dlgs_118_2011",
        "titolo": "Armonizzazione contabile enti locali",
        "estremi": "D.Lgs. 23 giugno 2011, n. 118",
        "descrizione": "Disciplina i sistemi contabili e gli schemi di bilancio di Regioni, Province e Comuni. Regolamenta la corretta imputazione delle spese e gli impegni di bilancio.",
        "articoli_chiave": ["art. 56 — principi contabili applicati", "Allegato 4/2 — principio della competenza finanziaria"],
        "tags": ["bilancio", "fondo", "comune", "provincia", "contabilita", "impegno", "spesa"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2011-06-23;118",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+118+2011+armonizzazione+contabile",
    },
    {
        "id": "pnrr_missione1",
        "titolo": "PNRR — Missione 1: Digitalizzazione PA",
        "estremi": "Piano Nazionale di Ripresa e Resilienza, Missione 1",
        "descrizione": "Definisce gli investimenti per la transizione digitale della PA. Gli acquisti ICT finanziati dal PNRR devono rispettare le linee guida AgID e i requisiti cloud.",
        "articoli_chiave": ["Componente 1.1 — Infrastrutture digitali", "Componente 1.2 — Abilitazione migrazione al cloud"],
        "tags": ["pnrr", "digitalizzazione", "agid", "fondo", "cloud", "ict", "transizione"],
        "url_normattiva": "https://www.normattiva.it/ricerca/semplice?query=PNRR+piano+nazionale+ripresa+resilienza+digitalizzazione",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=PNRR+piano+nazionale+ripresa+resilienza+digitalizzazione",
    },
    {
        "id": "l_136_2010",
        "titolo": "Tracciabilità dei flussi finanziari (CIG/CUP)",
        "estremi": "L. 13 agosto 2010, n. 136",
        "descrizione": "Obbliga le stazioni appaltanti a utilizzare conti dedicati e strumenti tracciabili. Ogni contratto pubblico deve riportare il CIG e, se finanziato con fondi pubblici, il CUP. La mancata indicazione nelle determine costituisce violazione.",
        "articoli_chiave": ["art. 3 — obblighi di tracciabilità dei flussi finanziari", "art. 3 co. 5 — obbligo CIG e CUP", "art. 6 — sanzioni per violazione tracciabilità"],
        "tags": ["cig", "cup", "tracciabilità", "rup", "tracciabilita", "flussi", "contratto"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2010-08-13;136",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+136+2010+tracciabilita+flussi+finanziari+CIG",
    },
    {
        "id": "l_241_1990",
        "titolo": "Legge sul procedimento amministrativo",
        "estremi": "L. 7 agosto 1990, n. 241",
        "descrizione": "Regola il procedimento amministrativo in tutte le sue fasi: avvio, istruttoria, partecipazione dei privati, motivazione degli atti, silenzio-assenso, accesso agli atti. È il riferimento trasversale per la legittimità di qualsiasi provvedimento della PA, incluse determine e delibere.",
        "articoli_chiave": ["art. 1 — principi generali (efficacia, economicità, imparzialità)", "art. 3 — obbligo di motivazione del provvedimento", "art. 7 — comunicazione avvio del procedimento", "art. 21-octies — annullabilità del provvedimento", "art. 22 — accesso agli atti amministrativi"],
        "tags": ["procedimento", "motivazione", "accesso", "provvedimento", "determina", "delibera", "legittimita", "silenzio"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1990-08-07;241",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+241+1990+procedimento+amministrativo",
    },
    {
        "id": "dlgs_50_2016",
        "titolo": "Codice dei contratti pubblici 2016 (previgente)",
        "estremi": "D.Lgs. 18 aprile 2016, n. 50",
        "descrizione": "Codice appalti previgente, abrogato dal D.Lgs. 36/2023 ma ancora applicabile ai contratti aggiudicati prima del 1° luglio 2023 e ai procedimenti in corso. Rilevante per contestare o gestire appalti storici, proroghe e collaudi di contratti avviati sotto la vecchia disciplina.",
        "articoli_chiave": ["art. 36 — contratti sotto soglia (affidamento diretto, procedura negoziata)", "art. 63 — procedura negoziata senza bando", "art. 95 — criteri di aggiudicazione", "art. 106 — modifica dei contratti in corso"],
        "tags": ["proroga", "affidamento", "appalto", "previgente", "storico", "collaudo", "modifica"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2016-04-18;50",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+50+2016+codice+contratti+pubblici",
    },
    {
        "id": "l_296_2006_consip",
        "titolo": "Obbligo Consip / MEPA (L. Finanziaria 2007)",
        "estremi": "L. 27 dicembre 2006, n. 296, art. 1 co. 449-450",
        "descrizione": "Obbliga le amministrazioni statali ad approvvigionarsi tramite convenzioni Consip o a utilizzarne i parametri come prezzi di riferimento (benchmark). Le PA non statali (Comuni, Province, ASL) devono comunque ricorrere al MEPA o giustificare la convenienza economica di procedure autonome. Il mancato rispetto espone il RUP a responsabilità erariale.",
        "articoli_chiave": ["art. 1 co. 449 — obbligo adesione convenzioni Consip per PA statali", "art. 1 co. 450 — obbligo MEPA per acquisti sotto soglia comunitaria", "art. 1 co. 452 — benchmark prezzi Consip per PA non statali"],
        "tags": ["mepa", "consip", "benchmark", "convenzione", "acquisto"],
        "convenzione_only": True,
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2006-12-27;296",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+296+2006+finanziaria+consip+mepa+449",
    },
    {
        "id": "dlgs_231_2001",
        "titolo": "Responsabilità amministrativa degli enti (D.Lgs. 231)",
        "estremi": "D.Lgs. 8 giugno 2001, n. 231",
        "descrizione": "Disciplina la responsabilità amministrativa delle persone giuridiche private per reati commessi nell'interesse o a vantaggio dell'ente. Rilevante negli appalti pubblici: la PA deve verificare che il fornitore privato sia dotato di Modello Organizzativo 231 (MOG) per prevenire reati di corruzione, frode e riciclaggio.",
        "articoli_chiave": ["art. 5 — responsabilità dell'ente per reati dei propri soggetti", "art. 6 — esimenti: adozione ed efficace attuazione del MOG", "art. 24 — reati contro la PA (corruzione, concussione, frode)", "art. 25 — peculato, corruzione e induzione indebita"],
        "tags": ["mog", "231", "corruzione", "fornitore", "appalto", "responsabilita", "anticorruzione"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2001-06-08;231",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+231+2001+responsabilita+amministrativa+enti",
    },
    {
        "id": "circ_agid_cloud_2021",
        "titolo": "Qualificazione cloud PA — Linee guida AgID / ACN",
        "estremi": "Circolare AgID n. 2/2018 + Determinazione AgID 628/2021 + Regolamento ACN 2022",
        "descrizione": "Definisce i requisiti di qualificazione per i servizi cloud acquistabili dalla PA (IaaS, PaaS, SaaS). Solo i servizi presenti nel Catalogo Cloud PA (marketplace.cloud.gov.it) possono essere acquisiti. Classifica i servizi in tre livelli: PSN, Cloud qualificato, SaaS qualificato. Rilevante per ogni acquisto cloud, anche tramite MEPA.",
        "articoli_chiave": ["Determinazione 628/2021 — qualificazione servizi SaaS per PA", "Regolamento ACN 2022 — classificazione dati e servizi cloud", "Circolare AgID 2/2018 — criteri qualificazione CSP e SaaS"],
        "tags": ["qualificazione", "marketplace", "psn", "saas", "agid", "cloud", "acn", "iaas", "paas"],
        "url_normattiva": "https://www.agid.gov.it/it/infrastrutture/cloud-pa",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=AgID+qualificazione+cloud+PA+628+2021",
    },
    {
        "id": "l_328_2000",
        "titolo": "Legge quadro per la realizzazione del sistema integrato di interventi e servizi sociali",
        "estremi": "L. 8 novembre 2000, n. 328",
        "descrizione": "Legge quadro che disciplina il sistema integrato di interventi e servizi sociali. L'art. 6 attribuisce ai Comuni le funzioni di programmazione, progettazione e gestione del sistema locale dei servizi sociali a rete, inclusa l'erogazione dei servizi e delle prestazioni economiche. L'art. 25 stabilisce l'utilizzo dell'ISEE come strumento di determinazione e differenziazione dei criteri di accesso alle prestazioni sociali e socio-sanitarie.",
        "articoli_chiave": ["art. 6 — funzioni dei Comuni", "art. 22 — sistema integrato", "art. 25 — ISEE"],
        "tags": ["servizi-sociali", "sociale", "isee", "retta", "anziani", "disabili", "minori", "assistenza", "contributo", "prestazione", "compartecipazione", "comune", "welfare", "bisogno", "nucleo-familiare", "assistente-sociale"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2000-11-08;328",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+328+2000+servizi+sociali",
    },
    {
        "id": "dpcm_159_2013",
        "titolo": "Regolamento ISEE — Indicatore della Situazione Economica Equivalente",
        "estremi": "D.P.C.M. 5 dicembre 2013, n. 159",
        "descrizione": "Regolamento che disciplina la determinazione dell'ISEE. L'art. 6 disciplina specificamente le prestazioni agevolate di natura socio-sanitaria residenziale (RSA, case di riposo, strutture per disabili), prevedendo l'utilizzo dell'ISEE socio-sanitario.",
        "articoli_chiave": ["art. 2 — ISEE ordinario", "art. 6 — ISEE socio-sanitario", "art. 7 — ISEE minorenni", "art. 4 — nucleo familiare"],
        "tags": ["isee", "isee-sociosanitario", "retta", "rsa", "ricovero", "anziani", "disabili", "servizi-sociali", "sociale", "nucleo-familiare", "assistenza", "prestazione", "socio-sanitario", "struttura-residenziale", "casa-riposo"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.del.presidente.del.consiglio.dei.ministri:2013-12-05;159",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=DPCM+159+2013+ISEE+regolamento",
    },
    {
        "id": "l_104_1992",
        "titolo": "Legge-quadro per l'assistenza, l'integrazione sociale e i diritti delle persone handicappate",
        "estremi": "L. 5 febbraio 1992, n. 104",
        "descrizione": "Legge quadro sull'assistenza e l'integrazione sociale delle persone con disabilità. Attribuisce ai Comuni l'obbligo di garantire i servizi di assistenza, riabilitazione e integrazione.",
        "articoli_chiave": ["art. 3 — definizione handicap grave", "art. 8 — interventi a favore delle persone handicappate", "art. 10 — integrazione scolastica", "art. 33 — agevolazioni lavorative"],
        "tags": ["disabili", "handicap", "disabilita", "assistenza", "integrazione", "servizi-sociali", "sociale", "comune", "retta", "contributo", "permessi", "welfare", "prestazione"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1992-02-05;104",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+104+1992+assistenza+disabili",
    },
]

TAG_INDEX: dict = {}
TAG_INDEX_CONV: dict = {}
for _n in NORMATIVE_DB:
    _is_conv_only = _n.get("convenzione_only", False)
    _target = TAG_INDEX_CONV if _is_conv_only else TAG_INDEX
    for _t in _n["tags"]:
        _target.setdefault(_t, [])
        if _n["id"] not in _target[_t]:
            _target[_t].append(_n["id"])
NORME_BY_ID = {n["id"]: n for n in NORMATIVE_DB}

TIPO_ATTO_TAGS = {
    "determina":  ["cig", "determina"],
    "delibera":   ["delibera", "comune"],
    "ordinanza":  ["ordinanza"],
    "decreto":    [],
    "contratto":  ["contratto", "sicurezza"],
}

SEMANTIC_MAP = {
    "acquisto": ["acquisto", "appalto"], "appalto": ["appalto", "gara", "contratto"],
    "gara": ["gara", "appalto"], "affidamento": ["affidamento", "acquisto", "appalto"],
    "fornitore": ["fornitore", "appalto"], "software": ["software", "digitalizzazione", "saas", "ict"],
    "cloud": ["cloud", "pnrr", "saas", "agid", "qualificazione", "psn"],
    "hardware": ["acquisto", "ict"], "digitale": ["software", "cloud", "pnrr", "agid", "digitalizzazione"],
    "ict": ["software", "cloud", "agid", "ict"], "gestionale": ["software", "dati", "ict"],
    "licenza": ["software", "riuso"], "abbonamento": ["software", "saas"],
    "saas": ["saas", "cloud", "qualificazione"], "iaas": ["iaas", "cloud", "qualificazione"],
    "paas": ["paas", "cloud", "qualificazione"], "open-source": ["open-source", "riuso", "software"],
    "riuso": ["riuso", "software"], "agid": ["agid", "digitalizzazione", "qualificazione"],
    "acn": ["acn", "qualificazione", "cloud"], "psn": ["psn", "agid", "pnrr", "cloud"],
    "qualificazione": ["qualificazione", "saas", "agid", "cloud"], "marketplace": ["marketplace", "agid", "saas"],
    "pnrr": ["pnrr", "cup", "digitalizzazione", "cloud"], "transizione": ["digitalizzazione", "pnrr", "agid"],
    "servizi": ["appalto", "sicurezza", "servizi"], "manutenzione": ["appalto", "sicurezza", "lavori"],
    "lavori": ["lavori", "sicurezza", "appalto", "cantiere"], "sicurezza": ["sicurezza", "duvri", "cantiere"],
    "duvri": ["duvri", "sicurezza", "appalto"], "consulenza": ["consulenza", "personale", "incarico"],
    "formazione": ["formazione", "personale"], "incarico": ["consulenza", "personale", "incarico", "dirigente"],
    "personale": ["personale", "dipendente", "lavoro"], "dirigente": ["dirigente", "personale", "ente-locale"],
    "dipendente": ["dipendente", "personale", "lavoro"], "comune": ["comune", "ente-locale", "delibera"],
    "regione": ["comune", "ente-locale"], "provincia": ["comune", "bilancio", "ente-locale"],
    "delibera": ["delibera", "comune", "ente-locale", "provvedimento"], "determina": ["determina", "cig", "provvedimento"],
    "bilancio": ["bilancio", "fondo", "contabilita", "impegno"], "spesa": ["spesa", "bilancio", "impegno"],
    "impegno": ["impegno", "bilancio", "contabilita"], "contabilita": ["contabilita", "bilancio", "fondo"],
    "cig": ["cig", "tracciabilita", "rup"], "cup": ["cup", "pnrr", "tracciabilita"],
    "tracciabilita": ["tracciabilita", "cig", "cup", "flussi"], "rup": ["rup", "cig", "appalto"],
    "stazione": ["appalto", "cig", "rup"], "privacy": ["privacy", "dati", "gdpr", "trattamento"],
    "dati": ["dati", "privacy", "trattamento"], "gdpr": ["privacy", "dati", "gdpr", "trattamento"],
    "trattamento": ["trattamento", "privacy", "dati", "gdpr"], "personali": ["personali", "privacy", "gdpr"],
    "trasparenza": ["trasparenza", "anticorruzione", "pubblicazione", "foia"],
    "anticorruzione": ["anticorruzione", "trasparenza", "ptpct", "corruzione"],
    "corruzione": ["corruzione", "anticorruzione", "mog", "231"], "ptpct": ["ptpct", "anticorruzione"],
    "foia": ["foia", "trasparenza", "accesso"], "pubblicazione": ["pubblicazione", "trasparenza", "accesso"],
    "accesso": ["accesso", "trasparenza", "foia", "provvedimento"], "procedimento": ["procedimento", "motivazione", "provvedimento", "legittimita"],
    "motivazione": ["motivazione", "procedimento", "provvedimento"], "provvedimento": ["provvedimento", "motivazione", "procedimento", "legittimita"],
    "legittimita": ["legittimita", "procedimento", "motivazione"], "silenzio": ["silenzio", "procedimento"],
    "mog": ["mog", "231", "anticorruzione"], "231": ["mog", "231", "responsabilita"],
    "responsabilita": ["responsabilita", "mog", "231", "anticorruzione"], "mepa": ["mepa", "consip", "benchmark", "convenzione"],
    "consip": ["mepa", "consip", "benchmark", "convenzione"], "convenzione": ["convenzione", "mepa", "consip", "benchmark"],
    "benchmark": ["benchmark", "mepa", "consip"], "proroga": ["proroga", "affidamento", "previgente", "modifica"],
    "storico": ["storico", "previgente", "proroga"], "collaudo": ["collaudo", "appalto", "contratto"],
    "modifica": ["modifica", "proroga", "contratto"], "sociale": ["servizi-sociali", "sociale", "assistenza", "isee", "welfare"],
    "sociali": ["servizi-sociali", "sociale", "assistenza", "isee", "welfare"],
    "isee": ["isee", "isee-sociosanitario", "servizi-sociali", "retta", "compartecipazione"],
    "sociosanitario": ["isee-sociosanitario", "retta", "rsa", "ricovero", "socio-sanitario"],
    "socio-sanitario": ["isee-sociosanitario", "retta", "rsa", "ricovero", "socio-sanitario"],
    "retta": ["retta", "isee", "isee-sociosanitario", "rsa", "ricovero", "compartecipazione", "servizi-sociali"],
    "rsa": ["rsa", "retta", "isee-sociosanitario", "ricovero", "anziani", "struttura-residenziale"],
    "ricovero": ["ricovero", "rsa", "retta", "isee-sociosanitario", "residenziale", "struttura-residenziale"],
    "residenziale": ["residenziale", "rsa", "retta", "isee-sociosanitario", "struttura-residenziale"],
    "anziani": ["anziani", "rsa", "retta", "isee-sociosanitario", "servizi-sociali", "casa-riposo"],
    "anziano": ["anziani", "rsa", "retta", "isee-sociosanitario", "servizi-sociali"],
    "anziana": ["anziani", "rsa", "retta", "isee-sociosanitario", "servizi-sociali"],
    "disabili": ["disabili", "handicap", "disabilita", "assistenza", "servizi-sociali", "retta"],
    "disabile": ["disabili", "handicap", "disabilita", "assistenza", "servizi-sociali"],
    "disabilita": ["disabili", "handicap", "disabilita", "assistenza", "servizi-sociali"],
    "handicap": ["handicap", "disabili", "disabilita", "assistenza", "permessi"],
    "minori": ["minori", "servizi-sociali", "assistenza", "isee", "welfare"],
    "assistenza": ["assistenza", "servizi-sociali", "sociale", "isee", "welfare"],
    "compartecipazione": ["compartecipazione", "retta", "isee", "isee-sociosanitario", "servizi-sociali"],
    "integrazione": ["integrazione", "disabili", "servizi-sociali", "assistenza"],
    "welfare": ["welfare", "servizi-sociali", "sociale", "isee", "assistenza"],
    "nucleo": ["nucleo-familiare", "isee", "isee-sociosanitario", "servizi-sociali"],
    "familiare": ["nucleo-familiare", "isee", "servizi-sociali"],
    "assistente": ["assistente-sociale", "servizi-sociali", "sociale"],
}

STOP_WORDS = {"il","lo","la","i","gli","le","un","uno","una","di","del","della","degli","dei","delle","a","al","alla","ai","agli","alle","da","dal","dalla","dai","dagli","dalle","in","nel","nella","nei","negli","nelle","con","su","per","tra","fra","che","chi","cui","non","ma","se","ho","ha","hanno","devo","deve","voglio","fare","sono","e","o","come","quando","dove","questo","questa","questi","queste","also","such"}
_ALL_VALID_TAGS = sorted(set(tag for norma in NORMATIVE_DB for tag in norma["tags"]))


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
        return ["mepa", "consip", "cig", "convenzione"]
    if val <= SEMI_THRESHOLD:
        return ["acquisto"]
    elif val <= DIRECT_THRESHOLD:
        return ["acquisto", "appalto", "cig"]
    elif val <= NEGO_THRESHOLD:
        return ["appalto", "gara", "cig"]
    return ["appalto", "gara", "lavori", "cig"]


def _importo_label(importo_str: str, convenzione: bool = False) -> str:
    val = _parse_importo(importo_str)
    if val is None:
        return ""
    if convenzione:
        return f"€{val:,.0f} — Adesione a convenzione Consip / Ordine su MEPA"
    if val <= SEMI_THRESHOLD:
        return f"€{val:,.0f} — Affidamento diretto semplificato (art. 50 co. 1, D.Lgs. 36/2023)"
    elif val <= DIRECT_THRESHOLD:
        return f"€{val:,.0f} — Affidamento diretto (art. 50, D.Lgs. 36/2023)"
    elif val <= NEGO_THRESHOLD:
        return f"€{val:,.0f} — Procedura negoziata (art. 72, D.Lgs. 36/2023)"
    return f"€{val:,.0f} — Procedura aperta (art. 71, D.Lgs. 36/2023)"


def _fetch_norma_text(url: str, timeout: int = FETCH_TIMEOUT_PER_NORMA) -> str:
    if not url:
        return ""
    now = time.time()
    cached = _NORM_TEXT_CACHE.get(url)
    if cached and (now - cached["fetched_at"] < _CACHE_TTL):
        return cached["text"]
    headers = {
        "User-Agent": "NormAttivaBot/1.0 (+https://github.com/enricobrunazzo/normattiva)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            encoding = resp.headers.get_content_charset() or "utf-8"
            html_text = raw.decode(encoding, errors="replace")
        cleaned = re.sub(r"<(script|style)[^>]*>.*?</\\1>", "", html_text, flags=re.S | re.I)
        cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.S)
        block = None
        for pattern in [
            r'<(?:div|article|section)[^>]+(?:id|class)=["\\']?[^"\\']*(?:atto|norma|testo|corpo|content)[^"\\']*["\\']?[^>]*>(.*?)</(?:div|article|section)>',
            r'<(?:div|article)[^>]+id=["\\']?main["\\']?[^>]*>(.*?)</(?:div|article)>',
        ]:
            m = re.search(pattern, cleaned, flags=re.S | re.I)
            if m:
                block = m.group(1)
                break
        if not block:
            m2 = re.search(r"<body[^>]*>([\\s\\S]*?)</body>", cleaned, flags=re.I)
            block = m2.group(1) if m2 else cleaned
        text = re.sub(r"<[^>]+>", " ", block)
        text = unescape(text)
        text = re.sub(r"\\s+", " ", text).strip()[:8000]
        _NORM_TEXT_CACHE[url] = {"text": text, "fetched_at": now}
        return text
    except Exception:
        return ""


def _fetch_norme_parallel(candidates: list, k: int = K_FETCH_LIVE, budget: float = FETCH_BUDGET_TOTAL) -> None:
    top = candidates[:k]
    for n in candidates:
        n.setdefault("text_vigente", "")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=k) as executor:
        future_to_norma = {executor.submit(_fetch_norma_text, n.get("url_normattiva", "")): n for n in top}
        for future in as_completed(future_to_norma, timeout=budget):
            norma = future_to_norma[future]
            try:
                if not norma.get("text_vigente"):
                    norma["text_vigente"] = future.result()
            except Exception:
                pass
    print(f"[NORMATTV_PARALLEL] done | hits={sum(1 for n in top if n.get('text_vigente','').strip())} | elapsed={time.time()-t0:.2f}s", flush=True)


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\\s*([\\s\\S]*?)```", raw)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    m = re.search(r"(\\{[\\s\\S]*\\})", raw)
    if m:
        return json.loads(m.group(1))
    raise ValueError(f"Nessun JSON valido trovato. Raw: {raw[:300]!r}")


def _groq_expand_query(testo: str, oggetto: str, tipo_atto: str) -> list[str]:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return []
    tag_list_str = ", ".join(_ALL_VALID_TAGS)
    full_query = f"{testo} {oggetto}".strip()
    prompt = (
        "Sei un esperto di diritto amministrativo italiano e di contratti pubblici.\\n"
        "Restituisci SOLO i tag più rilevanti tra quelli forniti.\\n\\n"
        f"Richiesta:\\n- Tipo atto: {tipo_atto or 'non specificato'}\\n- Testo: {full_query}\\n\\n"
        f"Tag disponibili:\\n{tag_list_str}\\n\\n"
        "Restituisci JSON: {\\"tags\\": [\\"tag1\\", \\\"tag2\\\"]}"
    )
    try:
        payload = json.dumps({"model": MODEL_EXPAND, "messages": [{"role": "user", "content": prompt}], "temperature": 0.0, "max_tokens": 256}).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
        data = _extract_json(body["choices"][0]["message"]["content"])
        return [t for t in data.get("tags", []) if t in set(_ALL_VALID_TAGS)]
    except Exception:
        return []


def _tag_search(testo: str, tipo_atto: str, oggetto: str, importo: str, convenzione: bool = False, expanded_tags: list | None = None) -> list:
    matched: dict = {}
    def _add(nid: str, score: int = 1) -> None:
        norma = NORME_BY_ID.get(nid)
        if norma is None:
            return
        if norma.get("convenzione_only", False) and not convenzione:
            return
        matched[nid] = matched.get(nid, 0) + score
    def _lookup(tag: str, score: int) -> None:
        for nid in TAG_INDEX.get(tag, []):
            _add(nid, score)
        if convenzione:
            for nid in TAG_INDEX_CONV.get(tag, []):
                _add(nid, score)
    if tipo_atto and tipo_atto.lower() in TIPO_ATTO_TAGS:
        for tag in TIPO_ATTO_TAGS[tipo_atto.lower()]:
            _lookup(tag, 2)
    for tag in _importo_tags(importo, convenzione):
        _lookup(tag, 3)
    for tag in (expanded_tags or []):
        _lookup(tag, 3)
    full_text = f"{testo} {oggetto}".lower()
    tokens = re.split(r"[\\s,./;:()\\[\\]\\\"']+", full_text)
    for token in tokens:
        token = token.strip()
        if not token or token in STOP_WORDS or len(token) < 3:
            continue
        _lookup(token, 2)
        for sem_tag in SEMANTIC_MAP.get(token, []):
            _lookup(sem_tag, 1)
    if convenzione:
        for boost_id in ("l_136_2010", "dlgs_33_2013", "dlgs_267_2000", "l_296_2006_consip"):
            if boost_id in NORME_BY_ID:
                _add(boost_id, 4)
    sorted_ids = sorted(matched.items(), key=lambda x: x[1], reverse=True)
    results = []
    for nid, score in sorted_ids:
        if score < MIN_SCORE_FOR_GROQ:
            continue
        norma = NORME_BY_ID[nid].copy()
        norma["score"] = score
        norma["ai_motivation"] = ""
        results.append(norma)
    return results


def _groq_rank(testo: str, tipo_atto: str, oggetto: str, importo: str, candidates: list, convenzione: bool = False) -> list:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return candidates
    groq_candidates = candidates[:GROQ_MAX_CANDIDATES]
    remaining = candidates[GROQ_MAX_CANDIDATES:]
    try:
        norme_lines = []
        for n in groq_candidates:
            line = f"- ID: {n['id']} | {n['estremi']} — {n['titolo']}"
            testo_vigente = n.get("text_vigente", "").strip()
            if testo_vigente:
                line += f"\\n  [Testo vigente]: {testo_vigente[:600].replace('\\n', ' ')}..."
            norme_lines.append(line)
        prompt = (
            "Sei un esperto di diritto amministrativo italiano.\\n"
            f"- Tipo atto: {tipo_atto or 'non specificato'}\\n"
            f"- Oggetto: {oggetto or 'non specificato'}\\n"
            f"- Importo: {importo or 'non specificato'}\\n"
            f"- Convenzione: {'sì' if convenzione else 'no'}\\n"
            f"- Descrizione esigenza: {testo}\\n\\n"
            "Norme candidate:\\n" + "\\n".join(norme_lines) + "\\n\\n"
            "Restituisci JSON: {\\"ranked\\": [{\\"id\\": \\\"<id_norma>\\\", \\\"motivation\\\": \\\"<1-2 frasi specifiche>\\\"}]}"
        )
        payload = json.dumps({"model": MODEL_RANK, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 1024}).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode())
        ranked_data = _extract_json(body["choices"][0]["message"]["content"])
        ranked_list = ranked_data.get("ranked", [])
        ranked_map = {item["id"]: item.get("motivation", "") for item in ranked_list}
        reranked = []
        for item in ranked_list:
            nid = item["id"]
            if nid in NORME_BY_ID:
                norma = next((c for c in groq_candidates if c["id"] == nid), NORME_BY_ID[nid].copy())
                norma = norma.copy()
                norma["score"] = 100 - len(reranked)
                norma["ai_motivation"] = ranked_map.get(nid, "")
                norma["text_vigente_disponibile"] = bool(norma.get("text_vigente", "").strip())
                reranked.append(norma)
        seen = {n["id"] for n in reranked}
        for n in groq_candidates:
            if n["id"] not in seen:
                n_copy = n.copy()
                n_copy["text_vigente_disponibile"] = bool(n.get("text_vigente", "").strip())
                reranked.append(n_copy)
        return reranked + remaining
    except Exception as exc:
        print(f"[GROQ ERROR] {type(exc).__name__}: {exc}", flush=True)
        return candidates


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        testo = params.get("q", [""])[0].strip()
        tipo_atto = params.get("tipo_atto", [""])[0].strip().lower()
        oggetto = params.get("oggetto", [""])[0].strip()
        importo = params.get("importo", [""])[0].strip()
        convenzione = params.get("convenzione", ["false"])[0].strip().lower() in ("true", "1", "yes")
        t_start = time.time()
        print(f"[REQUEST] q={testo!r} | tipo={tipo_atto!r} | oggetto={oggetto!r} | importo={importo!r} | convenzione={convenzione}", flush=True)

        expanded_tags = _groq_expand_query(testo, oggetto, tipo_atto)
        full_query = f"{testo} {oggetto}".strip()

        candidates = supabase_vector_search(full_query, convenzione=convenzione)
        source = "supabase"
        if not candidates:
            candidates = _tag_search(testo, tipo_atto, oggetto, importo, convenzione, expanded_tags)
            source = "tag_fallback"
        print(f"[SEARCH] source={source} | candidates={len(candidates)}", flush=True)

        _fetch_norme_parallel(candidates)
        results = _groq_rank(testo, tipo_atto, oggetto, importo, candidates, convenzione)
        elapsed_ms = round((time.time() - t_start) * 1000)

        output = {
            "query": testo,
            "tipo_atto": tipo_atto,
            "oggetto": oggetto,
            "importo_label": _importo_label(importo, convenzione),
            "convenzione": convenzione,
            "search_source": source,
            "results": results,
            "elapsed_ms": elapsed_ms,
        }

        log_query_to_supabase(
            query_text=testo,
            tipo_atto=tipo_atto,
            oggetto=oggetto,
            importo=importo,
            convenzione=convenzione,
            results_count=len(results),
            elapsed_ms=elapsed_ms,
            groq_used=bool(os.environ.get("GROQ_API_KEY", "")),
        )

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
