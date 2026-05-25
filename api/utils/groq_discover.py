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

MODEL_RANK = "llama-3.3-70b-versatile"  # fix: era openai/gpt-oss-120b (non più disponibile su Groq)

# ── Soglia D: similarity minima tra query e descrizione norma scoperta
# Valore empirico: le norme pertinenti hanno similarity ≥ 0.75 con la query;
# norme generiche/irrilevanti scendono sotto 0.70.
DISCOVER_MIN_SIMILARITY = 0.72

# ── Titoli generici che Groq usa per norme inventate (Opzione E)
# Se il titolo inizia con una di queste parole e NON contiene un numero di legge,
# la norma viene considerata allucinazione.
_GENERIC_TITLE_PREFIXES = (
    "disposizioni per",
    "disposizioni in materia",
    "disposizioni recanti",
    "norme per",
    "norme in materia",
    "regolamento per",
    "regolamento recante",
    "attuazione della direttiva",
    "attuazione del regolamento",
    "misure per",
    "misure urgenti",
    "misure di",
)

# Segnali negativi nell'ai_motivation che indicano NON pertinenza.
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
    "non è pertinente",
    "non è applicabile",
    "non è direttamente applicabile",
    "applicabile esclusivamente ai fornitori",
    "riguarda esclusivamente i fornitori",
    "disciplina esclusivamente i fornitori",
    "applicabile solo ai soggetti privati",
    "non riguarda procedimenti interni",
]

# Norme già presenti nel DB locale: (numero, anno)
_LOCAL_DB_NORME_ESTREMI = [
    ("36", "2023"),
    ("82", "2005"),
    ("33", "2013"),
    ("190", "2012"),
    ("267", "2000"),
    ("165", "2001"),
    ("196", "2003"),
    ("81", "2008"),
    ("118", "2011"),
    ("136", "2010"),
    ("241", "1990"),
    ("50", "2016"),
    ("296", "2006"),
    ("231", "2001"),
    ("328", "2000"),
    ("104", "1992"),
    ("159", "2013"),
]

_LOCAL_DB_NORME_IDS = {
    "dlgs_36_2023", "dlgs_82_2005", "dlgs_33_2013", "l_190_2012",
    "dlgs_267_2000", "dlgs_165_2001", "dlgs_196_2003", "dlgs_81_2008",
    "dlgs_118_2011", "pnrr_missione1", "l_136_2010", "l_241_1990",
    "dlgs_50_2016", "l_296_2006_consip", "dlgs_231_2001",
    "circ_agid_cloud_2021", "l_328_2000", "dpcm_159_2013", "l_104_1992",
}

# ── Blocklist: norme da non inserire mai in Supabase (numero, anno, motivo)
_BLOCKLIST_ESTREMI = [
    ("285", "1992", "D.Lgs. 285/1992 = Codice della Strada, irrilevante per PA amministrativa"),
    ("117", "2017", "D.Lgs. 117/2017 = Codice Terzo Settore, non pertinente per appalti ordinari PA"),
]

# Mappa: prefisso estremi -> tipo URN normattiva.it
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

# Mappa: prefisso estremi -> prefisso ID snake_case
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
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Nessun JSON valido trovato. Raw: {raw[:300]!r}")


