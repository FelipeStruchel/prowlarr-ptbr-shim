#!/usr/bin/env python3
"""Torznab shim: entrypoint HTTP. Scraping/TMDB/Prowlarr vivem nos modulos ao lado
(config.py, tmdb.py, scraper.py, prowlarr.py, torznab.py, sources/, utils/).

Somente biblioteca padrao. Configuracao em config.json (veja config.example.json).
"""
import logging
import os
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
from config import CFG
from prowlarr import fanout_results
from scraper import latest_results, site_results
from tmdb import resolve_titles
from torznab import caps_xml, error_xml, results_xml
from utils.logging_setup import setup_logging

HERE = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("shim")


def do_search(p):
    started = time.time()
    has_query = any(p.get(k) for k in ("q", "imdbid", "tmdbid", "tvdbid"))
    if not has_query:
        res = latest_results(p)
        log.info("RSS/teste: %d resultados", len(res))
        return res
    infos = resolve_titles(p)
    if not infos:
        return []
    log.info("busca %s -> %s", {k: v for k, v in p.items() if k in ("t", "q", "imdbid", "tmdbid", "tvdbid", "season", "ep")},
             [(i["kind"], i["pt"], i["orig"], i.get("year")) for i in infos])
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_site = ex.submit(site_results, infos, p)
        f_fan = ex.submit(fanout_results, infos, p) if CFG["prowlarr"]["enabled"] else None
        site = f_site.result()
        fan = f_fan.result() if f_fan else []
    log.info("resultados: site=%d prowlarr=%d em %.1fs", len(site), len(fan), time.time() - started)
    return (site + fan)[:100]


class Handler(BaseHTTPRequestHandler):
    server_version = "ptbr-shim/1.0"

    def log_message(self, fmt, *args):  # silencia o log padrao
        pass

    def reply(self, body, status=200, ctype="application/xml; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        url = urllib.parse.urlparse(self.path)
        p = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        if url.path == "/health":
            return self.reply("ok", ctype="text/plain")
        if url.path not in ("/", "/api"):
            return self.reply(error_xml(100, "not found"), 404)
        if p.get("apikey") != CFG["torznab_apikey"] and p.get("t") != "caps":
            return self.reply(error_xml(100, "Incorrect user credentials"), 401)
        t = p.get("t", "search")
        try:
            if t == "caps":
                return self.reply(caps_xml())
            if t in ("search", "tvsearch", "movie"):
                p["t"] = t
                return self.reply(results_xml(do_search(p)))
            return self.reply(error_xml(202, "No such function: " + t))
        except Exception as e:  # noqa: BLE001
            log.exception("erro em %s", t)
            return self.reply(error_xml(900, type(e).__name__ + ": " + str(e)[:150]), 500)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "config.json")
    config.apply_config(path)
    setup_logging(os.path.join(HERE, "shim.log"))
    if not CFG["tmdb_api_key"]:
        log.warning("tmdb_api_key vazio: a traducao PT-BR via TMDB esta desativada")
    srv = ThreadingHTTPServer((CFG["host"], CFG["port"]), Handler)
    srv.daemon_threads = True
    log.info("ouvindo em http://%s:%s", CFG["host"], CFG["port"])
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
