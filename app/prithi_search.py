from __future__ import annotations

import html
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SearchSource:
    title: str
    url: str
    snippet: str
    quality: int = 4

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SearchEvidence:
    query: str
    searched_at: str
    sources: list[SearchSource]
    confidence: float
    summary: str
    conflicting: bool = False
    retry_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {**asdict(self), "sources": [source.as_dict() for source in self.sources]}


def source_quality(url: str) -> int:
    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    if host.endswith((".gov", ".gov.in", ".nic.in", ".int")) or host in {
        "who.int", "un.org", "europa.eu", "whitehouse.gov", "presidentofindia.nic.in",
    }:
        return 1
    if host in {
        "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nasa.gov", "nature.com",
        "thehindu.com", "indianexpress.com", "espn.com", "cricbuzz.com",
    }:
        return 2
    if host.endswith((".edu", ".ac.in")) or host.startswith("docs."):
        return 2
    return 3 if host else 4


class _DuckParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._capture = ""
        self._href = ""
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = values.get("class", "") or ""
        if tag == "a" and "result__a" in classes:
            self._capture, self._href, self._buffer = "title", values.get("href", "") or "", []
        elif "result__snippet" in classes:
            self._capture, self._buffer = "snippet", []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title" and tag == "a":
            self.results.append({"title": " ".join(self._buffer), "url": self._href, "snippet": ""})
            self._capture = ""
        elif self._capture == "snippet" and tag in {"a", "div", "span"}:
            if self.results:
                self.results[-1]["snippet"] = " ".join(self._buffer)
            self._capture = ""


def _direct_url(value: str) -> str:
    decoded = html.unescape(value)
    parsed = urlparse(decoded)
    target = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(target) if target else decoded


class DuckDuckGoSearchProvider:
    """Small no-key HTML search adapter; callers can inject another provider."""

    endpoint = "https://html.duckduckgo.com/html/"

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout

    def search(self, query: str, limit: int = 6) -> list[SearchSource]:
        response = httpx.get(
            self.endpoint,
            params={"q": query},
            headers={"User-Agent": "PrithiVoice/3.1 knowledge retrieval"},
            timeout=self.timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
        parser = _DuckParser()
        parser.feed(response.text)
        sources: list[SearchSource] = []
        seen: set[str] = set()
        for item in parser.results:
            url = _direct_url(item["url"])
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            title = re.sub(r"\s+", " ", html.unescape(item["title"])).strip()[:180]
            snippet = re.sub(r"\s+", " ", html.unescape(item["snippet"])).strip()[:500]
            if title:
                sources.append(SearchSource(title, url, snippet, source_quality(url)))
            if len(sources) >= limit:
                break
        return sources


def sources_disagree(sources: list[SearchSource]) -> bool:
    positives, negatives = [], []
    for source in sources:
        text = source.snippet.casefold()
        tokens = set(re.findall(r"[a-z\u0980-\u09ff\u0900-\u097f]{3,}", text))
        negative = bool(re.search(r"\b(?:is|was|has|are|were) not\b|\bno longer\b|নয়|নেই|नहीं", text))
        (negatives if negative else positives).append(tokens)
    return any(len(a.intersection(b)) / max(1, min(len(a), len(b))) >= .35 for a in positives for b in negatives)


def summarize_sources(sources: list[SearchSource]) -> str:
    lines = []
    for source in sorted(sources, key=lambda item: item.quality)[:4]:
        evidence = source.snippet or source.title
        lines.append(f"[{source.title}] {evidence[:360]} ({source.url})")
    return "\n".join(lines)


def evidence_from_sources(query: str, sources: list[SearchSource], retry_count: int = 0) -> SearchEvidence:
    ranked = sorted(sources, key=lambda item: item.quality)
    authoritative = sum(source.quality == 1 for source in ranked)
    reputable = sum(source.quality <= 2 for source in ranked)
    domains = {urlparse(source.url).hostname for source in ranked if urlparse(source.url).hostname}
    confidence = min(.95, .18 + .14 * min(len(ranked), 4) + .15 * min(authoritative, 2) + .07 * min(reputable, 2) + .04 * min(len(domains), 3))
    conflicting = sources_disagree(ranked)
    if conflicting:
        confidence = min(confidence, .48)
    return SearchEvidence(query, utc_now().isoformat(timespec="seconds"), ranked[:6], round(confidence, 3), summarize_sources(ranked), conflicting, retry_count)


_FAST_MOVING = (
    "score", "live", "price", "stock", "crypto", "weather", "today", "right now", "news",
    "দাম", "স্কোর", "আজকের", "এখন", "भाव",
)
_SLOW_MOVING = (
    "president", "prime minister", "chief minister", "capital", "population", "ceo",
    "রাষ্ট্রপতি", "প্রধানমন্ত্রী", "राष्ट्रपति", "प्रधानमंत्री",
)


def ttl_for_query(query: str, default_seconds: int = 900) -> int:
    """Fast-moving facts expire quickly; slow-moving office holders may be cached longer."""
    low = f" {query.casefold()} "
    if any(marker in low for marker in _FAST_MOVING):
        return min(default_seconds, 180)
    if any(marker in low for marker in _SLOW_MOVING):
        return max(default_seconds, 6 * 3600)
    return default_seconds


class SearchHistoryStore:
    """TTL cache kept separate from user memory and learned behavior."""

    def __init__(self, db_path: str | Path, ttl_seconds: int = 900) -> None:
        self.db_path, self.ttl_seconds = Path(db_path), max(30, int(ttl_seconds))
        with sqlite3.connect(self.db_path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS retrieval_cache(
                query_key TEXT PRIMARY KEY, query TEXT NOT NULL, searched_at TEXT NOT NULL,
                expires_at TEXT NOT NULL, confidence REAL NOT NULL, evidence_json TEXT NOT NULL)""")

    @staticmethod
    def _key(query: str) -> str:
        return re.sub(r"\s+", " ", query.casefold()).strip()

    def get(self, query: str) -> SearchEvidence | None:
        with sqlite3.connect(self.db_path) as db:
            row = db.execute("SELECT expires_at,evidence_json FROM retrieval_cache WHERE query_key=?", (self._key(query),)).fetchone()
        if not row or datetime.fromisoformat(row[0]) <= utc_now():
            return None
        payload = json.loads(row[1])
        payload["sources"] = [SearchSource(**source) for source in payload["sources"]]
        return SearchEvidence(**payload)

    def put(self, evidence: SearchEvidence, ttl_seconds: int | None = None) -> None:
        expires = utc_now() + timedelta(seconds=max(30, int(ttl_seconds)) if ttl_seconds else self.ttl_seconds)
        payload = json.dumps(evidence.as_dict(), ensure_ascii=False, separators=(",", ":"))
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT OR REPLACE INTO retrieval_cache(query_key,query,searched_at,expires_at,confidence,evidence_json) VALUES(?,?,?,?,?,?)",
                (self._key(evidence.query), evidence.query, evidence.searched_at, expires.isoformat(timespec="seconds"), evidence.confidence, payload),
            )