def _normalize_id(norma: dict) -> str:
    """
    Normalizza l'ID della norma: prefisso_numero_anno, lowercase.
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


def _is_blocklisted(norma: dict) -> bool:
    estremi = (norma.get("estremi") or "").lower()
    numeri = re.findall(r"\b(\d{2,4})\b", estremi)
    anni = [n for n in numeri if 1980 <= int(n) <= 2030]
    numeri_norma = [n for n in numeri if int(n) not in range(1980, 2031)]
    for num, anno, motivo in _BLOCKLIST_ESTREMI:
        if anno in anni and num in numeri_norma:
            print(f"[PERSIST] BLOCKLIST: {norma.get('id')!r} bloccato → {motivo}", flush=True)
            return True
    return False


def _is_valid_norma_italiana(norma: dict) -> bool:
    """
    Opzione E — Validazione stricta anti-allucinazione:
    1. Campi obbligatori presenti
    2. ID formato snake_case valido
    3. Numero norma nell'ID deve matchare esattamente il numero negli estremi
       (NON basta che sia nell'anno: l_19_2019 con n.56/2019 → FAIL)
    4. Anno nell'ID deve matchare l'anno negli estremi
    5. Titolo non generico senza numero di legge
    6. Numero norma presente anche nella descrizione o nel titolo (doppio check)
    """
    nid = (norma.get("id") or "").strip().lower()
    estremi = (norma.get("estremi") or "").strip()
    descrizione = (norma.get("descrizione") or "").strip()
    titolo = (norma.get("titolo") or "").strip()

    # 1. Campi obbligatori
    if not nid or not estremi or not descrizione or not titolo:
        print(f"[PERSIST] VALIDATION E1: scheda incompleta (id={nid!r}), skip", flush=True)
        return False

    # 2. Formato ID
    if not re.match(r'^[a-z]+_\d{2,3}_\d{4}$', nid):
        if not re.match(r'^[a-z0-9_]+$', nid) or len(nid) < 8:
            print(f"[PERSIST] VALIDATION E2: ID {nid!r} formato non valido, skip", flush=True)
            return False

    # 3+4. Numero e anno: match ESATTO tra ID e estremi
    id_parts = nid.split("_")
    numeri_nel_id = [p for p in id_parts if p.isdigit() and len(p) <= 4]
    if numeri_nel_id:
        numero_norma = numeri_nel_id[0]   # es. "19" in l_19_2019
        anno_norma = numeri_nel_id[-1] if len(numeri_nel_id) > 1 else ""  # es. "2019"
        estremi_lower = estremi.lower()

        # Numero deve apparire come "n. <numero>" o ", <numero>" negli estremi
        # Questo blocca l_19_2019 con estremi "L. 56/2019" dove 19 è solo parte dell'anno
        numero_pattern = rf"(?:n\.\s*|,\s*){re.escape(numero_norma)}\b"
        if not re.search(numero_pattern, estremi_lower):
            # Fallback: numero come token standalone (non come parte di anno)
            # Verifica che il numero sia un token autonomo e non contenuto nell'anno
            all_tokens = re.findall(r"\b(\d{2,4})\b", estremi_lower)
            anni_in_estremi = [t for t in all_tokens if 1980 <= int(t) <= 2030]
            numeri_in_estremi = [t for t in all_tokens if int(t) not in range(1980, 2031)]
            if numero_norma not in numeri_in_estremi:
                print(
                    f"[PERSIST] VALIDATION E3: numero {numero_norma!r} dell'ID {nid!r} "
                    f"non trovato come numero di norma negli estremi {estremi!r}, skip",
                    flush=True,
                )
                return False

        if anno_norma and anno_norma not in estremi_lower:
            print(
                f"[PERSIST] VALIDATION E4: anno {anno_norma!r} dell'ID {nid!r} "
                f"non trovato negli estremi {estremi!r}, skip",
                flush=True,
            )
            return False

        # 6. Numero norma presente anche in titolo o descrizione (doppio check anti-invenzione)
        titolo_desc = f"{titolo} {descrizione}".lower()
        if numero_norma not in titolo_desc and anno_norma not in titolo_desc:
            print(
                f"[PERSIST] VALIDATION E6: numero/anno dell'ID {nid!r} "
                f"non trovati nel titolo né nella descrizione, skip",
                flush=True,
            )
            return False

    # 5. Titolo generico senza numero di legge
    titolo_lower = titolo.lower().strip()
    for prefix in _GENERIC_TITLE_PREFIXES:
        if titolo_lower.startswith(prefix):
            # Accetta solo se nel titolo c'è un numero di legge esplicito
            if not re.search(r"\b\d{2,4}/\d{4}\b|n\.\s*\d{2,3}", titolo_lower):
                print(
                    f"[PERSIST] VALIDATION E5: titolo generico senza numero legge: "
                    f"{titolo!r}, skip",
                    flush=True,
                )
                return False
            break

    return True


def _cosine_similarity(v1: list, v2: list) -> float:
    """Calcola similarity coseno tra due vettori (list of float)."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def _check_discover_similarity(
    norma: dict,
    query_embedding: list,
) -> bool:
    """
    Opzione D — Similarity check: calcola coseno tra embedding query e
    embedding della descrizione norma scoperta.
    Se similarity < DISCOVER_MIN_SIMILARITY → norma irrilevante, scarta.

    Usa get_embedding() già disponibile in supabase_search.
    Fail open se l'embedding fallisce (non blocca norme reali per errori rete).
    """
    from api.utils.supabase_search import get_embedding

    if not query_embedding:
        return True  # fail open: nessun embedding query disponibile

    embed_text = " ".join(filter(None, [
        norma.get("titolo", ""),
        norma.get("estremi", ""),
        norma.get("descrizione", ""),
    ]))
    norma_embedding = get_embedding(embed_text)
    if norma_embedding is None:
        print(
            f"[PERSIST] SIMILARITY D: embedding fallito per {norma.get('id')!r} → fail open",
            flush=True,
        )
        return True  # fail open

    sim = _cosine_similarity(query_embedding, norma_embedding)
    ok = sim >= DISCOVER_MIN_SIMILARITY
    print(
        f"[PERSIST] SIMILARITY D: {norma.get('id')!r} sim={sim:.4f} "
        f"({'OK' if ok else 'SCARTATA threshold=' + str(DISCOVER_MIN_SIMILARITY)})",
        flush=True,
    )
    return ok


