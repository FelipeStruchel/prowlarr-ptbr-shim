"""Auto-descoberta de sources: cada arquivo .py nesta pasta (exceto os que
comecam com "_") deve expor um dict SOURCE com name/search/fetch_post (e,
opcionalmente, latest) - ver sources/_template.py para o contrato completo.

Um source com erro de importacao (sintaxe, campo faltando, SOURCE ausente)
e ignorado e logado - nunca derruba o servidor inteiro.
"""
import importlib
import logging
import os

log = logging.getLogger("shim")

REQUIRED_CALLABLES = ("search", "fetch_post")


def load_sites():
    sites = {}
    pkg_dir = os.path.dirname(__file__)
    for fname in sorted(os.listdir(pkg_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        site_id = fname[:-3]
        try:
            mod = importlib.import_module(f"sources.{site_id}")
            site = mod.SOURCE
            if not site.get("name"):
                raise ValueError("campo 'name' faltando ou vazio no SOURCE")
            missing = [f for f in REQUIRED_CALLABLES if not callable(site.get(f))]
            if missing:
                raise ValueError("campo(s) faltando/invalido(s) no SOURCE: " + ", ".join(missing))
        except Exception as e:  # noqa: BLE001
            log.error("source '%s' ignorada (erro ao carregar): %s", site_id, e)
            continue
        sites[site_id] = site
    return sites
