-- Backup schema progetto Supabase "Normattiva" (ref: gjuycxhgcoexeovlsvvq, eu-west-1)
-- Esportato il 2026-07-12 prima della chiusura del progetto.
-- Ripristino: eseguire questo file su un database Postgres/Supabase,
-- poi data/norme.sql e (opzionale) importare data/query_log.json.

create extension if not exists "uuid-ossp";
create extension if not exists pgcrypto;
create extension if not exists vector;

-- ============================================================
-- TABELLE
-- ============================================================

create table public.norme (
  id uuid primary key default gen_random_uuid(),
  norma_id text not null unique,
  titolo text not null,
  estremi text not null,
  descrizione text not null,
  articoli_chiave text[] default '{}'::text[],
  tags text[] default '{}'::text[],
  url_normattiva text,
  url_ricerca text,
  convenzione_only boolean default false,
  testo_vigente text,
  testo_vigente_at timestamptz,
  embedding vector(384), -- gte-small (Supabase.ai), vettori normalizzati
  creato_il timestamptz default now(),
  aggiornato_il timestamptz default now()
);

create table public.query_log (
  id uuid primary key default gen_random_uuid(),
  query_text text,
  tipo_atto text,
  oggetto text,
  importo text,
  convenzione boolean default false,
  results_count integer,
  elapsed_ms integer,
  groq_used boolean default false,
  creato_il timestamptz default now()
);

-- ============================================================
-- INDICI
-- ============================================================

create index norme_norma_id_idx on public.norme using btree (norma_id);
create index norme_tags_gin_idx on public.norme using gin (tags);
create index norme_embedding_idx on public.norme
  using ivfflat (embedding vector_cosine_ops) with (lists = '50');

-- ============================================================
-- RLS (abilitata senza policy: accesso solo con service role)
-- ============================================================

alter table public.norme enable row level security;
alter table public.query_log enable row level security;

-- ============================================================
-- FUNZIONI
-- ============================================================

CREATE OR REPLACE FUNCTION public.update_norma_embedding(p_norma_id text, p_embedding vector)
 RETURNS void
 LANGUAGE sql
AS $function$
  update norme set embedding = p_embedding where norma_id = p_norma_id;
$function$;

CREATE OR REPLACE FUNCTION public.update_aggiornato_il()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
begin
  new.aggiornato_il = now();
  return new;
end;
$function$;

CREATE OR REPLACE FUNCTION public.search_norme_by_embedding(query_embedding vector, match_threshold double precision DEFAULT 0.55, match_count integer DEFAULT 12)
 RETURNS TABLE(norma_id text, titolo text, estremi text, descrizione text, articoli_chiave text[], tags text[], url_normattiva text, url_ricerca text, convenzione_only boolean, testo_vigente text, similarity double precision)
 LANGUAGE sql
 STABLE
AS $function$
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
$function$;

-- ============================================================
-- TRIGGER
-- ============================================================

CREATE TRIGGER norme_aggiornato_il
  BEFORE UPDATE ON public.norme
  FOR EACH ROW EXECUTE FUNCTION update_aggiornato_il();
