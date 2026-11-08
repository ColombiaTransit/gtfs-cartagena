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
from urllib.parse import unquote, urljoin

import requests

PAGE = "https://transcaribe.gov.co/index.php/rutas-sitm/"
OUT = Path(__file__).resolve().parent.parent / "raw" / "web"
OUT.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "ColombiaTransit-gtfs-cartagena/1.0 (+https://github.com/ColombiaTransit/gtfs-cartagena)"

HEADING = re.compile(r"<h\d[^>]*>\s*(?:<[^>]+>\s*)*((?:Ruta\s+[ATXC]\d{3}E?)|Mapa General)", re.I)
IMG = re.compile(r"<img[^>]+src=\"([^\"]+/wp-content/uploads/(?!2021/11/)[^\"]+\.(?:png|jpe?g|webp))\"", re.I)
PDF = re.compile(r"href=\"([^\"]+\.pdf)\"", re.I)


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

    events = [(m.start(), "h", m.group(1).strip()) for m in HEADING.finditer(html)]
    events += [(m.start(), "i", urljoin(PAGE, m.group(1))) for m in IMG.finditer(html)]
    events.sort()

    index: dict[str, list[str]] = {}
    current = None
    for _, kind, value in events:
        if kind == "h":
            current = re.sub(r"\s+", " ", value)
        elif current:
            index.setdefault(current, [])
            name = download(value)
            if name not in index[current]:
                index[current].append(name)

    pdfs = sorted({urljoin(PAGE, u) for u in PDF.findall(html) if "/wp-content/uploads/" in u})
    index["pdf"] = [download(u) for u in pdfs]

    (OUT / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(index) - 1} headings with images, {len(index['pdf'])} PDFs")
    return 0 if len(index) > 1 else 1


if __name__ == "__main__":
    sys.exit(main())
