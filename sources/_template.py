r"""Modelo para um novo source.

Renomeie este arquivo para <site_id>.py (sem o "_" na frente - arquivos com
"_" sao ignorados pela auto-descoberta) e escolha uma das duas formas abaixo.
O unico contrato real e a forma dos dados: um dict SOURCE com

  name        -> str, nome exibido (aparece como "indexer" no resultado)
  search(term) -> list de cards {url, title, year, is_tv, site}
  fetch_post(card) -> {orig, pub, magnets: [{href, anchor, before}, ...]}
  latest(is_tv)  -> list de cards (opcional; so usado no feed de teste do
                     Prowlarr - se faltar, o source so nao aparece nesse feed)

Como search/fetch_post/latest sao implementados e livre - pode ser regex
sobre HTML, uma API JSON do proprio site, scraping com browser, o que for.

--- Opcao 1: HTML simples com regex (caso comum, zero codigo custom) -------

import re
from sources._common import regex_source

SOURCE = regex_source(
    name="NomeDoSite",
    base_url="https://exemplo.com",
    movie_path="/filmes/",
    tv_path="/series/",
    card_re=re.compile(r"<PLACEHOLDER>(.*?)</PLACEHOLDER>", re.S),
    title_re=re.compile(r'<a href="([^"]+)"[^>]*>([^<]+)</a>'),
    year_re=re.compile(r"\((\d{4})\)"),
)

Os regexes sao sempre escritos olhando o HTML real do site, nao o que se
imagina que ele deveria ser:
  card_re   -> isola o bloco HTML de UM card de resultado
  title_re  -> dentro do bloco, captura (url_do_post, titulo)
  year_re   -> dentro do bloco, captura o ano (pode nao casar)

--- Opcao 2: 100% customizado (API, paginacao propria, etc.) ---------------

def search(term):
    # devolver list de {"url": ..., "title": ..., "year": ..., "is_tv": ...,
    # "site": "NomeDoSite"}
    ...

def fetch_post(card):
    # devolver {"orig": str|None, "pub": timestamp|None,
    #           "magnets": [{"href": "magnet:?...", "anchor": str, "before": str}]}
    ...

SOURCE = {"name": "NomeDoSite", "search": search, "fetch_post": fetch_post}
# "latest" e opcional - inclua so se fizer sentido pro feed de teste do Prowlarr

Da pra misturar: usar sources._common.parse_cards/fetch_post_html dentro de um
search/fetch_post customizado, em vez de implementar tudo do zero.

IMPORTANTE: se o site usa link locker/encurtador de anuncio para liberar o
magnet (precisa "ver um anuncio" antes do link real aparecer), NAO adicione
esse site aqui - ver a secao correspondente em CONTRIBUTING.md.
"""