def _check_url_normattiva_exists(norma: dict) -> bool:
    """
    Verifica che l'URL normattiva.it della norma risponda con un codice HTTP
    valido (200, 301, 302).
    - HEAD request, timeout 8s.
    - Fail open per errori rete / server (non scarta norme reali per problemi transitori).
    - 404 → scarta definitivamente.
    """
    url = (norma.get("url_normattiva") or "").strip()
    if not url:
        print(f"[PERSIST] URL_CHECK: {norma.get('id')!r} senza url_normattiva, skip check", flush=True)
        return True

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NormativaBot/1.0)"},
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            status = resp.status
        ok = status in (200, 301, 302)
        if ok:
            print(f"[PERSIST] URL_CHECK OK: {norma.get('id')!r} → HTTP {status}", flush=True)
        else:
            print(
                f"[PERSIST] URL_CHECK FAIL: {norma.get('id')!r} → HTTP {status} "
                f"| url={url[:80]!r} | norma scartata",
                flush=True,
            )
        return ok
    except urllib.error.HTTPError as exc:
        status = exc.code
        if status == 404:
            print(
                f"[PERSIST] URL_CHECK 404: {norma.get('id')!r} non trovata su normattiva.it "
                f"| url={url[:80]!r} | norma scartata",
                flush=True,
            )
            return False
        print(
            f"[PERSIST] URL_CHECK HTTP {status}: {norma.get('id')!r} → fail open",
            flush=True,
        )
        return True
    except Exception as exc:
        print(
            f"[PERSIST] URL_CHECK ERROR: {norma.get('id')!r} → {type(exc).__name__}: {exc} → fail open",
            flush=True,
        )
        return True


