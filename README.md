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

## Upgrades in 0.2

1. Trainable lead weights (`run.py label` / `run.py train`)
2. Hashed n-gram embeddings (`itl/embeddings.py`)
3. Contact quality scoring (`info@` < named founder)
4. CSV export of leads and contacts
5. Incremental recrawl by lastmod and change rate
6. SimHash near-duplicate detection
7. Per-host politeness and block detection
8. JS rendering as automatic fallback
9. Lead workspace APIs in Atlas
10. Contact-graph influence (`run.py influence --contacts`)

Plus `itl/brain.py` — brief, explain, refine, draft, ask. Not a downloaded model. A model of this product that reads the store.
