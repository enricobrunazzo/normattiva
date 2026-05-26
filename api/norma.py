"""Endpoint GET /api/norma?id=<norma_id> — scheda dettaglio norma con articoli_dettaglio."""
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse

# ── Database normativo locale (mirror di search.py — nessun import cross-function) ──
NORMATIVE_DB = [
    {
        "id": "dlgs_36_2023",
        "titolo": "Codice dei contratti pubblici",
        "estremi": "D.Lgs. 31 marzo 2023, n. 36",
        "descrizione": "Disciplina l'affidamento e l'esecuzione di appalti pubblici e concessioni. Regolamenta le soglie per affidamento diretto (art. 50), procedura negoziata (art. 72) e procedura aperta (art. 71). Obbliga alla nomina del RUP e all'acquisizione del CIG.",
        "articoli_chiave": ["art. 50 — affidamento diretto", "art. 51 — procedura negoziata semplificata", "art. 71 — procedura aperta", "art. 72 — procedura negoziata", "art. 15 — RUP"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2023-03-31;36",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+36+2023+codice+contratti+pubblici",
    },
    {
        "id": "dlgs_82_2005",
        "titolo": "Codice dell'Amministrazione Digitale (CAD)",
        "estremi": "D.Lgs. 7 marzo 2005, n. 82",
        "descrizione": "Regola la digitalizzazione della PA, l'uso di software, cloud computing e servizi ICT. Stabilisce l'obbligo di preferenza per soluzioni open source (art. 68) e il riuso del software (art. 69).",
        "articoli_chiave": ["art. 68 — analisi comparativa soluzioni", "art. 69 — riuso del software", "art. 50 — disponibilità dei dati"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2005-03-07;82",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=codice+amministrazione+digitale+CAD+82+2005",
    },
    {
        "id": "dlgs_33_2013",
        "titolo": "Trasparenza e accesso civico",
        "estremi": "D.Lgs. 14 marzo 2013, n. 33",
        "descrizione": "Obbliga le PA alla pubblicazione su 'Amministrazione Trasparente' di dati su contratti, affidamenti e spese. Ogni determina di acquisto rilevante deve essere pubblicata. Disciplina anche il FOIA (art. 5).",
        "articoli_chiave": ["art. 23 — obblighi pubblicazione provvedimenti", "art. 37 — pubblicazione contratti e appalti", "art. 5 — accesso civico"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2013-03-14;33",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+33+2013+trasparenza+amministrativa",
    },
    {
        "id": "l_190_2012",
        "titolo": "Legge Anticorruzione",
        "estremi": "L. 6 novembre 2012, n. 190",
        "descrizione": "Introduce misure per la prevenzione della corruzione nella PA. Obbliga gli enti al PTPCT. L'art. 1 co. 41 richiede l'attestazione di assenza di conflitto d'interessi in ogni provvedimento.",
        "articoli_chiave": ["art. 1 — PTPCT", "art. 1 co. 9 — misure obbligatorie", "art. 1 co. 41 — conflitto d'interessi"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2012-11-06;190",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+190+2012+anticorruzione",
    },
    {
        "id": "dlgs_267_2000",
        "titolo": "Testo Unico Enti Locali (TUEL)",
        "estremi": "D.Lgs. 18 agosto 2000, n. 267",
        "descrizione": "Disciplina l'organizzazione di Comuni e Province. Regolamenta competenze degli organi, forma degli atti (delibere, determine) e gestione finanziaria. Riferimento primario per ogni atto amministrativo di ente locale.",
        "articoli_chiave": ["art. 107 — competenze dirigenziali", "art. 192 — determinazione a contrarre", "art. 183 — assunzione impegno di spesa"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2000-08-18;267",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=testo+unico+enti+locali+TUEL+267+2000",
    },
    {
        "id": "dlgs_165_2001",
        "titolo": "Testo Unico Pubblico Impiego (TUPI)",
        "estremi": "D.Lgs. 30 marzo 2001, n. 165",
        "descrizione": "Disciplina il rapporto di lavoro dei dipendenti PA. Regola incarichi, consulenze esterne (art. 7), formazione e organizzazione degli uffici.",
        "articoli_chiave": ["art. 7 — gestione risorse e incarichi", "art. 19 — incarichi dirigenziali", "art. 36 — utilizzo flessibile"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2001-03-30;165",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=testo+unico+pubblico+impiego+165+2001",
    },
    {
        "id": "dlgs_196_2003",
        "titolo": "Codice Privacy + GDPR",
        "estremi": "D.Lgs. 30 giugno 2003, n. 196 (mod. dal Reg. UE 2016/679)",
        "descrizione": "Disciplina il trattamento dei dati personali. Il GDPR è direttamente applicabile. Rilevante per acquisti di software, cloud e qualsiasi trattamento dati personali da parte della PA.",
        "articoli_chiave": ["art. 13 GDPR — informativa", "art. 28 GDPR — responsabile trattamento", "art. 32 GDPR — sicurezza trattamento"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003-06-30;196",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=codice+privacy+196+2003+GDPR",
    },
    {
        "id": "dlgs_81_2008",
        "titolo": "Testo Unico Sicurezza sul Lavoro",
        "estremi": "D.Lgs. 9 aprile 2008, n. 81",
        "descrizione": "Disciplina la sicurezza nei luoghi di lavoro. Negli appalti richiede il DUVRI e la verifica dei requisiti di sicurezza del fornitore.",
        "articoli_chiave": ["art. 26 — obblighi connessi ai contratti d'appalto (DUVRI)", "art. 17 — obblighi non delegabili"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2008-04-09;81",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=testo+unico+sicurezza+lavoro+81+2008",
    },
    {
        "id": "dlgs_118_2011",
        "titolo": "Armonizzazione contabile enti locali",
        "estremi": "D.Lgs. 23 giugno 2011, n. 118",
        "descrizione": "Disciplina i sistemi contabili e gli schemi di bilancio di Regioni, Province e Comuni. Regolamenta la corretta imputazione delle spese e gli impegni di bilancio.",
        "articoli_chiave": ["art. 56 — principi contabili applicati", "Allegato 4/2 — principio della competenza finanziaria"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2011-06-23;118",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+118+2011+armonizzazione+contabile",
    },
    {
        "id": "pnrr_missione1",
        "titolo": "PNRR — Missione 1: Digitalizzazione PA",
        "estremi": "Piano Nazionale di Ripresa e Resilienza, Missione 1",
        "descrizione": "Definisce gli investimenti per la transizione digitale della PA. Gli acquisti ICT finanziati dal PNRR devono rispettare le linee guida AgID e i requisiti cloud.",
        "articoli_chiave": ["Componente 1.1 — Infrastrutture digitali", "Componente 1.2 — Abilitazione migrazione al cloud"],
        "url_normattiva": "https://www.normattiva.it/ricerca/semplice?query=PNRR+piano+nazionale+ripresa+resilienza+digitalizzazione",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=PNRR+piano+nazionale+ripresa+resilienza+digitalizzazione",
    },
    {
        "id": "l_136_2010",
        "titolo": "Tracciabilità dei flussi finanziari (CIG/CUP)",
        "estremi": "L. 13 agosto 2010, n. 136",
        "descrizione": "Obbliga le stazioni appaltanti a utilizzare conti dedicati e strumenti tracciabili. Ogni contratto pubblico deve riportare il CIG e, se finanziato con fondi pubblici, il CUP. La mancata indicazione nelle determine costituisce violazione.",
        "articoli_chiave": ["art. 3 — obblighi di tracciabilità dei flussi finanziari", "art. 3 co. 5 — obbligo CIG e CUP", "art. 6 — sanzioni per violazione tracciabilità"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2010-08-13;136",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+136+2010+tracciabilita+flussi+finanziari+CIG",
    },
    {
        "id": "l_241_1990",
        "titolo": "Legge sul procedimento amministrativo",
        "estremi": "L. 7 agosto 1990, n. 241",
        "descrizione": "Regola il procedimento amministrativo in tutte le sue fasi: avvio, istruttoria, partecipazione dei privati, motivazione degli atti, silenzio-assenso, accesso agli atti. È il riferimento trasversale per la legittimità di qualsiasi provvedimento della PA, incluse determine e delibere.",
        "articoli_chiave": ["art. 1 — principi generali (efficacia, economicità, imparzialità)", "art. 3 — obbligo di motivazione del provvedimento", "art. 7 — comunicazione avvio del procedimento", "art. 21-octies — annullabilità del provvedimento", "art. 22 — accesso agli atti amministrativi"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1990-08-07;241",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+241+1990+procedimento+amministrativo",
    },
    {
        "id": "dlgs_50_2016",
        "titolo": "Codice dei contratti pubblici 2016 (previgente)",
        "estremi": "D.Lgs. 18 aprile 2016, n. 50",
        "descrizione": "Codice appalti previgente, abrogato dal D.Lgs. 36/2023 ma ancora applicabile ai contratti aggiudicati prima del 1° luglio 2023 e ai procedimenti in corso. Rilevante per contestare o gestire appalti storici, proroghe e collaudi di contratti avviati sotto la vecchia disciplina.",
        "articoli_chiave": ["art. 36 — contratti sotto soglia (affidamento diretto, procedura negoziata)", "art. 63 — procedura negoziata senza bando", "art. 95 — criteri di aggiudicazione", "art. 106 — modifica dei contratti in corso"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2016-04-18;50",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+50+2016+codice+contratti+pubblici",
    },
    {
        "id": "l_296_2006_consip",
        "titolo": "Obbligo Consip / MEPA (L. Finanziaria 2007)",
        "estremi": "L. 27 dicembre 2006, n. 296, art. 1 co. 449-450",
        "descrizione": "Obbliga le amministrazioni statali ad approvvigionarsi tramite convenzioni Consip o a utilizzarne i parametri come prezzi di riferimento (benchmark). Le PA non statali (Comuni, Province, ASL) devono comunque ricorrere al MEPA o giustificare la convenienza economica di procedure autonome. Il mancato rispetto espone il RUP a responsabilità erariale.",
        "articoli_chiave": ["art. 1 co. 449 — obbligo adesione convenzioni Consip per PA statali", "art. 1 co. 450 — obbligo MEPA per acquisti sotto soglia comunitaria", "art. 1 co. 452 — benchmark prezzi Consip per PA non statali"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2006-12-27;296",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+296+2006+finanziaria+consip+mepa+449",
    },
    {
        "id": "dlgs_231_2001",
        "titolo": "Responsabilità amministrativa degli enti (D.Lgs. 231)",
        "estremi": "D.Lgs. 8 giugno 2001, n. 231",
        "descrizione": "Disciplina la responsabilità amministrativa delle persone giuridiche private per reati commessi nell'interesse o a vantaggio dell'ente. Rilevante negli appalti pubblici: la PA deve verificare che il fornitore privato sia dotato di Modello Organizzativo 231 (MOG) per prevenire reati di corruzione, frode e riciclaggio.",
        "articoli_chiave": ["art. 5 — responsabilità dell'ente per reati dei propri soggetti", "art. 6 — esimenti: adozione ed efficace attuazione del MOG", "art. 24 — reati contro la PA (corruzione, concussione, frode)", "art. 25 — peculato, corruzione e induzione indebita"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2001-06-08;231",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+231+2001+responsabilita+amministrativa+enti",
    },
    {
        "id": "circ_agid_cloud_2021",
        "titolo": "Qualificazione cloud PA — Linee guida AgID / ACN",
        "estremi": "Circolare AgID n. 2/2018 + Determinazione AgID 628/2021 + Regolamento ACN 2022",
        "descrizione": "Definisce i requisiti di qualificazione per i servizi cloud acquistabili dalla PA (IaaS, PaaS, SaaS). Solo i servizi presenti nel Catalogo Cloud PA (marketplace.cloud.gov.it) possono essere acquisiti. Classifica i servizi in tre livelli: PSN, Cloud qualificato, SaaS qualificato. Rilevante per ogni acquisto cloud, anche tramite MEPA.",
        "articoli_chiave": ["Determinazione 628/2021 — qualificazione servizi SaaS per PA", "Regolamento ACN 2022 — classificazione dati e servizi cloud", "Circolare AgID 2/2018 — criteri qualificazione CSP e SaaS"],
        "url_normattiva": "https://www.agid.gov.it/it/infrastrutture/cloud-pa",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=AgID+qualificazione+cloud+PA+628+2021",
    },
    {
        "id": "l_328_2000",
        "titolo": "Legge quadro per la realizzazione del sistema integrato di interventi e servizi sociali",
        "estremi": "L. 8 novembre 2000, n. 328",
        "descrizione": "Legge quadro che disciplina il sistema integrato di interventi e servizi sociali. L'art. 6 attribuisce ai Comuni le funzioni di programmazione, progettazione e gestione del sistema locale dei servizi sociali a rete, inclusa l'erogazione dei servizi e delle prestazioni economiche. L'art. 25 stabilisce l'utilizzo dell'ISEE come strumento di determinazione e differenziazione dei criteri di accesso alle prestazioni sociali e socio-sanitarie.",
        "articoli_chiave": ["art. 6 — funzioni dei Comuni", "art. 22 — sistema integrato", "art. 25 — ISEE"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2000-11-08;328",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+328+2000+servizi+sociali",
    },
    {
        "id": "dpcm_159_2013",
        "titolo": "Regolamento ISEE — Indicatore della Situazione Economica Equivalente",
        "estremi": "D.P.C.M. 5 dicembre 2013, n. 159",
        "descrizione": "Regolamento che disciplina la determinazione dell'ISEE. L'art. 6 disciplina specificamente le prestazioni agevolate di natura socio-sanitaria residenziale (RSA, case di riposo, strutture per disabili), prevedendo l'utilizzo dell'ISEE socio-sanitario.",
        "articoli_chiave": ["art. 2 — ISEE ordinario", "art. 6 — ISEE socio-sanitario", "art. 7 — ISEE minorenni", "art. 4 — nucleo familiare"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.del.presidente.del.consiglio.dei.ministri:2013-12-05;159",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=DPCM+159+2013+ISEE+regolamento",
    },
    {
        "id": "l_104_1992",
        "titolo": "Legge-quadro per l'assistenza, l'integrazione sociale e i diritti delle persone handicappate",
        "estremi": "L. 5 febbraio 1992, n. 104",
        "descrizione": "Legge quadro sull'assistenza e l'integrazione sociale delle persone con disabilità. Attribuisce ai Comuni l'obbligo di garantire i servizi di assistenza, riabilitazione e integrazione.",
        "articoli_chiave": ["art. 3 — definizione handicap grave", "art. 8 — interventi a favore delle persone handicappate", "art. 10 — integrazione scolastica", "art. 33 — agevolazioni lavorative"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1992-02-05;104",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+104+1992+assistenza+disabili",
    },
]

NORME_BY_ID = {n["id"]: n for n in NORMATIVE_DB}

# ── Testi sintetici degli articoli chiave per ciascuna norma ────────────────────
ARTICOLI_TESTO = {
    "dlgs_36_2023": {
        "art. 50 — affidamento diretto": (
            "Le stazioni appaltanti procedono all'affidamento diretto di servizi e forniture di importo "
            "inferiore a 140.000 euro anche senza consultazione di più operatori, assicurando che il "
            "soggetto scelto abbia documentate esperienze pregresse. Per importi inferiori a 5.000 euro "
            "('affidamento diretto semplificato') è consentita la trattativa con un unico operatore. "
            "Obbligo di nomina del RUP e acquisizione del CIG in ogni caso."
        ),
        "art. 51 — procedura negoziata semplificata": (
            "Per servizi e forniture di importo pari o superiore a 140.000 euro e fino alle soglie "
            "comunitarie, la stazione appaltante consulta almeno cinque operatori economici nel rispetto "
            "del criterio di rotazione degli inviti. La selezione avviene tramite indagine di mercato "
            "o albo fornitori; è richiesta motivazione della scelta degli operatori invitati."
        ),
        "art. 71 — procedura aperta": (
            "Nelle procedure aperte qualsiasi operatore può presentare offerta. Il termine minimo per "
            "la ricezione delle offerte è 35 giorni dalla trasmissione del bando, riducibile a 15 giorni "
            "in caso di urgenza o previo avviso di pre-informazione. Obbligatoria per importi superiori "
            "alle soglie comunitarie (attualmente: forniture/servizi ≥ 221.000 euro per enti locali)."
        ),
        "art. 72 — procedura negoziata": (
            "Applicabile a servizi e forniture tra 215.000 euro e la soglia comunitaria. Richiede "
            "pubblicazione di un avviso e consultazione di almeno cinque operatori. La stazione appaltante "
            "può ricorrere alla procedura negoziata senza previa pubblicazione solo nei casi tassativamente "
            "previsti (estrema urgenza, unicita' del fornitore, appalti di ricerca)."
        ),
        "art. 15 — RUP": (
            "Per ogni contratto pubblico la stazione appaltante nomina un Responsabile Unico del "
            "Procedimento (RUP) con adeguate competenze. Il RUP sovrintende a tutte le fasi: "
            "programmazione, progettazione, affidamento ed esecuzione. L'atto di nomina deve essere "
            "inserito nella determina a contrarre o nell'atto equivalente."
        ),
    },
    "dlgs_82_2005": {
        "art. 68 — analisi comparativa soluzioni": (
            "Prima di acquisire software, le PA effettuano una valutazione comparativa delle soluzioni "
            "disponibili, dando preferenza — a parità di costo — a soluzioni aperte e riusabili. "
            "La valutazione deve essere documentata negli atti della procedura di acquisto. "
            "AgID pubblica linee guida specifiche su developers.italia.it."
        ),
        "art. 69 — riuso del software": (
            "Le PA titolari di software sviluppato su loro indicazione sono obbligate a pubblicare il "
            "codice sorgente su un repository pubblico (es. GitHub) sotto licenza aperta, mettendolo "
            "a disposizione gratuita di altre PA. Il catalogo del software riusabile è su "
            "developers.italia.it/it/software."
        ),
        "art. 50 — disponibilità dei dati": (
            "I dati delle PA sono formati, raccolti e resi disponibili con tecnologie ICT in formato "
            "aperto e interoperabile. Le PA devono garantire la disponibilità, l'accessibilità e la "
            "fruibilità dei propri dati, abilitando il riuso e l'interoperabilità tra sistemi pubblici."
        ),
    },
    "dlgs_33_2013": {
        "art. 23 — obblighi pubblicazione provvedimenti": (
            "Le PA pubblicano su Amministrazione Trasparente, con cadenza semestrale, l'elenco dei "
            "provvedimenti adottati dagli organi politici e dai dirigenti, indicando oggetto, contenuto, "
            "eventuale spesa e riferimenti agli atti del fascicolo. La mancata pubblicazione è sanzionabile."
        ),
        "art. 37 — pubblicazione contratti e appalti": (
            "Le stazioni appaltanti pubblicano su Amministrazione Trasparente: struttura proponente, "
            "oggetto del bando, operatori invitati, aggiudicatario, importo di aggiudicazione, tempi "
            "di esecuzione e importi liquidati. La pubblicazione su AT sostituisce il bollettino ufficiale."
        ),
        "art. 5 — accesso civico": (
            "Chiunque può richiedere atti e documenti la cui pubblicazione è obbligatoria ma è stata "
            "omessa (accesso civico semplice). Il FOIA (accesso civico generalizzato) consente di accedere "
            "a qualsiasi dato o documento della PA, salvo le eccezioni previste dall'art. 5-bis."
        ),
    },
    "l_190_2012": {
        "art. 1 — PTPCT": (
            "Ogni PA adotta il Piano triennale di prevenzione della corruzione e della trasparenza (PTPCT), "
            "proposto dal RPCT e approvato dall'organo di indirizzo. Il piano identifica le aree a rischio "
            "e le misure organizzative obbligatorie, inclusa la rotazione del personale e la formazione."
        ),
        "art. 1 co. 9 — misure obbligatorie": (
            "Sono misure obbligatorie: rotazione degli incarichi nelle aree a rischio, astensione in caso "
            "di conflitto d'interessi, tutela del whistleblower, formazione obbligatoria sul tema "
            "anticorruzione, pubblicazione dei dati relativi ai procedimenti amministrativi rilevanti."
        ),
        "art. 1 co. 41 — conflitto d'interessi": (
            "Il responsabile del procedimento e i titolari degli uffici devono astenersi e segnalare ogni "
            "conflitto d'interesse, anche potenziale. L'attestazione di assenza di conflitti è richiesta "
            "in ogni atto di affidamento e deve essere allegata alla determina."
        ),
    },
    "dlgs_267_2000": {
        "art. 107 — competenze dirigenziali": (
            "I dirigenti adottano tutti gli atti di gestione che impegnano l'ente verso l'esterno, "
            "comprese le determine di affidamento e di impegno di spesa. La separazione tra indirizzo "
            "politico (organi elettivi) e gestione amministrativa (dirigenti) è il principio cardine del TUEL."
        ),
        "art. 192 — determinazione a contrarre": (
            "Prima di ogni procedura di affidamento, il responsabile del servizio adotta una determina "
            "a contrarre che indica: finalità, oggetto, forma del contratto, clausole essenziali, modalità "
            "di scelta del contraente e relativa motivazione. È l'atto presupposto obbligatorio di ogni gara."
        ),
        "art. 183 — assunzione impegno di spesa": (
            "L'impegno di spesa è l'atto con cui si perfeziona l'obbligazione verso terzi e si vincola "
            "la somma necessaria al bilancio dell'esercizio competente. Deve essere assunto prima o "
            "contestualmente alla determina di affidamento, verificata la disponibilità sul capitolo."
        ),
    },
    "dlgs_165_2001": {
        "art. 7 — gestione risorse e incarichi": (
            "Le PA possono conferire incarichi individuali, con contratti di lavoro autonomo, solo per "
            "esigenze cui non possono far fronte con il personale in servizio, quando la prestazione sia "
            "di natura temporanea o altamente qualificata. L'incarico deve essere motivato e pubblicato."
        ),
        "art. 19 — incarichi dirigenziali": (
            "Gli incarichi dirigenziali sono conferiti con provvedimento motivato, per un periodo non "
            "superiore a cinque anni, a dirigenti appartenenti ai ruoli dell'amministrazione o, in "
            "via eccezionale, a soggetti esterni (con limite di quota). Ogni incarico è revocabile."
        ),
        "art. 36 — utilizzo flessibile": (
            "Le PA possono stipulare contratti a tempo determinato, di somministrazione o altre forme "
            "flessibili solo per far fronte a esigenze temporanee e straordinarie, previo rispetto dei "
            "contingenti fissati dal CCNL e previa verifica dell'impossibilità di utilizzo di personale "
            "interno. Il mancato rispetto espone l'ente a responsabilità erariale."
        ),
    },
    "dlgs_196_2003": {
        "art. 13 GDPR — informativa": (
            "Il titolare del trattamento fornisce all'interessato, al momento della raccolta dei dati, "
            "tutte le informazioni previste dall'art. 13 GDPR: identità del titolare, finalità e base "
            "giuridica del trattamento, destinatari, periodo di conservazione, diritti dell'interessato. "
            "L'informativa deve essere concisa, trasparente e facilmente accessibile."
        ),
        "art. 28 GDPR — responsabile trattamento": (
            "Quando un fornitore tratta dati personali per conto della PA, deve essere nominato "
            "Responsabile del Trattamento (DPA) tramite atto scritto (contratto o altro atto giuridico) "
            "che specifichi oggetto, durata, natura del trattamento e obblighi del responsabile. "
            "La nomina va allegata al contratto di fornitura."
        ),
        "art. 32 GDPR — sicurezza trattamento": (
            "Il titolare e il responsabile del trattamento mettono in atto misure tecniche e organizzative "
            "adeguate per garantire un livello di sicurezza proporzionato al rischio: pseudonimizzazione, "
            "cifratura, continuità operativa, backup e ripristino, verifica periodica delle misure."
        ),
    },
    "dlgs_81_2008": {
        "art. 26 — obblighi connessi ai contratti d'appalto (DUVRI)": (
            "In caso di affidamento di lavori, servizi o forniture a imprese appaltatrici o lavoratori "
            "autonomi all'interno dell'azienda committente, il datore di lavoro verifica l'idoneità tecnico "
            "professionale delle imprese e redige il Documento Unico di Valutazione dei Rischi da "
            "Interferenze (DUVRI), allegato al contratto, che indica le misure adottate per eliminare o "
            "ridurre i rischi da interferenze."
        ),
        "art. 17 — obblighi non delegabili": (
            "Il datore di lavoro non può delegare la valutazione di tutti i rischi con la conseguente "
            "elaborazione del documento di valutazione dei rischi (DVR) e la designazione del Responsabile "
            "del Servizio di Prevenzione e Protezione (RSPP). Tutti gli altri obblighi di sicurezza "
            "possono essere delegati con atto scritto, purché il delegato abbia competenze adeguate."
        ),
    },
    "dlgs_118_2011": {
        "art. 56 — principi contabili applicati": (
            "I principi contabili applicati disciplinano le modalità di applicazione dei postulati del "
            "bilancio negli enti locali. Il principio della competenza finanziaria potenziata (Allegato 4/2) "
            "prevede che le obbligazioni attive e passive siano imputate all'esercizio in cui vengono a "
            "scadenza, garantendo la veridicità del bilancio."
        ),
        "Allegato 4/2 — principio della competenza finanziaria": (
            "Le entrate e le spese sono registrate nel bilancio dell'anno in cui l'obbligazione giuridica "
            "viene a scadenza (esigibilità). Le obbligazioni non scadute nell'esercizio confluiscono nel "
            "Fondo Pluriennale Vincolato (FPV). Questo principio previene il ricorso a residui attivi e "
            "passivi impropri, rendendo il bilancio più realistico."
        ),
    },
    "l_136_2010": {
        "art. 3 — obblighi di tracciabilità dei flussi finanziari": (
            "I soggetti appaltanti e gli appaltatori devono avvalersi di conti correnti bancari o postali "
            "dedicati, anche non in via esclusiva, per tutti i movimenti finanziari relativi ai contratti "
            "pubblici. Ogni transazione deve essere eseguita tramite strumenti tracciabili (bonifico, RID, "
            "ecc.) con indicazione del CIG e, ove previsto, del CUP."
        ),
        "art. 3 co. 5 — obbligo CIG e CUP": (
            "Il CIG (Codice Identificativo Gara) deve essere riportato in ogni contratto e in ogni "
            "strumento di pagamento. Il CUP (Codice Unico di Progetto) è obbligatorio quando il contratto "
            "riguarda investimenti pubblici finanziati con fondi pubblici nazionali o europei. "
            "La mancata indicazione costituisce causa di nullità del contratto e dà luogo a sanzioni."
        ),
        "art. 6 — sanzioni per violazione tracciabilità": (
            "La violazione degli obblighi di tracciabilità comporta la nullità assoluta del contratto. "
            "Sono previste sanzioni amministrative pecuniarie dal 5% al 20% del valore della transazione "
            "irregolare, con un minimo di 500 euro. Il RUP è responsabile del rispetto degli obblighi."
        ),
    },
    "l_241_1990": {
        "art. 1 — principi generali (efficacia, economicità, imparzialità)": (
            "L'attività amministrativa persegue i fini determinati dalla legge ed è retta da criteri di "
            "economicità, efficacia, imparzialità, proporzionalità, pubblicità e trasparenza. "
            "Le PA devono motivare ogni scostamento da tali principi e garantire la partecipazione "
            "degli interessati al procedimento."
        ),
        "art. 3 — obbligo di motivazione del provvedimento": (
            "Ogni provvedimento amministrativo deve essere motivato, con indicazione dei presupposti di "
            "fatto e delle ragioni giuridiche che hanno determinato la decisione. La motivazione mancante "
            "o insufficiente rende il provvedimento annullabile (art. 21-octies). Per gli atti vincolati "
            "la motivazione può essere per relationem."
        ),
        "art. 7 — comunicazione avvio del procedimento": (
            "L'amministrazione comunica l'avvio del procedimento ai soggetti nei confronti dei quali il "
            "provvedimento finale è destinato a produrre effetti diretti e a quelli che per legge devono "
            "intervenire. La comunicazione indica: amministrazione competente, oggetto del procedimento, "
            "RUP, ufficio e termine di conclusione."
        ),
        "art. 21-octies — annullabilità del provvedimento": (
            "Il provvedimento amministrativo è annullabile per violazione di legge, incompetenza ed eccesso "
            "di potere. Non è annullabile il provvedimento adottato in violazione di norme sul procedimento "
            "o sulla forma se, per la natura vincolata dell'atto, è palese che il contenuto dispositivo "
            "non avrebbe potuto essere diverso da quello in concreto adottato."
        ),
        "art. 22 — accesso agli atti amministrativi": (
            "I soggetti privati portatori di un interesse diretto, concreto e attuale hanno diritto di "
            "prendere visione e di estrarre copia di documenti amministrativi. Il diritto di accesso si "
            "esercita mediante richiesta motivata. L'accesso può essere limitato o escluso per ragioni di "
            "riservatezza, sicurezza o tutela di altri interessi pubblici."
        ),
    },
    "dlgs_50_2016": {
        "art. 36 — contratti sotto soglia (affidamento diretto, procedura negoziata)": (
            "(Disciplina previgente, applicabile ai contratti avviati prima del 1° luglio 2023.) "
            "Per lavori sotto 40.000 euro e servizi/forniture sotto 40.000 euro era ammesso l'affidamento "
            "diretto. Tra 40.000 e 150.000 euro per lavori e tra 40.000 euro e soglia comunitaria per "
            "servizi/forniture era richiesta procedura negoziata con almeno tre o cinque operatori."
        ),
        "art. 63 — procedura negoziata senza bando": (
            "(Disciplina previgente.) La procedura negoziata senza previa pubblicazione del bando era "
            "ammessa in casi eccezionali tassativi: estrema urgenza, unicita' del fornitore, precedente gara "
            "andata deserta, appalti di ricerca e sviluppo, appalti complementari. Richiede motivazione "
            "specifica nell'atto di avvio e trasmissione ANAC."
        ),
        "art. 95 — criteri di aggiudicazione": (
            "(Disciplina previgente.) I contratti devono essere aggiudicati con il criterio dell'offerta "
            "economicamente più vantaggiosa (OEPV) oppure, nei soli casi ammessi, con il criterio del "
            "minor prezzo. L'OEPV valuta qualità, prezzo, caratteristiche tecniche, ambientali e sociali."
        ),
        "art. 106 — modifica dei contratti in corso": (
            "(Disciplina previgente.) I contratti possono essere modificati senza nuova procedura di "
            "affidamento nei casi previsti: modifiche previamente contemplate nel contratto, lavori o "
            "servizi supplementari necessari, circostanze impreviste, cambio di contraente legittimo, "
            "modifiche non sostanziali. Le modifiche sostanziali richiedono una nuova gara."
        ),
    },
    "l_296_2006_consip": {
        "art. 1 co. 449 — obbligo adesione convenzioni Consip per PA statali": (
            "Le amministrazioni statali centrali e periferiche sono obbligate ad approvvigionarsi "
            "utilizzando le convenzioni-quadro stipulate da Consip. Le PA non statali possono aderire "
            "alle convenzioni Consip e devono in ogni caso utilizzarne i parametri di prezzo-qualità "
            "come limite massimo per i propri contratti autonomi, pena la nullità."
        ),
        "art. 1 co. 450 — obbligo MEPA per acquisti sotto soglia comunitaria": (
            "Le PA, per acquisti di beni e servizi di importo inferiore alla soglia comunitaria, "
            "ricorrono al Mercato Elettronico della PA (MEPA). È consentito procedere autonomamente "
            "solo previa verifica dell'assenza di prodotti/servizi equivalenti sul MEPA o dimostrazione "
            "di convenienza economica della procedura autonoma. Il RUP risponde erarialmente del mancato "
            "ricorso al MEPA."
        ),
        "art. 1 co. 452 — benchmark prezzi Consip per PA non statali": (
            "Le PA non statali (Comuni, Province, Regioni, ASL, Università) che non aderiscono alle "
            "convenzioni Consip devono dimostrare che i prezzi dei propri contratti autonomi sono "
            "inferiori o uguali a quelli delle convenzioni Consip vigenti, assunti come benchmark. "
            "Il superamento del benchmark espone il RUP a responsabilità erariale."
        ),
    },
    "dlgs_231_2001": {
        "art. 5 — responsabilità dell'ente per reati dei propri soggetti": (
            "L'ente è responsabile per i reati commessi nel suo interesse o a suo vantaggio da soggetti "
            "in posizione apicale o loro sottoposti, se il reato è stato reso possibile dall'inosservanza "
            "degli obblighi di direzione o vigilanza. La responsabilità dell'ente sussiste anche quando "
            "l'autore del reato non è identificato o non è imputabile."
        ),
        "art. 6 — esimenti: adozione ed efficace attuazione del MOG": (
            "L'ente è esonerato da responsabilità se dimostra di aver adottato ed efficacemente attuato, "
            "prima della commissione del reato, un Modello di organizzazione, gestione e controllo (MOG) "
            "idoneo a prevenire reati della specie di quello verificatosi, e di aver istituito un "
            "Organismo di Vigilanza (OdV) con poteri autonomi di controllo."
        ),
        "art. 24 — reati contro la PA (corruzione, concussione, frode)": (
            "In relazione a corruzione, concussione, indebita induzione, frode nelle pubbliche forniture "
            "e frode informatica in danno della PA, l'ente subisce sanzioni pecuniarie da 200 a 600 quote, "
            "più sanzioni interdittive (interdizione dall'esercizio dell'attività, esclusione da "
            "finanziamenti, revoca di autorizzazioni). Tali sanzioni incidono sulla qualificazione SOA."
        ),
        "art. 25 — peculato, corruzione e induzione indebita": (
            "Per i reati di cui agli artt. 317, 318, 319, 319-ter, 319-quater, 320, 321, 322-bis c.p., "
            "si applicano sanzioni pecuniarie fino a 1.000 quote e, per i casi più gravi, sanzioni "
            "interdittive permanenti. La PA appaltante deve verificare che il fornitore abbia adottato "
            "un MOG adeguato prima dell'affidamento."
        ),
    },
    "circ_agid_cloud_2021": {
        "Determinazione 628/2021 — qualificazione servizi SaaS per PA": (
            "AgID qualifica i servizi SaaS acquistabili dalla PA previa verifica di requisiti tecnici, "
            "organizzativi e di sicurezza. Solo i servizi presenti nel Catalogo Cloud PA "
            "(marketplace.cloud.gov.it) possono essere acquisiti dalla PA. La qualificazione ha durata "
            "triennale ed è soggetta a verifica periodica. Il mancato utilizzo di servizi qualificati "
            "può esporre il RUP a responsabilità."
        ),
        "Regolamento ACN 2022 — classificazione dati e servizi cloud": (
            "Il regolamento ACN classifica i dati della PA in quattro categorie (ordinari, critici, "
            "strategici, riservati) e stabilisce i livelli minimi di qualificazione cloud richiesti per "
            "ciascuna categoria. I dati strategici e riservati possono essere trattati solo in "
            "infrastrutture PSN o cloud qualificato di livello equivalente."
        ),
        "Circolare AgID 2/2018 — criteri qualificazione CSP e SaaS": (
            "La circolare definisce i criteri di qualificazione per i Cloud Service Provider (CSP) e "
            "per i servizi SaaS. I CSP devono soddisfare requisiti di sicurezza, continuità operativa, "
            "portabilità dei dati e reversibilità. Le PA devono verificare la presenza del fornitore "
            "nel catalogo AgID prima di avviare qualsiasi procedura di acquisto cloud."
        ),
    },
    "l_328_2000": {
        "art. 6 — funzioni dei Comuni": (
            "I Comuni sono titolari delle funzioni amministrative relative ai servizi sociali. "
            "Programmano, progettano e gestiscono il sistema locale dei servizi a rete, erogano le "
            "prestazioni economiche e garantiscono l'accesso ai servizi. L'esercizio può avvenire "
            "in forma associata tramite Ambiti Territoriali Sociali (ATS)."
        ),
        "art. 22 — sistema integrato": (
            "Il sistema integrato di interventi e servizi sociali comprende: misure di contrasto della "
            "povertà, servizi di supporto alla famiglia, servizi educativi per l'infanzia, interventi per "
            "persone disabili e anziani, strutture residenziali e semiresidenziali. La programmazione "
            "avviene tramite Piani di Zona triennali."
        ),
        "art. 25 — ISEE": (
            "L'accesso ai servizi sociali a tariffa agevolata è determinato sulla base dell'ISEE. "
            "I Comuni e le ASL possono articolare le tariffe in modo differenziato in base alla "
            "situazione economica del nucleo familiare. Il DPCM 159/2013 disciplina le modalità di "
            "calcolo dell'ISEE applicabile a ciascuna tipologia di prestazione."
        ),
    },
    "dpcm_159_2013": {
        "art. 2 — ISEE ordinario": (
            "L'ISEE ordinario è calcolato sulla base dei redditi e del patrimonio del nucleo familiare, "
            "come risultanti dalla DSU (Dichiarazione Sostitutiva Unica). Tiene conto del reddito "
            "complessivo, del patrimonio mobiliare e immobiliare e di specifiche franchigie per minori, "
            "disabili e percettori di trattamenti sociosanitari."
        ),
        "art. 6 — ISEE socio-sanitario": (
            "Per le prestazioni sociosanitarie residenziali e semiresidenziali (RSA, strutture per disabili), "
            "si utilizza l'ISEE socio-sanitario, calcolato con riferimento al solo nucleo ristretto del "
            "richiedente (disabile o anziano) e del coniuge, escludendo i figli. Questo riduce l'ISEE "
            "rispetto a quello ordinario, alleggerendo il carico familiare per le rette."
        ),
        "art. 7 — ISEE minorenni": (
            "Per le prestazioni agevolate rivolte a minorenni (asili nido, servizi scolastici, "
            "prestazioni sociali per minori), l'ISEE è calcolato includendo nel nucleo familiare entrambi "
            "i genitori, anche se non conviventi o separati, salvo eccezioni per affidamento esclusivo. "
            "Questo garantisce che entrambi i genitori contribuiscano alla compartecipazione."
        ),
        "art. 4 — nucleo familiare": (
            "Il nucleo familiare di riferimento per il calcolo ISEE è quello anagrafico alla data di "
            "presentazione della DSU, salvo le integrazioni previste dall'art. 3 (componenti non "
            "conviventi equiparati). La corretta individuazione del nucleo è presupposto della validità "
            "dell'ISEE e dell'accesso alle prestazioni agevolate."
        ),
    },
    "l_104_1992": {
        "art. 3 — definizione handicap grave": (
            "La situazione di handicap grave (comma 3) ricorre quando la minorazione, singola o plurima, "
            "ha ridotto l'autonomia personale in modo da rendere necessario un intervento assistenziale "
            "permanente, continuativo e globale nella sfera individuale o in quella di relazione. "
            "L'accertamento è effettuato dalle commissioni mediche ASL."
        ),
        "art. 8 — interventi a favore delle persone handicappate": (
            "I servizi di cui all'art. 8 comprendono: assistenza domiciliare, inserimento in centri "
            "diurni, inserimento in strutture residenziali quando non è possibile l'assistenza a domicilio, "
            "supporto all'integrazione scolastica e lavorativa. I Comuni garantiscono l'erogazione in "
            "forma diretta o tramite convenzionamento."
        ),
        "art. 10 — integrazione scolastica": (
            "L'integrazione scolastica degli alunni con disabilità è garantita dalle istituzioni scolastiche "
            "di ogni ordine e grado. Il Comune è responsabile dell'assistenza educativa e del trasporto "
            "scolastico. Il Piano Educativo Individualizzato (PEI) è redatto congiuntamente da scuola, "
            "famiglia, ASL e Comune."
        ),
        "art. 33 — agevolazioni lavorative": (
            "Il lavoratore con disabilità grave o che assiste un familiare con disabilità grave ha diritto "
            "a tre giorni di permesso mensile retribuito (o due ore al giorno), al prolungamento del "
            "congedo parentale e alla scelta della sede di lavoro più vicina al domicilio. "
            "Tali diritti sono opponibili al datore di lavoro pubblico e privato."
        ),
    },
    "pnrr_missione1": {
        "Componente 1.1 — Infrastrutture digitali": (
            "Finanzia la migrazione delle PA verso infrastrutture cloud sicure e la realizzazione del "
            "Polo Strategico Nazionale (PSN). Gli acquisti ICT con fondi PNRR devono rispettare i "
            "criteri di qualificazione AgID/ACN e le linee guida cloud-first. È obbligatorio il CUP "
            "in tutti i contratti finanziati con risorse PNRR."
        ),
        "Componente 1.2 — Abilitazione migrazione al cloud": (
            "Supporta la migrazione applicazioni e dati della PA verso il cloud qualificato, tramite "
            "voucher e assistenza tecnica. Le PA beneficiarie devono rendicontare le spese secondo le "
            "regole PNRR (target, milestone, indicatori). La mancata rendicontazione comporta il "
            "recupero delle somme erogate."
        ),
    },
}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        norma_id = params.get("id", [""])[0].strip()

        if not norma_id:
            self._send_error(400, "Parametro 'id' mancante")
            return

        norma = NORME_BY_ID.get(norma_id)
        if not norma:
            self._send_error(404, f"Norma '{norma_id}' non trovata")
            return

        testi_norma = ARTICOLI_TESTO.get(norma_id, {})
        articoli_dettaglio = [
            {"label": label, "testo": testi_norma.get(label, "")}
            for label in norma.get("articoli_chiave", [])
        ]

        output = {
            "id":                 norma["id"],
            "titolo":             norma["titolo"],
            "estremi":            norma["estremi"],
            "descrizione":        norma["descrizione"],
            "articoli_chiave":    norma.get("articoli_chiave", []),
            "articoli_dettaglio": articoli_dettaglio,
            "url_normattiva":     norma.get("url_normattiva", ""),
            "url_ricerca":        norma.get("url_ricerca", ""),
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

    def _send_error(self, code: int, msg: str) -> None:
        body = json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


handler = handler
