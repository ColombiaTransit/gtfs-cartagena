#!/usr/bin/env python3
"""
Download all news items from transcaribe.gov.co through the WordPress REST API
(/wp-json/wp/v2/noticia) into raw/news/.

The news items list stops per route, detours, new routes, special timetables
and frequency changes, often more up to date than the open data.

Writes:
- raw/news/text/<id>.txt   one file per item: title, date, link, plain text
                            and image links (timetables are often images)
- raw/news/index.csv       one row per item, with the route codes it names
                            and topic flags (paraderos, desvio, horario, ...)
- raw/news/routes.csv      one row per route code per item, newest first

Usage: python scripts/fetch_news.py [--type noticia] [--type posts]
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import requests

API = "https://transcaribe.gov.co/index.php/wp-json/wp/v2/"
OUT = Path(__file__).resolve().parent.parent / "raw" / "news"
FIELDS = "id,date,modified,slug,link,title,content"
PER_PAGE = 100

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "ColombiaTransit-gtfs-cartagena/1.0 (+https://github.com/ColombiaTransit/gtfs-cartagena)"

# A101, A-101, X 105, T100E, X105P (precarga), C018
ROUTE = re.compile(r"(?<![A-Za-z0-9])([ATXC])[\s\-]?(\d{3})([EP])?(?![0-9])")

# topic flags, matched on the lower-cased text without accents
TOPICS = {
    "paraderos": r"\bparader",
    "desvio": r"\bdesvi|\bcierre|retorno operacional|dejan? de cubrir",
    "nueva_ruta": r"nueva ruta|nuevas rutas|entra(ra)? en operacion|inicia(ra)? operacion",
    "horario": r"\bhorario|a\. ?m\.|p\. ?m\.",
    "frecuencia": r"\bfrecuencia|intervalo|cada \d+ minutos",
    "festivo": r"\bfestiv|dias? civic|semana santa|navidad|ano nuevo|fiestas",
    "tarifa": r"\btarifa|pasaje|\bpago",
}
TOPICS = {k: re.compile(v) for k, v in TOPICS.items()}
ACCENTS = str.maketrans("áéíóúüñ", "aeiouun")


class TextExtractor(HTMLParser):
    """HTML to plain text, keeping paragraphs, list items and image links."""

    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.images: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "img":
            a = dict(attrs)
            src = a.get("data-src") or a.get("src")
            if src and src not in self.images:
                self.images.append(src)
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK and tag != "li":
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        t = "".join(self.parts).replace("\xa0", " ")
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r" *\n *", "\n", t)
        return re.sub(r"\n{3,}", "\n\n", t).strip()


def html_to_text(s: str) -> tuple[str, list[str]]:
    p = TextExtractor()
    p.feed(s or "")
    p.close()
    return p.text(), p.images


def route_codes(text: str) -> list[str]:
    codes = {f"{m.group(1)}{m.group(2)}{m.group(3) or ''}".upper() for m in ROUTE.finditer(text)}
    return sorted(codes)


def topics(text: str) -> list[str]:
    t = text.lower().translate(ACCENTS)
    return [k for k, rx in TOPICS.items() if rx.search(t)]


def get(url: str, params: dict) -> requests.Response:
    for attempt in range(4):
        try:
            r = SESSION.get(url, params=params, timeout=90)
            if r.status_code < 500:
                return r
        except requests.RequestException as e:
            print(f"  {e}", file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    r.raise_for_status()
    return r


def fetch_type(post_type: str) -> list[dict]:
    items: list[dict] = []
    page, pages = 1, 1
    while page <= pages:
        r = get(API + post_type, {"per_page": PER_PAGE, "page": page, "_fields": FIELDS,
                                  "orderby": "date", "order": "desc"})
        if r.status_code == 400 and page > 1:      # past the last page
            break
        if r.status_code == 404:
            print(f"{post_type}: not found, skipped")
            return []
        r.raise_for_status()
        pages = int(r.headers.get("X-WP-TotalPages", pages))
        batch = r.json()
        if not batch:
            break
        items.extend(batch)
        print(f"{post_type}: page {page}/{pages}, {len(items)} items")
        page += 1
        time.sleep(1)
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", action="append", dest="types",
                    help="WordPress post type (default: noticia)")
    args = ap.parse_args()
    types = args.types or ["noticia"]

    (OUT / "text").mkdir(parents=True, exist_ok=True)
    rows, route_rows = [], []
    for post_type in types:
        for it in fetch_type(post_type):
            title = html.unescape(re.sub(r"<[^>]+>", "", it.get("title", {}).get("rendered", ""))).strip()
            body, images = html_to_text(it.get("content", {}).get("rendered", ""))
            date = it.get("date", "")[:10]
            codes = route_codes(title + "\n" + body)
            flags = topics(title + "\n" + body)

            lines = [title, f"{date} (modified {it.get('modified', '')[:10]})", it.get("link", ""),
                     "", body]
            if images:
                lines += ["", "Images:"] + images
            (OUT / "text" / f"{it['id']}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

            rows.append({"id": it["id"], "type": post_type, "date": date,
                         "modified": it.get("modified", "")[:10], "title": title,
                         "routes": " ".join(codes), "topics": " ".join(flags),
                         "images": len(images), "link": it.get("link", "")})
            route_rows += [{"route": c, "date": date, "id": it["id"], "topics": " ".join(flags),
                            "title": title} for c in codes]

    if not rows:
        print("No items fetched.", file=sys.stderr)
        return 1

    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    with open(OUT / "index.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    route_rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)   # newest first per route
    route_rows.sort(key=lambda r: r["route"])
    with open(OUT / "routes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["route", "date", "id", "topics", "title"])
        w.writeheader()
        w.writerows(route_rows)

    n_routes = len({r["route"] for r in route_rows})
    print(f"{len(rows)} items, {len(route_rows)} route mentions, {n_routes} route codes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
