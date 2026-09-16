"""Fetch a URL with stdlib first, Chromium if the page looks empty."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from itl.browser import available, extract_text, needs_render
from itl.polite import USER_AGENT, Gate

TIMEOUT = 20


@dataclass
class Fetched:
    url: str
    final_url: str
    status: int | None
    html: str
    text: str
    title: str
    rendered: bool
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.html)


def _static(url: str, user_agent: str = USER_AGENT) -> Fetched:
    req = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*"})
    ctx = ssl.create_default_context()
    try:
        with urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            html = raw.decode(charset, errors="replace")
            title, text = extract_text(html)
            return Fetched(
                url=url,
                final_url=resp.geturl() or url,
                status=getattr(resp, "status", 200),
                html=html,
                text=text,
                title=title,
                rendered=False,
            )
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        title, text = extract_text(body)
        return Fetched(url, url, exc.code, body, text, title, False, str(exc))
    except (URLError, TimeoutError, ValueError, ssl.SSLError) as exc:
        return Fetched(url, url, None, "", "", "", False, str(exc))


def fetch(
    url: str,
    gate: Gate | None = None,
    render: bool | None = None,
    browser=None,
) -> Fetched:
    if gate is not None:
        if not gate.allowed(url):
            return Fetched(url, url, 403, "", "", "", False, "blocked by robots.txt")
        gate.wait(url)

    page = _static(url)
    use_browser = render if render is not None else needs_render(page.html, page.text)
    if not use_browser or not available():
        return page

    from itl.browser import Browser

    owned = False
    engine = browser
    if engine is None:
        engine = Browser()
        engine.start()
        owned = True
    try:
        result = engine.render(page.final_url or url)
        if not result.ok:
            return page
        return Fetched(
            url=url,
            final_url=result.final_url,
            status=result.status or page.status,
            html=result.html,
            text=result.text,
            title=result.title or page.title,
            rendered=True,
        )
    finally:
        if owned:
            engine.close()
