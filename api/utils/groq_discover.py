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

# Segnali negativi nell'ai_motivation che indicano NON pertinenza.
# ATTENZIONE: usare solo frasi sufficientemente specifiche per evitare falsi positivi.
# NON usare segnali condizionali generici come "solo se" / "solo qualora" che
# compaiono anche in motivazioni legittime (es. "qualora l'edificio sia vincolato").
_NON_PERTINENCE_SIGNALS = [
    # Negazioni esplicite
    "non pertinente",
    "non ha attinenza",
    "non disciplina",
    "marginalmente rilevante",
    "non riguarda",
    "non si applica",
    "non tratta",
    "non copre",
    "non concerne",
    "non è pertinente",
    "non è applicabile",
    # Segnali specifici per norme PA-fornitore usate fuori contesto
    "non è direttamente applicabile",
    "applicabile esclusivamente ai fornitori",
    "riguarda esclusivamente i fornitori",
    "disciplina esclusivamente i fornitori",
    "applicabile solo ai soggetti privati",
    "non riguarda procedimenti interni",
]

# Norme già presenti nel DB locale: (numero, anno) estratti dagli estremi
# Usato per bloccare duplicati generati da Groq con ID diverso
_LOCAL_DB_NORME_ESTREMI = [
    ("36", "2023"),   # D.Lgs. 36/2023
    ("82", "2005"),   # D.Lgs. 82/2005 CAD
    ("33", "2013"),   # D.Lgs. 33/2013
    ("190", "2012"),  # L. 190/2012
    ("267", "2000"),  # D.Lgs. 267/2000 TUEL
    ("165", "2001"),  # D.Lgs. 165/2001 TUPI
    ("196", "2003"),  # D.Lgs. 196/2003 Privacy
    ("81", "2008"),   # D.Lgs. 81/2008
    ("118", "2011"),  # D.Lgs. 118/2011
    ("136", "2010"),  # L. 136/2010
    ("241", "1990"),  # L. 241/1990
    ("50", "2016"),   # D.Lgs. 50/2016
    ("296", "2006"),  # L. 296/2006
    ("231", "2001"),  # D.Lgs. 231/2001
    ("328", "2000"),  # L. 328/2000
    ("104", "1992"),  # L. 104/1992
    ("159", "2013"),  # D.P.C.M. 159/2013
]

_LOCAL_DB_NORME_IDS = {
    "dlgs_36_2023", "dlgs_82_2005", "dlgs_33_2013", "l_190_2012",
    "dlgs_267_2000", "dlgs_165_2001", "dlgs_196_2003", "dlgs_81_2008",
    "dlgs_118_2011", "pnrr_missione1", "l_136_2010", "l_241_1990",
    "dlgs_50_2016", "l_296_2006_consip", "dlgs_231_2001",
    "circ_agid_cloud_2021", "l_328_2000", "dpcm_159_2013", "l_104_1992",
}

# Mappa: prefisso degli estremi -> tipo corretto nell'URN normattiva.it
_ESTREMI_TO_URN_TYPE = [
    (r"d\.?lgs\.?",           "decreto.legislativo"),
    (r"decreto legislativo",   "decreto.legislativo"),
    (r"d\.?p\.?r\.?",         "decreto.del.presidente.della.repubblica"),
    (r"decreto del presidente della repubblica", "decreto.del.presidente.della.repubblica"),
    (r"d\.?p\.?c\.?m\.?",    "decreto.del.presidente.del.consiglio.dei.ministri"),
    (r"decreto del presidente del consiglio",    "decreto.del.presidente.del.consiglio.dei.ministri"),
    (r"d\.?m\.?",             "decreto.ministeriale"),
    (r"decreto ministeriale",  "decreto.ministeriale"),
    (r"l\.",                   "legge"),
    (r"legge",                 "legge"),
]

