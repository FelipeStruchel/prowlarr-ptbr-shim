"""Configuracao do shim: defaults e carregamento do config.json.

CFG e um dict mutado em-lugar (clear+update) por apply_config(), nunca
reatribuido - assim todo modulo que fizer `from config import CFG` continua
vendo os valores atuais depois do load, independente da ordem de import.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "host": "127.0.0.1",
    "port": 9797,
    "torznab_apikey": "ptbr-shim",
    "tmdb_api_key": "",
    "sites": ["baixetorrentshd", "torrentfilmehds", "baixafilmestorrent"],
    "language_tag": "Brazilian",
    "assume_source": "BluRay",
    "default_seeders": 1,
    "max_posts": 8,
    "cache_minutes": 360,
    "rewrite_titles": True,
    "site_timeout": 15,
    "prowlarr": {
        "enabled": True,
        "url": "http://localhost:9696",
        "api_key": "",
        "config_xml": r"C:\ProgramData\Prowlarr\config.xml",
        "exclude_names": ["BaixeTorrentsHD"],
        "timeout": 30,
        "per_indexer_timeout": 25,
        "max_results": 60,
    },
}

CFG = {}


def load_config(path):
    cfg = json.loads(json.dumps(DEFAULTS))
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def apply_config(path):
    CFG.clear()
    CFG.update(load_config(path))
    return CFG
