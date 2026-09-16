"""Build LLM prompt packs from extracted leads."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from itl.contacts import ContactHit, Lead

SYSTEM = (
    "You score contractor and local-business leads. "
    "Use only the fields in each record. Do not invent phone numbers, emails, "
    "or addresses. If a field is empty, say it is missing. "
    "Return valid JSON."
)

USER_TEMPLATE = """Rank these leads for: {profile}

Return a JSON array. Each item must include:
- company
- website
- fit (0-1)
- why (one sentence)
- outreach_angle (one sentence)
- best_contact (phone or email copied from the record, or null)
- missing (list of fields still needed)

Do not invent contact details.

Leads:
{payload}
"""


def rows_to_leads(rows: list[dict]) -> list[Lead]:
    leads: list[Lead] = []
    for row in rows:
        lead = Lead(
            company=row.get("company") or "",
            url=row.get("website") or row.get("url") or "",
            address=row.get("address") or "",
            services=list(row.get("services") or []),
            summary=row.get("summary") or "",
            score=float(row.get("score") or 0),
            source_pages=list(row.get("sources") or row.get("source_pages") or []),
        )
        phones = row.get("phones") or ([row["best_phone"]] if row.get("best_phone") else [])
        emails = row.get("emails") or ([row["best_email"]] if row.get("best_email") else [])
        for phone in phones:
            if isinstance(phone, dict):
                lead.phones.append(
                    ContactHit(
                        value=str(phone.get("value", "")),
                        kind=str(phone.get("kind", "phone")),
                        confidence=float(phone.get("confidence") or 0.6),
                        source=str(phone.get("source", "import")),
                    )
                )
            elif phone:
                lead.phones.append(
                    ContactHit(str(phone), "phone", float(row.get("phone_confidence") or 0.6), "import")
                )
        for email in emails:
            if isinstance(email, dict):
                lead.emails.append(
                    ContactHit(
                        value=str(email.get("value", "")),
                        kind=str(email.get("kind", "email")),
                        confidence=float(email.get("confidence") or 0.6),
                        source=str(email.get("source", "import")),
                    )
                )
            elif email:
                lead.emails.append(
                    ContactHit(str(email), "email", float(row.get("email_confidence") or 0.6), "import")
                )
        leads.append(lead)
    return leads


def load_jsonl(path: str) -> list[Lead]:
    text = Path(path).read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    return rows_to_leads(rows)


def records(leads: list[Lead]) -> list[dict]:
    return [lead.compact() for lead in leads]


def messages(leads: list[Lead], profile: str) -> list[dict]:
    user = USER_TEMPLATE.format(
        profile=profile,
        payload=json.dumps(records(leads), indent=2, ensure_ascii=False),
    )
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]


def grok_pack(leads: list[Lead], profile: str) -> dict:
    recs = records(leads)
    return {
        "schema_version": "1.1",
        "format": "grok",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "profile": profile,
        "lead_count": len(recs),
        "how_to_use": "Paste messages into Grok chat, or send them to the xAI chat API.",
        "messages": messages(leads, profile),
        "leads": recs,
    }


def openai_pack(leads: list[Lead], profile: str, model: str = "gpt-4.1") -> dict:
    return {
        "schema_version": "1.1",
        "format": "openai",
        "model": model,
        "profile": profile,
        "lead_count": len(leads),
        "how_to_use": "POST this body to the OpenAI Chat Completions API.",
        "request": {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": messages(leads, profile)
            + [{"role": "user", "content": "Wrap the array in {\"rankings\": [...]}."}],
        },
        "leads": records(leads),
    }


def claude_pack(leads: list[Lead], profile: str, model: str = "claude-sonnet-4-5") -> dict:
    msgs = messages(leads, profile)
    return {
        "schema_version": "1.1",
        "format": "claude",
        "model": model,
        "profile": profile,
        "lead_count": len(leads),
        "how_to_use": "POST this body to the Anthropic Messages API.",
        "request": {
            "model": model,
            "max_tokens": 2000,
            "temperature": 0,
            "system": msgs[0]["content"],
            "messages": [{"role": "user", "content": msgs[1]["content"]}],
        },
        "leads": records(leads),
    }


def markdown_pack(leads: list[Lead], profile: str) -> str:
    lines = [
        "# Lead pack",
        "",
        f"Profile: {profile}",
        f"Leads: {len(leads)}",
        "",
        SYSTEM,
        "",
        "## Task",
        "",
        f"Rank these public business leads for **{profile}**.",
        "Copy contact fields only. Do not invent phones or emails.",
        "",
    ]
    for i, lead in enumerate(leads, 1):
        row = lead.compact()
        lines.extend(
            [
                f"### {i}. {row['company'] or 'Unknown company'}",
                f"- Website: {row['website'] or 'missing'}",
                f"- Phone: {row['best_phone'] or 'missing'} (confidence {row['phone_confidence']})",
                f"- Email: {row['best_email'] or 'missing'} (confidence {row['email_confidence']})",
                f"- Address: {row['address'] or 'missing'}",
                f"- Services: {', '.join(row['services']) or 'missing'}",
                f"- Score: {row['score']}",
                f"- Sources: {' '.join(row['sources']) or 'missing'}",
                f"- Summary: {row['summary'] or 'missing'}",
                "",
            ]
        )
    lines.extend(
        [
            "## Return JSON",
            "",
            "```json",
            "[",
            "  {",
            '    "company": "",',
            '    "website": "",',
            '    "fit": 0.0,',
            '    "why": "",',
            '    "outreach_angle": "",',
            '    "best_contact": null,',
            '    "missing": []',
            "  }",
            "]",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_pack(
    leads: list[Lead],
    path: str,
    profile: str = "local contractor leads",
    fmt: str = "grok",
) -> str:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fmt = (fmt or "grok").lower()
    if fmt in {"md", "markdown"}:
        out.write_text(markdown_pack(leads, profile), encoding="utf-8")
        return str(out)
    if fmt in {"openai", "chatgpt", "gpt"}:
        payload = openai_pack(leads, profile)
    elif fmt in {"claude", "anthropic"}:
        payload = claude_pack(leads, profile)
    else:
        payload = grok_pack(leads, profile)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out)


def write_all(
    leads: list[Lead],
    directory: str,
    profile: str = "local contractor leads",
    stem: str = "lead_pack",
) -> dict[str, str]:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    return {
        "grok": write_pack(leads, str(root / f"{stem}.grok.json"), profile, "grok"),
        "openai": write_pack(leads, str(root / f"{stem}.openai.json"), profile, "openai"),
        "claude": write_pack(leads, str(root / f"{stem}.claude.json"), profile, "claude"),
        "markdown": write_pack(leads, str(root / f"{stem}.md"), profile, "markdown"),
    }
