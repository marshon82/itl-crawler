#!/usr/bin/env python3
"""ITL Crawler CLI — extract public business contacts and export for LLMs."""

from __future__ import annotations

import argparse
import json
import sys

from itl.browser import Browser, available
from itl.contacts import discover_contact_urls, extract_lead, merge_leads
from itl.export import write_csv, write_jsonl, write_llm_pack
from itl.fetch import fetch
from itl.pack import load_jsonl, write_all, write_pack
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
    leads = load_jsonl(args.jsonl)
    if not leads:
        raise SystemExit("no leads in jsonl")
    if args.all:
        directory = "packs" if args.out in {"lead_pack.json", None, ""} else args.out
        written = write_all(leads, directory, profile=args.profile, stem=args.stem)
        print(json.dumps(written, indent=2))
        return 0
    path = write_pack(leads, args.out or "lead_pack.json", profile=args.profile, fmt=args.format)
    print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run.py", description="ITL crawler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    extract = sub.add_parser("extract", help="Fetch a site and extract contacts")
    extract.add_argument("url")
    extract.add_argument("--jsonl")
    extract.add_argument("--csv")
    extract.add_argument("--pack", help="Write a Grok prompt pack")
    extract.add_argument("--profile", default="local contractor leads")
    extract.add_argument("--max-pages", type=int, default=5)
    extract.add_argument("--no-follow", action="store_true")
    extract.add_argument("--render", action="store_true", default=None)
    extract.add_argument("--no-render", action="store_false", dest="render")
    extract.set_defaults(func=cmd_extract)

    pack = sub.add_parser("pack", help="Turn a JSONL file into an LLM prompt pack")
    pack.add_argument("jsonl")
    pack.add_argument("--out", default="lead_pack.json")
    pack.add_argument("--profile", default="local contractor leads")
    pack.add_argument("--format", default="grok", help="grok | openai | claude | markdown")
    pack.add_argument("--all", action="store_true", help="Write grok, openai, claude, and markdown packs")
    pack.add_argument("--stem", default="lead_pack")
    pack.set_defaults(func=cmd_pack)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
