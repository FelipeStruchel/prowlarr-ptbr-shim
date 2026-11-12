"""Helpers genericos de texto usados tanto pelo scraper quanto por sources."""
import html
import re
import unicodedata

SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB)", re.I)


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


def strip_tags(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def size_to_bytes(num, unit):
    v = float(num.replace(",", "."))
    return int(v * {"MB": 1024 ** 2, "GB": 1024 ** 3, "TB": 1024 ** 4}[unit.upper()])
