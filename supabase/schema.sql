-- ============================================================
-- Normattiva — Schema Supabase
-- Embedding: Supabase AI built-in gte-small (384 dimensioni)
-- Esegui questo script UNA SOLA VOLTA nel SQL Editor di Supabase
-- ============================================================

-- 1. Abilita pgvector
create extension if not exists vector;

-- 2. Tabella principale
create table if not exists norme (
  id                uuid primary key default gen_random_uuid(),
  norma_id          text not null unique,
  titolo            text not null,
  estremi           text not null,
  descrizione       text not null,
  articoli_chiave   text[] default '{}',
  tags              text[] default '{}',
  url_normattiva    text,
  url_ricerca       text,
  convenzione_only  boolean default false,
  testo_vigente     text,
  testo_vigente_at  timestamptz,
  embedding         vector(384),
  creato_il         timestamptz default now(),
  aggiornato_il     timestamptz default now()
);

-- 3. Indice vettoriale cosine (ivfflat)
--    lists=10 è ottimale per < 1000 righe
create index if not exists norme_embedding_idx
  on norme using ivfflat (embedding vector_cosine_ops)
  with (lists = 10);

-- 4. Indice GIN su tags
create index if not exists norme_tags_gin_idx
  on norme using gin (tags);

-- 5. Indice su norma_id
create index if not exists norme_norma_id_idx
  on norme (norma_id);

-- 6. Tabella log query
create table if not exists query_log (
  id             uuid primary key default gen_random_uuid(),
  query_text     text,
  tipo_atto      text,
  oggetto        text,
  importo        text,
  convenzione    boolean default false,
  results_count  int,
  elapsed_ms     int,
  groq_used      boolean default false,
  creato_il      timestamptz default now()
);

-- 7. Funzione RPC ricerca vettoriale (384 dim)
create or replace function search_norme_by_embedding(
  query_embedding  vector(384),
  match_threshold  float default 0.55,
  match_count      int   default 12
)
returns table (
  norma_id          text,
  titolo            text,
  estremi           text,
  descrizione       text,
  articoli_chiave   text[],
  tags              text[],
  url_normattiva    text,
  url_ricerca       text,
  convenzione_only  boolean,
  testo_vigente     text,
  similarity        float
)
language sql stable
as $$
  select
    norma_id, titolo, estremi, descrizione,
    articoli_chiave, tags, url_normattiva, url_ricerca,
    convenzione_only, testo_vigente,
    1 - (embedding <=> query_embedding) as similarity
  from norme
  where embedding is not null
    and 1 - (embedding <=> query_embedding) > match_threshold
  order by embedding <=> query_embedding
  limit match_count;
$$;

-- 8. Trigger aggiornamento timestamp
create or replace function update_aggiornato_il()
returns trigger language plpgsql as $$
begin
  new.aggiornato_il = now();
  return new;
end;
$$;

drop trigger if exists norme_aggiornato_il on norme;
create trigger norme_aggiornato_il
  before update on norme
  for each row execute function update_aggiornato_il();

-- 9. Edge Function per embedding (deploy separato via Supabase CLI)
-- Vedi: supabase/functions/embed/index.ts
-- La funzione accetta POST { "input": "testo" } e restituisce { "embedding": [...] }
-- usando il modello gte-small integrato in Supabase AI.
