# Normattiva Search

Strumento di supporto per funzionari della Pubblica Amministrazione italiana. Permette di descrivere un'esigenza amministrativa e ottenere le norme applicabili con link diretti a [Normattiva.it](https://www.normattiva.it).

🔗 **Demo live:** [normattiva.vercel.app](https://normattiva.vercel.app)

---

## Funzionalità

- **Ricerca contestuale** per tipo atto, importo, oggetto e descrizione libera
- **Soglie procedurali automatiche** basate sul D.Lgs. 36/2023 (Codice dei contratti pubblici)
- **Modalità Convenzione/MEPA**: attiva norme specifiche sull'obbligo di utilizzo Consip/MEPA
- **Ricerca vettoriale Supabase**: embedding semantico (384 dimensioni) via Edge Function — risultati più precisi rispetto al solo matching per tag
- **Pipeline AI a 4 stadi** con Groq:
  - **Stadio 0 — Query Expansion**: Groq traduce la query in tag canonici per arricchire il matching
  - **Stadio 1 — Ricerca candidati**: Supabase vector search (primario) con fallback su tag engine locale
  - **Stadio 2 — AI Ranking**: Groq riordina i candidati e genera una motivazione specifica per ogni norma
  - **Stadio 3 — Discover**: Groq individua norme rilevanti non ancora nel DB e le persiste automaticamente in Supabase
- **Auto-espansione del DB normativo**: le norme scoperte dal Discover vengono inserite in Supabase con embedding e rese disponibili per le ricerche future
- **Validazione anti-allucinazione**: le norme generate da Groq vengono controllate contro il DB locale prima di essere salvate (blocco duplicati per ID e per numero+anno; normalizzazione automatica del tipo atto nell'URL normattiva.it)
- **Fetch testo vigente in parallelo**: recupero del testo degli articoli da normattiva.it in background (max 3 norme, timeout 3s, budget totale 4s)
- **Scheda dettaglio**: pannello slide-in con testo completo degli articoli chiave
- **Modalità debug**: `?debug=true` restituisce diagnostica completa (embed, RPC Supabase, env vars)
- **Dark mode** con toggle manuale e rispetto di `prefers-color-scheme`
- **Design responsive** ottimizzato per desktop e mobile

---

## Architettura

```
normattiva/
├── api/
│   ├── search.py              # GET /api/search — pipeline principale
│   ├── norma.py               # GET /api/norma?id=<id> — dettaglio singola norma
│   └── utils/
│       ├── __init__.py
│       ├── supabase_search.py    # Vector search, embedding, insert, log query
│       ├── groq_discover.py      # Discover norme mancanti + persist + validazione
│       ├── keywords.py           # Utility parole chiave (stub)
│       └── normattiva.py         # Utility URL normattiva (stub)
├── public/
│   └── index.html             # Frontend statico (HTML/CSS/JS inline)
├── supabase/
│   └── functions/
│       └── embed/               # Edge Function Supabase: genera embedding (384d)
├── scripts/                   # Script di utilità e seed
├── vercel.json               # Routing Vercel: /api/* → Python, /* → static
├── requirements.txt          # Dipendenze Python (nessuna esterna — solo stdlib)
└── README.md
```

### Flusso di una richiesta

```
Browser → GET /api/search?q=...&tipo_atto=...&importo=...&convenzione=...
              │
              ├─ Stadio 0: _groq_expand_query()
              │    └─ Groq → lista tag canonici (max 15)
              │
              ├─ Stadio 1: ricerca candidati
              │    ├─ supabase_vector_search()     [primario]
              │    │    ├─ get_embedding() → Edge Function Supabase (384d)
              │    │    └─ RPC search_norme_by_embedding() → top-N per similarità coseno
              │    └─ _tag_search()                [fallback se Supabase vuoto]
              │         ├─ match tipo_atto  → +2 per tag
              │         ├─ match importo    → +3 per tag soglia
              │         ├─ tag espansi Groq → +3 per tag
              │         ├─ token testuali   → +2 diretti, +1 semantici
              │         └─ boost convenzione → +4 per norme MEPA/Consip
              │
              ├─ Fetch testo vigente in parallelo (_fetch_norme_parallel)
              │    └─ ThreadPoolExecutor: max 3 norme, timeout 3s/norma, budget 4s totale
              │
              ├─ Stadio 2: _groq_rank()
              │    └─ Groq → ranking finale + motivazione per norma (omette non pertinenti)
              │
              ├─ filter_pertinent()
              │    └─ Rimuove risultati con ai_motivation negativa
              │
              └─ Stadio 3: discover_missing_norme() [sempre attivo se GROQ_API_KEY presente]
                   ├─ Groq individua norme mancanti (max 3)
                   ├─ _is_duplicate_of_local_db() → scarta duplicati
                   ├─ _normalize_url_normattiva() → corregge tipo atto nell'URN
                   ├─ get_embedding() + insert_norma_to_supabase()
                   └─ Aggiunge le norme nuove ai risultati (con deduplica per ID)
```

### Parametri interni configurabili (`api/search.py`)

| Costante | Valore | Descrizione |
|---|---|---|
| `GROQ_MAX_CANDIDATES` | `12` | Max norme passate a Groq per il ranking |
| `MIN_SCORE_FOR_GROQ` | `2` | Score minimo tag per entrare nel pool (fallback) |
| `SEMI_THRESHOLD` | `5.000 €` | Soglia affidamento diretto semplificato |
| `DIRECT_THRESHOLD` | `140.000 €` | Soglia affidamento diretto |
| `NEGO_THRESHOLD` | `215.000 €` | Soglia procedura negoziata |
| `K_FETCH_LIVE` | `3` | Numero massimo di norme per fetch testo vigente |
| `FETCH_TIMEOUT_PER_NORMA` | `3s` | Timeout per singola fetch normattiva.it |
| `FETCH_BUDGET_TOTAL` | `4s` | Budget totale per il fetch parallelo |

---

## Supabase

### Tabella `norme`

Contenuto indicizzato con vettore embedding (384 dimensioni). Ogni riga corrisponde a una norma con i campi: `id`, `titolo`, `estremi`, `descrizione`, `articoli_chiave`, `tags`, `url_normattiva`, `url_ricerca`, `embedding`.

### RPC `search_norme_by_embedding`

```sql
SELECT * FROM search_norme_by_embedding(
  query_embedding := '<vector 384d>',
  match_threshold := 0.3,
  match_count      := 5
);
```

Restituisce le norme ordinate per similarità coseno decrescente.

### Edge Function `embed`

Eseguita su Supabase Edge Runtime (Deno). Riceve `{ "input": "testo" }` e restituisce `{ "embedding": [float x 384] }`. È usata sia per la ricerca (query embedding) sia per l'inserimento di nuove norme (discover embedding).

### Tabella `query_logs`

Logga ogni richiesta con: `query_text`, `tipo_atto`, `oggetto`, `importo`, `convenzione`, `results_count`, `elapsed_ms`, `groq_used`, `created_at`.

### Variabili d'ambiente Supabase

| Variabile | Descrizione |
|---|---|
| `SUPABASE_URL` | URL del progetto Supabase |
| `SUPABASE_KEY` | Service role key (o anon key con policy adeguate) |

---

## Soglie procedurali (D.Lgs. 36/2023)

| Importo | Procedura | Articolo |
|---|---|---|
| < 5.000 € | Affidamento diretto semplificato | art. 50 co. 1 |
| 5.000 € – 140.000 € | Affidamento diretto | art. 50 |
| 140.000 € – 215.000 € | Procedura negoziata | art. 72 |
| > 215.000 € | Procedura aperta | art. 71 |

---

## Database normativo locale

Il DB locale è embedded in `api/search.py` (19 norme) ed è la base per il tag engine di fallback e per la validazione anti-duplicati del Discover. Le norme aggiuntive scoperte da Groq vengono salvate **solo in Supabase** e non nel DB locale.

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
| `debug` | `true`/`false` | ❌ | Aggiunge `_diagnostics` alla risposta (embed, RPC, env vars) |

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
  "search_source": "supabase",
  "ai_active": true,
  "new_norme_added": [],
  "results": [
    {
      "id": "dlgs_36_2023",
      "titolo": "Codice dei contratti pubblici",
      "estremi": "D.Lgs. 31 marzo 2023, n. 36",
      "descrizione": "...",
      "articoli_chiave": ["art. 50 — affidamento diretto"],
      "tags": ["acquisto", "appalto"],
      "url_normattiva": "https://www.normattiva.it/...",
      "url_ricerca": "https://www.normattiva.it/...",
      "score": 100,
      "similarity": 0.923,
      "ai_motivation": "...",
      "text_vigente_disponibile": false
    }
  ],
  "elapsed_ms": 4821
}
```

**Campo `search_source`:** `"supabase"` se la ricerca vettoriale ha restituito risultati, `"tag_fallback"` se Supabase non era raggiungibile o non aveva risultati.

**Campo `new_norme_added`:** lista degli ID delle norme scoperte dal Discover e aggiunte alla risposta (non erano presenti nei risultati iniziali).

### `GET /api/search?debug=true`

Restituisce il campo aggiuntivo `_diagnostics`:

```json
"_diagnostics": {
  "supabase_url_set": true,
  "supabase_key_set": true,
  "groq_key_set": true,
  "supabase_url_prefix": "https://xxxx.supabase.co",
  "embed_status": 200,
  "embed_dim": 384,
  "embed_ok": true,
  "rpc_status": 200,
  "rpc_results_count": 3,
  "rpc_ok": true
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
git clone https://github.com/enricobrunazzo/normattiva.git
cd normattiva
npm i -g vercel
vercel
```

### Variabili d'ambiente

Nel pannello **Settings → Environment Variables** del progetto Vercel:

| Variabile | Ambiente | Descrizione |
|---|---|---|
| `GROQ_API_KEY` | Production, Preview | API key Groq (da [console.groq.com](https://console.groq.com)) |
| `SUPABASE_URL` | Production, Preview | URL progetto Supabase (es. `https://xxxx.supabase.co`) |
| `SUPABASE_KEY` | Production, Preview | Service role key Supabase |

> **⚠️ IMPORTANTE — Redeploy dopo aver aggiunto variabili d'ambiente**
>
> Il pulsante "Redeploy" nella dashboard Vercel riusa il **build cacheato** e non include le variabili aggiunte dopo quel build. Per forzare un build fresco:
>
> ```bash
> vercel --prod
> ```
>
> Oppure da dashboard: **Deployments → ⋯ → Redeploy → DESELEZIONA "Use existing Build Cache"**
>
> Il corretto funzionamento è verificabile dai **Runtime Logs**:
> - `[INIT] GROQ_API_KEY present: True`
> - `[SEARCH] source=supabase | candidates=N`
> - `[DISCOVER] norme scoperte da Groq: N`
>
> Se la funzione risponde in < 200ms con `search_source: tag_fallback`, Supabase non è configurato correttamente.

### Deploy successivi

```bash
# Push su main → deploy automatico (se Git integration attiva)
git push

# Oppure deploy manuale
vercel --prod
```

---

## Sviluppo locale

```bash
npm i -g vercel
vercel dev
```

Variabili d'ambiente nel file `.env.local` (non committare):

```bash
# .env.local
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Stack tecnico

| Layer | Tecnologia |
|---|---|
| Frontend | HTML/CSS/JS vanilla (nessun framework) |
| Backend | Python 3.x — stdlib pura (`http.server`, `urllib`, `json`, `re`) |
| AI | Groq API — modelli `openai/gpt-oss-20b` (expand) e `openai/gpt-oss-120b` (rank/discover) |
| Vector DB | Supabase (pgvector) + Edge Function embed (Deno) |
| Hosting | Vercel (Serverless Functions + Static) |
| Dipendenze Python | nessuna (zero `pip install`) |

---

## Log di riferimento (Vercel Runtime Logs)

| Log | Significato |
|---|---|
| `[INIT] GROQ_API_KEY present: True` | Groq configurato correttamente |
| `[SEARCH] source=supabase \| candidates=N` | Ricerca vettoriale attiva |
| `[SEARCH] source=tag_fallback \| candidates=N` | Supabase non raggiungibile o vuoto |
| `[GROQ EXPAND] tags=[...]` | Tag espansi dalla query |
| `[GROQ RANK] reranked=N norme pertinenti` | Ranking completato |
| `[FILTER] Escluso 'id': motivazione non pertinente` | Norma rimossa dal filter_pertinent |
| `[DISCOVER] norme scoperte da Groq: N` | Discover attivato |
| `[PERSIST] 'id' è duplicato del DB locale, skip` | Validazione anti-allucinazione attiva |
| `[PERSIST] URL corretto: '...' -> '...'` | Normalizzazione URL tipo atto |
| `[PERSIST] 'id' inserita in Supabase` | Nuova norma salvata nel vector DB |
| `[NORMATTV_PARALLEL] done \| hits=N \| elapsed=X.Xs` | Fetch testo vigente completato |

---

## Note legali

Strumento di supporto per funzionari PA — **non costituisce parere legale**. Le norme restituite sono indicative; verificare sempre la versione vigente e la giurisprudenza applicabile su [Normattiva.it](https://www.normattiva.it). Dati normativi aggiornati a maggio 2026.
