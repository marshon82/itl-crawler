"""Extract business contacts from HTML and plain text."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from itl.urls import host_of, normalize

PHONE_RE = re.compile(
    r"""
    (?<!\d)
    (?:
        \+?1[\s.\-]*
    )?
    (?:
        \(?\d{3}\)?[\s.\-]*
        \d{3}[\s.\-]*
        \d{4}
    )
    (?!\d)
    """,
    re.VERBOSE,
)

EMAIL_RE = re.compile(
    r"""
    [a-zA-Z0-9][a-zA-Z0-9._%+\-]{0,63}
    @
    [a-zA-Z0-9][a-zA-Z0-9.\-]{0,250}
    \.[a-zA-Z]{2,24}
    """,
    re.VERBOSE,
)

JUNK_EMAIL_HOSTS = {
    "example.com",
    "example.org",
    "email.com",
    "domain.com",
    "sentry.io",
    "wixpress.com",
    "squarespace.com",
}

GENERIC_LOCAL = {
    "info",
    "hello",
    "contact",
    "office",
    "admin",
    "support",
    "sales",
    "webmaster",
    "noreply",
    "no-reply",
    "donotreply",
    "privacy",
    "billing",
}

CONTACT_PATHS = (
    "/contact",
    "/contact-us",
    "/contactus",
    "/about",
    "/about-us",
    "/aboutus",
    "/team",
    "/our-team",
    "/staff",
    "/locations",
    "/location",
    "/get-a-quote",
    "/quote",
    "/request-quote",
)

SERVICE_HINTS = (
    "drywall",
    "painting",
    "remodel",
    "remodeling",
    "renovation",
    "contractor",
    "handyman",
    "plumbing",
    "electrical",
    "roofing",
    "flooring",
    "hvac",
    "carpentry",
    "siding",
    "kitchen",
    "bathroom",
)


@dataclass
class ContactHit:
    value: str
    kind: str
    confidence: float
    source: str
    page: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Lead:
    company: str
    url: str
    phones: list[ContactHit] = field(default_factory=list)
    emails: list[ContactHit] = field(default_factory=list)
    address: str = ""
    services: list[str] = field(default_factory=list)
    summary: str = ""
    score: float = 0.0
    source_pages: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "url": self.url,
            "phones": [p.to_dict() for p in self.phones],
            "emails": [e.to_dict() for e in self.emails],
            "address": self.address,
            "services": self.services,
            "summary": self.summary,
            "score": round(self.score, 3),
            "source_pages": self.source_pages,
            "extra": self.extra,
        }

    def compact(self) -> dict:
        """Flat record models can consume without nested noise."""
        return {
            "company": self.company,
            "website": self.url,
            "phones": [p.value for p in self.phones],
            "emails": [e.value for e in self.emails],
            "best_phone": self.phones[0].value if self.phones else "",
            "best_email": self.emails[0].value if self.emails else "",
            "phone_confidence": self.phones[0].confidence if self.phones else 0.0,
            "email_confidence": self.emails[0].confidence if self.emails else 0.0,
            "address": self.address,
            "services": self.services,
            "summary": self.summary,
            "score": round(self.score, 3),
            "sources": self.source_pages,
        }


class _PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.title = ""
        self._in_title = False
        self._skip = 0
        self._chunks: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.jsonld: list[str] = []
        self.tels: list[str] = []
        self.mailtos: list[str] = []
        self._in_ld = False
        self._ld_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        ad = {k.lower(): (v or "") for k, v in attrs}
        if tag in self.SKIP:
            self._skip += 1
            if tag == "script" and "ld+json" in ad.get("type", "").lower():
                self._in_ld = True
                self._ld_chunks = []
                self._skip -= 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = ad.get("href", "").strip()
            if href:
                self.links.append((href, ad.get("title", "")))
                low = href.lower()
                if low.startswith("tel:"):
                    self.tels.append(unquote(href[4:]))
                elif low.startswith("mailto:"):
                    self.mailtos.append(unquote(href[7:].split("?", 1)[0]))
        if tag in {"a", "span", "div", "p", "li"}:
            itemprop = ad.get("itemprop", "").lower()
            if itemprop in {"telephone", "phone"} and ad.get("content"):
                self.tels.append(ad["content"])
            if itemprop == "email" and ad.get("content"):
                self.mailtos.append(ad["content"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if self._in_ld and tag == "script":
            blob = "".join(self._ld_chunks).strip()
            if blob:
                self.jsonld.append(blob)
            self._in_ld = False
            self._ld_chunks = []
            return
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self._ld_chunks.append(data)
            return
        if self._skip:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title = (self.title + " " + text).strip()
            return
        self._chunks.append(text)

    def text(self) -> str:
        return " ".join(self._chunks)


def parse_page(html: str, url: str) -> _PageParser:
    parser = _PageParser(url)
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    return parser


def _clean_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10:
        return None
    if digits[0] in "01" or digits[3] in "01":
        return None
    return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"


def _phone_confidence(source: str, raw: str) -> float:
    score = {"tel": 0.95, "jsonld": 0.9, "microdata": 0.85, "regex": 0.62}.get(source, 0.5)
    if raw.strip().startswith("+"):
        score = min(1.0, score + 0.03)
    return score


def _email_confidence(addr: str, source: str) -> float:
    local, _, host = addr.partition("@")
    score = {"mailto": 0.93, "jsonld": 0.9, "microdata": 0.85, "regex": 0.7}.get(source, 0.55)
    if local.lower() in GENERIC_LOCAL:
        score -= 0.18
    if any(local.lower().startswith(p) for p in ("info", "hello", "contact", "office")):
        score -= 0.08
    if "." in local or local[0].isupper():
        score += 0.08
    if host.lower() in JUNK_EMAIL_HOSTS:
        return 0.05
    return max(0.05, min(0.99, score))


def _walk_jsonld(node, out: dict) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_jsonld(item, out)
        return
    if not isinstance(node, dict):
        return
    typ = node.get("@type")
    if isinstance(typ, list):
        types = {str(t).lower() for t in typ}
    else:
        types = {str(typ).lower()} if typ else set()
    interesting = types & {
        "organization",
        "localbusiness",
        "homeandconstructionbusiness",
        "professionalservice",
        "place",
        "postaladdress",
        "person",
        "contactpoint",
    }
    if interesting or node.get("telephone") or node.get("email"):
        name = node.get("name")
        if isinstance(name, str) and name.strip() and not out.get("name"):
            out["name"] = name.strip()
        tel = node.get("telephone") or node.get("phone")
        if tel:
            out.setdefault("phones", []).append(str(tel))
        email = node.get("email")
        if email:
            out.setdefault("emails", []).append(str(email))
        addr = node.get("address")
        if isinstance(addr, str) and addr.strip() and not out.get("address"):
            out["address"] = addr.strip()
        elif isinstance(addr, dict):
            parts = [
                addr.get("streetAddress"),
                addr.get("addressLocality"),
                addr.get("addressRegion"),
                addr.get("postalCode"),
            ]
            line = ", ".join(str(p) for p in parts if p)
            if line and not out.get("address"):
                out["address"] = line
    for key in ("@graph", "department", "contactPoint", "subOrganization", "location"):
        if key in node:
            _walk_jsonld(node[key], out)


def parse_jsonld(blobs: list[str]) -> dict:
    out: dict = {}
    for blob in blobs:
        blob = blob.strip()
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        _walk_jsonld(data, out)
    return out


def extract_phones(text: str, extra: list[str] | None = None, source: str = "regex") -> list[ContactHit]:
    hits: list[ContactHit] = []
    seen: set[str] = set()

    def add(raw: str, src: str) -> None:
        cleaned = _clean_phone(raw)
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        hits.append(ContactHit(cleaned, "phone", _phone_confidence(src, raw), src))

    for raw in extra or []:
        add(raw, source)
    for match in PHONE_RE.finditer(text or ""):
        add(match.group(0), "regex")
    hits.sort(key=lambda h: h.confidence, reverse=True)
    return hits


def extract_emails(text: str, extra: list[str] | None = None, source: str = "regex") -> list[ContactHit]:
    hits: list[ContactHit] = []
    seen: set[str] = set()

    def add(raw: str, src: str) -> None:
        addr = (raw or "").strip().strip(".,;<>()[]").lower()
        if not EMAIL_RE.fullmatch(addr):
            return
        local, _, host = addr.partition("@")
        if host in JUNK_EMAIL_HOSTS:
            return
        if addr in seen:
            return
        seen.add(addr)
        hits.append(ContactHit(addr, "email", _email_confidence(addr, src), src))

    for raw in extra or []:
        add(raw, source)
    for match in EMAIL_RE.finditer(text or ""):
        add(match.group(0), "regex")
    hits.sort(key=lambda h: h.confidence, reverse=True)
    return hits


def infer_services(text: str) -> list[str]:
    low = (text or "").lower()
    found = [s for s in SERVICE_HINTS if s in low]
    return found[:8]


def summarize(text: str, limit: int = 420) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def discover_contact_urls(html: str, base: str, limit: int = 8) -> list[str]:
    parser = parse_page(html, base)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    origin_host = host_of(base)
    for href, title in parser.links:
        url = normalize(href, base)
        if not url or host_of(url) != origin_host:
            continue
        raw_path = (urlsplit(url).path or "/").lower()
        blob = f"{raw_path} {title.lower()} {href.lower()}"
        score = 0
        for hint in CONTACT_PATHS:
            if raw_path.rstrip("/") == hint or raw_path.startswith(hint + "/"):
                score += 8
            elif hint.strip("/") in raw_path or hint.strip("/") in blob:
                score += 3
        if score and url not in seen:
            seen.add(url)
            scored.append((score, url))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [u for _, u in scored[:limit]]


def extract_lead(html: str, url: str, text: str | None = None, company: str | None = None) -> Lead:
    parser = parse_page(html, url)
    body = text if text is not None else parser.text()
    ld = parse_jsonld(parser.jsonld)
    phones = extract_phones(body, extra=parser.tels + ld.get("phones", []), source="tel")
    emails = extract_emails(body, extra=parser.mailtos + ld.get("emails", []), source="mailto")
    name = company or ld.get("name") or parser.title or host_of(url)
    name = re.sub(r"\s+[|\-\u2013].*$", "", name).strip() or host_of(url)
    lead = Lead(
        company=name,
        url=url,
        phones=phones,
        emails=emails,
        address=ld.get("address", ""),
        services=infer_services(body),
        summary=summarize(body),
        source_pages=[url],
        extra={"title": parser.title, "jsonld": bool(ld)},
    )
    lead.score = score_lead(lead)
    return lead


def score_lead(lead: Lead) -> float:
    score = 0.0
    if lead.phones:
        score += 0.38 + 0.12 * lead.phones[0].confidence
    if lead.emails:
        score += 0.22 + 0.1 * lead.emails[0].confidence
    if lead.address:
        score += 0.12
    if lead.services:
        score += min(0.12, 0.03 * len(lead.services))
    if any("/contact" in p or "/about" in p for p in lead.source_pages):
        score += 0.04
    return min(1.0, score)


def merge_leads(primary: Lead, extra: Lead) -> Lead:
    phones = {p.value: p for p in primary.phones}
    for hit in extra.phones:
        cur = phones.get(hit.value)
        if cur is None or hit.confidence > cur.confidence:
            phones[hit.value] = hit
    emails = {e.value: e for e in primary.emails}
    for hit in extra.emails:
        cur = emails.get(hit.value)
        if cur is None or hit.confidence > cur.confidence:
            emails[hit.value] = hit
    primary.phones = sorted(phones.values(), key=lambda h: h.confidence, reverse=True)
    primary.emails = sorted(emails.values(), key=lambda h: h.confidence, reverse=True)
    if extra.address and not primary.address:
        primary.address = extra.address
    if extra.company and len(extra.company) < len(primary.company):
        primary.company = extra.company
    primary.services = list(dict.fromkeys(primary.services + extra.services))
    for page in extra.source_pages:
        if page not in primary.source_pages:
            primary.source_pages.append(page)
    if extra.summary and len(extra.summary) > len(primary.summary):
        primary.summary = extra.summary
    primary.score = score_lead(primary)
    return primary
