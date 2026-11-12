import re

from sources._common import regex_source

SOURCE = regex_source(
    name="BaixaFilmesTorrent",
    base_url="https://baixafilmestorrent.com",
    movie_path="/filmes/",
    tv_path="/series/",
    # os cards de "mais acessados"/"relacionados" usam o mesmo div.item, mas com
    # title="Link para ..." - o lookahead abaixo os exclui dos resultados de busca
    card_re=re.compile(r'<div class="item">(.*?)</a>\s*</div>', re.S),
    title_re=re.compile(r'<a href="([^"]+)" title="(?!Link para )([^"]+?)\s+Torrent\b', re.S),
    year_re=re.compile(r"\((\d{4})\)"),
)
