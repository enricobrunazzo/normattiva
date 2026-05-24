#!/usr/bin/env python3
"""
Script di ingest: popola Supabase con embedding per tutte le 19 norme.

Uso:
    SUPABASE_URL=https://xxx.supabase.co SUPABASE_KEY=service_role_key python supabase/ingest_norme.py

Prerequisiti:
    1. schema.sql applicato nel SQL Editor di Supabase
    2. seed_norme.sql applicato nel SQL Editor di Supabase
    3. Edge Function 'embed' deployata: supabase functions deploy embed
"""
import json
import os
import sys
import time
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERRORE: SUPABASE_URL e SUPABASE_KEY devono essere impostate come env var.")
    sys.exit(1)


def get_embedding(text: str) -> list[float]:
    payload = json.dumps({"input": text[:2048]}).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/functions/v1/embed",
        data=payload,
        headers={
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode())
    emb = body.get("embedding")
    if emb is None:
        raise ValueError(f"Embedding non trovato nella risposta: {body}")
    return emb


def get_all_norme() -> list[dict]:
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/norme?select=norma_id,titolo,descrizione,embedding",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def update_embedding(norma_id: str, embedding: list[float]) -> None:
    payload = json.dumps({"embedding": embedding}).encode()
    url = f"{SUPABASE_URL}/rest/v1/norme?norma_id=eq.{urllib.parse.quote(norma_id)}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="PATCH",
    )
    urllib.request.urlopen(req, timeout=10)


import urllib.parse

def main():
    print(f"Connessione a {SUPABASE_URL}")
    norme = get_all_norme()
    print(f"Trovate {len(norme)} norme nel DB.")

    da_processare = [n for n in norme if not n.get("embedding")]
    print(f"Norme senza embedding: {len(da_processare)}")

    if not da_processare:
        print("Tutti gli embedding sono già presenti. Nulla da fare.")
        return

    for i, norma in enumerate(da_processare, 1):
        norma_id = norma["norma_id"]
        testo_per_embedding = f"{norma['titolo']}. {norma['descrizione']}"
        print(f"[{i}/{len(da_processare)}] Embedding per {norma_id!r}...", end=" ", flush=True)
        try:
            embedding = get_embedding(testo_per_embedding)
            update_embedding(norma_id, embedding)
            print(f"OK ({len(embedding)} dim)")
        except Exception as exc:
            print(f"ERRORE: {exc}")
        time.sleep(0.3)  # rate limit gentile

    print("\nIngest completato.")


if __name__ == "__main__":
    main()
