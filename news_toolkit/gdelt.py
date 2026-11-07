"""
GDELT news search and coverage timelines.

GDELT (the Global Database of Events, Language and Tone) indexes news articles from around the world in over 100
languages and is free to query, with no key. This module wraps its DOC 2.0 API for two questions a reporter asks:

  * which articles mention a topic (``search``), and
  * how much coverage does a topic get over time (``timeline``).

    python -m news_toolkit.gdelt search "water crisis" --max 20 --timespan 7d --out articles.csv
    python -m news_toolkit.gdelt timeline "water crisis" --timespan 3months --out coverage.csv

GDELT allows about one request every five seconds; ``search_many`` waits between requests.
"""
from __future__ import annotations

import argparse
import csv
import time
from typing import Iterable, Optional

import requests

API = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "news-data-toolkit/1.0 (research use)"
PAUSE_SECONDS = 5.5


class GdeltError(Exception):
    """GDELT answered with something that is not data (a rate-limit or syntax message)."""


def _get(params: dict, session=None, timeout: float = 30.0) -> dict:
    r = (session or requests).get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        # GDELT returns plain text for a bad query or when you ask too fast
        raise GdeltError(r.text.strip()[:200] or "empty answer")


def search(query: str, max_records: int = 10, timespan: str = "7d", language: Optional[str] = None,
           country: Optional[str] = None, session=None) -> list[dict]:
    """Articles matching a query, most relevant first. Each row: title, url, domain, language, country, seen_date."""
    q = query
    if language:
        q += f" sourcelang:{language}"
    if country:
        q += f" sourcecountry:{country}"
    data = _get({"query": q, "mode": "artlist", "format": "json", "maxrecords": min(max_records, 250),
                 "timespan": timespan, "sort": "hybridrel"}, session)
    rows = []
    for a in data.get("articles", []):
        rows.append({"title": a.get("title", ""), "url": a.get("url", ""), "domain": a.get("domain", ""),
                     "language": a.get("language", ""), "country": a.get("sourcecountry", ""),
                     "seen_date": a.get("seendate", "")})
    return rows


def timeline(query: str, timespan: str = "3months", session=None) -> list[dict]:
    """Share of all monitored coverage that mentions the query, over time. Each row: date, value."""
    data = _get({"query": query, "mode": "timelinevol", "format": "json", "timespan": timespan}, session)
    series = (data.get("timeline") or [{}])[0].get("data", [])
    return [{"date": p["date"][:8], "value": float(p["value"])} for p in series]


def search_many(queries: Iterable[str], pause: float = PAUSE_SECONDS, sleep=time.sleep, **kwargs) -> list[dict]:
    """Run several searches politely (one every `pause` seconds) and tag each row with its query."""
    out = []
    for i, q in enumerate(queries):
        if i:
            sleep(pause)
        for row in search(q, **kwargs):
            out.append({"query": q, **row})
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


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="list articles that match a query")
    s.add_argument("query")
    s.add_argument("--max", type=int, default=10, dest="max_records")
    s.add_argument("--timespan", default="7d", help="for example 24h, 7d, 3months")
    s.add_argument("--language", help="source language, for example spanish")
    s.add_argument("--country", help="source country code, for example CO")
    s.add_argument("--out", default="gdelt_articles.csv")
    t = sub.add_parser("timeline", help="coverage volume over time")
    t.add_argument("query")
    t.add_argument("--timespan", default="3months")
    t.add_argument("--out", default="gdelt_timeline.csv")
    args = ap.parse_args(argv)
    if args.cmd == "search":
        write_csv(search(args.query, args.max_records, args.timespan, args.language, args.country), args.out)
    else:
        write_csv(timeline(args.query, args.timespan), args.out)


if __name__ == "__main__":
    main()
