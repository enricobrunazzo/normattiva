# Supabase — Setup Normattiva

## 1. Crea il progetto Supabase

1. Vai su [supabase.com](https://supabase.com) → crea un nuovo progetto free
2. Nota **Project URL** e **service_role key** (Settings → API)

## 2. Esegui lo schema

Nel **SQL Editor** di Supabase, incolla ed esegui il contenuto di `schema.sql`.

Verifica che l'estensione `vector` sia abilitata:
```sql
select * from pg_extension where extname = 'vector';
```

## 3. Configura le variabili d'ambiente

### Locale (per lo script di ingestione)
```bash
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_KEY=eyJ...  # service_role key
export GROQ_API_KEY=gsk_...
```

### Su Vercel
In **Settings → Environment Variables** aggiungi:
- `SUPABASE_URL`
- `SUPABASE_KEY` (usa la `anon` key per Vercel, la `service_role` solo per lo script locale)

## 4. Popola il DB (una volta sola)

```bash
pip install supabase
python scripts/ingest_norme.py
```

Per testare senza scrivere:
```bash
python scripts/ingest_norme.py --dry-run
```

## 5. Come funziona la ricerca

```
Query utente
  │
  ├─► Groq embedding (nomic-embed-text)
  │
  ├─► Supabase vector search (cosine similarity)
  │     └── fallback: motore tag locale se Supabase non risponde
  │
  └─► Groq ranking + motivazione (solo top candidati)
```

## 6. Struttura tabelle

| Tabella | Descrizione |
|---|---|
| `norme` | Tutte le norme con embedding vettoriale |
| `query_log` | Log delle query per analytics |

## 7. Aggiornare una norma

Ri-esegui l'ingest su una norma specifica modificando `NORMATIVE_DB` in `api/search.py`
e poi:
```bash
python scripts/ingest_norme.py
```
L'upsert su `norma_id` garantisce idempotenza.
