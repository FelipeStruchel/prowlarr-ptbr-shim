"""Wrapper HTTP generico (sem dependencia do CFG - cada chamador decide o timeout)."""
import time
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


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
