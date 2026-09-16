"""Write leads as CSV, JSONL, and LLM prompt packs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from itl.contacts import Lead

GROK_SYSTEM = (
    "You score contractor and local-business leads. "
    "Use only the fields in each record. Do not invent phone numbers, emails, "
    "or addresses. If a field is empty, say it is missing. "
    "Return valid JSON."
)

GROK_USER_TEMPLATE = """Rank these leads for: {profile}

Return a JSON array. Each item:
- company
- website
- fit (0-1)
- why (one sentence)
- outreach_angle (one sentence)
- best_contact (phone or email from the record, or null)
- missing (list of fields you still need)

Leads:
{payload}
"""


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
    records = [lead.compact() for lead in leads]
    user = GROK_USER_TEMPLATE.format(
        profile=profile,
        payload=json.dumps(records, indent=2, ensure_ascii=False),
    )
    return {
        "schema_version": "1.0",
        "model_hint": model,
        "profile": profile,
        "lead_count": len(records),
        "messages": [
            {"role": "system", "content": GROK_SYSTEM},
            {"role": "user", "content": user},
        ],
        "leads": records,
    }


def write_llm_pack(leads: list[Lead], path: str, profile: str = "local contractor leads") -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pack = llm_pack(leads, profile=profile)
    out.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out)
