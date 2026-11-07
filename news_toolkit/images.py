"""
Finds the lead image of news articles (the one the page itself declares for social sharing) and downloads it.
Check the licence of every image before you publish it: this tool finds pictures, it does not clear rights.

    python -m news_toolkit.images https://example.com/story-1 https://example.com/story-2 --out lead_images/
    python -m news_toolkit.images --urls-file links.txt --report images.csv --list-only

The image URL is read from the page's ``og:image`` tag, then ``twitter:image``, then the first large ``<img>``.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

HEADERS = {"User-Agent": "news-data-toolkit/1.0 (research use)"}


def find_lead_image(html: str, base_url: str) -> Optional[str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}, {"property": "og:image:url"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return urljoin(base_url, tag["content"])
    for img in soup.find_all("img"):
        w = re.sub(r"\D", "", str(img.get("width", "")))
        if img.get("src") and w and int(w) >= 400:
            return urljoin(base_url, img["src"])
    return None


def file_name(article_url: str, image_url: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (urlparse(article_url).path.strip("/").split("/")[-1] or urlparse(article_url).netloc).lower())
    ext = Path(urlparse(image_url).path).suffix.lower()
    return f"{index:03d}-{slug[:60].strip('-')}{ext if ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif') else '.jpg'}"


def process(urls: list[str], out_dir: Optional[Path], session=None) -> list[dict]:
    import requests
    s = session or requests
    rows = []
    for i, url in enumerate(urls, 1):
        row = {"article": url, "image": "", "file": "", "status": ""}
        try:
            page = s.get(url, headers=HEADERS, timeout=30)
            page.raise_for_status()
            image = find_lead_image(page.text, url)
            if not image:
                row["status"] = "no image found"
            else:
                row["image"] = image
                if out_dir is None:
                    row["status"] = "found"
                else:
                    out_dir.mkdir(parents=True, exist_ok=True)
                    data = s.get(image, headers=HEADERS, timeout=60)
                    data.raise_for_status()
                    target = out_dir / file_name(url, image, i)
                    target.write_bytes(data.content)
                    row["file"], row["status"] = str(target), "downloaded"
        except Exception as exc:  # one bad link must not stop the list
            row["status"] = f"error: {type(exc).__name__}"
        rows.append(row)
    return rows


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--urls-file")
    ap.add_argument("--out", default="lead_images", type=Path)
    ap.add_argument("--list-only", action="store_true", help="only find the image addresses, download nothing")
    ap.add_argument("--report", default="lead_images.csv")
    args = ap.parse_args(argv)
    urls = list(args.urls)
    if args.urls_file:
        urls += [u.strip() for u in Path(args.urls_file).read_text(encoding="utf-8").splitlines() if u.strip()]
    if not urls:
        ap.error("give at least one URL or --urls-file")
    rows = process(urls, None if args.list_only else args.out)
    with open(args.report, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["article", "image", "file", "status"])
        w.writeheader()
        w.writerows(rows)
    print(f"{sum(1 for r in rows if r['image'])} of {len(rows)} articles had a lead image; report in {args.report}")


if __name__ == "__main__":
    main()
