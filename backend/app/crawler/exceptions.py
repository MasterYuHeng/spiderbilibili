from __future__ import annotations


class BilibiliCrawlerError(Exception):
    """Base crawler error."""


class BilibiliRequestError(BilibiliCrawlerError):
    """Raised when an HTTP request fails."""


class BilibiliApiError(BilibiliCrawlerError):
    """Raised when the Bilibili API returns an application error."""


class BilibiliAntiCrawlerError(BilibiliCrawlerError):
    """Raised when Bilibili anti-crawler checks block the request."""


class BilibiliParseError(BilibiliCrawlerError):
    """Raised when a response cannot be parsed into the expected shape."""
