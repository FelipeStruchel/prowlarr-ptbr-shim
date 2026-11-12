"""Resolucao de titulos via TMDB (pt-BR) a partir dos parametros Torznab."""
import json
import logging
import re
import urllib.parse

from config import CFG
from utils.cache import cache_get, cache_set
from utils.http import http_get
from utils.text import norm

log = logging.getLogger("shim")


def tmdb(path, **params):
    key = CFG["tmdb_api_key"]
    if not key:
        return None
    headers = {}
    params = {k: v for k, v in params.items() if v not in (None, "")}
    if key.startswith("eyJ"):  # token v4 (Bearer)
        headers["Authorization"] = "Bearer " + key
    else:
        params["api_key"] = key
    url = "https://api.themoviedb.org/3" + path + "?" + urllib.parse.urlencode(params)
    ck = "tmdb:" + path + json.dumps(sorted((k, v) for k, v in params.items() if k != "api_key"))
    hit = cache_get(ck)
    if hit is not None:
        return hit
    try:
        data = json.loads(http_get(url, headers=headers, timeout=15))
    except Exception as e:  # noqa: BLE001
        log.warning("TMDB falhou em %s: %s", path, type(e).__name__)
        return None
    cache_set(ck, data, 24 * 60)
    return data


def info_from(kind, d, year_hint=None):
    if kind == "movie":
        pt, orig = d.get("title"), d.get("original_title")
        date = d.get("release_date") or ""
    else:
        pt, orig = d.get("name"), d.get("original_name")
        date = d.get("first_air_date") or ""
    year = int(date[:4]) if date[:4].isdigit() else year_hint
    return {"kind": kind, "pt": pt, "orig": orig, "year": year, "tmdb_id": d.get("id")}


def parse_query(q):
    """Extrai ano, temporada e episodio de um texto livre de busca."""
    q = q or ""
    season = ep = year = None
    m = re.search(r"\bS(\d{1,2})(?:E(\d{1,3}))?\b", q, re.I)
    if m:
        season = int(m.group(1))
        ep = int(m.group(2)) if m.group(2) else None
        q = q.replace(m.group(0), " ")
    m = re.search(r"\b(19\d{2}|20\d{2})\b\s*$", q.strip())
    if m:
        year = int(m.group(1))
        q = q.strip()[: m.start()]
    return re.sub(r"\s+", " ", q).strip(), year, season, ep


def resolve_titles(p):
    """Devolve lista de dicts {kind, pt, orig, year} para a busca."""
    t = p.get("t", "search")
    cats = [c for c in (p.get("cat") or "").split(",") if c]
    if t == "movie":
        kinds = ["movie"]
    elif t == "tvsearch":
        kinds = ["tv"]
    else:
        kinds = []
        if any(c.startswith("2") for c in cats):
            kinds.append("movie")
        if any(c.startswith("5") for c in cats):
            kinds.append("tv")
        kinds = kinds or ["movie", "tv"]

    q_clean, q_year, q_season, q_ep = parse_query(p.get("q"))
    year_hint = int(p["year"]) if str(p.get("year", "")).isdigit() else q_year
    out = []

    imdb = (p.get("imdbid") or "").strip()
    if imdb and not imdb.startswith("tt"):
        imdb = "tt" + imdb
    tmdbid = (p.get("tmdbid") or "").strip()
    tvdbid = (p.get("tvdbid") or "").strip()

    for kind in kinds:
        d = None
        if tmdbid.isdigit():
            d = tmdb(f"/{kind}/{tmdbid}", language="pt-BR")
        elif imdb:
            r = tmdb(f"/find/{imdb}", external_source="imdb_id", language="pt-BR")
            res = (r or {}).get(kind + "_results") or []
            d = res[0] if res else None
        elif tvdbid.isdigit() and kind == "tv":
            r = tmdb(f"/find/{tvdbid}", external_source="tvdb_id", language="pt-BR")
            res = (r or {}).get("tv_results") or []
            d = res[0] if res else None
        elif q_clean:
            r = tmdb(f"/search/{kind}", query=q_clean, language="pt-BR",
                     year=year_hint if kind == "movie" else None,
                     first_air_date_year=year_hint if kind == "tv" else None)
            res = (r or {}).get("results") or []
            if res:
                nq = norm(q_clean)
                exact = [x for x in res if nq in (norm(x.get("title") or x.get("name")),
                                                  norm(x.get("original_title") or x.get("original_name")))]
                d = (exact or res)[0]
        if d:
            info = info_from(kind, d, year_hint)
        elif q_clean:
            info = {"kind": kind, "pt": q_clean, "orig": q_clean, "year": year_hint, "tmdb_id": None}
        else:
            continue
        info["q_clean"] = q_clean
        info["season"] = int(p["season"]) if str(p.get("season", "")).isdigit() else q_season
        info["ep"] = int(p["ep"]) if str(p.get("ep", "")).isdigit() else q_ep
        out.append(info)
    return out
