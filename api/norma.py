"""Endpoint GET /api/norma?id=<norma_id> — restituisce dettaglio di una singola norma."""
from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.parse

# Importa il database normativo dal modulo search
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Testo sintetico per articoli chiave (espanso rispetto ai soli estremi)
ARTICOLI_TESTO = {
    "dlgs_36_2023": {
        "art. 50 — affidamento diretto": (
            "Le stazioni appaltanti procedono all'affidamento diretto di lavori di importo inferiore "
            "a 150.000 euro e di servizi e forniture, ivi compresi i servizi di ingegneria e architettura "
            "e l'attività di progettazione, di importo inferiore a 140.000 euro, anche senza consultazione "
            "di più operatori economici, assicurando che siano scelti soggetti in possesso di documentate "
            "esperienze pregresse idonee all'esecuzione delle prestazioni contrattuali. "
            "Per affidamenti di importo inferiore a 5.000 euro è consentita la trattativa diretta con "
            "un unico operatore (c.d. affidamento diretto semplificato)."
        ),
        "art. 51 — procedura negoziata semplificata": (
            "Per lavori di importo pari o superiore a 150.000 euro e inferiore a 1.000.000 di euro, "
            "le stazioni appaltanti possono procedere mediante procedura negoziata previa consultazione "
            "di almeno cinque operatori economici. Per servizi e forniture di importo pari o superiore "
            "a 140.000 euro e fino alle soglie europee, la stazione appaltante consulta almeno cinque "
            "operatori economici nel rispetto del criterio di rotazione."
        ),
        "art. 71 — procedura aperta": (
            "Nelle procedure aperte, qualsiasi operatore economico interessato può presentare un'offerta. "
            "Il termine minimo per la ricezione delle offerte è di 35 giorni dalla trasmissione del bando "
            "di gara. Il termine può essere ridotto a 15 giorni qualora la stazione appaltante abbia "
            "pubblicato un avviso di pre-informazione. La procedura è obbligatoria per importi superiori "
            "alle soglie comunitarie."
        ),
        "art. 72 — procedura negoziata": (
            "Le stazioni appaltanti possono aggiudicare appalti pubblici mediante procedura negoziata "
            "previa pubblicazione di un bando di gara nei seguenti casi: lavori di importo pari o superiore "
            "a 1.000.000 di euro e inferiore alla soglia comunitaria; servizi e forniture di importo pari o "
            "superiore a 215.000 euro e inferiore alla soglia comunitaria. La consultazione deve avvenire "
            "con almeno cinque operatori economici."
        ),
        "art. 15 — RUP": (
            "Per ogni intervento da realizzarsi mediante un contratto pubblico, le stazioni appaltanti "
            "nominano un responsabile del procedimento unico per le fasi di programmazione, progettazione, "
            "affidamento ed esecuzione (RUP). Il RUP deve possedere titolo di studio e competenze adeguate "
            "alla natura e alla complessità del contratto. L'atto di nomina del RUP deve essere inserito "
            "nella determina a contrarre o nell'atto equivalente."
        ),
    },
    "dlgs_82_2005": {
        "art. 68 — analisi comparativa soluzioni": (
            "Le pubbliche amministrazioni che intendono acquisire programmi informatici o parti di essi "
            "devono effettuare prioritariamente una valutazione comparativa delle soluzioni disponibili sul "
            "mercato, tenendo conto delle soluzioni già in uso. Viene data preferenza, a parità di costo, "
            "al software aperto e riusabile. La valutazione deve essere documentata e inserita negli atti "
            "della procedura di acquisto. L'AGID pubblica linee guida specifiche."
        ),
        "art. 69 — riuso del software": (
            "Le pubbliche amministrazioni che sono titolari di soluzioni e programmi informatici realizzati "
            "su loro specifica indicazione, a loro trasferiti o da esse sviluppati, hanno l'obbligo di "
            "rendere disponibile il relativo codice sorgente, completo della documentazione e rilasciato in "
            "repertorio pubblico sotto licenza aperta, in uso gratuito ad altre pubbliche amministrazioni. "
            "Il catalogo del software riusabile è pubblicato su developers.italia.it."
        ),
        "art. 50 — disponibilità dei dati": (
            "I dati delle pubbliche amministrazioni sono formati, raccolti, conservati, resi disponibili e "
            "accessibili con l'uso delle tecnologie dell'informazione e della comunicazione. Le PA devono "
            "rendere disponibili i dati in formato aperto, salvo i casi di esclusione previsti dalla legge. "
            "La disponibilità dei dati abilita l'interoperabilità e il riuso."
        ),
    },
    "dlgs_33_2013": {
        "art. 23 — obblighi pubblicazione provvedimenti": (
            "Le pubbliche amministrazioni pubblicano e aggiornano ogni sei mesi, in distinte partizioni "
            "della sezione 'Amministrazione trasparente', le liste dei provvedimenti adottati dagli organi "
            "di indirizzo politico e dai dirigenti. Per ogni provvedimento devono essere indicati il "
            "contenuto, l'oggetto, la eventuale spesa prevista e gli estremi relativi ai principali "
            "documenti contenuti nel fascicolo del procedimento."
        ),
        "art. 37 — pubblicazione contratti e appalti": (
            "Le stazioni appaltanti sono tenute a pubblicare nella sezione 'Amministrazione trasparente', "
            "gli atti e le informazioni oggetto di pubblicazione ai sensi del decreto legislativo 18 aprile "
            "2016, n. 50. In particolare devono essere pubblicati: struttura proponente, oggetto del bando, "
            "elenco degli operatori invitati a presentare offerta, aggiudicatario, importo di "
            "aggiudicazione, tempi di completamento dell'opera, servizio o fornitura, importo delle somme "
            "liquidate. La pubblicazione su Amministrazione trasparente sostituisce il bollettino ufficiale."
        ),
        "art. 5 — accesso civico": (
            "L'obbligo previsto dalla normativa vigente in capo alle pubbliche amministrazioni di "
            "pubblicare documenti, informazioni o dati comporta il diritto di chiunque di richiedere i "
            "medesimi, nei casi in cui sia stata omessa la loro pubblicazione (accesso civico semplice). "
            "L'accesso civico generalizzato (FOIA) consente a chiunque di accedere a dati e documenti "
            "ulteriori rispetto a quelli oggetto di pubblicazione obbligatoria, nel rispetto dei limiti "
            "relativi alla tutela di interessi giuridicamente rilevanti."
        ),
    },
    "l_190_2012": {
        "art. 1 — PTPCT": (
            "Ogni pubblica amministrazione adotta il Piano triennale di prevenzione della corruzione e della "
            "trasparenza (PTPCT). Il piano individua le attività nelle quali è più elevato il rischio di "
            "corruzione, indica le misure organizzative per prevenire il rischio e monitora il rispetto "
            "delle misure. Il PTPCT è adottato dall'organo di indirizzo politico su proposta del "
            "responsabile della prevenzione della corruzione e della trasparenza (RPCT)."
        ),
        "art. 1 co. 9 — misure obbligatorie": (
            "Costituiscono misure obbligatorie di prevenzione della corruzione: la rotazione del personale "
            "addetto alle aree a rischio; l'astensione in caso di conflitto di interesse; la tutela del "
            "dipendente che segnala illeciti (whistleblower); l'attività di formazione; la pubblicazione sul "
            "sito istituzionale dei dati relativi a procedimenti amministrativi."
        ),
        "art. 1 co. 41 — conflitto d'interessi": (
            "Il responsabile del procedimento e i titolari degli uffici competenti ad adottare i pareri, "
            "le valutazioni tecniche, gli atti endoprocedimentali e il provvedimento finale devono astenersi "
            "in caso di conflitto di interessi, segnalando ogni situazione di conflitto, anche potenziale, "
            "al responsabile dell'ufficio. L'attestazione di assenza di conflitto d'interessi è richiesta "
            "in ogni provvedimento di affidamento."
        ),
    },
    "dlgs_267_2000": {
        "art. 107 — competenze dirigenziali": (
            "Spetta ai dirigenti la direzione degli uffici e dei servizi secondo i criteri e le norme "
            "dettati dagli statuti e dai regolamenti, che si uniformano al principio per cui i poteri di "
            "indirizzo e di controllo politico-amministrativo spettano agli organi di governo mentre la "
            "gestione amministrativa, finanziaria e tecnica è attribuita ai dirigenti. I dirigenti adottano "
            "gli atti e i provvedimenti amministrativi, compresi tutti gli atti che impegnano "
            "l'amministrazione verso l'esterno, incluse le determinazioni dirigenziali di affidamento."
        ),
        "art. 192 — determinazione a contrarre": (
            "Prima di procedere all'espletamento delle gare o all'affidamento in economia di lavori, "
            "servizi e forniture, gli enti locali adottano apposita determinazione del responsabile del "
            "servizio con cui si determina di procedere alla stipula del contratto, il fine che con il "
            "contratto si intende perseguire, l'oggetto del contratto, la sua forma, le clausole ritenute "
            "essenziali, le modalità di scelta del contraente e le ragioni che ne sono alla base. "
            "La determinazione a contrarre è l'atto fondativo di ogni procedura di acquisto."
        ),
        "art. 183 — assunzione impegno di spesa": (
            "L'impegno costituisce la prima fase del procedimento di spesa, con la quale viene accertata la "
            "sussistenza della ragione del credito, determinata la somma da pagare, individuato il soggetto "
            "creditore, indicata la ragione e costituito il vincolo sulle previsioni di bilancio. "
            "Gli impegni di spesa sono assunti nei limiti dei rispettivi stanziamenti di competenza del "
            "bilancio di previsione. Non è possibile adottare la determinazione a contrarre senza "
            "contestuale impegno di spesa o attestazione di copertura finanziaria."
        ),
    },
    "dlgs_165_2001": {
        "art. 7 — gestione risorse e incarichi": (
            "Le amministrazioni pubbliche disciplinano e organizzano il lavoro, anche agile, dei propri "
            "dipendenti. Per esigenze cui non possono far fronte con personale in servizio, le "
            "amministrazioni pubbliche possono conferire incarichi individuali, con contratti di lavoro "
            "autonomo, ad esperti di particolare e comprovata specializzazione, a condizione che: "
            "l'oggetto della prestazione sia coerente con le missioni istituzionali; l'amministrazione "
            "abbia preliminarmente accertato l'impossibilità oggettiva di utilizzare risorse interne; "
            "la prestazione sia di natura temporanea e altamente qualificata."
        ),
        "art. 19 — incarichi dirigenziali": (
            "Per il conferimento di ciascun incarico di funzione dirigenziale si tiene conto, in relazione "
            "alla natura e alle caratteristiche degli obiettivi prefissati, delle attitudini e delle "
            "capacità professionali del singolo dirigente. Gli incarichi hanno durata da tre a cinque anni "
            "e sono conferiti con provvedimento motivato, previo accordo con l'interessato, da parte degli "
            "organi di vertice delle singole amministrazioni."
        ),
        "art. 36 — utilizzo flessibile": (
            "Per le esigenze connesse con il fabbisogno ordinario le pubbliche amministrazioni assumono "
            "esclusivamente con contratti di lavoro subordinato a tempo indeterminato. È consentito "
            "il ricorso a contratti flessibili (a termine, somministrazione) esclusivamente per esigenze "
            "temporanee e straordinarie, previa valutazione del fabbisogno e nel rispetto delle dotazioni "
            "organiche e dei vincoli finanziari."
        ),
    },
    "dlgs_196_2003": {
        "art. 13 GDPR — informativa": (
            "In caso di raccolta di dati personali presso l'interessato, il titolare del trattamento "
            "fornisce all'interessato, nel momento in cui i dati personali sono ottenuti, le seguenti "
            "informazioni: identità e dati di contatto del titolare; finalità e base giuridica del "
            "trattamento; destinatari dei dati; periodo di conservazione; diritti dell'interessato "
            "(accesso, rettifica, cancellazione, portabilità, opposizione). "
            "Per le PA, la base giuridica è generalmente il compito di interesse pubblico (art. 6.1.e GDPR)."
        ),
        "art. 28 GDPR — responsabile trattamento": (
            "Qualora un trattamento debba essere effettuato per conto del titolare del trattamento, "
            "quest'ultimo ricorre unicamente a responsabili del trattamento che presentino garanzie "
            "sufficienti. Il responsabile del trattamento (es. fornitore cloud, software house) è "
            "designato con apposito contratto o atto giuridico (DPA — Data Processing Agreement) che "
            "vincola il responsabile al titolare e ne definisce oggetto, durata, natura e finalità del "
            "trattamento. Il DPA è obbligatorio e deve essere allegato al contratto di fornitura."
        ),
        "art. 32 GDPR — sicurezza trattamento": (
            "Il titolare del trattamento e il responsabile del trattamento mettono in atto misure tecniche "
            "e organizzative adeguate per garantire un livello di sicurezza adeguato al rischio, tra cui, "
            "se del caso: la pseudonimizzazione e la cifratura dei dati personali; la capacità di "
            "assicurare la continua riservatezza, integrità, disponibilità e resilienza dei sistemi. "
            "Nel contesto degli acquisti PA, il fornitore deve dichiarare le misure di sicurezza adottate "
            "nella propria offerta tecnica o nell'allegato tecnico al contratto."
        ),
    },
    "dlgs_81_2008": {
        "art. 26 — obblighi connessi ai contratti d'appalto (DUVRI)": (
            "Il datore di lavoro, in caso di affidamento di lavori, servizi e forniture all'impresa "
            "appaltatrice o a lavoratori autonomi all'interno della propria azienda, promuove la "
            "cooperazione e il coordinamento. Nei contratti di appalto o d'opera o di somministrazione, "
            "viene elaborato un unico documento di valutazione dei rischi (DUVRI) che indica le misure "
            "adottate per eliminare i rischi da interferenze. Il DUVRI deve essere allegato al contratto "
            "di appalto o di opera e adeguato in funzione dell'evoluzione dei lavori."
        ),
        "art. 17 — obblighi non delegabili": (
            "Il datore di lavoro non può delegare le seguenti attività: la valutazione di tutti i rischi "
            "con la conseguente elaborazione del documento di valutazione dei rischi (DVR); la designazione "
            "del responsabile del servizio di prevenzione e protezione dai rischi (RSPP). "
            "Negli appalti, la stazione appaltante deve verificare che il fornitore abbia adempiuto agli "
            "obblighi di sicurezza non delegabili prima della stipula del contratto."
        ),
    },
    "dlgs_118_2011": {
        "art. 56 — principi contabili applicati": (
            "Le regioni e gli enti locali adottano la contabilità finanziaria, cui affiancano, ai fini "
            "conoscitivi, un sistema di contabilità economico-patrimoniale. I principi contabili applicati "
            "sono allegati al presente decreto e ne costituiscono parte integrante. Il principio della "
            "competenza finanziaria potenziata impone che le obbligazioni giuridiche attive e passive, "
            "perfezionate con l'ente, devono essere registrate nelle scritture contabili con imputazione "
            "all'esercizio in cui vengono a scadenza."
        ),
        "Allegato 4/2 — principio della competenza finanziaria": (
            "Le spese sono impegnate nell'esercizio in cui l'obbligazione giuridica è perfezionata, con "
            "imputazione all'esercizio in cui l'obbligazione viene a scadenza (esigibilità). Le spese per "
            "beni e servizi si imputano nell'esercizio di consegna del bene o di ultimazione del servizio. "
            "Le spese per investimenti si imputano in base al SAL (stato avanzamento lavori). "
            "Il mancato rispetto del principio di competenza finanziaria potenziata costituisce "
            "irregolarità contabile rilevabile dalla Corte dei conti."
        ),
    },
    "pnrr_missione1": {
        "Componente 1.1 — Infrastrutture digitali": (
            "La componente 1.1 del PNRR finanzia la migrazione delle PA verso infrastrutture cloud "
            "sicure e affidabili (Polo Strategico Nazionale — PSN) e il consolidamento dei data center. "
            "Gli enti che aderiscono devono rispettare le Misure Minime di Sicurezza ICT per le PA "
            "(Circolare AgID n. 2/2017) e le Linee Guida per la classificazione dei dati e dei servizi "
            "cloud. I contratti di migrazione cloud finanziati dal PNRR richiedono codice CUP e "
            "rendicontazione specifica verso il MEF."
        ),
        "Componente 1.2 — Abilitazione migrazione al cloud": (
            "La componente 1.2 supporta le PA nella qualificazione dei servizi cloud e nella migrazione "
            "delle applicazioni. I fornitori cloud devono essere qualificati AgID (categoria IaaS, PaaS, "
            "SaaS). L'acquisto di servizi cloud non qualificati AgID non è ammissibile come spesa PNRR. "
            "Le PA devono attestare il livello di maturità digitale prima e dopo la migrazione "
            "attraverso il DTM (Digital Transformation Management)."
        ),
    },
    "l_136_2010": {
        "art. 3 — obblighi di tracciabilità dei flussi finanziari": (
            "Al fine di assicurare la tracciabilità dei flussi finanziari finalizzata a prevenire "
            "infiltrazioni criminali, gli appaltatori, i subappaltatori e i subcontraenti della filiera "
            "delle imprese nonché i concessionari di finanziamenti pubblici anche europei a qualsiasi "
            "titolo interessati ai lavori, ai servizi e alle forniture pubblici devono utilizzare uno o "
            "più conti correnti bancari o postali dedicati, anche non in via esclusiva, alle commesse "
            "pubbliche. Tutti i movimenti finanziari relativi alle commesse pubbliche devono essere "
            "registrati su tali conti correnti dedicati."
        ),
        "art. 3 co. 5 — obbligo CIG e CUP": (
            "I pagamenti destinati a dipendenti, consulenti e fornitori di beni e servizi rientranti tra "
            "le spese generali nonché quelli destinati all'acquisto di immobilizzazioni tecniche devono "
            "essere eseguiti tramite conto corrente dedicato. Ai fini della tracciabilità dei flussi "
            "finanziari, il bonifico bancario o postale, ovvero gli altri strumenti di pagamento idonei "
            "a consentire la piena tracciabilità delle operazioni, devono riportare, in relazione a "
            "ciascuna transazione posta in essere dai soggetti di cui al comma 1, il CIG e, ove obbligatorio, il CUP."
        ),
        "art. 6 — sanzioni per violazione tracciabilità": (
            "La violazione, da parte dei soggetti di cui all'articolo 3, degli obblighi di tracciabilità "
            "dei flussi finanziari costituisce causa di risoluzione del contratto. Il mancato utilizzo del "
            "bonifico bancario o postale ovvero degli altri strumenti idonei a consentire la piena "
            "tracciabilità delle operazioni costituisce causa di risoluzione del contratto. "
            "L'Autorità Nazionale Anticorruzione (ANAC) è competente alla vigilanza sul rispetto "
            "degli obblighi di tracciabilità."
        ),
    },
}


# Importa il DB dal modulo search (lazy, per evitare doppia definizione)
def _get_db():
    try:
        from search import NORMATIVE_DB, NORME_BY_ID
        return NORMATIVE_DB, NORME_BY_ID
    except ImportError:
        return [], {}


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            norma_id = params.get("id", [""])[0].strip()

            if not norma_id:
                self._send_json({"error": "Parametro 'id' obbligatorio"}, 400)
                return

            _, NORME_BY_ID = _get_db()
            norma = NORME_BY_ID.get(norma_id)

            if not norma:
                self._send_json({"error": f"Norma '{norma_id}' non trovata"}, 404)
                return

            # Arricchisce con testi articoli
            articoli_con_testo = []
            testi_norma = ARTICOLI_TESTO.get(norma_id, {})
            for art in norma.get("articoli_chiave", []):
                articoli_con_testo.append({
                    "label": art,
                    "testo": testi_norma.get(art, ""),
                })

            result = {
                **norma,
                "articoli_dettaglio": articoli_con_testo,
            }
            self._send_json(result)

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
