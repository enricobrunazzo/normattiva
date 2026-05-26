"""
groq_discover.py

Dato un testo di query e i candidati già rankati da Groq, questo modulo:
1. Filtra i risultati non pertinenti (ai_motivation contiene segnali negativi)
2. Chiede a Groq se mancano norme rilevanti per il dominio della query
3. Se mancano, le genera come schede strutturate e le inserisce in Supabase

Validazione anti-allucinazione (pipeline persist_discovered_norme):
  E — strict ID/estremi check: numero E anno dell'ID devono matchare esattamente gli estremi;
      il numero di norma NON può essere solo nell'anno (ex: l_19_2019 con n.56/2019 → scartata);
      titolo non generico (no titoli che iniziano con parole vuote senza numero legge)
  D — similarity check: embedding coseno tra testo query e descrizione norma;
      se similarity < DISCOVER_MIN_SIMILARITY → norma scartata come irrilevante
  U — URL strutturale check: l'URL normattiva.it deve contenere 'urn:nir:stato:' nel path;
      URL con encoding base64 o path non canonici vengono scartati prima della HEAD request
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

MODEL_RANK = "llama-3.3-70b-versatile"

# ── Soglia D: similarity minima tra query e descrizione norma scoperta
DISCOVER_MIN_SIMILARITY = 0.72

# ── Titoli generici che Groq usa per norme inventate (Opzione E)
_GENERIC_TITLE_PREFIXES = (
    "disposizioni per",
    "dispo