def _normalize_url_normattiva(norma: dict) -> str:
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
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return []

    already_covered = [f"- {r['estremi']} — {r['titolo']}" for r in pertinent_results]
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
    already_str = "\n".join(already_covered + local_db_refs)

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
        "5. NON includere norme che disciplinano esclusivamente i rapporti tra PA e fornitori privati se la query riguarda un procedimento interno o autorizzativo della PA.\n"
        "6. NON includere norme generiche o di sistema (Codice Terzo Settore, Codice Civile, Codice della Strada) se non direttamente applicabili alla specifica esigenza PA.\n\n"
        "Convenzione ID: usa sempre il formato snake_case compatto:\n"
        "  D.Lgs. -> dlgs_<numero>_<anno>  (es. dlgs_42_2004)\n"
        "  D.P.R. -> dpr_<numero>_<anno>   (es. dpr_380_2001)\n"
        "  D.P.C.M. -> dpcm_<numero>_<anno>\n"
        "  D.M. -> dm_<numero>_<anno>\n"
        "  L. -> l_<numero>_<anno>          (es. l_241_1990)\n"
        "IMPORTANTE: il <numero> nell'ID deve corrispondere ESATTAMENTE al numero della norma\n"
        "negli estremi (es. L. 56/2019, n. 56 → ID l_56_2019, NON l_19_2019).\n\n"
        "Per ogni norma mancante reale, genera:\n"
        "- id: stringa snake_case secondo la convenzione sopra\n"
        "- titolo: titolo breve ufficiale (includi il numero di legge nel titolo)\n"
        "- estremi: riferimento normativo completo e preciso (es. D.P.R. 6 giugno 2001, n. 380)\n"
        "- descrizione: 2-3 frasi che spiegano cosa disciplina e perché è rilevante per questa query\n"
        "- articoli_chiave: lista di 3-5 articoli rilevanti con descrizione\n"
        "- tags: lista di 5-10 tag lowercase rilevanti\n"
        "- url_normattiva: URL su normattiva.it\n"
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


def persist_discovered_norme(discovered: list[dict], query_text: str = "") -> list[dict]:
    """
    Per ogni norma scoperta da Groq esegue (in ordine):
    1. Normalizzazione ID
    2. Check duplicato DB locale
    3. Check blocklist
    4. Validazione E — strict ID/estremi/titolo (anti-allucinazione strutturale)
    5. Normalizzazione URL normattiva
    6. Validazione D — similarity coseno query↔descrizione norma
    7. Verifica HTTP esistenza su normattiva.it
    8. Generazione embedding + insert Supabase
    """
    from api.utils.supabase_search import get_embedding, insert_norma_to_supabase

    # Pre-calcola embedding query una sola volta (riuso per tutti i candidati)
    query_embedding = None
    if query_text.strip():
        query_embedding = get_embedding(query_text)
        if query_embedding is None:
            print("[PERSIST] query_embedding fallito → similarity check D disabilitato", flush=True)

    persisted = []
    for norma in discovered:
        if not norma.get("id") or not norma.get("titolo"):
            print("[PERSIST] scheda senza id o titolo, skip", flush=True)
            continue

        # 1. Normalizza ID
        norma["id"] = _normalize_id(norma)

        # 2. Duplicato DB locale
        if _is_duplicate_of_local_db(norma):
            print(f"[PERSIST] {norma['id']!r} è duplicato DB locale, skip", flush=True)
            continue

        # 3. Blocklist
        if _is_blocklisted(norma):
            continue

        # 4. Validazione E (strict)
        if not _is_valid_norma_italiana(norma):
            continue

        # 5. Normalizza URL
        norma["url_normattiva"] = _normalize_url_normattiva(norma)
        norma.setdefault("url_ricerca", norma["url_normattiva"])

        # 6. Validazione D (similarity)
        if query_embedding and not _check_discover_similarity(norma, query_embedding):
            print(
                f"[PERSIST] {norma['id']!r} scartata: similarity < {DISCOVER_MIN_SIMILARITY}",
                flush=True,
            )
            continue

        # 7. Verifica HTTP
        if not _check_url_normattiva_exists(norma):
            print(
                f"[PERSIST] {norma['id']!r} scartata: URL non trovato su normattiva.it",
                flush=True,
            )
            continue

        # 8. Embedding + insert Supabase
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
