#!/usr/bin/env python3
"""ITL Crawler CLI — extract public business contacts and export for LLMs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from itl.browser import Browser, available
from itl.contacts import discover_contact_urls, extract_lead, merge_leads
from itl.export import write_csv, write_jsonl, write_llm_pack
from itl.fetch import fetch
from itl.polite import Gate
from itl.urls import normalize


def _harvest(url: str, follow: bool, render: bool | None, max_pages: int) -> list:
    start = normalize(url)
    if not start:
        raise SystemExit(f"invalid url: {url}")
    gate = Gate()
    browser = None
    if available() and render is not False:
        browser = Browser()
        browser.start()
    leads = []
    try:
        home = fetch(start, gate=gate, render=render, browser=browser)
        if not home.ok:
            raise SystemExit(f"fetch failed: {home.error or home.status}")
        lead = extract_lead(home.html, home.final_url, home.text)
        pages = [home.final_url]
        if follow:
            extra = discover_contact_urls(home.html, home.final_url, limit=max(0, max_pages - 1))
            for href in extra:
                page = fetch(href, gate=gate, render=render, browser=browser)
                if not page.ok:
                    continue
                pages.append(page.final_url)
                lead = merge_leads(
                    lead,
                    extract_lead(page.html, page.final_url, page.text, company=lead.company),
                )
        lead.source_pages = list(dict.fromkeys(pages))
        leads.append(lead)
    finally:
        if browser is not None:
            browser.close()
    return leads


def cmd_extract(args: argparse.Namespace) -> int:
    leads = _harvest(args.url, follow=not args.no_follow, render=args.render, max_pages=args.max_pages)
    lead = leads[0]
    if args.jsonl:
        write_jsonl(leads, args.jsonl)
    if args.csv:
        write_csv(leads, args.csv)
    if args.pack:
        write_llm_pack(leads, args.pack, profile=args.profile)
    print(json.dumps(lead.compact(), indent=2, ensure_ascii=False))
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    rows = []
    text = Path(args.jsonl).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    from itl.contacts import ContactHit, Lead

    leads = []
    for row in rows:
        lead = Lead(
            company=row.get("company") or "",
            url=row.get("website") or row.get("url") or "",
            address=row.get("address") or "",
            services=row.get("services") or [],
            summary=row.get("summary") or "",
            score=float(row.get("score") or 0),
            source_pages=row.get("sources") or row.get("source_pages") or [],
        )
        for phone in row.get("phones") or ([row["best_phone"]] if row.get("best_phone") else []):
            if isinstance(phone, dict):
                lead.phones.append(
                    ContactHit(**{k: phone[k] for k in ("value", "kind", "confidence", "source") if k in phone})
                )
            else:
                lead.phones.append(
                    ContactHit(str(phone), "phone", float(row.get("phone_confidence") or 0.6), "import")
                )
        for email in row.get("emails") or ([row["best_email"]] if row.get("best_email") else []):
            if isinstance(email, dict):
                lead.emails.append(
                    ContactHit(**{k: email[k] for k in ("value", "kind", "confidence", "source") if k in email})
                )
            else:
                lead.emails.append(
                    ContactHit(str(email), "email", float(row.get("email_confidence") or 0.6), "import")
                )
        leads.append(lead)
    path = write_llm_pack(leads, args.out, profile=args.profile)
    print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run.py", description="ITL crawler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    extract = sub.add_parser("extract", help="Fetch a site and extract contacts")
    extract.add_argument("url")
    extract.add_argument("--jsonl")
    extract.add_argument("--csv")
    extract.add_argument("--pack", help="Write a Grok/ChatGPT prompt pack")
    extract.add_argument("--profile", default="local contractor leads")
    extract.add_argument("--max-pages", type=int, default=5)
    extract.add_argument("--no-follow", action="store_true")
    extract.add_argument("--render", action="store_true", default=None)
    extract.add_argument("--no-render", action="store_false", dest="render")
    extract.set_defaults(func=cmd_extract)

    pack = sub.add_parser("pack", help="Turn a JSONL file into an LLM prompt pack")
    pack.add_argument("jsonl")
    pack.add_argument("--out", default="llm_pack.json")
    pack.add_argument("--profile", default="local contractor leads")
    pack.set_defaults(func=cmd_pack)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
