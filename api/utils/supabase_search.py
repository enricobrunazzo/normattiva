"""
Modulo di ricerca su Supabase con fallback al motore tag locale.

Embedding: Edge Function embed (gte-small, 384 dimensioni).
Groq viene usato SOLO per LLM (query expansion + ranking), non per embedding.

Flusso:
- Se Supabase è configurato → genera embedding via Edge Function → ricerca vettoriale
- Altrimenti → fallback alla logica tag esistente (zero downtime)
"""

import json
import os
import urllib.request
from typing import Optional

# NOTA: NON leggere le env var a module load time su Vercel serverless.
# Le variabili d'ambiente sono disponibili solo a runtime (invocazione).
# Usare sempre os.environ.get() direttamente nelle funzioni.


def _supabase_url() -> str:
    return os.environ.get("SUPABASE_URL", "")


def _supabase_key() -> str:
    return os.environ.get("SUPABASE_KEY", "")


def is_supabase_configured() -> bool:
    url = _supabase_url()
    key = _supabase_key()
    configured = bool(url and key)
    if not configured:
        print(
            f"[SUPA DIAG] is_supabase_configured=False | "
            f"SUPABASE_URL={'SET' if url else 'MISSING'} | "
            f"SUPABASE_KEY={'SET' if key else 'MISSING'}",
            flush=True,
        )
    return configured


