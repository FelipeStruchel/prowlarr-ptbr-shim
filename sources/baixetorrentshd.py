import re

SITE = {
    "name": "BaixeTorrentsHD",
    "base_url": "https://www.baixetorrentshd.com",
    "movie_path": "/categoria/filmes/",
    "tv_path": "/categoria/series/",
    "card_re": re.compile(r'<article class="movie-card">(.*?)</article>', re.S),
    "title_re": re.compile(r'movie-card__title"><a href="([^"]+)">([^<]+)</a>'),
    "year_re": re.compile(r'movie-card__badge">(\d{4})<'),
}
