# Backup progetto Supabase "Normattiva"

Backup completo del progetto Supabase **Normattiva** (ref `gjuycxhgcoexeovlsvvq`, regione `eu-west-1`), esportato il **12/07/2026** prima della chiusura del progetto per liberare uno slot del piano free.

## Contenuto

| File | Descrizione |
|---|---|
| `schema.sql` | DDL completo: estensioni (`vector`, `uuid-ossp`, `pgcrypto`), tabelle `norme` e `query_log`, indici (incluso ivfflat per ricerca vettoriale), RLS, funzioni SQL (`search_norme_by_embedding`, `update_norma_embedding`, `update_aggiornato_il`) e trigger |
| `data/norme.sql` | 45 righe della tabella `norme` come INSERT, **embedding inclusi** (gte-small, 384 dimensioni) |
| `data/norme.json` | Stesse 45 righe in formato JSON |
| `data/query_log.json` | 94 righe del log query (usage log, solo a scopo storico) |
| `functions/embed/index.ts` | Edge Function `embed` (verify_jwt: true): genera embedding con `Supabase.ai` modello **gte-small** |

## Stato del progetto al momento del backup

- Nessun utente in `auth.users`, nessun bucket Storage, nessuna migrazione registrata
- RLS abilitata su entrambe le tabelle **senza policy** (accesso solo via service role / API server-side)
- Tabella `norme`: 45 norme catalogate (appalti, PA digitale, ISEE, urbanistica…) con embedding; campo `testo_vigente` mai valorizzato

## Ripristino su un nuovo progetto Supabase

1. SQL Editor → esegui `schema.sql`
2. SQL Editor → esegui `data/norme.sql`
3. Edge function: `supabase functions deploy embed` con il sorgente in `functions/embed/`
4. (Opzionale) reimporta `data/query_log.json`

Gli embedding sono inclusi nel backup, quindi la ricerca semantica (`search_norme_by_embedding`) funziona subito dopo il ripristino, senza dover rigenerare nulla.
