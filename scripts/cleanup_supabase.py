"""
scripts/cleanup_supabase.py

Script di manutenzione del DB Supabase `norme`.
Elimina record con metadati errati inseriti da groq_discover.

Uso:
    SUPABASE_URL=... SUPABASE_KEY=... python scripts/cleanup_supabase.py

Opzioni:
    --dry-run   mostra cosa verrebbe eliminato/aggiornato senza eseguire
    --list      elenca tutti i record nella tabella norme
"""

import json
import os
import sys
import urllib.request

# ── Norme da eliminare (ID errati o metadati sbagliati inseriti da Groq)
# Formato: (norma_id, motivo)
TO_DELETE = [
    (
        "dlgs_285_1992",
        "D.Lgs. 285/1992 è il Codice della Strada: metadati nella scheda Supabase "
        "erano errati (descritto come TUEL). Il vero TUEL è dlgs_267_2000.",
    ),
]

# ── Norme da aggiornare (ID corretto -> nuovi metadati)
# Formato: (norma_id, dict_campi_da_aggiornare)
TO_UPDATE = [
    # esempio:
    # ("dpr_380_2001", {"url_normattiva": "https://..."}),
]


def _supa_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def _supa_key() -> str:
    return os.environ.get("SUPABASE_KEY", "")


def _headers() -> dict:
    key = _supa_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def list_norme() -> list:
    """Elenca tutti i record nella tabella norme."""
    url = f"{_supa_url()}/rest/v1/norme?select=norma_id,titolo,estremi&order=norma_id"
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def delete_norma(norma_id: str, dry_run: bool = False) -> bool:
    """Elimina un record dalla tabella norme per norma_id."""
    url = f"{_supa_url()}/rest/v1/norme?norma_id=eq.{norma_id}"
    if dry_run:
        print(f"  [DRY-RUN] DELETE norme WHERE norma_id = '{norma_id}'")
        return True
    req = urllib.request.Request(
        url,
        headers={**_headers(), "Prefer": "return=minimal"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  [DELETE] {norma_id!r} → HTTP {resp.status}")
            return resp.status in (200, 204)
    except Exception as exc:
        print(f"  [DELETE ERROR] {norma_id!r}: {exc}")
        return False


def update_norma(norma_id: str, fields: dict, dry_run: bool = False) -> bool:
    """Aggiorna campi di un record nella tabella norme."""
    url = f"{_supa_url()}/rest/v1/norme?norma_id=eq.{norma_id}"
    if dry_run:
        print(f"  [DRY-RUN] PATCH norme WHERE norma_id = '{norma_id}' SET {fields}")
        return True
    payload = json.dumps(fields).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={**_headers(), "Prefer": "return=minimal"},
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"  [UPDATE] {norma_id!r} → HTTP {resp.status}")
            return resp.status in (200, 204)
    except Exception as exc:
        print(f"  [UPDATE ERROR] {norma_id!r}: {exc}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv
    do_list = "--list" in sys.argv

    url = _supa_url()
    key = _supa_key()
    if not url or not key:
        print("ERRORE: SUPABASE_URL e SUPABASE_KEY devono essere impostate.")
        print("Uso: SUPABASE_URL=... SUPABASE_KEY=... python scripts/cleanup_supabase.py")
        sys.exit(1)

    print(f"Connesso a: {url[:50]}")
    print(f"Modalità: {'DRY-RUN' if dry_run else 'LIVE'}\n")

    if do_list:
        print("=== Elenco norme nel DB Supabase ===")
        records = list_norme()
        for r in records:
            print(f"  {r['norma_id']:<30} | {r['estremi']:<45} | {r['titolo']}")
        print(f"\nTotale: {len(records)} record")
        return

    # ── DELETE
    if TO_DELETE:
        print(f"=== DELETE ({len(TO_DELETE)} record) ===")
        for norma_id, motivo in TO_DELETE:
            print(f"\n  ID: {norma_id}")
            print(f"  Motivo: {motivo}")
            delete_norma(norma_id, dry_run=dry_run)

    # ── UPDATE
    if TO_UPDATE:
        print(f"\n=== UPDATE ({len(TO_UPDATE)} record) ===")
        for norma_id, fields in TO_UPDATE:
            print(f"\n  ID: {norma_id} → {fields}")
            update_norma(norma_id, fields, dry_run=dry_run)

    print("\nManutenzione completata.")
    if dry_run:
        print("(nessuna modifica eseguita — rimuovi --dry-run per applicare)")


if __name__ == "__main__":
    main()
