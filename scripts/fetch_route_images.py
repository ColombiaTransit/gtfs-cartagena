#!/usr/bin/env python3
"""
Download the route maps (with first/last departure times) from
https://transcaribe.gov.co/index.php/rutas-sitm/ into raw/web/.

Writes raw/web/index.json mapping each heading ("Ruta A104", "Mapa General")
to the downloaded file, plus any PDFs linked from the page.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import requests

PAGE = "https://transcaribe.gov.co/index.php/rutas-sitm/"
OUT = Path(__file__).resolve().parent.parent / "raw" / "web"
OUT.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "ColombiaTransit-gtfs-cartagena/1.0 (+https://github.com/ColombiaTransit/gtfs-cartagena)"

# any image in the uploads folder, in src, data-src, srcset etc. (the page lazy-loads)
IMG = re.compile(r"(https?://[^\s\"',]+/wp-content/uploads/(?!2021/11/)[^\s\"',]+?\.(?:png|jpe?g|webp))", re.I)
PDF = re.compile(r"(https?://[^\s\"']+/wp-content/uploads/[^\s\"']+\.pdf)", re.I)
# the route code is in the file name: A104-min.png, Rutas_T101_Actual-min.png, Mapa_A118_min.png
CODE = re.compile(r"(?<![A-Za-z0-9])([ATXC]\d{3}E?)(?![0-9])")
SIZE = re.compile(r"-\d+x\d+(?=\.\w+$)")


def download(url: str) -> str:
    name = unquote(url.rsplit("/", 1)[-1])
    r = SESSION.get(url, timeout=120)
    r.raise_for_status()
    (OUT / name).write_bytes(r.content)
    print(f"{len(r.content):>9} {name}")
    return name


def main() -> int:
    html = SESSION.get(PAGE, timeout=60).text
    (OUT / "rutas-sitm.html").write_text(html, encoding="utf-8")

    urls = sorted({SIZE.sub("", u) for u in IMG.findall(html)})   # full size, no thumbnails
    index: dict[str, list[str]] = {}
    for url in urls:
        name = unquote(url.rsplit("/", 1)[-1])
        m = CODE.search(name)
        key = f"Ruta {m.group(1)}" if m else ("Mapa General" if "general" in name.lower() else None)
        if not key:
            continue
        index.setdefault(key, []).append(download(url))

    pdfs = sorted(set(PDF.findall(html)))
    index["pdf"] = [download(u) for u in pdfs]

    (OUT / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(index) - 1} headings with images, {len(index['pdf'])} PDFs")
    return 0 if len(index) > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
