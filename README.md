# 🏗️ Normattiva Search

App di ricerca normativa assistita per la Pubblica Amministrazione italiana.

Inserisci un'esigenza amministrativa in linguaggio naturale (es. *"devo acquistare un software gestionale per un Comune, importo 50.000 euro"*) e l'app individua automaticamente le norme di riferimento da [Normattiva](https://www.normattiva.it), con ranking AI e motivazione specifica per ogni risultato.

🔗 **Live demo:** [normattiva.vercel.app](https://normattiva.vercel.app)

---

## Stack tecnico

| Layer | Tecnologia |
|---|---|
| **Frontend** | HTML / CSS / Vanilla JS (zero dipendenze) |
| **Backend** | Python serverless — `api/search.py` (Vercel Functions) |
| **AI ranking** | [Groq](https://console.groq.com) — Llama 3.3 70B (free tier) |
| **Motore tag** | Pre-filtro semantico interno (stdlib Python, zero latenza) |
| **Fonte normativa** | [Normattiva](https://www.normattiva.it) — link diretti agli articoli |
| **Hosting** | [Vercel Hobby](https://vercel.com) (gratuito) |

---

## Come funziona

### Pipeline a due stadi

```
Input utente (testo, tipo atto, importo, oggetto)
        ↓
 [Stadio 1] Motore tag-based
   • Analisi tipo atto  → TIPO_ATTO_TAGS
   • Analisi importo    → soglie D.Lgs. 36/2023
   • Analisi semantica  → SEMANTIC_MAP + TAG_INDEX
   • Output: lista candidati ordinati per score (min. score: 2)
        ↓
 [Stadio 2] Groq AI ranking (Llama 3.3 70B)
   • Riceve fino a 12 norme candidate (GROQ_MAX_CANDIDATES = 12)
   • Le riordina per rilevanza rispetto al caso specifico
   • Aggiunge motivazione contestuale (1-2 frasi) per ciascuna
   • Fallback silenzioso: se GROQ_API_KEY assente, usa solo lo stadio 1
        ↓
 Risultati con link Normattiva + etichetta importo + motivazione AI
```

### Soglie D.Lgs. 36/2023 applicate automaticamente

| Importo | Procedura | Articolo |
|---|---|---|
| ≤ €5.000 | Affidamento diretto semplificato | art. 50 co. 1 |
| ≤ €140.000 | Affidamento diretto | art. 50 |
| ≤ €215.000 | Procedura negoziata | art. 72 |
| > €215.000 | Procedura aperta | art. 71 |

### Modalità Convenzione / MEPA

Attivando il flag **Convenzione Consip / MEPA**, il motore modifica il ranking privilegiando le norme su tracciabilità (L. 136/2010), trasparenza (D.Lgs. 33/2013) e TUEL (D.Lgs. 267/2000) rispetto a quelle sulle procedure di gara autonome.

---

## Database normativo

17 norme attualmente indicizzate:

| ID | Norma | Tag principali |
|---|---|---|
| `dlgs_36_2023` | Codice dei contratti pubblici | acquisto, appalto, gara, CIG, RUP |
| `dlgs_82_2005` | CAD — Codice Amministrazione Digitale | software, cloud, ICT, AgID |
| `dlgs_33_2013` | Trasparenza e accesso civico | trasparenza, determina, FOIA |
| `l_190_2012` | Legge Anticorruzione | anticorruzione, conflitto interessi |
| `dlgs_267_2000` | TUEL | comune, delibera, determina, bilancio |
| `dlgs_165_2001` | TUPI — Pubblico Impiego | personale, consulenza, incarico |
| `dlgs_196_2003` | Codice Privacy + GDPR | privacy, dati, software, cloud |
| `dlgs_81_2008` | T.U. Sicurezza sul Lavoro | sicurezza, DUVRI, appalto |
| `dlgs_118_2011` | Armonizzazione contabile enti locali | bilancio, competenza finanziaria |
| `pnrr_missione1` | PNRR — Missione 1 Digitalizzazione | cloud, AgID, transizione digitale |
| `l_136_2010` | Tracciabilità flussi finanziari | CIG, CUP, tracciabilità |
| `l_241_1990` | Legge sul procedimento amministrativo | motivazione, accesso atti, provvedimento |
| `dlgs_50_2016` | Codice contratti pubblici 2016 (previgente) | proroga, appalto storico, collaudo |
| `l_296_2006_consip` | Obbligo Consip / MEPA (L. Finanziaria 2007) | MEPA, Consip, benchmark, convenzione |
| `dlgs_231_2001` | Responsabilità amministrativa degli enti | MOG, corruzione, fornitore |
| `circ_agid_cloud_2021` | Qualificazione cloud PA — AgID / ACN | cloud qualificato, SaaS, marketplace PA |
| `l_328_2000` + `dpcm_159_2013` + `l_104_1992` | Servizi sociali, ISEE, disabilità | servizi sociali, ISEE, RSA, retta, disabili |

---

## Struttura del progetto

```
normattiva/
├── public/
│   └── index.html          # Interfaccia utente (SPA, zero framework)
├── api/
│   └── search.py           # Serverless function: tag engine + Groq ranking
├── vercel.json             # Routing Vercel (api/* → Python, resto → static)
├── requirements.txt        # Vuoto: solo stdlib Python (urllib, json, os)
└── README.md
```

> **Nessuna dipendenza esterna.** Il backend usa esclusivamente la standard library Python.
> Le chiamate a Groq avvengono tramite `urllib.request` nativo.

---

## Deploy su Vercel

```bash
# 1. Clona il repo
git clone https://github.com/enricobrunazzo/normattiva.git
cd normattiva

# 2. Installa Vercel CLI (se non presente)
npm i -g vercel

# 3. Deploy
vercel --prod
```

### Variabile d'ambiente obbligatoria

Nel pannello Vercel → **Settings → Environment Variables**:

```
GROQ_API_KEY=gsk_...
```

> ⚠️ **Importante:** dopo aver aggiunto o modificato la variabile, effettua sempre
> un nuovo deploy con `vercel --prod` (o un Redeploy dalla dashboard **senza**
> spuntare "Use existing Build Cache"). Il semplice Redeploy da cache non aggiorna
> le variabili d'ambiente nelle serverless functions.

**Groq free tier:** 14.400 token/minuto, nessuna carta di credito richiesta.
Registrati su [console.groq.com](https://console.groq.com) e genera una API key gratuita.

---

## Sviluppo locale

```bash
# Nessuna installazione Python necessaria

# Imposta la chiave Groq
export GROQ_API_KEY=gsk_...

# Avvia Vercel dev server (emula le serverless functions in locale)
vercel dev
```

L'app sarà disponibile su `http://localhost:3000`.

---

## Architettura variabili d'ambiente su Vercel

Le env vars nelle **serverless functions Python** di Vercel sono disponibili a runtime (non solo a build time). Tuttavia:

- Un **Redeploy da cache** (`vercel redeploy --reuse-build`) riusa il bundle già compilato e **non aggiorna** le variabili nel contesto di esecuzione
- Un **nuovo build** (`vercel --prod` da CLI o push su branch) preleva sempre le variabili aggiornate
- Il log `[INIT] GROQ_API_KEY present: True` nei Runtime Logs di Vercel conferma il corretto caricamento

---

## Roadmap

- [x] Struttura base progetto
- [x] Frontend SPA — form input esigenza
- [x] Motore tag-based con mappa semantica (SEMANTIC_MAP + TAG_INDEX)
- [x] Ranking AI con Groq / Llama 3.3 70B
- [x] Motivazione AI contestuale per ogni norma
- [x] Soglie automatiche D.Lgs. 36/2023
- [x] Modalità Convenzione Consip / MEPA con boost norme dedicate
- [x] Log diagnostici runtime (`[INIT]`, `[GROQ]`, `[REQUEST]`)
- [x] Copertura AI su tutte le norme del DB (GROQ_MAX_CANDIDATES = 12)
- [x] Espansione database: L. 241/1990, D.Lgs. 50/2016, L. 296/2006, D.Lgs. 231/2001, AgID cloud, servizi sociali (L. 328/2000, DPCM 159/2013, L. 104/1992)
- [ ] Scheda dettaglio norma con testo degli articoli chiave
- [ ] Integrazione dati.normattiva.it open data API
- [ ] Storico ricerche (localStorage)
- [ ] Export PDF/Word delle norme trovate

---

## Licenza

I dati normativi sono tratti da [Normattiva](https://www.normattiva.it), disponibili con licenza [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) dal 1° gennaio 2026.
Il codice sorgente del progetto è rilasciato sotto licenza MIT.
