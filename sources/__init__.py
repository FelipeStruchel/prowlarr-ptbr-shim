"""Auto-descoberta de sources: cada arquivo .py nesta pasta (exceto os que
comecam com "_") deve expor um dict SITE com os campos obrigatorios abaixo.

Um source com erro de importacao (sintaxe, regex invalido, campo faltando)
e ignorado e logado - nunca derruba o servidor inteiro.
"""
import importlib
import logging
import os

log = logging.getLogger("shim")

REQUIRED_FIELDS = ("name", "base_url", "movie_path", "tv_path", "card_re", "title_re", "year_re")


def load_sites():
    sites = {}
    pkg_dir = os.path.dirname(__file__)
    for fname in sorted(os.listdir(pkg_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        site_id = fname[:-3]
        try:
            mod = importlib.import_module(f"sources.{site_id}")
            site = mod.SITE
            missing = [f for f in REQUIRED_FIELDS if f not in site]
            if missing:
                raise ValueError("campo(s) faltando no SITE: " + ", ".join(missing))
        except Exception as e:  # noqa: BLE001
            log.error("source '%s' ignorada (erro ao carregar): %s", site_id, e)
            continue
        sites[site_id] = site
    return sites
