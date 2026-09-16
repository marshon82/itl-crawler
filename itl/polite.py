"""robots.txt checks and per-host crawl delay."""

from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlsplit

from itl.urls import origin_of

DEFAULT_DELAY = 1.0
USER_AGENT = "ITLCrawler/0.2"


class Gate:
    def __init__(self, user_agent: str = USER_AGENT, delay: float = DEFAULT_DELAY) -> None:
        self.user_agent = user_agent
        self.delay = delay
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._next: dict[str, float] = {}

    def _parser(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        origin = origin_of(url)
        if origin in self._robots:
            return self._robots[origin]
        robots_url = origin.rstrip("/") + "/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
            self._robots[origin] = parser
        except Exception:
            self._robots[origin] = None
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        parser = self._parser(url)
        if parser is None:
            return True
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def crawl_delay(self, url: str) -> float:
        parser = self._parser(url)
        delay = self.delay
        if parser is not None:
            try:
                stated = parser.crawl_delay(self.user_agent)
                if stated:
                    delay = max(delay, float(stated))
            except Exception:
                pass
        return delay

    def wait(self, url: str) -> None:
        host = (urlsplit(url).hostname or "").lower()
        now = time.monotonic()
        due = self._next.get(host, 0.0)
        if due > now:
            time.sleep(due - now)
        self._next[host] = time.monotonic() + self.crawl_delay(url)