def get_embedding(text: str) -> Optional[list[float]]:
    """
    Genera embedding via Edge Function embed (gte-small, 384 dim).
    """
    url = _supabase_url()
    key = _supabase_key()
    if not url or not key:
        print("[EMBED] Skip: Supabase non configurato", flush=True)
        return None

    edge_url = f"{url}/functions/v1/embed"
    print(f"[EMBED] Calling Edge Function: {edge_url[:60]}", flush=True)

    try:
        payload = json.dumps({"input": text[:2048]}).encode()
        req = urllib.request.Request(
            edge_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = json.loads(resp.read().decode())
        print(f"[EMBED] Edge Function response: status={status} | keys={list(body.keys())}", flush=True)
        emb = body.get("embedding") or body.get("data", [{}])[0].get("embedding")
        if emb is None:
            print(f"[EMBED] WARNING: embedding key non trovata nel body: {str(body)[:200]}", flush=True)
        else:
            print(f"[EMBED] OK: dimensioni={len(emb)}", flush=True)
        return emb
    except Exception as exc:
        print(
            f"[EMBED ERROR] {type(exc).__name__}: {exc} | "
            f"Edge URL: {edge_url[:60]}",
            flush=True,
        )
        return None


def supabase_vector_search(
    query_text: str,
    match_threshold: float = 0.55,
    match_count: int = 12,
    convenzione: bool = False,
) -> Optional[list[dict]]:
    """
    Esegue ricerca vettoriale su Supabase tramite la funzione RPC search_norme_by_embedding.
    Ritorna lista di norme ordinate per similarità, o None se fallisce.
    """
    url = _supabase_url()
    key = _supabase_key()
    if not url or not key:
        print("[SUPA] Supabase non configurato, skip vector search", flush=True)
        return None

    print(f"[SUPA] Avvio vector search | q={query_text[:50]!r}", flush=True)

    embedding = get_embedding(query_text)
    if embedding is None:
        print("[SUPA] Vector search abortita: embedding=None", flush=True)
        return None

    # PostgREST + pgvector richiedono la stringa "[v1,v2,...]" non un array JSON
    vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
    rpc_url = f"{url}/rest/v1/rpc/search_norme_by_embedding"
    print(f"[SUPA] Chiamata RPC: {rpc_url[:60]} | threshold={match_threshold} | count={match_count}", flush=True)

    try:
        payload = json.dumps({
            "query_embedding": vector_str,
            "match_threshold":  match_threshold,
            "match_count":      match_count,
        }).encode()

        req = urllib.request.Request(
            rpc_url,
            data=payload,
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
                "Prefer":        "return=representation",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            raw = resp.read().decode()
        print(f"[SUPA] RPC response: status={status} | len={len(raw)}", flush=True)
        results = json.loads(raw)

        if not isinstance(results, list):
            print(f"[SUPA ERROR] risposta inattesa (non lista): {str(results)[:200]}", flush=True)
            return None

        if not convenzione:
            results = [r for r in results if not r.get("convenzione_only", False)]

        if not results:
            print("[SUPA] Vector search: 0 risultati sopra soglia", flush=True)
            return None

        normalized = []
        for r in results:
            normalized.append({
                "id":               r["norma_id"],
                "titolo":           r["titolo"],
                "estremi":          r["estremi"],
                "descrizione":      r["descrizione"],
                "articoli_chiave":  r.get("articoli_chiave") or [],
                "tags":             r.get("tags") or [],
                "url_normattiva":   r.get("url_normattiva", ""),
                "url_ricerca":      r.get("url_ricerca", ""),
                "convenzione_only": r.get("convenzione_only", False),
                "text_vigente":     r.get("testo_vigente", "") or "",
                "score":            round(r.get("similarity", 0) * 100),
                "ai_motivation":    "",
                "similarity":       r.get("similarity", 0),
            })

        print(
            f"[SUPA] vector search OK | q={query_text[:60]!r} | "
            f"results={len(normalized)} | top_sim={normalized[0]['similarity']:.3f if normalized else 0}",
            flush=True,
        )
        return normalized

    except Exception as exc:
        print(
            f"[SUPA ERROR] RPC fallita: {type(exc).__name__}: {exc} | URL: {rpc_url[:60]}",
            flush=True,
        )
        return None


def insert_norma_to_supabase(norma: dict, embedding: list[float]) -> bool:
    """
    Inserisce o aggiorna una norma nel DB Supabase con il suo embedding.
    """
    url = _supabase_url()
    key = _supabase_key()
    if not url or not key:
        return False
    try:
        vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
        payload = json.dumps([{
            "norma_id":         norma["id"],
            "titolo":           norma.get("titolo", ""),
            "estremi":          norma.get("estremi", ""),
            "descrizione":      norma.get("descrizione", ""),
            "articoli_chiave":  norma.get("articoli_chiave", []),
            "tags":             norma.get("tags", []),
            "url_normattiva":   norma.get("url_normattiva", ""),
            "url_ricerca":      norma.get("url_ricerca", ""),
            "convenzione_only": norma.get("convenzione_only", False),
            "testo_vigente":    norma.get("text_vigente", ""),
            "embedding":        vector_str,
        }]).encode()
        req = urllib.request.Request(
            f"{url}/rest/v1/norme",
            data=payload,
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
                "Prefer":        "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        print(f"[SUPA INSERT] norma_id={norma['id']!r} inserita/aggiornata", flush=True)
        return True
    except Exception as exc:
        print(f"[SUPA INSERT ERROR] {type(exc).__name__}: {exc}", flush=True)
        return False


def log_query_to_supabase(
    query_text: str,
    tipo_atto: str,
    oggetto: str,
    importo: str,
    convenzione: bool,
    results_count: int,
    elapsed_ms: int,
    groq_used: bool,
) -> None:
    """Logga la query su Supabase in modo best-effort."""
    url = _supabase_url()
    key = _supabase_key()
    if not url or not key:
        return
    try:
        payload = json.dumps([{
            "query_text":    query_text,
            "tipo_atto":     tipo_atto,
            "oggetto":       oggetto,
            "importo":       importo,
            "convenzione":   convenzione,
            "results_count": results_count,
            "elapsed_ms":    elapsed_ms,
            "groq_used":     groq_used,
        }]).encode()
        req = urllib.request.Request(
            f"{url}/rest/v1/query_log",
            data=payload,
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
                "Prefer":        "return=minimal",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass
