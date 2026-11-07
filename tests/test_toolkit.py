"""Tests for the news toolkit. No network, no accounts: HTTP and Google clients are replaced by fakes."""
import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news_toolkit import ga4, gdelt, googlenews, images, quotes  # noqa: E402


class FakeResponse:
    def __init__(self, payload=None, text="", status=200, content=b""):
        self._payload, self.text, self.status_code, self.content = payload, text, status, content

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        return self.responses.pop(0)


# ── GDELT ────────────────────────────────────────────────────────────────────

def test_gdelt_search_returns_clean_rows_and_adds_language_and_country_filters():
    s = FakeSession([FakeResponse({"articles": [{"title": "A", "url": "http://a", "domain": "a.com", "language": "Spanish",
                                                 "sourcecountry": "Colombia", "seendate": "20250101T000000Z"}]})])
    rows = gdelt.search("agua", 5, "7d", language="spanish", country="CO", session=s)
    assert rows == [{"title": "A", "url": "http://a", "domain": "a.com", "language": "Spanish", "country": "Colombia",
                     "seen_date": "20250101T000000Z"}]
    assert s.calls[0][1]["query"] == "agua sourcelang:spanish sourcecountry:CO" and s.calls[0][1]["maxrecords"] == 5


def test_gdelt_text_answers_become_a_clear_error():
    s = FakeSession([FakeResponse(None, text="Please limit requests to one every 5 seconds")])
    with pytest.raises(gdelt.GdeltError, match="limit requests"):
        gdelt.search("x", session=s)


def test_gdelt_timeline_parses_dates_and_values():
    payload = {"timeline": [{"series": "Volume", "data": [{"date": "20250101T000000Z", "value": 0.5}, {"date": "20250102T000000Z", "value": 0.75}]}]}
    assert gdelt.timeline("x", session=FakeSession([FakeResponse(payload)])) == [{"date": "20250101", "value": 0.5}, {"date": "20250102", "value": 0.75}]


def test_gdelt_search_many_waits_between_requests_and_tags_rows(monkeypatch):
    pauses = []
    monkeypatch.setattr(gdelt, "search", lambda q, **k: [{"title": q}])
    rows = gdelt.search_many(["a", "b", "c"], pause=5.5, sleep=pauses.append)
    assert [r["query"] for r in rows] == ["a", "b", "c"] and pauses == [5.5, 5.5]


# ── Google News ─────────────────────────────────────────────────────────────

def test_google_news_url_quotes_the_term_and_sets_edition():
    url = googlenews.feed_url("water crisis", "es-419", "CO")
    assert "q=%22water+crisis%22" in url and "hl=es-419" in url and "ceid=CO:es-419" in url
    assert "%22" not in googlenews.feed_url("water", exact=False)


def test_google_news_keeps_per_term_limit_and_drops_stories_found_twice():
    def entries(*items):
        return SimpleNamespace(entries=[{"title": t, "link": l, "published": "p", "source": {"title": "S"}} for t, l in items])
    feeds = {"one": entries(("T1", "u1"), ("T2", "u2"), ("T3", "u3")), "two": entries(("T2 again", "u2"), ("T4", "u4"))}
    rows = googlenews.search_terms(["one", "two"], per_term=2, fetch=lambda url: feeds["one" if "one" in url else "two"], sleep=lambda s: None)
    assert [(r["term"], r["url"]) for r in rows] == [("one", "u1"), ("one", "u2"), ("two", "u4")]


# ── quotes ──────────────────────────────────────────────────────────────────

def test_quotes_with_the_speaker_after_before_and_in_spanish():
    text = ('"The river has not been this low in forty years," said Maria Lopez. Later, Juan Pérez de la Cruz told reporters: '
            '“We will open the records next week.” «No hay presupuesto para eso», dijo Ana Torres.')
    found = {q.text: q.speaker for q in quotes.extract_quotes(text)}
    assert found["The river has not been this low in forty years,"] == "Maria Lopez"
    assert found["We will open the records next week."] == "Juan Pérez de la Cruz"
    assert found["No hay presupuesto para eso"] == "Ana Torres"


def test_a_quote_with_no_named_speaker_leaves_the_field_empty():
    found = quotes.extract_quotes('Residents called it "completely unacceptable for a city this size" in the meeting.')
    assert len(found) == 1 and found[0].speaker == ""


