"""Headless Chromium fallback for JS-heavy pages.

Optional. Core crawl stays stdlib. If Playwright + Chromium are installed,
this module fetches a URL, waits for the page to settle, and returns the
rendered HTML plus extracted text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

DEFAULT_TIMEOUT_MS = 20_000
DEFAULT_WAIT = "networkidle"
USER_AGENT = (
    "ITLCrawler/0.2 (+https://github.com/marshon82/itl-crawler) "
    "Mozilla/5.0 (compatible; ITLBot/0.2)"
)

# Thin pages that often mean the real content is behind JS.
THIN_TEXT_CHARS = 400
SPA_MARKERS = (
    "id=\"root\"",
    "id='root'",
    "id=\"app\"",
    "id='app'",
    "id=\"__next\"",
    "ng-version",
    "data-reactroot",
    "__NUXT__",
)


class BrowserUnavailable(RuntimeError):
    """Playwright or Chromium is not installed."""


@dataclass
class RenderResult:
    url: str
    final_url: str
    status: int | None
    title: str
    html: str
    text: str
    rendered: bool = True
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.html)


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._chunks: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
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


def extract_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        pass
    return parser.title, parser.text()


def available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False
    return True


def needs_render(html: str | None, text: str | None = None) -> bool:
    """Heuristic: static fetch looked empty or like an SPA shell."""
    raw = html or ""
    body = text if text is not None else extract_text(raw)[1]
    if len(body) < THIN_TEXT_CHARS:
        return True
    lower = raw.lower()
    return any(marker in lower for marker in SPA_MARKERS)


class Browser:
    """Reusable headless Chromium session."""

    def __init__(
        self,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        wait_until: str = DEFAULT_WAIT,
        user_agent: str = USER_AGENT,
        headless: bool = True,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.wait_until = wait_until
        self.user_agent = user_agent
        self.headless = headless
        self._pw = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "Browser":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start(self) -> None:
        if self._browser is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailable(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            ) from exc
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=self.headless)
        except Exception as exc:
            self._pw.stop()
            self._pw = None
            raise BrowserUnavailable(
                "Chromium is missing. Run: playwright install chromium"
            ) from exc
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        self._context.set_default_timeout(self.timeout_ms)

    def close(self) -> None:
        for closer in (self._context, self._browser):
            if closer is not None:
                try:
                    closer.close()
                except Exception:
                    pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._context = None
        self._browser = None
        self._pw = None

    def render(self, url: str) -> RenderResult:
        self.start()
        assert self._context is not None
        page = self._context.new_page()
        status: int | None = None
        final_url = url
        try:
            response = page.goto(url, wait_until=self.wait_until, timeout=self.timeout_ms)
            if response is not None:
                status = response.status
                final_url = response.url or page.url
            else:
                final_url = page.url
            try:
                page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 8_000))
            except Exception:
                pass
            html = page.content() or ""
            title, text = extract_text(html)
            if not title:
                title = (page.title() or "").strip()
            return RenderResult(
                url=url,
                final_url=final_url,
                status=status,
                title=title,
                html=html,
                text=text,
            )
        except Exception as exc:
            return RenderResult(
                url=url,
                final_url=final_url,
                status=status,
                title="",
                html="",
                text="",
                rendered=False,
                error=str(exc),
            )
        finally:
            try:
                page.close()
            except Exception:
                pass


def render(url: str, **kwargs) -> RenderResult:
    """One-shot render. Opens Chromium, fetches the page, then shuts down."""
    with Browser(**kwargs) as browser:
        return browser.render(url)
