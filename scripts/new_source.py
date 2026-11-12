#!/usr/bin/env python3
"""Cria sources/<site_id>.py com o esqueleto padrao (regex_source), ja com
nome e base_url preenchidos. Pra um source 100% customizado em vez de regex,
veja sources/_template.py (opcao 2) e escreva o arquivo na mao.

Uso: python scripts/new_source.py <site_id> "<Nome do Site>" <base_url>
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TEMPLATE = r'''import re

from sources._common import regex_source

SOURCE = regex_source(
    name="__NAME__",
    base_url="__BASE_URL__",
    movie_path="/filmes/",
    tv_path="/series/",
    card_re=re.compile(r"<PLACEHOLDER>(.*?)</PLACEHOLDER>", re.S),
    title_re=re.compile(r'<a href="([^"]+)"[^>]*>([^<]+)</a>'),
    year_re=re.compile(r"\((\d{4})\)"),
)
'''


def main():
    if len(sys.argv) != 4:
        print('uso: python scripts/new_source.py <site_id> "<Nome do Site>" <base_url>')
        sys.exit(1)
    site_id, name, base_url = sys.argv[1], sys.argv[2], sys.argv[3].rstrip("/")
    dest = ROOT / "sources" / f"{site_id}.py"
    if dest.exists():
        print(f"ja existe: {dest}")
        sys.exit(1)
    text = TEMPLATE.replace("__NAME__", name).replace("__BASE_URL__", base_url)
    dest.write_text(text, encoding="utf-8")
    print(f"criado: {dest}")
    print("agora preencha card_re/title_re/year_re olhando o HTML real do site.")
    print("(pra um source 100% customizado em vez de regex, ver sources/_template.py)")


if __name__ == "__main__":
    main()
