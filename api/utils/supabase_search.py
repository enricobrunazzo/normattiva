"""
Modulo di ricerca su Supabase con fallback al motore tag locale.

Questa funzione sostituisce progressivamente _tag_search() in search.py:
- Se Supabase è configurato e l'embedding è disponibile → ricerca vettoriale
- Altrimenti → fallback alla logica tag esistente (zero downtime)
"""

import json
import os
import urllib.request
from typing import Optional

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

EMBEDDING_MODEL = "nomic-embed-text-v1_5"


def is_supabase_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_KEY)


def get_embedding(text: str) -> Optional[list[float]]:
    """Genera embedding della query via Groq."""
    if not _GROQ_API_KEY:
        return None
    try:
        payload = json.dumps({
            "model": EMBEDDING_MODEL,
            "input": text[:2048],
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/embeddings",
            data=payload,
            headers={
                "Authorization": f"Bearer {_GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
        return body["data"][0]["embedding"]
    except Exception as exc:
        print(f"[EMBED ERROR] {type(exc).__name__}: {exc}", flush=True)
        return None


def supabase_vector_search(
    query_text: str,
    match_threshold: float = 0.60,
    match_count: int = 12,
    convenzione: bool = False,
) -> Optional[list[dict]]:
    """
    Esegue ricerca vettoriale su Supabase tramite la funzione RPC search_norme_by_embedding.
    Ritorna lista di norme ordinate per similarità, o None se fallisce.
    """
    if not is_supabase_configured():
        return None

    embedding = get_embedding(query_text)
    if embedding is None:
        return None

    try:
        payload = json.dumps({
            "query_embedding": embedding,
            "match_threshold":  match_threshold,
            "match_count":      match_count,
        }).encode()

        req = urllib.request.Request(
            f"{_SUPABASE_URL}/rest/v1/rpc/search_norme_by_embedding",
            data=payload,
            headers={
                "apikey":        _SUPABASE_KEY,
                "Authorization": f"Bearer {_SUPABASE_KEY}",
                "Content-Type":  "application/json",
                "Prefer":        "return=representation",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read().decode())

        if not isinstance(results, list):
            print(f"[SUPA ERROR] risposta inattesa: {str(results)[:200]}", flush=True)
            return None

        # Filtra norme convenzione_only se non richiesta
        if not convenzione:
            results = [r for r in results if not r.get("convenzione_only", False)]

        # Normalizza al formato usato dal resto di search.py
        normalized = []
        for r in results:
            normalized.append({
                "id":              r["norma_id"],
                "titolo":          r["titolo"],
                "estremi":         r["estremi"],
                "descrizione":     r["descrizione"],
                "articoli_chiave": r.get("articoli_chiave") or [],
                "tags":            r.get("tags") or [],
                "url_normattiva":  r.get("url_normattiva", ""),
                "url_ricerca":     r.get("url_ricerca", ""),
                "convenzione_only": r.get("convenzione_only", False),
                "testo_vigente":   r.get("testo_vigente", "") or "",
                "score":           round(r.get("similarity", 0) * 100),
                "ai_motivation":   "",
                "similarity":      r.get("similarity", 0),
            })

        print(
            f"[SUPA] vector search OK | q={query_text[:60]!r} | "
            f"results={len(normalized)} | top_sim={normalized[0]['similarity']:.3f if normalized else 0}",
            flush=True,
        )
        return normalized

    except Exception as exc:
        print(f"[SUPA ERROR] {type(exc).__name__}: {exc}", flush=True)
        return None


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
    """Logga la query su Supabase in modo asincrono/best-effort."""
    if not is_supabase_configured():
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
            f"{_SUPABASE_URL}/rest/v1/query_log",
            data=payload,
            headers={
                "apikey":        _SUPABASE_KEY,
                "Authorization": f"Bearer {_SUPABASE_KEY}",
                "Content-Type":  "application/json",
                "Prefer":        "return=minimal",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass  # log fallure non deve bloccare la risposta
