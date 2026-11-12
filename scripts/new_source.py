#!/usr/bin/env python3
"""Cria sources/<site_id>.py a partir do template, ja com nome e base_url.

Uso: python scripts/new_source.py <site_id> "<Nome do Site>" <base_url>
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "sources" / "_template.py"


def main():
    if len(sys.argv) != 4:
        print('uso: python scripts/new_source.py <site_id> "<Nome do Site>" <base_url>')
        sys.exit(1)
    site_id, name, base_url = sys.argv[1], sys.argv[2], sys.argv[3].rstrip("/")
    dest = ROOT / "sources" / f"{site_id}.py"
    if dest.exists():
        print(f"ja existe: {dest}")
        sys.exit(1)
    text = TEMPLATE.read_text(encoding="utf-8")
    text = text.replace("NomeDoSite", name).replace("https://exemplo.com", base_url)
    dest.write_text(text, encoding="utf-8")
    print(f"criado: {dest}")
    print("agora preencha card_re/title_re/year_re olhando o HTML real do site.")


if __name__ == "__main__":
    main()
