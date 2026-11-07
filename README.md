# News Data Toolkit

Small, tested command-line tools for reporters who work with data: measure how much coverage a topic gets, monitor
the news for a list of names, pull direct quotes out of documents, read audience numbers, and collect lead images.
Each tool is one file and works on its own. Nothing here is tied to any outlet, client or account.

| Tool | Question it answers | Needs |
|---|---|---|
| `gdelt` | Which articles mention this topic, and how much coverage does it get over time? | Nothing (public API) |
| `googlenews` | What is the newest coverage for each name on my list? | Nothing (public RSS) |
| `quotes` | Who said what in this article, document or folder? | Nothing |
| `ga4` | How many visitors per month, how long do they stay, who are they (place, age, gender)? | A GA4 property, or `--demo` |
| `images` | What is the lead image of each article in this list? | Nothing |

## Install

```bash
pip install -r requirements.txt
python -m pytest            # 18 tests, no network and no accounts needed
```

## GDELT: coverage of a topic

[GDELT](https://www.gdeltproject.org/) indexes news from around the world in more than 100 languages and is free to
query. It allows about one request every five seconds; the tool waits between requests when you give several queries.

```bash
python -m news_toolkit.gdelt search "water crisis" --max 20 --timespan 7d --language spanish --country CO --out articles.csv
python -m news_toolkit.gdelt timeline "water crisis" --timespan 3months --out coverage.csv
```

`search` writes title, link, site, language, country and date. `timeline` writes the share of all monitored coverage
that mentions the topic, per day: a quick way to see when a story took off.

## Google News: monitor a list of names

Reads Google News' public RSS feed (no scraping), keeps the newest results for each term and drops stories already
found under another term.

```bash
python -m news_toolkit.googlenews "city water authority" "regional mining permits" --per-term 5 --lang es-419 --country CO
python -m news_toolkit.googlenews --terms-file terms.txt --out coverage.csv     # one term per line
```

Terms are searched as exact phrases; add `--loose` to match any of their words.

## Quotes: who said what

```bash
python -m news_toolkit.quotes examples/sample_article.txt --out quotes.csv
```

```
speaker              text
Maria Lopez          The river has not been this low in forty years,
Juan Pérez de la Cruz  We will open the records next week.
Ana Torres           No hay presupuesto para eso
                     completely unacceptable for a city this size
```

It reads text files, `.docx` files, folders of them and web pages. It understands straight, curly and Spanish angle
quotes and finds the speaker in patterns like `"...", said Name`, `Name told reporters: "..."` and `«...», dijo Nombre`.
When the text names nobody, the speaker stays empty: nothing is guessed. Use it as a first pass for fact-checking, then
read the context column.

## Audience numbers (GA4)

```bash
python -m news_toolkit.ga4 monthly-users --start 2025-01-01 --end 2025-06-30 --demo
```

`--demo` uses invented numbers so you can try every report with no account. For real data set `GA4_PROPERTY_ID` and
`GA4_CREDENTIALS_PATH` (a service-account JSON kept outside the repository) and drop `--demo`. Reports: `monthly-users`,
`session-length`, `outside-city --city NAME`, `under-35`, `gender-by-month`. Output is CSV, or Excel with `--out file.xlsx`.

## Lead images

```bash
python -m news_toolkit.images --urls-file links.txt --report images.csv --list-only     # only find them
python -m news_toolkit.images https://example.com/story --out lead_images/               # download
```

It reads the page's own `og:image` tag, then `twitter:image`, then the first large image. **Check each image's licence
before publishing:** the tool finds pictures, it does not clear rights.

## Design notes

- Every network call goes through a function that tests replace with a fake, so the whole suite runs offline.
- One bad link or one rate-limit answer never stops a list: errors are reported per row.
- Exports are plain CSV so any spreadsheet or notebook can pick them up.
- Python 3.10 or newer.