def test_short_quoted_words_are_not_quotes():
    assert quotes.extract_quotes('He called it "fine" and left.') == []


def test_quotes_are_collected_from_text_files_and_folders(tmp_path):
    (tmp_path / "a.txt").write_text('"This is a long enough quote for the test," said Sam Reed.', encoding="utf-8")
    (tmp_path / "b.txt").write_text("nothing quoted here", encoding="utf-8")
    got = quotes.collect([str(tmp_path)])
    assert [(q.source, q.speaker) for q in got] == [("a.txt", "Sam Reed")]


# ── GA4 ─────────────────────────────────────────────────────────────────────

def fake_rows(*rows):
    mk = lambda dims, mets: SimpleNamespace(dimension_values=[SimpleNamespace(value=d) for d in dims],
                                            metric_values=[SimpleNamespace(value=m) for m in mets])
    return SimpleNamespace(rows=[mk(d, m) for d, m in rows])


def test_ga4_rows_are_sorted_by_month():
    r = ga4.rows_from_response(fake_rows((["202502"], ["30"]), (["202501"], ["20"])), 1, 1)
    assert r == [["202501", 20.0], ["202502", 30.0]]


def test_under_35_adds_the_two_youngest_brackets_per_month():
    rows = [["202501", "18-24", 10.0], ["202501", "25-34", 20.0], ["202501", "35-44", 99.0], ["202502", "25-34", 5.0]]
    assert ga4.keep_under_35(rows) == [["202501", 30.0], ["202502", 5.0]]


def test_demo_numbers_cover_every_month_and_are_repeatable():
    a = ga4.demo_rows("monthly-users", "2025-01-01", "2025-06-30")
    assert [r[0] for r in a] == ["202501", "202502", "202503", "202504", "202505", "202506"]
    assert a == ga4.demo_rows("monthly-users", "2025-01-01", "2025-06-30")
    assert len(ga4.demo_rows("gender-by-month", "2025-01-01", "2025-03-31")) == 6


def test_ga4_demo_run_writes_a_csv(tmp_path):
    out = tmp_path / "users.csv"
    ga4.main(["monthly-users", "--start", "2025-01-01", "--end", "2025-03-31", "--demo", "--out", str(out)])
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows[0] == ["month", "activeUsers"] and len(rows) == 4


def test_ga4_real_run_needs_a_property_and_uses_the_fetcher(tmp_path, monkeypatch):
    monkeypatch.delenv("GA4_PROPERTY_ID", raising=False)
    with pytest.raises(SystemExit):
        ga4.main(["monthly-users", "--start", "2025-01-01"])
    calls = []
    ga4.main(["monthly-users", "--start", "2025-01-01", "--property", "42", "--out", str(tmp_path / "x.csv")],
             fetcher=lambda *a: calls.append(a) or [["202501", 1.0]])
    assert calls[0][3] == "42"


# ── images ──────────────────────────────────────────────────────────────────

def test_lead_image_prefers_the_social_sharing_tag_and_resolves_relative_links():
    html = '<html><head><meta property="og:image" content="/img/lead.jpg"></head><body><img src="/small.png" width="50"></body></html>'
    assert images.find_lead_image(html, "https://example.com/news/story") == "https://example.com/img/lead.jpg"


def test_lead_image_falls_back_to_a_large_image_and_ignores_small_ones():
    html = '<img src="/icon.png" width="40"><img src="/hero.jpg" width="800">'
    assert images.find_lead_image(html, "https://example.com/a") == "https://example.com/hero.jpg"
    assert images.find_lead_image('<img src="/icon.png" width="40">', "https://example.com/a") is None


def test_process_downloads_and_reports_each_link_even_when_one_fails(tmp_path):
    page = '<meta property="og:image" content="https://cdn.example.com/p.jpg">'
    s = FakeSession([FakeResponse(text=page), FakeResponse(content=b"IMG"), FakeResponse(status=404)])
    rows = images.process(["https://example.com/story-one", "https://example.com/missing"], tmp_path, session=s)
    assert rows[0]["status"] == "downloaded" and Path(rows[0]["file"]).read_bytes() == b"IMG"
    assert Path(rows[0]["file"]).name == "001-story-one.jpg"
    assert rows[1]["status"].startswith("error")
