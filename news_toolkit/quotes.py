"""
Pulls direct quotes, and who said them, out of articles, documents and web pages. A first pass for fact-checking:
every quote lands in one list with its speaker (when the text names one) and the sentence around it.

    python -m news_toolkit.quotes article.txt report.docx https://example.com/story --out quotes.csv
    python -m news_toolkit.quotes notes_folder/            # every .txt and .docx inside

Handles straight quotes ("..."), curly quotes (“...”) and Spanish angle quotes («...»). The speaker is read from patterns
such as '"..." said Jane Doe', 'Jane Doe said: "..."' and '"...", dijo Jane Doe'. When no speaker is found the field is
empty: nothing is guessed.
"""
from __future__ import annotations

import argparse
import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

QUOTE = re.compile(r'"([^"\n]{10,}?)"|“([^”\n]{10,}?)”|«([^»\n]{10,}?)»')
VERBS = (r"said|says|told|added|argued|explained|noted|stated|according to|dijo|dice|afirmó|afirma|explicó|señaló|aseguró|"
         r"declaró|indicó|agregó|manifestó|según")
NAME = r"((?:[A-ZÁÉÍÓÚÑ]\.|[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'-]+)(?:\s+(?:de|del|la|van|von|da|[A-ZÁÉÍÓÚÑ]\.|[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ'-]+)){0,4})"
AFTER = re.compile(rf"^[\s,.;:–—-]*(?:(?i:{VERBS}))\s+{NAME}")
AFTER_NAME_FIRST = re.compile(rf"^[\s,.;:–—-]*{NAME}\s+(?:(?i:{VERBS}))\b")
BEFORE = re.compile(rf"{NAME}\s*,?\s*(?:(?i:{VERBS}))(?:\s+(?:to\s+)?\w+)?[\s,:;–—-]*$")


@dataclass
class Quote:
    text: str
    speaker: str
    context: str
    source: str = ""


def _speaker(text: str, start: int, end: int) -> str:
    after = text[end:end + 120]
    m = AFTER.match(after) or AFTER_NAME_FIRST.match(after)
    if m and m.group(1)[0].isupper():
        return m.group(1).strip()
    m = BEFORE.search(text[max(0, start - 100):start])
    if m and m.group(1)[0].isupper():
        return m.group(1).strip()
    return ""


def extract_quotes(text: str, source: str = "") -> list[Quote]:
    out = []
    for m in QUOTE.finditer(text):
        quote = next(g for g in m.groups() if g)
        lo, hi = max(0, m.start() - 80), min(len(text), m.end() + 80)
        out.append(Quote(quote.strip(), _speaker(text, m.start(), m.end()), " ".join(text[lo:hi].split()), source))
    return out


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(str(path)).paragraphs)
    return path.read_text(encoding="utf-8", errors="replace")


def read_url(url: str, session=None) -> str:
    import requests
    from bs4 import BeautifulSoup
    r = (session or requests).get(url, timeout=30, headers={"User-Agent": "news-data-toolkit/1.0 (research use)"})
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)


def collect(inputs: Iterable[str]) -> list[Quote]:
    out = []
    for item in inputs:
        if item.startswith(("http://", "https://")):
            out += extract_quotes(read_url(item), item)
            continue
        p = Path(item)
        files = sorted(p.glob("*.txt")) + sorted(p.glob("*.docx")) if p.is_dir() else [p]
        for f in files:
            out += extract_quotes(read_text(f), f.name)
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="text or .docx files, folders, or URLs")
    ap.add_argument("--out", default="quotes.csv")
    args = ap.parse_args(argv)
    quotes = collect(args.inputs)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source", "speaker", "text", "context"])
        w.writeheader()
        for q in quotes:
            d = asdict(q)
            w.writerow({k: d[k] for k in w.fieldnames})
    named = sum(1 for q in quotes if q.speaker)
    print(f"{len(quotes)} quotes ({named} with a named speaker) written to {args.out}")


if __name__ == "__main__":
    main()
