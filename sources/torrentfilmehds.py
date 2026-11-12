import re

SITE = {
    "name": "TorrentFilmesHD",
    "base_url": "https://www.torrentfilmehds.net",
    "movie_path": "/genero/filmes/",
    "tv_path": "/genero/series/",
    "card_re": re.compile(r'<article class="item">(.*?)</article>', re.S),
    "title_re": re.compile(r'<a href="([^"]+)"[^>]*>.*?<div class="titulo"><span>([^<]+)</span>', re.S),
    "year_re": re.compile(r'<div class="imagem"><span>(\d{4})</span>'),
}
