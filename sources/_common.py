"""Helpers reaproveitaveis para sources baseados em HTML simples (regex).

Nenhum source e obrigado a usar isso. O contrato real de um source e so a
forma dos dados que entram e saem de `search`/`fetch_post`/`latest` (ver
CONTRIBUTING.md); como ele produz esses dados e escolha de quem escreve o
source. `regex_source()` cobre o caso comum (card_re/title_re/year_re sobre
HTML estatico) com zero codigo customizado - se isso nao servir, ignore este
modulo e implemente search/fetch_post do seu jeito.
"""
import html
import re
import urllib.parse
from datetime import datetime

from config import CFG
from utils.cache import cache_get, cache_set
from utils.http import http_get
from utils.text import strip_tags

MAGNET_RE = re.compile(r'<a\s[^>]*href="(magnet:[^"]+)"[^>]*>(.*?)</a>', re.S | re.I)


def parse_cards(page, name, card_re, title_re, year_re):
    """HTML de uma pagina de busca/listagem -> lista de cards {url, title, year, is_tv, site}."""
    cards = []
    for block in card_re.findall(page):
        m = title_re.search(block)
        if not m:
            continue
        y = year_re.search(block)
        title = html.unescape(m.group(2)).strip()
        cards.append({"url": html.unescape(m.group(1)), "title": title,
                      "year": int(y.group(1)) if y else None,
                      "is_tv": bool(re.search(r"Temporada|Season", title, re.I)),
                      "site": name})
    return cards


def fetch_post_html(url):
    """URL de um post -> {orig, pub, magnets}, extraindo tudo via regex do HTML.
    Serve pra qualquer site que publica o magnet direto no HTML do post."""
    page = http_get(url, timeout=CFG["site_timeout"])
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
    return {"orig": orig, "pub": pub, "magnets": magnets}


def regex_source(name, base_url, movie_path, tv_path, card_re, title_re, year_re):
    """Monta um SOURCE completo (search/fetch_post/latest) a partir dos 3
    regexes classicos sobre HTML estatico. E o caminho facil - ver
    sources/baixetorrentshd.py como exemplo de uso."""
    base = base_url.rstrip("/")

    def search(term):
        url = base + "/?s=" + urllib.parse.quote_plus(term)
        ck = "site:" + url
        hit = cache_get(ck)
        if hit is not None:
            return hit
        cards = parse_cards(http_get(url, timeout=CFG["site_timeout"]), name, card_re, title_re, year_re)
        cache_set(ck, cards, 30)
        return cards

    def fetch_post(card):
        ck = "post:" + card["url"]
        hit = cache_get(ck)
        if hit is not None:
            return hit
        data = fetch_post_html(card["url"])
        cache_set(ck, data)
        return data

    def latest(is_tv):
        page = http_get(base + (tv_path if is_tv else movie_path), timeout=CFG["site_timeout"])
        return [c for c in parse_cards(page, name, card_re, title_re, year_re) if c["is_tv"] == is_tv]

    return {"name": name, "search": search, "fetch_post": fetch_post, "latest": latest}
