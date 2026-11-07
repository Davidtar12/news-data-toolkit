"""
Audience reports from Google Analytics 4: monthly visitors, average session length, and audience splits by place, age
and gender. Writes CSV (or Excel). Works without any account in ``--demo`` mode, which uses invented numbers.

    python -m news_toolkit.ga4 monthly-users   --start 2025-01-01 --end 2025-06-30 --demo
    python -m news_toolkit.ga4 session-length  --start 2025-01-01 --end 2025-06-30 --demo
    python -m news_toolkit.ga4 outside-city    --city Bogotá --start 2025-01-01 --end 2025-06-30 --property 123456789
    python -m news_toolkit.ga4 under-35        --start 2025-01-01 --end 2025-06-30 --property 123456789
    python -m news_toolkit.ga4 gender-by-month --start 2025-01-01 --end 2025-06-30 --property 123456789

Real data needs the property id (``--property`` or GA4_PROPERTY_ID) and a service-account JSON file kept outside the
repository (GA4_CREDENTIALS_PATH). Install the client with ``pip install google-analytics-data``.
"""
from __future__ import annotations

import argparse
import csv
import os
import random
from datetime import date
from typing import Callable

# report name -> (dimensions, metrics, optional filter as (dimension, match, value, negate))
REPORTS = {
    "monthly-users": (["yearMonth"], ["activeUsers"], None),
    "session-length": (["yearMonth"], ["averageSessionDuration"], None),
    "outside-city": (["yearMonth"], ["activeUsers"], "city"),
    "under-35": (["yearMonth", "userAgeBracket"], ["activeUsers"], "age"),
    "gender-by-month": (["yearMonth", "userGender"], ["activeUsers"], None),
}
UNDER_35 = {"18-24", "25-34"}


def rows_from_response(response, dims: int, metrics: int) -> list[list]:
    """Turn a GA4 response (rows with dimension_values and metric_values) into plain lists."""
    out = []
    for row in response.rows:
        out.append([v.value for v in row.dimension_values[:dims]] + [float(v.value) for v in row.metric_values[:metrics]])
    return sorted(out, key=lambda r: r[0])


def keep_under_35(rows: list[list]) -> list[list]:
    """Sum the 18-24 and 25-34 age brackets per month."""
    per_month: dict = {}
    for month, bracket, users in rows:
        if bracket in UNDER_35:
            per_month[month] = per_month.get(month, 0) + users
    return [[m, u] for m, u in sorted(per_month.items())]


def fetch(report: str, start: str, end: str, property_id: str, credentials: str, city: str = "") -> list[list]:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (DateRange, Dimension, Filter, FilterExpression, Metric,
                                                    RunReportRequest)
    dims, metrics, kind = REPORTS[report]
    client = BetaAnalyticsDataClient.from_service_account_file(credentials)
    flt = None
    if kind == "city":
        flt = FilterExpression(not_expression=FilterExpression(filter=Filter(
            field_name="city", string_filter=Filter.StringFilter(value=city, match_type=Filter.StringFilter.MatchType.EXACT))))
    response = client.run_report(RunReportRequest(
        property=f"properties/{property_id}", date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name=d) for d in dims], metrics=[Metric(name=m) for m in metrics], dimension_filter=flt))
    rows = rows_from_response(response, len(dims), len(metrics))
    return keep_under_35(rows) if kind == "age" else rows


def demo_rows(report: str, start: str, end: str, seed: int = 11) -> list[list]:
    """Invented numbers with a plausible shape, so the tool can be tried with no account."""
    rnd = random.Random(seed)
    y0, m0, y1, m1 = int(start[:4]), int(start[5:7]), int(end[:4]), int(end[5:7])
    months = [f"{y0 + (m0 - 1 + i) // 12}{(m0 - 1 + i) % 12 + 1:02d}" for i in range((y1 - y0) * 12 + m1 - m0 + 1)]
    base = 52000
    out = []
    for i, month in enumerate(months):
        users = base * (1 + 0.04 * i) * rnd.uniform(0.9, 1.1)
        if report == "monthly-users":
            out.append([month, round(users)])
        elif report == "session-length":
            out.append([month, round(rnd.uniform(78, 126), 1)])
        elif report == "outside-city":
            out.append([month, round(users * rnd.uniform(0.35, 0.45))])
        elif report == "under-35":
            out.append([month, round(users * rnd.uniform(0.28, 0.36))])
        else:
            share = rnd.uniform(0.44, 0.52)
            out += [[month, "female", round(users * share)], [month, "male", round(users * (1 - share) * 0.97)]]
    return out


def write(rows: list[list], report: str, path: str) -> None:
    dims, metrics, _ = REPORTS[report]
    header = {"yearMonth": "month", "userAgeBracket": "age", "userGender": "gender"}
    cols = [header.get(d, d) for d in dims if not (report == "under-35" and d == "userAgeBracket")] + metrics
    if path.endswith(".xlsx"):
        import pandas as pd
        pd.DataFrame(rows, columns=cols).to_excel(path, index=False)
    else:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
    print(f"{len(rows)} rows written to {path}")


def main(argv=None, fetcher: Callable = fetch) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", choices=list(REPORTS))
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--property", default=os.getenv("GA4_PROPERTY_ID", ""))
    ap.add_argument("--credentials", default=os.getenv("GA4_CREDENTIALS_PATH", "credentials.json"))
    ap.add_argument("--city", default="", help="for outside-city: the city to leave out")
    ap.add_argument("--demo", action="store_true", help="use invented numbers, no account needed")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    if args.report == "outside-city" and not args.city and not args.demo:
        ap.error("outside-city needs --city")
    if args.demo:
        rows = demo_rows(args.report, args.start, args.end)
    else:
        if not args.property:
            ap.error("give --property or set GA4_PROPERTY_ID (or use --demo)")
        rows = fetcher(args.report, args.start, args.end, args.property, args.credentials, args.city)
    write(rows, args.report, args.out or f"ga4_{args.report.replace('-', '_')}.csv")


if __name__ == "__main__":
    main()
