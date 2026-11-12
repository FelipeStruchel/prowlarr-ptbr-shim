"""Motor de busca: chama os sources habilitados pelo contrato comum
(search/fetch_post/latest) e monta os releases a partir dos magnets.

Entrada e saida sao as mesmas pra qualquer source - cada um em sources/ e
so o "meio" entre um termo de busca e uma lista de cards/magnets no formato
padrao (ver sources/_template.py). Como cada source produz isso (regex, API
proprio, etc.) e irrelevante aqui. Erros de um source especifico (HTTP,
timeout, parse) sao logados e ignorados; os outros sources continuam
normalmente.
"""
import logging
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from config import CFG
from sources import load_sites
from utils.text import SIZE_RE, fuzzy_pattern, norm, size_to_bytes

log = logging.getLogger("shim")

RES_RE = re.compile(r"\b(2160p|4K|1080p|720p|480p)\b", re.I)
SRC_RE = re.compile(r"\b(WEB-?DL|WEBRip|BluRay|Blu-Ray|BDRip|BRRip|HDTV|HDRip|DVDRip|REMUX|HDCAM|CAM)\b", re.I)
LANG_RE = re.compile(r"\b(PT-?BR|PTBR|portugu[eê]s|brazilian|brasil|dublado|nacional)\b", re.I)
DUAL_RE = re.compile(r"(dual|dublad|nacional)", re.I)
SEASON_TAG_RE = re.compile(r"\bS\d{1,2}(E\d{1,3})?\b|\b\d{1,2}x\d{2}\b|Temporada|Season", re.I)

_SITES = None


def enabled_sites():
    """Sources carregados (uma vez, na primeira chamada) e filtrados por CFG["sites"]."""
    global _SITES
    if _SITES is None:
        _SITES = load_sites()
    return [_SITES[s] for s in CFG["sites"] if s in _SITES]


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
                    found = site["search"](term)
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
                    c["_site"] = site
                    cards.setdefault(c["url"], (c, info))
    items = list(cards.values())[: CFG["max_posts"]]
    return fetch_and_build(items, p)


def fetch_and_build(items, p):
    results = []

    def work(ci):
        card, info = ci
        try:
            post = card["_site"]["fetch_post"](card)
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
    """Ultimos posts (RSS / teste do Prowlarr), respeitando as categorias pedidas.
    Sources sem "latest" (opcional no contrato) simplesmente nao aparecem aqui."""
    cats = [c for c in (p.get("cat") or "").split(",") if c]
    t = p.get("t")
    want_tv = t == "tvsearch" or any(c.startswith("5") for c in cats)
    want_movie = t == "movie" or any(c.startswith("2") for c in cats)
    if not want_tv and not want_movie:
        want_tv = want_movie = True
    picked = []
    for site in enabled_sites():
        latest = site.get("latest")
        if not latest:
            continue
        wants = ([False] if want_movie else []) + ([True] if want_tv else [])
        for is_tv in wants:
            try:
                cards = latest(is_tv)
            except Exception as e:  # noqa: BLE001
                log.warning("falha ao listar %s (is_tv=%s): %s", site["name"], is_tv, type(e).__name__)
                continue
            for c in cards:
                c["_site"] = site
            picked += cards[:5]
    items = [(c, {"kind": "tv" if c["is_tv"] else "movie", "pt": None, "orig": None}) for c in picked]
    return fetch_and_build(items, p)
