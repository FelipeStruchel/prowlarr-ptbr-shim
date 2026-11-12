"""Modelo para um novo source.

Renomeie este arquivo para <site_id>.py (sem o "_" na frente - arquivos com
"_" sao ignorados pela auto-descoberta) e ajuste os campos de SITE abaixo.
Prefira gerar a partir do template com scripts/new_source.py.

Como preencher os regexes (sempre em cima do HTML real do site, nao do que
voce imagina que ele deveria ser):

  card_re   -> isola o bloco HTML de UM card de resultado na pagina de busca
               (/?s=<termo>) e nas paginas de listagem (movie_path/tv_path)
  title_re  -> dentro do bloco do card, captura (url_do_post, titulo)
  year_re   -> dentro do bloco do card, captura o ano (pode nao casar; os
               cards ainda sao aceitos sem ano)

Se o site usa link locker/encurtador para liberar o magnet (ex.: precisa
ver um anuncio antes do link real aparecer), NAO adicione esse site aqui -
isso quebra a politica de indexadores do Jackett/Prowlarr e e fragil por
natureza. So vale a pena se o magnet aparecer direto no HTML do post.
"""
import re

SITE = {
    "name": "NomeDoSite",
    "base_url": "https://exemplo.com",
    "movie_path": "/filmes/",
    "tv_path": "/series/",
    "card_re": re.compile(r"<PLACEHOLDER>(.*?)</PLACEHOLDER>", re.S),
    "title_re": re.compile(r'<a href="([^"]+)"[^>]*>([^<]+)</a>'),
    "year_re": re.compile(r"\((\d{4})\)"),
}
