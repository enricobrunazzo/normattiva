-- ============================================================
-- Normattiva — Schema Supabase
-- Esegui questo script una volta sola nel SQL Editor di Supabase
-- ============================================================

-- Abilita l'estensione pgvector (necessaria per la ricerca semantica)
create extension if not exists vector;

-- ── Tabella principale delle norme ───────────────────────────────────────────
create table if not exists norme (
  id            uuid primary key default gen_random_uuid(),
  norma_id      text not null unique,          -- es. "dlgs_36_2023"
  titolo        text not null,
  estremi       text not null,
  descrizione   text not null,
  articoli_chiave text[] default '{}',
  tags          text[] default '{}',
  url_normattiva text,
  url_ricerca   text,
  convenzione_only boolean default false,
  testo_vigente text,                          -- testo scraping Normattiva (aggiornabile)
  testo_vigente_at timestamptz,               -- quando è stato aggiornato l'ultima volta
  embedding     vector(1536),                 -- embedding del testo (descrizione + testo_vigente)
  creato_il     timestamptz default now(),
  aggiornato_il timestamptz default now()
);

-- ── Indice vettoriale (cosine similarity) ────────────────────────────────────
create index if not exists norme_embedding_idx
  on norme using ivfflat (embedding vector_cosine_ops)
  with (lists = 50);

-- ── Indice su tags (array GIN) ────────────────────────────────────────────────
create index if not exists norme_tags_gin_idx
  on norme using gin (tags);

-- ── Indice su norma_id ───────────────────────────────────────────────────────
create index if not exists norme_norma_id_idx
  on norme (norma_id);

-- ── Tabella log delle query (per analytics e debug) ─────────────────────────
create table if not exists query_log (
  id            uuid primary key default gen_random_uuid(),
  query_text    text,
  tipo_atto     text,
  oggetto       text,
  importo       text,
  convenzione   boolean default false,
  results_count int,
  elapsed_ms    int,
  groq_used     boolean default false,
  creato_il     timestamptz default now()
);

-- ── Funzione RPC per ricerca vettoriale ──────────────────────────────────────
create or replace function search_norme_by_embedding(
  query_embedding vector(1536),
  match_threshold float default 0.65,
  match_count     int   default 10
)
returns table (
  norma_id      text,
  titolo        text,
  estremi       text,
  descrizione   text,
  articoli_chiave text[],
  tags          text[],
  url_normattiva text,
  url_ricerca   text,
  convenzione_only boolean,
  testo_vigente text,
  similarity    float
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

-- ── Trigger aggiornamento timestamp ──────────────────────────────────────────
create or replace function update_aggiornato_il()
returns trigger language plpgsql as $$
begin
  new.aggiornato_il = now();
  return new;
end;
$$;

create trigger norme_aggiornato_il
  before update on norme
  for each row execute function update_aggiornato_il();
