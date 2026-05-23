# Normattiva Search

Strumento di supporto per funzionari della Pubblica Amministrazione italiana. Permette di descrivere un'esigenza amministrativa e ottenere le norme applicabili con link diretti a [Normattiva.it](https://www.normattiva.it).

🔗 **Demo live:** [normattiva.vercel.app](https://normattiva.vercel.app)

---

## Funzionalità

- **Ricerca contestuale** per tipo atto, importo, oggetto e descrizione libera
- **Soglie procedurali automatiche** basate sul D.Lgs. 36/2023 (Codice dei contratti pubblici)
- **Modalità Convenzione/MEPA**: attiva norme specifiche sull'obbligo di utilizzo Consip/MEPA
- **Pipeline AI a tre stadi** con Groq (Llama 3.3 70B):
  - **Stadio 0 — Query Expansion**: Groq traduce la query in tag canonici del sistema per arricchire il matching semantico
  - **Stadio 1 — Tag Engine**: pre-filtro locale che assegna score basato su tipo atto, importo, token testuali e tag espansi
  - **Stadio 2 — AI Ranking**: Groq riordina i candidati e genera una motivazione specifica per ogni norma
- **Scheda dettaglio**: pannello slide-in con testo completo degli articoli chiave
- **Dark mode** con toggle manuale e rispetto di `prefers-color-scheme`
- **Design responsive** ottimizzato per desktop e mobile

---

## Architettura

```
normattiva/
├── api/
│   ├── search.py          # GET /api/search — pipeline principale (tag engine + Groq)
│   ├── norma.py           # GET /api/norma?id=<id> — dettaglio singola norma
│   └── utils/
│       ├── __init__.py
│       ├── keywords.py    # utility parole chiave (stub)
│       └── normattiva.py  # utility URL normattiva (stub)
├── public/
│   └── index.html         # Frontend statico (HTML/CSS/JS inline)
├── vercel.json            # Routing Vercel: /api/* → Python, /* → static
├── requirements.txt       # Dipendenze Python (nessuna esterna — solo stdlib)
└── README.md
```

### Flusso di una richiesta

```
Browser → GET /api/search?q=...&tipo_atto=...&importo=...&convenzione=...
              │
              ├─ Stadio 0: _groq_expand_query()
              │    └─ Groq (Llama 3.3 70B) → lista tag canonici (max 15)
              │
              ├─ Stadio 1: _tag_search()
              │    ├─ match tipo_atto  → +2 per tag
              │    ├─ match importo    → +3 per tag soglia
              │    ├─ tag espansi Groq → +3 per tag
              │    ├─ token testuali   → +2 diretti, +1 semantici
              │    └─ boost convenzione → +4 per norme MEPA/Consip
              │
              └─ Stadio 2: _groq_rank()
                   └─ Groq (Llama 3.3 70B) → ranking finale + motivazione per norma
```

### Parametri interni configurabili (`api/search.py`)

| Costante | Valore | Descrizione |
|---|---|---|
| `GROQ_MAX_CANDIDATES` | `12` | Max norme passate a Groq per il ranking |
| `MIN_SCORE_FOR_GROQ` | `2` | Score minimo tag per entrare nel pool |
| `SEMI_THRESHOLD` | `5.000 €` | Soglia affidamento diretto semplificato |
| `DIRECT_THRESHOLD` | `140.000 €` | Soglia affidamento diretto |
| `NEGO_THRESHOLD` | `215.000 €` | Soglia procedura negoziata |

---

## Soglie procedurali (D.Lgs. 36/2023)

| Importo | Procedura | Articolo |
|---|---|---|
| < 5.000 € | Affidamento diretto semplificato | art. 50 co. 1 |
| 5.000 € – 140.000 € | Affidamento diretto | art. 50 |
| 140.000 € – 215.000 € | Procedura negoziata | art. 72 |
| > 215.000 € | Procedura aperta | art. 71 |

---

## Database normativo

Il database è embedded in `api/search.py` (nessun database esterno). Contiene 19 norme al 23 maggio 2026:

| ID | Estremi | Area tematica principale |
|---|---|---|
| `dlgs_36_2023` | D.Lgs. 36/2023 | Codice contratti pubblici (nuovo) |
| `dlgs_50_2016` | D.Lgs. 50/2016 | Codice contratti pubblici (previgente) |
| `dlgs_82_2005` | D.Lgs. 82/2005 | CAD — Codice Amministrazione Digitale |
| `dlgs_33_2013` | D.Lgs. 33/2013 | Trasparenza e accesso civico (FOIA) |
| `l_190_2012` | L. 190/2012 | Anticorruzione e PTPCT |
| `l_241_1990` | L. 241/1990 | Procedimento amministrativo |
| `dlgs_267_2000` | D.Lgs. 267/2000 | TUEL — Enti locali |
| `dlgs_165_2001` | D.Lgs. 165/2001 | TUPI — Pubblico impiego |
| `dlgs_196_2003` | D.Lgs. 196/2003 + GDPR | Privacy e trattamento dati |
| `dlgs_81_2008` | D.Lgs. 81/2008 | Sicurezza sul lavoro / DUVRI |
| `dlgs_118_2011` | D.Lgs. 118/2011 | Armonizzazione contabile enti locali |
| `l_136_2010` | L. 136/2010 | Tracciabilità flussi finanziari (CIG/CUP) |
| `l_296_2006_consip` | L. 296/2006 art. 1 co. 449-450 | Obbligo Consip/MEPA |
| `pnrr_missione1` | PNRR Missione 1 | Digitalizzazione PA |
| `circ_agid_cloud_2021` | Circ. AgID + Det. 628/2021 + ACN 2022 | Qualificazione cloud PA |
| `dlgs_231_2001` | D.Lgs. 231/2001 | Responsabilità amministrativa enti |
| `l_328_2000` | L. 328/2000 | Servizi sociali integrati |
| `dpcm_159_2013` | D.P.C.M. 159/2013 | Regolamento ISEE |
| `l_104_1992` | L. 104/1992 | Assistenza e disabilità |

---

## API

### `GET /api/search`

Ricerca norme applicabili con ranking AI.

**Parametri query string:**

| Parametro | Tipo | Obbligatorio | Descrizione |
|---|---|---|---|
| `q` | string | ✅ | Descrizione libera dell'esigenza |
| `tipo_atto` | string | ❌ | `determina`, `delibera`, `ordinanza`, `decreto`, `contratto` |
| `oggetto` | string | ❌ | Oggetto sintetico dell'atto |
| `importo` | string | ❌ | Importo in euro (es. `12000` o `12.000`) |
| `convenzione` | `true`/`false` | ❌ | Adesione a convenzione Consip / ordine MEPA |

**Esempio:**
```
GET /api/search?q=acquisto+licenze+software+gestionale&tipo_atto=determina&importo=25000
```

**Risposta:**
```json
{
  "query": "acquisto licenze software gestionale",
  "tipo_atto": "determina",
  "oggetto": "",
  "importo_label": "€25.000 — Affidamento diretto (art. 50, D.Lgs. 36/2023)",
  "convenzione": false,
  "results": [
    {
      "id": "dlgs_36_2023",
      "titolo": "Codice dei contratti pubblici",
      "estremi": "D.Lgs. 31 marzo 2023, n. 36",
      "descrizione": "...",
      "articoli_chiave": ["art. 50 — affidamento diretto", "..."],
      "tags": ["acquisto", "appalto", "..."],
      "url_normattiva": "https://www.normattiva.it/...",
      "url_ricerca": "https://www.normattiva.it/...",
      "score": 100,
      "ai_motivation": "L'affidamento diretto di €25.000 per licenze software rientra nella soglia..."
    }
  ],
  "elapsed_ms": 1842
}
```

### `GET /api/norma?id=<id>`

Restituisce il dettaglio di una norma con il testo degli articoli chiave.

**Esempio:**
```
GET /api/norma?id=dlgs_36_2023
```

---

## Deploy su Vercel

### Setup iniziale

```bash
# Clona il repository
git clone https://github.com/enricobrunazzo/normattiva.git
cd normattiva

# Installa la CLI Vercel
npm i -g vercel

# Deploy (primo deploy — crea il progetto)
vercel
```

### Variabili d'ambiente

Nel pannello **Settings → Environment Variables** del progetto Vercel, aggiungi:

| Variabile | Ambiente | Descrizione |
|---|---|---|
| `GROQ_API_KEY` | Production, Preview | API key Groq (da [console.groq.com](https://console.groq.com)) |

> **⚠️ IMPORTANTE — Redeploy dopo aver aggiunto variabili d'ambiente**
>
> Il pulsante "Redeploy" nella dashboard Vercel riusa il **build cacheato** e non include le variabili aggiunte dopo quel build. Per forzare un build fresco con le nuove variabili:
>
> ```bash
> # Opzione 1 — CLI (raccomandato)
> vercel --prod
> ```
>
> ```
> Opzione 2 — Dashboard
> Deployments → ⋯ → Redeploy → DESELEZIONA "Use existing Build Cache"
> ```
>
> Il corretto funzionamento di Groq è verificabile dai **Runtime Logs**: deve comparire
> `[INIT] GROQ_API_KEY present: True` e le request devono durare > 1 secondo.
> Se la funzione risponde in < 100ms, Groq non viene chiamato.

### Deploy successivi

```bash
# Push su main → deploy automatico (se Git integration attiva)
git push

# Oppure deploy manuale via CLI
vercel --prod
```

---

## Sviluppo locale

```bash
# Installa la CLI Vercel (include il runtime Python locale)
npm i -g vercel

# Avvia il dev server (porta 3000)
vercel dev
```

Il dev server emula l'ambiente Vercel localmente, incluse le serverless functions Python.
Le variabili d'ambiente vengono lette dal file `.env.local` (non committare mai questo file):

```bash
# .env.local
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx
```

---

## Stack tecnico

| Layer | Tecnologia |
|---|---|
| Frontend | HTML/CSS/JS vanilla (nessun framework) |
| Backend | Python 3.x — stdlib pura (`http.server`, `urllib`, `json`, `re`) |
| AI | Groq API — modello `llama-3.3-70b-versatile` |
| Hosting | Vercel (Serverless Functions + Static) |
| Dipendenze Python | nessuna (zero `pip install`) |

---

## Note legali

Strumento di supporto per funzionari PA — **non costituisce parere legale**. Le norme restituite sono indicative; verificare sempre la versione vigente e la giurisprudenza applicabile su [Normattiva.it](https://www.normattiva.it). Dati normativi aggiornati a maggio 2026.
