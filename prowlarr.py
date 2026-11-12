"""Fanout opcional: busca o titulo PT-BR nos demais indexadores do Prowlarr."""
import json
import logging
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from config import CFG
from scraper import maybe_rewrite
from utils.cache import cache_get, cache_set
from utils.http import http_get
from utils.text import norm

log = logging.getLogger("shim")


def prowlarr_key():
    pc = CFG["prowlarr"]
    if pc["api_key"]:
        return pc["api_key"]
    try:
        with open(pc["config_xml"], encoding="utf-8") as f:
            m = re.search(r"<ApiKey>([^<]+)</ApiKey>", f.read())
        return m.group(1) if m else ""
    except OSError:
        return ""


def prowlarr_get(path, params, timeout):
    base = CFG["prowlarr"]["url"].rstrip("/")
    qs = urllib.parse.urlencode(params, doseq=True)
    return json.loads(http_get(f"{base}/api/v1{path}?{qs}", headers={"X-Api-Key": prowlarr_key()},
                               timeout=timeout, retries=0))


def prowlarr_indexer_ids(timeout):
    hit = cache_get("prowlarr:indexers")
    if hit is not None:
        return hit
    ex = [e.lower() for e in CFG["prowlarr"]["exclude_names"]]
    ids = []
    for ix in prowlarr_get("/indexer", {}, timeout):
        name = (ix.get("name") or "").lower()
        if ix.get("enable") and ix.get("protocol") == "torrent" and not any(e in name for e in ex):
            ids.append(ix["id"])
    cache_set("prowlarr:indexers", ids, 10)
    return ids


def fanout_results(infos, p):
    pc = CFG["prowlarr"]
    results = []
    try:
        ids = prowlarr_indexer_ids(10)
    except Exception as e:  # noqa: BLE001
        log.warning("nao foi possivel listar indexadores do Prowlarr: %s", type(e).__name__)
        return []
    if not ids:
        return []
    for info in infos:
        pt, orig = info.get("pt"), info.get("orig")
        if not pt or norm(pt) == norm(orig or ""):
            continue  # sem traducao: os indexadores normais ja cobrem
        if info["kind"] == "movie":
            query = pt + (" %d" % info["year"] if info.get("year") else "")
            cats = [2000]
        else:
            query = pt
            if info.get("season"):
                query += " S%02d" % info["season"] + ("E%02d" % info["ep"] if info.get("ep") else "")
            cats = [5000]

        def one(iid, query=query, cats=cats):
            return prowlarr_get("/search", {"query": query, "type": "search", "categories": cats,
                                            "indexerIds": [iid]}, pc["per_indexer_timeout"])

        ex = ThreadPoolExecutor(max_workers=min(12, len(ids)))
        futs = [ex.submit(one, i) for i in ids]
        deadline = time.time() + pc["timeout"]
        raw = []
        for f in futs:
            try:
                raw.extend(f.result(timeout=max(0.1, deadline - time.time())))
            except Exception:  # noqa: BLE001 - indexador lento/fora do ar nao derruba a busca
                pass
        ex.shutdown(wait=False, cancel_futures=True)
        for r in raw:
            if r.get("protocol") != "torrent":
                continue
            title = maybe_rewrite(r.get("title") or "", info)
            link = r.get("downloadUrl") or r.get("magnetUrl")
            if not link:
                continue
            pub = time.time()
            try:
                pub = datetime.fromisoformat((r.get("publishDate") or "").replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
            results.append({
                "title": title, "infohash": (r.get("infoHash") or "").lower(), "magnet": r.get("magnetUrl"),
                "size": r.get("size") or 0, "pub": pub, "cats": [cats[0]],
                "details": r.get("infoUrl") or r.get("guid") or "", "indexer": r.get("indexer") or "Prowlarr",
                "seeders": r.get("seeders") if r.get("seeders") is not None else CFG["default_seeders"],
                "leechers": r.get("leechers") if r.get("leechers") is not None else 0,
                "link": link, "guid": r.get("guid"), "season": None, "tv": info["kind"] == "tv",
            })
    results.sort(key=lambda x: x["seeders"] or 0, reverse=True)
    return results[: pc["max_results"]]
