"""Endpoint GET /api/norma?id=<norma_id> — scheda dettaglio norma con articoli_dettaglio."""
import json
import os
import urllib.parse
import urllib.request

# ── Database normativo locale (mirror di search.py — nessun import cross-function) ──
NORMATIVE_DB = [
    {
        "id": "dlgs_36_2023",
        "titolo": "Codice dei contratti pubblici",
        "estremi": "D.Lgs. 31 marzo 2023, n. 36",
        "descrizione": "Disciplina l'affidamento e l'esecuzione di appalti pubblici e concessioni.",
        "articoli_chiave": ["art. 50 — affidamento diretto", "art. 51 — procedura negoziata semplificata", "art. 71 — procedura aperta", "art. 72 — procedura negoziata", "art. 15 — RUP"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2023-03-31;36",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+36+2023",
    },
    {
        "id": "dlgs_82_2005",
        "titolo": "Codice dell'Amministrazione Digitale (CAD)",
        "estremi": "D.Lgs. 7 marzo 2005, n. 82",
        "descrizione": "Regola la digitalizzazione della PA, l'uso di software, cloud computing e servizi ICT.",
        "articoli_chiave": ["art. 68 — analisi comparativa soluzioni", "art. 69 — riuso del software", "art. 50 — disponibilità dei dati"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2005-03-07;82",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=codice+amministrazione+digitale+82+2005",
    },
    {
        "id": "dlgs_33_2013",
        "titolo": "Trasparenza e accesso civico",
        "estremi": "D.Lgs. 14 marzo 2013, n. 33",
        "descrizione": "Obbliga le PA alla pubblicazione su Amministrazione Trasparente di dati su contratti, affidamenti e spese.",
        "articoli_chiave": ["art. 23 — obblighi pubblicazione provvedimenti", "art. 37 — pubblicazione contratti e appalti", "art. 5 — accesso civico"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2013-03-14;33",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+33+2013+trasparenza",
    },
    {
        "id": "l_190_2012",
        "titolo": "Legge Anticorruzione",
        "estremi": "L. 6 novembre 2012, n. 190",
        "descrizione": "Introduce misure per la prevenzione della corruzione nella PA. Obbliga gli enti al PTPCT.",
        "articoli_chiave": ["art. 1 — PTPCT", "art. 1 co. 9 — misure obbligatorie", "art. 1 co. 41 — conflitto d'interessi"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2012-11-06;190",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+190+2012+anticorruzione",
    },
    {
        "id": "dlgs_267_2000",
        "titolo": "Testo Unico Enti Locali (TUEL)",
        "estremi": "D.Lgs. 18 agosto 2000, n. 267",
        "descrizione": "Disciplina l'organizzazione di Comuni e Province.",
        "articoli_chiave": ["art. 107 — competenze dirigenziali", "art. 192 — determinazione a contrarre", "art. 183 — assunzione impegno di spesa"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2000-08-18;267",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=TUEL+267+2000",
    },
    {
        "id": "dlgs_165_2001",
        "titolo": "Testo Unico Pubblico Impiego (TUPI)",
        "estremi": "D.Lgs. 30 marzo 2001, n. 165",
        "descrizione": "Disciplina il rapporto di lavoro dei dipendenti PA.",
        "articoli_chiave": ["art. 7 — gestione risorse e incarichi", "art. 19 — incarichi dirigenziali", "art. 36 — utilizzo flessibile"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2001-03-30;165",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=TUPI+165+2001",
    },
    {
        "id": "dlgs_196_2003",
        "titolo": "Codice Privacy + GDPR",
        "estremi": "D.Lgs. 30 giugno 2003, n. 196 (mod. dal Reg. UE 2016/679)",
        "descrizione": "Disciplina il trattamento dei dati personali.",
        "articoli_chiave": ["art. 13 GDPR — informativa", "art. 28 GDPR — responsabile trattamento", "art. 32 GDPR — sicurezza trattamento"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003-06-30;196",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=codice+privacy+196+2003",
    },
    {
        "id": "dlgs_81_2008",
        "titolo": "Testo Unico Sicurezza sul Lavoro",
        "estremi": "D.Lgs. 9 aprile 2008, n. 81",
        "descrizione": "Disciplina la sicurezza nei luoghi di lavoro.",
        "articoli_chiave": ["art. 26 — obblighi connessi ai contratti d'appalto (DUVRI)", "art. 17 — obblighi non delegabili"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2008-04-09;81",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=sicurezza+lavoro+81+2008",
    },
    {
        "id": "dlgs_118_2011",
        "titolo": "Armonizzazione contabile enti locali",
        "estremi": "D.Lgs. 23 giugno 2011, n. 118",
        "descrizione": "Disciplina i sistemi contabili e gli schemi di bilancio di Regioni, Province e Comuni.",
        "articoli_chiave": ["art. 56 — principi contabili applicati", "Allegato 4/2 — principio della competenza finanziaria"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2011-06-23;118",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=armonizzazione+contabile+118+2011",
    },
    {
        "id": "pnrr_missione1",
        "titolo": "PNRR — Missione 1: Digitalizzazione PA",
        "estremi": "Piano Nazionale di Ripresa e Resilienza, Missione 1",
        "descrizione": "Definisce gli investimenti per la transizione digitale della PA.",
        "articoli_chiave": ["Componente 1.1 — Infrastrutture digitali", "Componente 1.2 — Abilitazione migrazione al cloud"],
        "url_normattiva": "https://www.normattiva.it/ricerca/semplice?query=PNRR+digitalizzazione",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=PNRR+digitalizzazione",
    },
    {
        "id": "l_136_2010",
        "titolo": "Tracciabilità dei flussi finanziari (CIG/CUP)",
        "estremi": "L. 13 agosto 2010, n. 136",
        "descrizione": "Obbliga le stazioni appaltanti a utilizzare conti dedicati e strumenti tracciabili.",
        "articoli_chiave": ["art. 3 — obblighi di tracciabilità dei flussi finanziari", "art. 3 co. 5 — obbligo CIG e CUP", "art. 6 — sanzioni per violazione tracciabilità"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2010-08-13;136",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+136+2010+tracciabilita+CIG",
    },
    {
        "id": "l_241_1990",
        "titolo": "Legge sul procedimento amministrativo",
        "estremi": "L. 7 agosto 1990, n. 241",
        "descrizione": "Regola il procedimento amministrativo in tutte le sue fasi.",
        "articoli_chiave": ["art. 1 — principi generali (efficacia, economicità, imparzialità)", "art. 3 — obbligo di motivazione del provvedimento", "art. 7 — comunicazione avvio del procedimento", "art. 21-octies — annullabilità del provvedimento", "art. 22 — accesso agli atti amministrativi"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1990-08-07;241",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+241+1990+procedimento",
    },
    {
        "id": "dlgs_50_2016",
        "titolo": "Codice dei contratti pubblici 2016 (previgente)",
        "estremi": "D.Lgs. 18 aprile 2016, n. 50",
        "descrizione": "Codice appalti previgente, applicabile ai contratti avviati prima del 1° luglio 2023.",
        "articoli_chiave": ["art. 36 — contratti sotto soglia (affidamento diretto, procedura negoziata)", "art. 63 — procedura negoziata senza bando", "art. 95 — criteri di aggiudicazione", "art. 106 — modifica dei contratti in corso"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2016-04-18;50",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+legislativo+50+2016+appalti",
    },
    {
        "id": "l_296_2006_consip",
        "titolo": "Obbligo Consip / MEPA (L. Finanziaria 2007)",
        "estremi": "L. 27 dicembre 2006, n. 296, art. 1 co. 449-450",
        "descrizione": "Obbliga le amministrazioni statali ad approvvigionarsi tramite convenzioni Consip o MEPA.",
        "articoli_chiave": ["art. 1 co. 449 — obbligo adesione convenzioni Consip per PA statali", "art. 1 co. 450 — obbligo MEPA per acquisti sotto soglia comunitaria", "art. 1 co. 452 — benchmark prezzi Consip per PA non statali"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2006-12-27;296",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+296+2006+consip+mepa",
    },
    {
        "id": "dlgs_231_2001",
        "titolo": "Responsabilità amministrativa degli enti (D.Lgs. 231)",
        "estremi": "D.Lgs. 8 giugno 2001, n. 231",
        "descrizione": "Disciplina la responsabilità amministrativa delle persone giuridiche per reati commessi nell'interesse dell'ente.",
        "articoli_chiave": ["art. 5 — responsabilità dell'ente per reati dei propri soggetti", "art. 6 — esimenti: adozione ed efficace attuazione del MOG", "art. 24 — reati contro la PA (corruzione, concussione, frode)", "art. 25 — peculato, corruzione e induzione indebita"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2001-06-08;231",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=decreto+231+2001+responsabilita+enti",
    },
    {
        "id": "circ_agid_cloud_2021",
        "titolo": "Qualificazione cloud PA — Linee guida AgID / ACN",
        "estremi": "Circolare AgID n. 2/2018 + Determinazione AgID 628/2021 + Regolamento ACN 2022",
        "descrizione": "Definisce i requisiti di qualificazione per i servizi cloud acquistabili dalla PA.",
        "articoli_chiave": ["Determinazione 628/2021 — qualificazione servizi SaaS per PA", "Regolamento ACN 2022 — classificazione dati e servizi cloud", "Circolare AgID 2/2018 — criteri qualificazione CSP e SaaS"],
        "url_normattiva": "https://www.agid.gov.it/it/infrastrutture/cloud-pa",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=AgID+qualificazione+cloud+PA",
    },
    {
        "id": "l_328_2000",
        "titolo": "Legge quadro servizi sociali",
        "estremi": "L. 8 novembre 2000, n. 328",
        "descrizione": "Legge quadro che disciplina il sistema integrato di interventi e servizi sociali.",
        "articoli_chiave": ["art. 6 — funzioni dei Comuni", "art. 22 — sistema integrato", "art. 25 — ISEE"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:2000-11-08;328",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+328+2000+servizi+sociali",
    },
    {
        "id": "dpcm_159_2013",
        "titolo": "Regolamento ISEE",
        "estremi": "D.P.C.M. 5 dicembre 2013, n. 159",
        "descrizione": "Regolamento che disciplina la determinazione dell'ISEE.",
        "articoli_chiave": ["art. 2 — ISEE ordinario", "art. 6 — ISEE socio-sanitario", "art. 7 — ISEE minorenni", "art. 4 — nucleo familiare"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.del.presidente.del.consiglio.dei.ministri:2013-12-05;159",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=DPCM+159+2013+ISEE",
    },
    {
        "id": "l_104_1992",
        "titolo": "Legge-quadro assistenza persone con disabilità",
        "estremi": "L. 5 febbraio 1992, n. 104",
        "descrizione": "Legge quadro sull'assistenza e l'integrazione sociale delle persone con disabilità.",
        "articoli_chiave": ["art. 3 — definizione handicap grave", "art. 8 — interventi a favore delle persone handicappate", "art. 10 — integrazione scolastica", "art. 33 — agevolazioni lavorative"],
        "url_normattiva": "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:legge:1992-02-05;104",
        "url_ricerca": "https://www.normattiva.it/ricerca/semplice?query=legge+104+1992+disabili",
    },
]

NORME_BY_ID = {n["id"]: n for n in NORMATIVE_DB}

# ── Testi sintetici degli articoli chiave ───────────────────────────────────────
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
            "del criterio di rotazione degli inviti."
        ),
        "art. 71 — procedura aperta": (
            "Nelle procedure aperte qualsiasi operatore può presentare offerta. Il termine minimo per "
            "la ricezione delle offerte è 35 giorni dalla trasmissione del bando, riducibile a 15 giorni "
            "in caso di urgenza. Obbligatoria per importi superiori alle soglie comunitarie."
        ),
        "art. 72 — procedura negoziata": (
            "Applicabile a servizi e forniture tra 215.000 euro e la soglia comunitaria. Richiede "
            "pubblicazione di un avviso e consultazione di almeno cinque operatori."
        ),
        "art. 15 — RUP": (
            "Per ogni contratto pubblico la stazione appaltante nomina un Responsabile Unico del "
            "Procedimento (RUP) con adeguate competenze. L'atto di nomina deve essere inserito nella "
            "determina a contrarre o nell'atto equivalente."
        ),
    },
    "dlgs_82_2005": {
        "art. 68 — analisi comparativa soluzioni": (
            "Prima di acquisire software, le PA effettuano una valutazione comparativa delle soluzioni "
            "disponibili, dando preferenza — a parità di costo — a soluzioni aperte e riusabili."
        ),
        "art. 69 — riuso del software": (
            "Le PA titolari di software sviluppato su loro indicazione sono obbligate a pubblicare il "
            "codice sorgente su un repository pubblico sotto licenza aperta."
        ),
        "art. 50 — disponibilità dei dati": (
            "I dati delle PA sono formati, raccolti e resi disponibili con tecnologie ICT in formato "
            "aperto e interoperabile."
        ),
    },
    "dlgs_33_2013": {
        "art. 23 — obblighi pubblicazione provvedimenti": (
            "Le PA pubblicano su Amministrazione Trasparente, con cadenza semestrale, l'elenco dei "
            "provvedimenti adottati dagli organi politici e dai dirigenti."
        ),
        "art. 37 — pubblicazione contratti e appalti": (
            "Le stazioni appaltanti pubblicano su Amministrazione Trasparente: struttura proponente, "
            "oggetto del bando, aggiudicatario, importo di aggiudicazione e importi liquidati."
        ),
        "art. 5 — accesso civico": (
            "Chiunque può richiedere atti e documenti la cui pubblicazione è obbligatoria ma è stata "
            "omessa. Il FOIA consente di accedere a qualsiasi dato o documento della PA."
        ),
    },
    "l_190_2012": {
        "art. 1 — PTPCT": (
            "Ogni PA adotta il Piano triennale di prevenzione della corruzione e della trasparenza (PTPCT), "
            "proposto dal RPCT e approvato dall'organo di indirizzo."
        ),
        "art. 1 co. 9 — misure obbligatorie": (
            "Sono misure obbligatorie: rotazione degli incarichi, astensione in caso di conflitto "
            "d'interessi, tutela del whistleblower, formazione anticorruzione."
        ),
        "art. 1 co. 41 — conflitto d'interessi": (
            "Il responsabile del procedimento deve astenersi e segnalare ogni conflitto d'interesse. "
            "L'attestazione di assenza di conflitti è richiesta in ogni atto di affidamento."
        ),
    },
    "dlgs_267_2000": {
        "art. 107 — competenze dirigenziali": (
            "I dirigenti adottano tutti gli atti di gestione che impegnano l'ente verso l'esterno, "
            "comprese le determine di affidamento e di impegno di spesa."
        ),
        "art. 192 — determinazione a contrarre": (
            "Prima di ogni procedura di affidamento, il responsabile del servizio adotta una determina "
            "a contrarre che indica finalità, oggetto, forma del contratto e modalità di scelta del contraente."
        ),
        "art. 183 — assunzione impegno di spesa": (
            "L'impegno di spesa è l'atto con cui si perfeziona l'obbligazione verso terzi e si vincola "
            "la somma necessaria al bilancio dell'esercizio competente."
        ),
    },
    "dlgs_165_2001": {
        "art. 7 — gestione risorse e incarichi": (
            "Le PA possono conferire incarichi individuali con contratti di lavoro autonomo solo per "
            "esigenze temporanee o altamente qualificate cui non possono far fronte con personale interno."
        ),
        "art. 19 — incarichi dirigenziali": (
            "Gli incarichi dirigenziali sono conferiti con provvedimento motivato, per un periodo non "
            "superiore a cinque anni. Ogni incarico è revocabile."
        ),
        "art. 36 — utilizzo flessibile": (
            "Le PA possono stipulare contratti flessibili solo per esigenze temporanee e straordinarie, "
            "previo rispetto dei contingenti fissati dal CCNL."
        ),
    },
    "dlgs_196_2003": {
        "art. 13 GDPR — informativa": (
            "Il titolare del trattamento fornisce all'interessato, al momento della raccolta dei dati, "
            "tutte le informazioni previste dall'art. 13 GDPR."
        ),
        "art. 28 GDPR — responsabile trattamento": (
            "Quando un fornitore tratta dati personali per conto della PA, deve essere nominato "
            "Responsabile del Trattamento tramite atto scritto allegato al contratto."
        ),
        "art. 32 GDPR — sicurezza trattamento": (
            "Il titolare e il responsabile del trattamento mettono in atto misure tecniche e organizzative "
            "adeguate per garantire sicurezza proporzionata al rischio."
        ),
    },
    "dlgs_81_2008": {
        "art. 26 — obblighi connessi ai contratti d'appalto (DUVRI)": (
            "In caso di affidamento di lavori o servizi, il datore di lavoro redige il DUVRI, allegato "
            "al contratto, che indica le misure adottate per eliminare i rischi da interferenze."
        ),
        "art. 17 — obblighi non delegabili": (
            "Il datore di lavoro non può delegare la valutazione dei rischi (DVR) e la designazione "
            "del RSPP."
        ),
    },
    "dlgs_118_2011": {
        "art. 56 — principi contabili applicati": (
            "I principi contabili applicati disciplinano le modalità di applicazione dei postulati "
            "del bilancio negli enti locali."
        ),
        "Allegato 4/2 — principio della competenza finanziaria": (
            "Le entrate e le spese sono registrate nel bilancio dell'anno in cui l'obbligazione "
            "giuridica viene a scadenza. Le obbligazioni non scadute confluiscono nel FPV."
        ),
    },
    "l_136_2010": {
        "art. 3 — obblighi di tracciabilità dei flussi finanziari": (
            "I soggetti appaltanti devono avvalersi di conti correnti dedicati per tutti i movimenti "
            "finanziari relativi ai contratti pubblici, con indicazione del CIG e del CUP."
        ),
        "art. 3 co. 5 — obbligo CIG e CUP": (
            "Il CIG deve essere riportato in ogni contratto e strumento di pagamento. Il CUP è "
            "obbligatorio per investimenti finanziati con fondi pubblici."
        ),
        "art. 6 — sanzioni per violazione tracciabilità": (
            "La violazione degli obblighi di tracciabilità comporta la nullità assoluta del contratto "
            "e sanzioni dal 5% al 20% del valore della transazione irregolare."
        ),
    },
    "l_241_1990": {
        "art. 1 — principi generali (efficacia, economicità, imparzialità)": (
            "L'attività amministrativa è retta da criteri di economicità, efficacia, imparzialità, "
            "proporzionalità, pubblicità e trasparenza."
        ),
        "art. 3 — obbligo di motivazione del provvedimento": (
            "Ogni provvedimento amministrativo deve essere motivato con i presupposti di fatto e le "
            "ragioni giuridiche. La motivazione mancante rende il provvedimento annullabile."
        ),
        "art. 7 — comunicazione avvio del procedimento": (
            "L'amministrazione comunica l'avvio del procedimento ai soggetti destinatari degli effetti "
            "diretti, indicando RUP, ufficio e termine di conclusione."
        ),
        "art. 21-octies — annullabilità del provvedimento": (
            "Il provvedimento è annullabile per violazione di legge, incompetenza ed eccesso di potere."
        ),
        "art. 22 — accesso agli atti amministrativi": (
            "I soggetti portatori di un interesse diretto, concreto e attuale hanno diritto di prendere "
            "visione e di estrarre copia di documenti amministrativi."
        ),
    },
    "dlgs_50_2016": {
        "art. 36 — contratti sotto soglia (affidamento diretto, procedura negoziata)": (
            "(Disciplina previgente.) Per lavori e servizi/forniture sotto 40.000 euro era ammesso "
            "l'affidamento diretto. Tra 40.000 euro e soglia comunitaria era richiesta procedura negoziata."
        ),
        "art. 63 — procedura negoziata senza bando": (
            "(Disciplina previgente.) Ammessa in casi tassativi: estrema urgenza, unicità del fornitore, "
            "gara deserta, appalti di ricerca."
        ),
        "art. 95 — criteri di aggiudicazione": (
            "(Disciplina previgente.) Aggiudicazione con offerta economicamente più vantaggiosa (OEPV) "
            "o, nei casi ammessi, con il criterio del minor prezzo."
        ),
        "art. 106 — modifica dei contratti in corso": (
            "(Disciplina previgente.) I contratti possono essere modificati senza nuova procedura solo "
            "nei casi tassativi previsti. Le modifiche sostanziali richiedono una nuova gara."
        ),
    },
    "l_296_2006_consip": {
        "art. 1 co. 449 — obbligo adesione convenzioni Consip per PA statali": (
            "Le amministrazioni statali sono obbligate ad approvvigionarsi tramite convenzioni Consip."
        ),
        "art. 1 co. 450 — obbligo MEPA per acquisti sotto soglia comunitaria": (
            "Le PA ricorrono al MEPA per acquisti sotto soglia. È consentito procedere autonomamente "
            "solo previa verifica dell'assenza di prodotti equivalenti sul MEPA."
        ),
        "art. 1 co. 452 — benchmark prezzi Consip per PA non statali": (
            "Le PA non statali che non aderiscono a Consip devono dimostrare che i propri prezzi "
            "siano inferiori o uguali al benchmark Consip vigente."
        ),
    },
    "dlgs_231_2001": {
        "art. 5 — responsabilità dell'ente per reati dei propri soggetti": (
            "L'ente è responsabile per i reati commessi nel suo interesse da soggetti in posizione "
            "apicale, se il reato è stato reso possibile dall'inosservanza degli obblighi di vigilanza."
        ),
        "art. 6 — esimenti: adozione ed efficace attuazione del MOG": (
            "L'ente è esonerato da responsabilità se ha adottato ed efficacemente attuato un MOG "
            "idoneo e ha istituito un Organismo di Vigilanza con poteri autonomi."
        ),
        "art. 24 — reati contro la PA (corruzione, concussione, frode)": (
            "Per corruzione e frode in danno della PA, l'ente subisce sanzioni pecuniarie e interdittive "
            "che incidono sulla qualificazione SOA."
        ),
        "art. 25 — peculato, corruzione e induzione indebita": (
            "Per i reati più gravi si applicano sanzioni pecuniarie fino a 1.000 quote e sanzioni "
            "interdittive permanenti."
        ),
    },
    "circ_agid_cloud_2021": {
        "Determinazione 628/2021 — qualificazione servizi SaaS per PA": (
            "Solo i servizi presenti nel Catalogo Cloud PA (marketplace.cloud.gov.it) possono essere "
            "acquisiti dalla PA. La qualificazione ha durata triennale."
        ),
        "Regolamento ACN 2022 — classificazione dati e servizi cloud": (
            "Il regolamento classifica i dati della PA in quattro categorie e stabilisce i livelli "
            "minimi di qualificazione cloud richiesti per ciascuna."
        ),
        "Circolare AgID 2/2018 — criteri qualificazione CSP e SaaS": (
            "La circolare definisce i criteri di qualificazione per i Cloud Service Provider e i "
            "servizi SaaS. Le PA devono verificare la presenza del fornitore nel catalogo AgID."
        ),
    },
    "l_328_2000": {
        "art. 6 — funzioni dei Comuni": (
            "I Comuni programmano, progettano e gestiscono il sistema locale dei servizi sociali a rete."
        ),
        "art. 22 — sistema integrato": (
            "Il sistema integrato comprende: misure di contrasto della povertà, servizi per la famiglia, "
            "servizi educativi, interventi per disabili e anziani. La programmazione avviene tramite Piani di Zona."
        ),
        "art. 25 — ISEE": (
            "L'accesso ai servizi sociali a tariffa agevolata è determinato sulla base dell'ISEE."
        ),
    },
    "dpcm_159_2013": {
        "art. 2 — ISEE ordinario": (
            "L'ISEE ordinario è calcolato sulla base dei redditi e del patrimonio del nucleo familiare "
            "come risultanti dalla DSU."
        ),
        "art. 6 — ISEE socio-sanitario": (
            "Per le prestazioni sociosanitarie residenziali (RSA, strutture per disabili) si utilizza "
            "l'ISEE socio-sanitario, calcolato con riferimento al solo nucleo ristretto."
        ),
        "art. 7 — ISEE minorenni": (
            "Per prestazioni rivolte a minorenni, l'ISEE include nel nucleo entrambi i genitori, "
            "anche se non conviventi o separati."
        ),
        "art. 4 — nucleo familiare": (
            "Il nucleo familiare di riferimento è quello anagrafico alla data di presentazione della DSU."
        ),
    },
    "l_104_1992": {
        "art. 3 — definizione handicap grave": (
            "La situazione di handicap grave ricorre quando la minorazione ha ridotto l'autonomia "
            "personale rendendo necessario un intervento assistenziale permanente e globale."
        ),
        "art. 8 — interventi a favore delle persone handicappate": (
            "I servizi comprendono: assistenza domiciliare, centri diurni, strutture residenziali, "
            "supporto all'integrazione scolastica e lavorativa."
        ),
        "art. 10 — integrazione scolastica": (
            "L'integrazione scolastica degli alunni con disabilità è garantita da ogni istituzione "
            "scolastica. Il PEI è redatto congiuntamente da scuola, famiglia, ASL e Comune."
        ),
        "art. 33 — agevolazioni lavorative": (
            "Il lavoratore che assiste un familiare con disabilità grave ha diritto a tre giorni di "
            "permesso mensile retribuito e alla scelta della sede di lavoro più vicina al domicilio."
        ),
    },
    "pnrr_missione1": {
        "Componente 1.1 — Infrastrutture digitali": (
            "Finanzia la migrazione delle PA verso infrastrutture cloud sicure e il PSN. "
            "È obbligatorio il CUP in tutti i contratti finanziati con risorse PNRR."
        ),
        "Componente 1.2 — Abilitazione migrazione al cloud": (
            "Supporta la migrazione applicazioni e dati verso il cloud qualificato. "
            "Le PA beneficiarie devono rendicontare le spese secondo le regole PNRR."
        ),
    },
}


def _fetch_from_supabase(norma_id: str) -> dict | None:
    """
    Fallback: cerca la norma su Supabase per norma_id.
    Usato per norme scoperte dinamicamente da Groq (Stadio 3) non presenti nel DB locale.
    """
    supa_url = os.environ.get("SUPABASE_URL", "")
    supa_key = os.environ.get("SUPABASE_KEY", "")
    if not supa_url or not supa_key:
        return None
    try:
        url = (
            f"{supa_url}/rest/v1/norme"
            f"?norma_id=eq.{urllib.parse.quote(norma_id)}"
            f"&select=norma_id,titolo,estremi,descrizione,articoli_chiave,url_normattiva,url_ricerca"
            f"&limit=1"
        )
        req = urllib.request.Request(
            url,
            headers={
                "apikey": supa_key,
                "Authorization": f"Bearer {supa_key}",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            rows = json.loads(resp.read().decode())
        if not rows:
            return None
        r = rows[0]
        return {
            "id":             r["norma_id"],
            "titolo":         r.get("titolo", ""),
            "estremi":        r.get("estremi", ""),
            "descrizione":    r.get("descrizione", ""),
            "articoli_chiave": r.get("articoli_chiave") or [],
            "url_normattiva": r.get("url_normattiva", ""),
            "url_ricerca":    r.get("url_ricerca", ""),
        }
    except Exception as exc:
        print(f"[NORMA SUPA] fallback fallito per {norma_id!r}: {exc}", flush=True)
        return None



from urllib.parse import urlparse, parse_qs

def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()

    if method == "OPTIONS":
        start_response("204 No Content", [
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
        ])
        return [b""]

    qs = environ.get("QUERY_STRING", "")
    params = parse_qs(qs)
    norma_id = params.get("id", [""])[0].strip()

    def send_error(code, msg):
        body = json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8")
        status = f"{code} {'Bad Request' if code == 400 else 'Not Found'}"
        start_response(status, [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Access-Control-Allow-Origin", "*"),
            ("Content-Length", str(len(body))),
        ])
        return [body]

    if not norma_id:
        return send_error(400, "Parametro 'id' mancante")

    norma = NORME_BY_ID.get(norma_id)
    if not norma:
        print(f"[NORMA] {norma_id!r} non nel DB locale, provo Supabase...", flush=True)
        norma = _fetch_from_supabase(norma_id)

    if not norma:
        return send_error(404, f"Norma '{norma_id}' non trovata")

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
    start_response("200 OK", [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Access-Control-Allow-Origin", "*"),
        ("Content-Length", str(len(body))),
    ])
    return [body]


handler = app