# Mappa: prefisso estremi -> prefisso ID snake_case canonico
_ESTREMI_TO_ID_PREFIX = [
    (r"d\.?lgs\.?",            "dlgs"),
    (r"decreto legislativo",    "dlgs"),
    (r"d\.?p\.?r\.?",          "dpr"),
    (r"decreto del presidente della repubblica", "dpr"),
    (r"d\.?p\.?c\.?m\.?",     "dpcm"),
    (r"decreto del presidente del consiglio",    "dpcm"),
    (r"d\.?m\.?",              "dm"),
    (r"decreto ministeriale",   "dm"),
    (r"l\.",                    "l"),
    (r"legge",                  "l"),
    (r"d\.?p\.?",               "dp"),
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


def _normalize_id(norma: dict) -> str:
    """
    Normalizza l'ID della norma generata da Groq per renderlo coerente
    con la convenzione del DB locale: prefisso_numero_anno, tutto lowercase,
    senza separatori multipli (es. d_lgs_42_2004 -> dlgs_42_2004).
    """
    nid = (norma.get("id") or "").strip().lower()
    estremi = (norma.get("estremi") or "").lower().strip()

    canonical_prefix = None
    for pattern, prefix in _ESTREMI_TO_ID_PREFIX:
        if re.match(pattern, estremi, re.IGNORECASE):
            canonical_prefix = prefix
            break

    if not canonical_prefix:
        return nid

    numeri = re.findall(r"\b(\d{2,4})\b", estremi)
    anni = [n for n in numeri if 1980 <= int(n) <= 2030]
    numeri_norma = [n for n in numeri if int(n) not in range(1980, 2031)]

    if not numeri_norma or not anni:
        return nid

    canonical_id = f"{canonical_prefix}_{numeri_norma[0]}_{anni[0]}"

    if canonical_id != nid:
        print(f"[PERSIST] ID normalizzato: {nid!r} -> {canonical_id!r}", flush=True)
    return canonical_id


def _is_duplicate_of_local_db(norma: dict) -> bool:
    """
    Controlla se la norma generata da Groq è un duplicato di una norma
    già presente nel DB locale, confrontando:
    1. L'ID esatto (anche dopo normalizzazione)
    2. Numero + anno estratti dagli estremi
    """
    nid = (norma.get("id") or "").strip().lower()
    if nid in _LOCAL_DB_NORME_IDS:
        return True

    estremi = (norma.get("estremi") or "").lower()
    numeri = re.findall(r"\b(\d{2,4})\b", estremi)
    anni = [n for n in numeri if 1980 <= int(n) <= 2030]
    numeri_norma = [n for n in numeri if int(n) not in range(1980, 2031)]

    for num, anno in _LOCAL_DB_NORME_ESTREMI:
        if anno in anni and num in numeri_norma:
            return True

    return False


def _normalize_url_normattiva(norma: dict) -> str:
    """
    Corregge il tipo atto nell'URL normattiva generato da Groq.
    Deriva il tipo corretto dagli estremi della norma e lo sostituisce
    nell'URL se risulta errato (es. decreto.legge -> decreto.legislativo).
    """
    url = (norma.get("url_normattiva") or "").strip()
    estremi = (norma.get("estremi") or "").lower().strip()
    if not url or not estremi:
        return url

    urn_type_correct = None
    for pattern, urn_type in _ESTREMI_TO_URN_TYPE:
        if re.match(pattern, estremi, re.IGNORECASE):
            urn_type_correct = urn_type
            break

    if not urn_type_correct:
        return url

    corrected = re.sub(
        r"(urn:nir:stato:)[^:]+(:)",
        lambda m: f"{m.group(1)}{urn_type_correct}{m.group(2)}",
        url,
    )
    if corrected != url:
        print(f"[PERSIST] URL corretto: {url!r} -> {corrected!r}", flush=True)
    return corrected


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
    local_db_refs = [
        "- D.Lgs. 36/2023 — Codice dei contratti pubblici",
        "- D.Lgs. 82/2005 — CAD",
        "- D.Lgs. 33/2013 — Trasparenza",
        "- L. 190/2012 — Anticorruzione",
        "- D.Lgs. 267/2000 — TUEL",
        "- D.Lgs. 165/2001 — TUPI",
        "- D.Lgs. 196/2003 — Privacy/GDPR",
        "- D.Lgs. 81/2008 — Sicurezza lavoro",
        "- D.Lgs. 118/2011 — Armonizzazione contabile",
        "- L. 136/2010 — Tracciabilità CIG/CUP",
        "- L. 241/1990 — Procedimento amministrativo",
        "- D.Lgs. 50/2016 — Codice appalti previgente",
        "- L. 296/2006 — Obbligo Consip/MEPA",
        "- D.Lgs. 231/2001 — Responsabilità enti",
        "- L. 328/2000 — Servizi sociali",
        "- L. 104/1992 — Assistenza disabili",
        "- D.P.C.M. 159/2013 — ISEE",
    ]
    all_covered = already_covered + local_db_refs
    already_str = "\n".join(all_covered)

    prompt = (
        "Sei un esperto di diritto amministrativo italiano.\n"
        f"Tipo atto: {tipo_atto or 'non specificato'}\n"
        f"Oggetto: {oggetto or 'non specificato'}\n"
        f"Descrizione esigenza: {testo}\n\n"
        "Norme già disponibili nel sistema (NON generare schede per queste, NON reinventarle con ID diversi):\n"
        f"{already_str}\n\n"
        "COMPITO:\n"
        "1. Valuta se esistono norme italiane VIGENTI rilevanti per questa query che NON sono già coperte.\n"
        "2. Se esistono, genera una scheda per CIASCUNA norma mancante (massimo 3).\n"
        "3. Se le norme già coperte sono sufficienti, restituisci discovered=[] (lista vuota).\n"
        "4. NON generare norme che non esistono realmente: verifica che ID, estremi e titolo corrispondano a una norma italiana vigente reale.\n"
        "5. NON includere norme che disciplinano esclusivamente i rapporti tra PA e fornitori privati se la query riguarda un procedimento interno o autorizzativo della PA.\n\n"
        "Convenzione ID: usa sempre il formato snake_case compatto senza trattini interni al prefisso:\n"
        "  D.Lgs. -> dlgs_<numero>_<anno>  (es. dlgs_42_2004)\n"
        "  D.P.R. -> dpr_<numero>_<anno>   (es. dpr_380_2001)\n"
        "  D.P.C.M. -> dpcm_<numero>_<anno>\n"
        "  D.M. -> dm_<numero>_<anno>\n"
        "  L. -> l_<numero>_<anno>          (es. l_241_1990)\n\n"
        "Per ogni norma mancante reale, genera:\n"
        "- id: stringa snake_case univoca secondo la convenzione sopra\n"
        "- titolo: titolo breve ufficiale\n"
        "- estremi: riferimento normativo completo e preciso (es. D.P.R. 6 giugno 2001, n. 380)\n"
        "- descrizione: 2-3 frasi che spiegano cosa disciplina e perché è rilevante per questa query\n"
        "- articoli_chiave: lista di 3-5 articoli rilevanti con descrizione (es. 'art. 10 — contenuto del PRG')\n"
        "- tags: lista di 5-10 tag lowercase rilevanti\n"
        "- url_normattiva: URL su normattiva.it (formato: https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:<tipo>:<data>;<numero>)\n"
        "  Usa il tipo corretto: decreto.legislativo per D.Lgs., decreto.del.presidente.della.repubblica per D.P.R., legge per L., decreto.ministeriale per D.M.\n"
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
    - Normalizza l'ID secondo la convenzione del DB locale
    - Valida che non sia un duplicato del DB locale
    - Normalizza l'URL normattiva
    - Genera l'embedding via Supabase Edge Function
    - Inserisce nel DB Supabase
    - Restituisce la lista delle norme effettivamente persisted (con score e ai_motivation)
    """
    from api.utils.supabase_search import get_embedding, insert_norma_to_supabase

    persisted = []
    for norma in discovered:
        if not norma.get("id") or not norma.get("titolo"):
            print(f"[PERSIST] scheda senza id o titolo, skip", flush=True)
            continue

        # Normalizza ID secondo convenzione del DB locale
        norma["id"] = _normalize_id(norma)

        # Validazione: scarta se è un duplicato del DB locale
        if _is_duplicate_of_local_db(norma):
            print(f"[PERSIST] {norma['id']!r} è duplicato di una norma già nel DB locale, skip", flush=True)
            continue

        # Normalizza URL normattiva (corregge tipo atto errato)
        norma["url_normattiva"] = _normalize_url_normattiva(norma)
        norma.setdefault("url_ricerca", norma["url_normattiva"])

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

        norma_result = norma.copy()
        norma_result["score"] = 95
        norma_result["text_vigente"] = ""
        norma_result["text_vigente_disponibile"] = False
        norma_result.setdefault("ai_motivation", "")
        norma_result.setdefault("convenzione_only", False)
        persisted.append(norma_result)
    return persisted
