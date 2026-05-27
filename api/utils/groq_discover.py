"""
groq_discover.py

Dato un testo di query e i candidati già rankati da Groq, questo modulo:
1. Filtra i risultati non pertinenti (ai_motivation contiene segnali negativi)
2. Chiede a Groq se mancano norme rilevanti per il dominio della query
3. Se mancano, le genera come schede strutturate e le inserisce in Supabase
"""

import json
import os
import re
import urllib.request
from typing import Optional

_GROQ_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://console.groq.com",
    "Referer": "https://console.groq.com/",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

MODEL_RANK = "openai/gpt-oss-120b"

# Segnali negativi nell'ai_motivation che indicano non pertinenza
_NON_PERTINENCE_SIGNALS = [
    "non pertinente",
    "non ha attinenza",
    "non disciplina",
    "marginalmente rilevante",
    "non riguarda",
    "non si applica",
    "non tratta",
    "non copre",
    "non concerne",
]


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    m = re.search(r"(\{[\s\S]*\})", raw)
    if m:
        return json.loads(m.group(1))
    raise ValueError(f"Nessun JSON valido trovato. Raw: {raw[:300]!r}")


def filter_pertinent(results: list) -> list:
    """
    Rimuove i risultati la cui ai_motivation contiene segnali di non pertinenza.
    Mantiene sempre i risultati senza ai_motivation (non ancora rankati da Groq).
    """
    filtered = []
    for r in results:
        motivation = (r.get("ai_motivation") or "").lower()
        if not motivation:
            filtered.append(r)
            continue
        if any(signal in motivation for signal in _NON_PERTINENCE_SIGNALS):
            print(f"[FILTER] Escluso {r['id']!r}: motivazione non pertinente", flush=True)
            continue
        filtered.append(r)
    return filtered


def discover_missing_norme(
    testo: str,
    tipo_atto: str,
    oggetto: str,
    pertinent_results: list,
) -> list[dict]:
    """
    Chiede a Groq se, dato il contesto della query, mancano norme italiane rilevanti
    non già presenti nei risultati pertinenti.
    Restituisce una lista di schede norma (dict) pronte per l'inserimento in Supabase.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return []

    already_covered = [
        f"- {r['estremi']} — {r['titolo']}" for r in pertinent_results
    ]
    already_str = "\n".join(already_covered) if already_covered else "Nessuna norma pertinente trovata."

    prompt = (
        "Sei un esperto di diritto amministrativo italiano.\n"
        f"Tipo atto: {tipo_atto or 'non specificato'}\n"
        f"Oggetto: {oggetto or 'non specificato'}\n"
        f"Descrizione esigenza: {testo}\n\n"
        "Norme già coperte (NON ripetere queste):\n"
        f"{already_str}\n\n"
        "COMPITO:\n"
        "1. Valuta se esistono norme italiane VIGENTI rilevanti per questa query che NON sono già coperte.\n"
        "2. Se esistono, genera una scheda per CIASCUNA norma mancante (massimo 3).\n"
        "3. Se le norme già coperte sono sufficienti, restituisci discovered=[] (lista vuota).\n\n"
        "Per ogni norma mancante, genera:\n"
        "- id: stringa snake_case univoca (es. dpr_380_2001)\n"
        "- titolo: titolo breve ufficiale\n"
        "- estremi: riferimento normativo completo (es. D.P.R. 6 giugno 2001, n. 380)\n"
        "- descrizione: 2-3 frasi che spiegano cosa disciplina e perché è rilevante per questa query\n"
        "- articoli_chiave: lista di 3-5 articoli rilevanti con descrizione (es. 'art. 10 — contenuto del PRG')\n"
        "- tags: lista di 5-10 tag lowercase rilevanti\n"
        "- url_normattiva: URL su normattiva.it (formato: https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:<tipo>:<data>;<numero>)\n"
        "- ai_motivation: 1-2 frasi su perché questa norma è pertinente per la query specifica\n\n"
        "Rispondi SOLO con JSON: {\"discovered\": [<lista schede>]}"
    )

    try:
        payload = json.dumps({
            "model": MODEL_RANK,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2048,
        }).encode()
        headers = {**_GROQ_HEADERS, "Authorization": f"Bearer {api_key}"}
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        data = _extract_json(body["choices"][0]["message"]["content"])
        discovered = data.get("discovered", [])
        print(f"[DISCOVER] norme scoperte da Groq: {len(discovered)}", flush=True)
        return discovered
    except Exception as exc:
        print(f"[DISCOVER ERROR] {type(exc).__name__}: {exc}", flush=True)
        return []


def persist_discovered_norme(discovered: list[dict]) -> list[dict]:
    """
    Per ogni norma scoperta da Groq:
    - Genera l'embedding via Supabase Edge Function
    - Inserisce nel DB Supabase
    - Restituisce la lista delle norme effettivamente persisted (con score e ai_motivation)
    """
    from api.utils.supabase_search import get_embedding, insert_norma_to_supabase

    persisted = []
    for norma in discovered:
        if not norma.get("id") or not norma.get("titolo"):
            continue
        # Testo per embedding: titolo + descrizione + articoli chiave
        embed_text = " ".join(filter(None, [
            norma.get("titolo", ""),
            norma.get("estremi", ""),
            norma.get("descrizione", ""),
            " ".join(norma.get("articoli_chiave", [])),
        ]))
        embedding = get_embedding(embed_text)
        if embedding is None:
            print(f"[PERSIST] embedding fallito per {norma['id']!r}, skip insert", flush=True)
        else:
            ok = insert_norma_to_supabase(norma, embedding)
            if ok:
                print(f"[PERSIST] {norma['id']!r} inserita in Supabase", flush=True)
            else:
                print(f"[PERSIST] insert fallito per {norma['id']!r}", flush=True)
        # Aggiungiamo ai risultati in ogni caso (anche senza embedding)
        norma_result = norma.copy()
        norma_result["score"] = 95
        norma_result["text_vigente"] = ""
        norma_result["text_vigente_disponibile"] = False
        norma_result.setdefault("ai_motivation", "")
        norma_result.setdefault("convenzione_only", False)
        norma_result.setdefault("url_ricerca", norma.get("url_normattiva", ""))
        persisted.append(norma_result)
    return persisted
