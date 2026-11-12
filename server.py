#!/usr/bin/env python3
"""Torznab shim: traduz titulos via TMDB (pt-BR), raspa o BaixeTorrentsHD com dados reais
e (opcional) busca o titulo PT-BR nos outros indexadores do Prowlarr.

Somente biblioteca padrao. Configuracao em config.json (veja config.example.json).
"""
import html
import json
import logging
import logging.handlers
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape, quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

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
log = logging.getLogger("shim")


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


# ----------------------------------------------------------------------------- utils
def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def fuzzy_pattern(text):
    """Regex que casa o texto ignorando acentos, caixa e pontuacao."""
    tokens = [t for t in re.split(r"[^\w]+", text or "", flags=re.U) if t]
    out = []
    for tok in tokens:
        part = ""
        for ch in tok:
            base = "".join(c for c in unicodedata.normalize("NFD", ch) if unicodedata.category(c) != "Mn")
            chars = {ch, base, ch.lower(), base.lower()}
            part += "[" + re.escape("".join(chars)) + "]" if len(chars) > 1 else re.escape(ch)
        out.append(part)
    return r"[\W_]+".join(out)


_cache = {}
_cache_lock = threading.Lock()


def cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
    if item and item[0] > time.time():
        return item[1]
    return None


def cache_set(key, value, minutes=None):
    ttl = (minutes if minutes is not None else CFG["cache_minutes"]) * 60
    with _cache_lock:
        _cache[key] = (time.time() + ttl, value)


def http_get(url, headers=None, timeout=20, retries=1):
    h = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}
    h.update(headers or {})
    last = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                return r.read().decode(charset, errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.4)
    raise last


# ----------------------------------------------------------------------------- TMDB
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


