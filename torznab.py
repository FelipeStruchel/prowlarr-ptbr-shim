"""Montagem das respostas XML do protocolo Torznab."""
from email.utils import formatdate
from xml.sax.saxutils import escape, quoteattr


def caps_xml():
    return """<?xml version="1.0" encoding="UTF-8"?>
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
