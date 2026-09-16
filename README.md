# ITL Crawler

Hybrid crawler: index, graph, sitemaps, ML, lead scoring, and a local brain.
One SQLite file. Zero required dependencies. Python 3.10+.

Repo is being filled with the 0.2 engine. Clone and, if any files are still landing, grab the full tree from the working copy.

```bash
python run.py crawl https://yoursite.com --max-pages 300 --depth 3
python run.py leads "drywall painting remodeling contractor chicago" -v --csv leads.csv
python run.py brain --profile "drywall contractor chicago"
python run.py dashboard --port 8080
python -m unittest tests.test_engine -v
```

## JS rendering (HTML browser)

Static fetches miss phones and copy that only appear after JavaScript runs.
`itl/browser.py` adds a headless Chromium fallback via Playwright.

```bash
pip install playwright
playwright install chromium
```

```python
from itl.browser import Browser, available, needs_render, render

# One page
page = render("https://example.com")
print(page.title, page.status, page.text[:200])

# Reuse one browser across many URLs
if available():
    with Browser() as browser:
        result = browser.render("https://example.com/contact")
        if result.ok:
            html, text = result.html, result.text
```

Use `needs_render(html, text)` after a cheap stdlib fetch. If the page looks
like an SPA shell or the extracted text is thin, fall back to Chromium.

## Upgrades in 0.2

1. Trainable lead weights (`run.py label` / `run.py train`)
2. Hashed n-gram embeddings (`itl/embeddings.py`)
3. Contact quality scoring (`info@` < named founder)
4. CSV export of leads and contacts
5. Incremental recrawl by lastmod and change rate
6. SimHash near-duplicate detection
7. Per-host politeness and block detection
8. JS rendering as automatic fallback (`itl/browser.py`)
9. Lead workspace APIs in Atlas
10. Contact-graph influence (`run.py influence --contacts`)

Plus `itl/brain.py` — brief, explain, refine, draft, ask. Not a downloaded model. A model of this product that reads the store.