# ----------------------------------------------------------------------------- site
SITE_DEFS = {
    "baixetorrentshd": {
        "name": "BaixeTorrentsHD",
        "base_url": "https://www.baixetorrentshd.com",
        "movie_path": "/categoria/filmes/",
        "tv_path": "/categoria/series/",
        "card_re": re.compile(r'<article class="movie-card">(.*?)</article>', re.S),
        "title_re": re.compile(r'movie-card__title"><a href="([^"]+)">([^<]+)</a>'),
        "year_re": re.compile(r'movie-card__badge">(\d{4})<'),
    },
    "torrentfilmehds": {
        "name": "TorrentFilmesHD",
        "base_url": "https://www.torrentfilmehds.net",
        "movie_path": "/genero/filmes/",
        "tv_path": "/genero/series/",
        "card_re": re.compile(r'<article class="item">(.*?)</article>', re.S),
        "title_re": re.compile(r'<a href="([^"]+)"[^>]*>.*?<div class="titulo"><span>([^<]+)</span>', re.S),
        "year_re": re.compile(r'<div class="imagem"><span>(\d{4})</span>'),
    },
    "baixafilmestorrent": {
        "name": "BaixaFilmesTorrent",
        "base_url": "https://baixafilmestorrent.com",
        "movie_path": "/filmes/",
        "tv_path": "/series/",
        # os cards de "mais acessados"/"relacionados" usam o mesmo div.item, mas com
        # title="Link para ..." - o lookahead abaixo os exclui dos resultados de busca
        "card_re": re.compile(r'<div class="item">(.*?)</a>\s*</div>', re.S),
        "title_re": re.compile(r'<a href="([^"]+)" title="(?!Link para )([^"]+?)\s+Torrent\b', re.S),
        "year_re": re.compile(r"\((\d{4})\)"),
    },
}
MAGNET_RE = re.compile(r'<a\s[^>]*href="(magnet:[^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB)", re.I)
RES_RE = re.compile(r"\b(2160p|4K|1080p|720p|480p)\b", re.I)
SRC_RE = re.compile(r"\b(WEB-?DL|WEBRip|BluRay|Blu-Ray|BDRip|BRRip|HDTV|HDRip|DVDRip|REMUX|HDCAM|CAM)\b", re.I)
LANG_RE = re.compile(r"\b(PT-?BR|PTBR|portugu[eê]s|brazilian|brasil|dublado|nacional)\b", re.I)
DUAL_RE = re.compile(r"(dual|dublad|nacional)", re.I)
SEASON_TAG_RE = re.compile(r"\bS\d{1,2}(E\d{1,3})?\b|\b\d{1,2}x\d{2}\b|Temporada|Season", re.I)


def enabled_sites():
    return [SITE_DEFS[s] for s in CFG["sites"] if s in SITE_DEFS]


def parse_cards(page, site):
    cards = []
    for block in site["card_re"].findall(page):
        m = site["title_re"].search(block)
        if not m:
            continue
        y = site["year_re"].search(block)
        title = html.unescape(m.group(2)).strip()
        cards.append({"url": html.unescape(m.group(1)), "title": title,
                      "year": int(y.group(1)) if y else None,
                      "is_tv": bool(re.search(r"Temporada|Season", title, re.I)),
                      "site": site["name"]})
    return cards


def site_search(term, site):
    url = site["base_url"].rstrip("/") + "/?s=" + urllib.parse.quote_plus(term)
    ck = "site:" + url
    hit = cache_get(ck)
    if hit is not None:
        return hit
    cards = parse_cards(http_get(url), site)
    cache_set(ck, cards, 30)
    return cards


def base_title(title):
    t = re.sub(r"\s*\(\d{4}\)\s*$", "", title)
    t = re.sub(r"\s*\d+\s*ª?\s*(?:até\s*\d+\s*ª?\s*)?Temporada.*$", "", t, flags=re.I)
    return norm(t)


def season_range(title):
    m = re.search(r"(\d+)\s*ª?\s*(?:até|a|-)\s*(\d+)\s*ª?\s*Temporada", title, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)\s*ª?\s*Temporada", title, re.I)
    if m:
        n = int(m.group(1))
        return n, n
    return None


def size_to_bytes(num, unit):
    v = float(num.replace(",", "."))
    return int(v * {"MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}[unit.upper()])


def strip_tags(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def fetch_post(card):
    ck = "post:" + card["url"]
    hit = cache_get(ck)
    if hit is not None:
        return hit
    page = http_get(card["url"])
    orig = None
    m = re.search(r"T[ií]tulo original:\s*([^<]+)", page)
    if m:
        orig = html.unescape(m.group(1)).strip()
    pub = None
    m = re.search(r'article:published_time"\s+content="([^"]+)"', page) or \
        re.search(r'content="([^"]+)"\s+property="article:published_time"', page)
    if m:
        try:
            pub = datetime.fromisoformat(m.group(1)).timestamp()
        except ValueError:
            pub = None
    magnets = []
    for m in MAGNET_RE.finditer(page):
        href = html.unescape(m.group(1))
        anchor = strip_tags(m.group(2))
        before = strip_tags(page[max(0, m.start() - 400): m.start()])[-230:]
        magnets.append({"href": href, "anchor": anchor, "before": before})
    data = {"orig": orig, "pub": pub, "magnets": magnets}
    cache_set(ck, data)
    return data


def build_release(card, post, mg, info):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(mg["href"]).query)
    xt = (q.get("xt") or [""])[0]
    m = re.search(r"btih:([0-9a-fA-F]{40}|[A-Za-z2-7]{32})", xt)
    if not m:
        return None
    infohash = m.group(1).lower() if len(m.group(1)) == 40 else m.group(1)
    dn = (q.get("dn") or [""])[0].strip()
    xl = (q.get("xl") or [""])[0]
    ctx = (mg["anchor"] + " | " + mg["before"])
    # descricao mais proxima do magnet: o texto do proprio botao vale mais que o contexto anterior
    desc = mg["anchor"] if SIZE_RE.search(mg["anchor"]) or RES_RE.search(mg["anchor"]) else mg["before"]

    size = int(xl) if xl.isdigit() else 0
    if not size:
        sizes = SIZE_RE.findall(desc)
        if sizes:
            size = size_to_bytes(*sizes[-1])
    res = RES_RE.findall(desc) or RES_RE.findall(dn) or RES_RE.findall(ctx)
    res = (res[-1] if res else "").lower().replace("4k", "2160p")
    src = SRC_RE.findall(desc) or SRC_RE.findall(dn)
    src = src[-1] if src else ""
    is_dual = bool(DUAL_RE.search(desc) or DUAL_RE.search(dn) or DUAL_RE.search(card["title"]))

    rng = season_range(card["title"]) if card["is_tv"] else None
    name = post.get("orig") or info.get("orig") or re.sub(r"\s*\(\d{4}\)\s*$", "", card["title"])
    if card["is_tv"]:
        name = re.sub(r"\s*\d+\s*ª?\s*(?:até\s*\d+\s*ª?\s*)?Temporada.*$", "", name, flags=re.I)
    year = card["year"]

    if dn:
        title = dn
    else:
        parts = [name.replace(" ", ".")]
        if not card["is_tv"] and year:
            parts.append(str(year))
        if rng:
            parts.append("S%02d" % rng[0] if rng[0] == rng[1] else "S%02d-S%02d" % rng)
        parts += [p for p in (res, src.upper() if src else "", "DUAL" if is_dual else "") if p]
        title = ".".join(parts)
    if card["is_tv"] and rng and not SEASON_TAG_RE.search(title):
        title += ".S%02d" % rng[0] if rng[0] == rng[1] else ".S%02d-S%02d" % rng
    # fonte desconhecida (nem no nome nem na descricao do post): assume a configurada, para nao cair em HDTV
    if CFG["assume_source"] and not SRC_RE.search(title):
        if RES_RE.search(title):
            title = RES_RE.sub(lambda m: m.group(0) + "." + CFG["assume_source"], title, count=1)
        else:
            title += "." + CFG["assume_source"]
    if CFG["language_tag"] and is_dual and not LANG_RE.search(title):
        title += "." + CFG["language_tag"]
    title = maybe_rewrite(title, info)

    tv = card["is_tv"]
    base = 5000 if tv else 2000
    sub = {"2160p": 45, "1080p": 40, "720p": 40}.get(res, 30)
    return {
        "title": title, "infohash": infohash, "magnet": mg["href"], "size": size,
        "pub": post.get("pub") or time.time(), "cats": [base, base + sub],
        "details": card["url"], "indexer": card["site"],
        "seeders": CFG["default_seeders"], "leechers": CFG["default_seeders"], "link": None,
        "season": rng, "tv": tv,
    }


def maybe_rewrite(title, info):
    """Troca o nome PT-BR do inicio do release pelo original (ajuda o Radarr/Sonarr a casar o titulo)."""
    if not CFG["rewrite_titles"]:
        return title
    pt, orig = info.get("pt"), info.get("orig")
    if not pt or not orig or norm(pt) == norm(orig):
        return title
    if re.search(fuzzy_pattern(orig), title, re.I):
        return title  # o nome original ja aparece no release
    pat = re.compile(r"^\W*" + fuzzy_pattern(pt), re.I)
    return pat.sub(orig.replace("\\", " "), title, count=1) if pat.search(title) else title


def site_results(infos, p):
    cards = {}
    for info in infos:
        terms = []
        for t in (info.get("pt"), info.get("orig"), info.get("q_clean")):
            if t and t not in terms:
                terms.append(t)
        keys = [norm(info.get("pt")), norm(info.get("orig"))]
        keys = [k for k in keys if k]
        for site in enabled_sites():
            for term in terms:
                try:
                    found = site_search(term, site)
                except Exception as e:  # noqa: BLE001
                    log.warning("busca em %s falhou (%s): %s", site["name"], term, type(e).__name__)
                    continue
                for c in found:
                    nt = " " + norm(c["title"]) + " "
                    if keys and not any(" " + k + " " in nt for k in keys):
                        continue
                    if (info["kind"] == "tv") != c["is_tv"]:
                        continue
                    if info["kind"] == "movie" and info.get("year") and c["year"] and abs(c["year"] - info["year"]) > 1:
                        continue
                    if info["kind"] == "tv" and info.get("season"):
                        rng = season_range(c["title"])
                        if rng and not (rng[0] <= info["season"] <= rng[1]):
                            continue
                    info["keys"] = keys
                    cards.setdefault(c["url"], (c, info))
    items = list(cards.values())[: CFG["max_posts"]]
    return fetch_and_build(items, p)


def fetch_and_build(items, p):
    results = []

    def work(ci):
        card, info = ci
        try:
            post = fetch_post(card)
        except Exception as e:  # noqa: BLE001
            log.warning("falha ao abrir %s: %s", card["url"], type(e).__name__)
            return []
        out = []
        keys = info.get("keys")
        if keys and base_title(card["title"]) not in keys and norm(post.get("orig")) not in keys:
            log.info("descartado (titulo nao confere): %s", card["title"])
            return []
        for mg in post["magnets"]:
            r = build_release(card, post, mg, info)
            if not r:
                continue
            ep = info.get("ep")
            mm = re.search(r"\bS\d{1,2}E(\d{1,3})\b", r["title"], re.I)
            if ep and mm and int(mm.group(1)) != ep:
                continue
            out.append(r)
        return out

    with ThreadPoolExecutor(max_workers=6) as ex:
        for chunk in ex.map(work, items):
            results.extend(chunk)
    return results


def latest_results(p):
    """Ultimos posts (RSS / teste do Prowlarr), respeitando as categorias pedidas."""
    cats = [c for c in (p.get("cat") or "").split(",") if c]
    t = p.get("t")
    want_tv = t == "tvsearch" or any(c.startswith("5") for c in cats)
    want_movie = t == "movie" or any(c.startswith("2") for c in cats)
    if not want_tv and not want_movie:
        want_tv = want_movie = True
    picked = []
    for site in enabled_sites():
        base = site["base_url"].rstrip("/")
        pages = []
        if want_movie:
            pages.append((site["movie_path"], False))
        if want_tv:
            pages.append((site["tv_path"], True))
        for path, is_tv in pages:
            try:
                cards = [c for c in parse_cards(http_get(base + path), site) if c["is_tv"] == is_tv]
            except Exception as e:  # noqa: BLE001
                log.warning("falha ao listar %s%s: %s", base, path, type(e).__name__)
                continue
            picked += cards[:5]
    items = [(c, {"kind": "tv" if c["is_tv"] else "movie", "pt": None, "orig": None}) for c in picked]
    return fetch_and_build(items, p)


# ----------------------------------------------------------------------------- Prowlarr
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


# ----------------------------------------------------------------------------- Torznab
def caps_xml():
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.0" title="BaixeTorrentsHD PT-BR" />
  <limits max="100" default="100" />
  <searching>
    <search available="yes" supportedParams="q" />
    <tv-search available="yes" supportedParams="q,season,ep,imdbid,tmdbid,tvdbid" />
    <movie-search available="yes" supportedParams="q,imdbid,tmdbid,year" />
  </searching>
  <categories>
    <category id="2000" name="Movies">
      <subcat id="2030" name="SD" /><subcat id="2040" name="HD" /><subcat id="2045" name="UHD" />
    </category>
    <category id="5000" name="TV">
      <subcat id="5030" name="SD" /><subcat id="5040" name="HD" /><subcat id="5045" name="UHD" />
    </category>
  </categories>
</caps>"""


def error_xml(code, desc):
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<error code="{code}" description={quoteattr(desc)} />'


def results_xml(results):
    seen, items = set(), []
    for r in results:
        key = r["infohash"] or r.get("guid") or r["title"]
        if key in seen:
            continue
        seen.add(key)
        link = r.get("link") or r["magnet"]
        guid = r.get("guid") or r["infohash"] or r["title"]
        attrs = "".join(f'<torznab:attr name="category" value="{c}" />' for c in r["cats"])
        attrs += f'<torznab:attr name="seeders" value="{r["seeders"]}" />'
        attrs += f'<torznab:attr name="peers" value="{(r["seeders"] or 0) + (r["leechers"] or 0)}" />'
        attrs += f'<torznab:attr name="size" value="{r["size"]}" />'
        if r["infohash"]:
            attrs += f'<torznab:attr name="infohash" value="{r["infohash"]}" />'
        if r.get("magnet"):
            attrs += f'<torznab:attr name="magneturl" value={quoteattr(r["magnet"])} />'
        items.append(
            "<item>"
            f"<title>{escape(r['title'])}</title>"
            f'<guid isPermaLink="false">{escape(str(guid))}</guid>'
            f"<link>{escape(link)}</link>"
            f"<comments>{escape(r.get('details') or '')}</comments>"
            f"<pubDate>{formatdate(r['pub'], usegmt=True)}</pubDate>"
            f"<size>{r['size']}</size>"
            f"<description>{escape(r['indexer'])}</description>"
            f'<enclosure url={quoteattr(link)} length="{r["size"]}" type="application/x-bittorrent" />'
            f"{attrs}</item>"
        )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:torznab="http://torznab.com/schemas/2015/feed">'
            "<channel><title>BaixeTorrentsHD PT-BR</title>"
            f'<torznab:response offset="0" total="{len(items)}" />' + "".join(items) + "</channel></rss>")


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
    global CFG
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "config.json")
    CFG = load_config(path)
    handler = logging.handlers.RotatingFileHandler(os.path.join(HERE, "shim.log"), maxBytes=1_000_000,
                                                   backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)
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
