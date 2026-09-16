"""Write leads as CSV, JSONL, and LLM prompt packs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from itl.contacts import Lead
from itl.pack import grok_pack, write_pack


def write_jsonl(leads: list[Lead], path: str, compact: bool = True) -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for lead in leads:
            row = lead.compact() if compact else lead.to_dict()
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return str(out)


def write_csv(leads: list[Lead], path: str) -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "company",
        "website",
        "best_phone",
        "best_email",
        "phone_confidence",
        "email_confidence",
        "address",
        "services",
        "score",
        "summary",
        "sources",
    ]
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for lead in leads:
            row = lead.compact()
            writer.writerow(
                {
                    "company": row["company"],
                    "website": row["website"],
                    "best_phone": row["best_phone"],
                    "best_email": row["best_email"],
                    "phone_confidence": row["phone_confidence"],
                    "email_confidence": row["email_confidence"],
                    "address": row["address"],
                    "services": "; ".join(row["services"]),
                    "score": row["score"],
                    "summary": row["summary"],
                    "sources": " ".join(row["sources"]),
                }
            )
    return str(out)


def llm_pack(
    leads: list[Lead],
    profile: str = "local contractor leads",
    model: str = "grok",
) -> dict:
    pack = grok_pack(leads, profile)
    pack["model_hint"] = model
    return pack


def write_llm_pack(leads: list[Lead], path: str, profile: str = "local contractor leads") -> str:
    return write_pack(leads, path, profile=profile, fmt="grok")
