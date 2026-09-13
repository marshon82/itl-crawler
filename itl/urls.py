"""URL normalization — the frontier's first line of defense."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

DROP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "mc_cid",
    "mc_eid", "igshid", "ref", "ref_src", "ref_url",
}


def normalize(url: str, base: str | None = None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if base:
        url = urljoin(base, url)
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower()
    if not host or host in ("localhost",):
        return None
    path = parts.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        if k.lower() in DROP_PARAMS:
            continue
        query.append((k, v))
    query.sort()
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, path, urlencode(query), ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def origin_of(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"
