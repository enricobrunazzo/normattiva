"""
Endpoint di ingest: popola gli embedding per tutte le norme senza embedding.

GET/POST /api/ingest
  - Richiede header X-Ingest-Key: <INGEST_SECRET> oppure param ?key=<INGEST_SECRET>
  - Chiama la Edge Function embed per ogni norma priva di embedding
  - Fa PATCH su Supabase per aggiornare il campo embedding
  - Restituisce un report JSON con i risultati

Variabili d'ambiente richieste:
  SUPABASE_URL, SUPABASE_KEY, INGEST_SECRET (opzionale, default 'normattiva-ingest')
"""

import json
import os
import time
import urllib.parse
import urllib.request

from http.server import BaseHTTPRequestHandler

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
INGEST_SECRET = os.environ.get("INGEST_SECRET", "normattiva-ingest")

_HEADERS_SUPA = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def _json_response(handler: BaseHTTPRequestHandler, data: dict, status: int = 200):
    body = json.dumps(data, ensure_ascii=False, indent=2).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _get_norme_senza_embedding() -> list[dict]:
    """Recupera tutte le norme con embedding NULL."""
    url = (
        f"{SUPABASE_URL}/rest/v1/norme"
        "?select=norma_id,titolo,estremi,descrizione,articoli_chiave"
        "&embedding=is.null"
        "&limit=100"
    )
    req = urllib.request.Request(url, headers=_HEADERS_SUPA, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _get_embedding(text: str) -> list[float] | None:
    """Chiama la Edge Function embed su Supabase."""
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
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode())
        emb = body.get("embedding")
        if emb is None:
            emb = body.get("data", [{}])[0].get("embedding")
        return emb
    except Exception as exc:
        print(f"[EMBED ERROR] {type(exc).__name__}: {exc}", flush=True)
        return None


def _update_embedding(norma_id: str, embedding: list[float]) -> bool:
    """Aggiorna il campo embedding per norma_id."""
    # pgvector richiede il formato stringa "[v1,v2,...]"
    vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
    payload = json.dumps({"embedding": vector_str}).encode()
    url = (
        f"{SUPABASE_URL}/rest/v1/norme"
        f"?norma_id=eq.{urllib.parse.quote(norma_id)}"
    )
    req = urllib.request.Request(
        url,
        data=payload,
        headers={**_HEADERS_SUPA, "Prefer": "return=minimal"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as exc:
        print(f"[PATCH ERROR] {norma_id}: {type(exc).__name__}: {exc}", flush=True)
        return False


def _run_ingest() -> dict:
    """Esegue l'ingest completo. Restituisce report."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"error": "SUPABASE_URL o SUPABASE_KEY non configurate", "processed": 0}

    t0 = time.time()
    try:
        norme = _get_norme_senza_embedding()
    except Exception as exc:
        return {"error": f"Impossibile leggere le norme: {exc}", "processed": 0}

    total = len(norme)
    print(f"[INGEST] Norme senza embedding: {total}", flush=True)

    if total == 0:
        return {
            "message": "Tutti gli embedding sono già presenti.",
            "processed": 0,
            "elapsed_ms": int((time.time() - t0) * 1000),
        }

    ok_list, fail_list = [], []

    for norma in norme:
        norma_id = norma["norma_id"]
        # Testo per embedding: titolo + estremi + descrizione + articoli chiave
        parts = [
            norma.get("titolo", ""),
            norma.get("estremi", ""),
            norma.get("descrizione", ""),
        ]
        articoli = norma.get("articoli_chiave") or []
        if articoli:
            parts.append(" ".join(articoli))
        embed_text = " ".join(p for p in parts if p)

        print(f"[INGEST] Embedding {norma_id!r}...", flush=True)
        embedding = _get_embedding(embed_text)

        if embedding is None:
            print(f"[INGEST] FAIL embed {norma_id!r}", flush=True)
            fail_list.append({"id": norma_id, "error": "embed fallito"})
            continue

        ok = _update_embedding(norma_id, embedding)
        if ok:
            print(f"[INGEST] OK {norma_id!r} ({len(embedding)} dim)", flush=True)
            ok_list.append(norma_id)
        else:
            fail_list.append({"id": norma_id, "error": "PATCH fallito"})

        time.sleep(0.2)  # rate-limit gentile verso la Edge Function

    elapsed = int((time.time() - t0) * 1000)
    print(f"[INGEST] Done: {len(ok_list)} ok, {len(fail_list)} fail in {elapsed}ms", flush=True)

    return {
        "total_senza_embedding": total,
        "processed_ok": len(ok_list),
        "processed_fail": len(fail_list),
        "ok": ok_list,
        "fail": fail_list,
        "elapsed_ms": elapsed,
    }


class HandlerClass(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: N802
        print(f"[INGEST HTTP] {fmt % args}", flush=True)

    def _check_auth(self) -> bool:
        # Controlla header X-Ingest-Key o query param key
        key_header = self.headers.get("X-Ingest-Key", "")
        qs = urllib.parse.parse_qs(
            urllib.parse.urlparse(self.path).query
        )
        key_param = qs.get("key", [""])[0]
        return (key_header == INGEST_SECRET) or (key_param == INGEST_SECRET)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Ingest-Key, Content-Type")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if not self._check_auth():
            _json_response(self, {"error": "Unauthorized: X-Ingest-Key mancante o errata"}, 401)
            return
        result = _run_ingest()
        _json_response(self, result)

    def do_POST(self):  # noqa: N802
        if not self._check_auth():
            _json_response(self, {"error": "Unauthorized: X-Ingest-Key mancante o errata"}, 401)
            return
        result = _run_ingest()
        _json_response(self, result)

handler = HandlerClass
