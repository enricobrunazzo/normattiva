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
            "essenziali, le modalità di scelta del contraente e le ragioni che ne sono alla base."
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

        # Import lazy del DB dalla cartella api/
        try:
            from api.search import NORME_BY_ID
        except ImportError:
            from search import NORME_BY_ID  # type: ignore

        norma = NORME_BY_ID.get(norma_id)
        if not norma:
            self._send_error(404, f"Norma '{norma_id}' non trovata")
            return

        result = norma.copy()
        result["articoli_testo"] = ARTICOLI_TESTO.get(norma_id, {})

        body = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
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


# Alias top-level esplicito richiesto dal parser statico di Vercel CLI 54+
handler = handler
