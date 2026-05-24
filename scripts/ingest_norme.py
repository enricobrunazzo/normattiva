#!/usr/bin/env python3
"""
Script di ingestione norme su Supabase.

Usage:
  pip install supabase groq
  export SUPABASE_URL=https://xxxx.supabase.co
  export SUPABASE_KEY=your-service-role-key
  export GROQ_API_KEY=your-groq-api-key
  python scripts/ingest_norme.py

Il script:
1. Carica il NORMATIVE_DB da api/search.py
2. Genera gli embedding di ogni norma via Groq (o OpenAI)
3. Salva su Supabase con upsert (safe da ri-eseguire)
"""

import os
import sys
import json
import time
import urllib.request
from pathlib import Path

# Assicura che il progetto sia nel path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supabase import create_client, Client

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

# Groq supporta embeddings con il modello nomic-embed-text
EMBEDDING_MODEL = "nomic-embed-text-v1_5"
EMBEDDING_DIM   = 768  # nomic-embed-text produce 768 dimensioni
# NOTA: se vuoi usare OpenAI text-embedding-3-small (1536 dim) modifica qui
# EMBEDDING_MODEL = "text-embedding-3-small"
# EMBEDDING_DIM = 1536


def get_embedding_groq(text: str) -> list[float]:
    """Genera embedding via Groq API."""
    payload = json.dumps({
        "model": EMBEDDING_MODEL,
        "input": text[:4096],  # max token Groq embed
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())

    return body["data"][0]["embedding"]


def build_embed_text(norma: dict) -> str:
    """Costruisce il testo da embeddare per una norma."""
    parts = [
        norma["titolo"],
        norma["estremi"],
        norma["descrizione"],
        "Articoli chiave: " + "; ".join(norma.get("articoli_chiave", [])),
        "Tag: " + ", ".join(norma.get("tags", [])),
    ]
    return "\n".join(parts)


def ingest(dry_run: bool = False):
    # Import del DB normativo dal file api/search.py
    from api.search import NORMATIVE_DB

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"[INGEST] Connesso a Supabase | norme da ingerire: {len(NORMATIVE_DB)}")

    errors = []
    for i, norma in enumerate(NORMATIVE_DB):
        nid = norma["id"]
        print(f"[{i+1}/{len(NORMATIVE_DB)}] {nid} — {norma['titolo'][:60]}")

        embed_text = build_embed_text(norma)

        try:
            embedding = get_embedding_groq(embed_text)
            print(f"  ✓ Embedding OK ({len(embedding)} dim)")
        except Exception as e:
            print(f"  ✗ Embedding FAILED: {e}")
            errors.append(nid)
            time.sleep(1)
            continue

        record = {
            "norma_id":        nid,
            "titolo":          norma["titolo"],
            "estremi":         norma["estremi"],
            "descrizione":     norma["descrizione"],
            "articoli_chiave": norma.get("articoli_chiave", []),
            "tags":            norma.get("tags", []),
            "url_normattiva":  norma.get("url_normattiva", ""),
            "url_ricerca":     norma.get("url_ricerca", ""),
            "convenzione_only": norma.get("convenzione_only", False),
            "embedding":       embedding,
        }

        if not dry_run:
            supabase.table("norme").upsert(
                record, on_conflict="norma_id"
            ).execute()
            print(f"  ✓ Salvato su Supabase")
        else:
            print(f"  [DRY RUN] Saltato salvataggio")

        # Rate limit gentile verso Groq
        time.sleep(0.3)

    print(f"\n[INGEST] Completato. Errori: {len(errors)}")
    if errors:
        print(f"  Norme fallite: {errors}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("[INGEST] Modalità DRY RUN — nessun dato salvato")
    ingest(dry_run=dry_run)
