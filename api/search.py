"""Endpoint /api/search — ricerca normativa su Normattiva."""
from http.server import BaseHTTPRequestHandler
import json
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from utils.keywords import extract_keywords
from utils.normattiva import search_normattiva


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            testo = params.get("testo", [""])[0].strip()
            tipo_atto = params.get("tipo_atto", [""])[0].strip()
            oggetto = params.get("oggetto", [""])[0].strip()
            importo = params.get("importo", [""])[0].strip()

            if not testo and not oggetto:
                self._send_json({"error": "Parametro 'testo' obbligatorio"}, 400)
                return

            # Estrai parole chiave dal testo libero
            keywords = extract_keywords(testo, tipo_atto, oggetto, importo)

            # Esegui ricerca su Normattiva
            results = search_normattiva(keywords)

            self._send_json({
                "keywords": keywords,
                "results": results,
                "total": len(results)
            })

        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def do_OPTIONS(self):
        self.send_response(200)
        self._add_cors_headers()
        self.end_headers()

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self._add_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _add_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
