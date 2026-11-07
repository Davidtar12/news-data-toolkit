"""
Google News search through its public RSS feed (no scraping, no key).

Searches one or many terms, keeps the newest results per term, removes the same story found under several terms and
writes a CSV. Useful for monitoring coverage of a list of names, companies or topics.

    python -m news_toolkit.googlenews "water crisis" "mining permits" --per-term 5 --lang es-419 --country CO
    python -m news_toolkit.googlenews --terms-file terms.txt --out coverage.csv

Put one term per line in the terms file. An exact phrase search is the default (the term is quoted).
"""
from __future__ import annotations

import argparse
import csv
import time
from typing import Iterable, Optional
from urllib.parse import quote_plus

import feedparser

RSS = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl}"


def feed_url(term: str, lang: str = "en-US", country: str = "US", exact: bool = True) -> str:
    q = f'"{term}"' if exact else term
    return RSS.format(q=quote_plus(q), hl=lang, gl=country)


def parse_feed(parsed, per_term: int) -> list[dict]:
    rows = []
    for e in parsed.entries[:per_term]:
        source = e.get("source", {}).get("title", "") if hasattr(e.get("source", {}), "get") else ""
        rows.append({"title": e.get("title", ""), "url": e.get("link", ""), "published": e.get("published", ""),
                     "source": source})
    return rows


def search_terms(terms: Iterable[str], per_term: int = 3, lang: str = "en-US", country: str = "US", exact: bool = True,
                 pause: float = 1.0, fetch=feedparser.parse, sleep=time.sleep) -> list[dict]:
    """One row per (term, article). An article already found under an earlier term is not listed again."""
    seen, out = set(), []
    for i, term in enumerate(t.strip() for t in terms if t.strip()):
        if i:
            sleep(pause)
        for row in parse_feed(fetch(feed_url(term, lang, country, exact)), per_term):
            key = row["url"] or row["title"]
            if key in seen:
                continue
            seen.add(key)
            out.append({"term": term, **row})
    return out


def write_csv(rows: list[dict], path: str) -> None:
    if not rows:
        print("nothing found")
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows written to {path}")


def main(argv: Optional[list] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("terms", nargs="*")
    ap.add_argument("--terms-file")
    ap.add_argument("--per-term", type=int, default=3)
    ap.add_argument("--lang", default="en-US", help="interface language, for example es-419")
    ap.add_argument("--country", default="US", help="edition country code, for example CO")
    ap.add_argument("--loose", action="store_true", help="do not quote the term (matches any of its words)")
    ap.add_argument("--out", default="google_news.csv")
    args = ap.parse_args(argv)
    terms = list(args.terms)
    if args.terms_file:
        with open(args.terms_file, encoding="utf-8") as f:
            terms += [line for line in f.read().splitlines()]
    if not terms:
        ap.error("give at least one term or --terms-file")
    write_csv(search_terms(terms, args.per_term, args.lang, args.country, exact=not args.loose), args.out)


if __name__ == "__main__":
    main()
