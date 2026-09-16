# ITL Crawler

Hybrid crawler: index, graph, sitemaps, ML, lead scoring, and a local brain.
One SQLite file. Zero required dependencies. Python 3.10+.

## Extract public business contacts

No API key. Fetches the site, follows `/contact` and `/about` when present,
pulls phones, emails, and schema.org data, then writes files a model can read.

```bash
python run.py extract https://yoursite.com --jsonl leads.jsonl --csv leads.csv --pack grok_pack.json
python run.py pack samples/leads.jsonl --format grok --out grok_pack.json --profile "drywall contractor chicago"
python run.py pack samples/leads.jsonl --all --out packs --profile "drywall contractor chicago"
python -m unittest tests.test_extract tests.test_pack -v
```

`--all` writes four packs: Grok, OpenAI, Claude, and Markdown.

Paste `messages` from the Grok pack into chat, or send the OpenAI/Claude `request` object to those APIs. The pack tells the model not to invent numbers that were not extracted.

```python
from itl.fetch import fetch
from itl.contacts import extract_lead
from itl.export import write_jsonl
from itl.pack import write_all

page = fetch("https://example.com")
lead = extract_lead(page.html, page.final_url, page.text)
write_jsonl([lead], "leads.jsonl")
write_all([lead], "packs", profile="remodeling contractor")
```

## JS rendering (HTML browser)

Static fetches miss phones and copy that only appear after JavaScript runs.
`itl/browser.py` adds a headless Chromium fallback via Playwright.

```bash
pip install playwright
playwright install chromium
```

Use `needs_render(html, text)` after a cheap stdlib fetch. If the page looks
like an SPA shell or the extracted text is thin, fall back to Chromium.

## What 0.2.1 adds

- `itl/contacts.py` — phones, emails, JSON-LD, confidence scores
- `itl/pack.py` — Grok, OpenAI, Claude, and Markdown packs
- `itl/export.py` — CSV and JSONL
- `itl/polite.py` — robots.txt + per-host delay
- `itl/fetch.py` — stdlib fetch with optional Chromium fallback
- `itl/browser.py` — Playwright renderer

## Planned engine pieces

1. Trainable lead weights (`run.py label` / `run.py train`)
2. Hashed n-gram embeddings (`itl/embeddings.py`)
3. Incremental recrawl by lastmod and change rate
4. SimHash near-duplicate detection
5. Lead workspace APIs in Atlas
6. Contact-graph influence (`run.py influence --contacts`)

Plus `itl/brain.py` — brief, explain, refine, draft, ask. Not a downloaded model. A model of this product that reads the store.
