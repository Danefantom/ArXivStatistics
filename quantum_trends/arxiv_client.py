"""Sequential, cached arXiv API retrieval with explicit coverage checks."""
from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import requests

API_URL = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom",
      "o": "http://a9.com/-/spec/opensearch/1.1/",
      "x": "http://arxiv.org/schemas/atom"}


class RetrievalError(RuntimeError):
    """Retrieval did not establish a complete corpus."""


def base_id(value: str) -> str:
    return re.sub(r"v\d+$", "", value.split("/abs/")[-1])


def parse_feed(content: bytes) -> tuple[int, int, list[dict]]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise RetrievalError("arXiv returned invalid XML") from exc
    papers = []
    for entry in root.findall("a:entry", NS):
        get = lambda key: " ".join((entry.findtext("a:" + key, "", NS)).split())
        if "/api/errors" in get("id") or get("title").lower() == "error":
            raise RetrievalError("arXiv API error: " + get("summary"))
        identifier = base_id(get("id"))
        primary = entry.find("x:primary_category", NS)
        paper = {"id": identifier, "title": get("title"), "abstract": get("summary"),
                 "published": get("published"), "updated": get("updated"),
                 "categories": [c.attrib["term"] for c in entry.findall("a:category", NS)],
                 "primary_category": primary.attrib.get("term", "") if primary is not None else "",
                 "authors": [a.findtext("a:name", "", NS) for a in entry.findall("a:author", NS)],
                 "url": "https://arxiv.org/abs/" + identifier}
        if not identifier or not paper["published"] or not paper["title"]:
            raise RetrievalError("An arXiv record is missing its ID, title, or submission date")
        papers.append(paper)
    try:
        total = int(root.findtext("o:totalResults", namespaces=NS))
        start = int(root.findtext("o:startIndex", namespaces=NS))
    except (ValueError, TypeError) as exc:
        raise RetrievalError("Missing OpenSearch coverage metadata") from exc
    return total, start, papers


def month_windows(start: date, end: date):
    while start <= end:
        following = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        stop = min(end, following - timedelta(days=1))
        yield start, stop
        start = stop + timedelta(days=1)


def default_dates(months: int = 12, today: date | None = None) -> tuple[date, date]:
    if not 1 <= months <= 120:
        raise ValueError("months must be between 1 and 120")
    today = today or datetime.now(timezone.utc).date()
    offset = today.year * 12 + today.month - months
    return date(offset // 12, offset % 12 + 1, 1), today


def save_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class ArxivClient:
    """Use one active client process at a time (arXiv limits apply across machines)."""

    def __init__(self, cache_dir: Path, *, page_size: int = 500,
                 cache_hours: float = 24, refresh: bool = False,
                 progress: Callable[[str], None] = print,
                 user_agent: str = "QuantumKeywordTrends/1.0 (personal research)"):
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be 1–1000")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.page_size, self.cache_hours, self.refresh = page_size, cache_hours, refresh
        self.progress = progress
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.last_request = 0.0
        self.cache_hits = 0
        self.network_requests = 0
        self.response_times: list[float] = []

    def page(self, query: str, offset: int):
        params = {"search_query": query, "start": offset, "max_results": self.page_size,
                  "sortBy": "submittedDate", "sortOrder": "ascending"}
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / (key + ".xml")
        if path.exists() and not self.refresh and time.time() - path.stat().st_mtime < self.cache_hours * 3600:
            try:
                parsed = parse_feed(path.read_bytes())
                self.cache_hits += 1
                self.response_times.append(path.stat().st_mtime)
                return parsed
            except RetrievalError:
                pass  # Replace a corrupt cache entry with a validated response.
        last_error = None
        for attempt in range(4):
            time.sleep(max(0, 3.1 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                self.network_requests += 1
                response = self.session.get(API_URL, params=params, timeout=(15, 90))
                if response.status_code == 429 or response.status_code >= 500:
                    retry_after = response.headers.get("Retry-After", "")
                    delay = float(retry_after) if retry_after.isdigit() else 6 * 2 ** attempt
                    if attempt < 3:
                        self.progress(f"arXiv HTTP {response.status_code}; retrying in {delay:.0f}s")
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                parsed = parse_feed(response.content)
                temporary = path.with_suffix(".tmp")
                temporary.write_bytes(response.content)
                temporary.replace(path)
                self.response_times.append(path.stat().st_mtime)
                return parsed
            except (requests.RequestException, RetrievalError) as exc:
                last_error = exc
                if isinstance(exc, requests.HTTPError) and exc.response is not None and 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
                    break
                if attempt < 3:
                    time.sleep(6 * 2 ** attempt)
        raise RetrievalError(f"Failed to retrieve arXiv offset {offset}: {last_error}. "
                             "Successful pages remain cached; rerun to resume.")

    def interval(self, start: date, end: date) -> tuple[list[dict], int, int]:
        # The API's minute-resolution upper bound can omit the last 59 seconds
        # of a day. Query through the following midnight, then trim locally.
        following = end + timedelta(days=1)
        query = f"cat:quant-ph AND submittedDate:[{start:%Y%m%d}0000 TO {following:%Y%m%d}0000]"
        total, index, papers = self.page(query, 0)
        if index != 0:
            raise RetrievalError("Unexpected first-page offset from arXiv")
        # Subdivide large searches to avoid the API's result ceiling and unstable deep paging.
        if total > 1000 and start < end:
            midpoint = start + (end - start) // 2
            left, nl, el = self.interval(start, midpoint)
            right, nr, er = self.interval(midpoint + timedelta(days=1), end)
            if nl + nr - el != total:
                raise RetrievalError("arXiv totals changed during retrieval. Retry with --refresh.")
            return left + right, total, er
        if total > 30000:
            raise RetrievalError("One day exceeds the API limit; use arXiv bulk metadata access")
        while len(papers) < total:
            offset = len(papers)
            n, index, batch = self.page(query, offset)
            if n != total or index != offset or not batch:
                raise RetrievalError("Incomplete or changing arXiv pagination. Retry with --refresh.")
            papers.extend(batch)
        if len(papers) != total or len({p["id"] for p in papers}) != total:
            raise RetrievalError("Duplicate records or inconsistent totals; cannot certify complete coverage")
        for paper in papers:
            submitted = date.fromisoformat(paper["published"][:10])
            if not start <= submitted <= following or "quant-ph" not in paper["categories"]:
                raise RetrievalError("API returned a record outside the requested date/category range")
        trimmed = [p for p in papers if date.fromisoformat(p["published"][:10]) <= end]
        return trimmed, total, total - len(trimmed)

    def fetch(self, start: date, end: date) -> dict:
        if start > end:
            raise ValueError("start must be on or before end")
        if end > datetime.now(timezone.utc).date():
            raise ValueError("end must not be in the future")
        papers, coverage = [], []
        for first, last in month_windows(start, end):
            self.progress(f"Fetching {first} to {last} …")
            batch, total, excluded = self.interval(first, last)
            papers.extend(batch)
            coverage.append({"month": first.strftime("%Y-%m"), "start": first.isoformat(),
                             "end": last.isoformat(), "api_total": total,
                             "boundary_excluded": excluded, "retrieved": len(batch),
                             "complete": True})
            self.progress(f"  verified {len(batch):,} papers")
        if len({p['id'] for p in papers}) != len(papers):
            raise RetrievalError("Duplicate IDs across monthly windows")
        return {"schema_version": 1, "source": "arXiv API", "category": "quant-ph",
                "start": start.isoformat(), "end": end.isoformat(),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "oldest_response_at": datetime.fromtimestamp(min(self.response_times), timezone.utc).isoformat() if self.response_times else None,
                "complete": True, "coverage": coverage,
                "cache_hits": self.cache_hits, "network_requests": self.network_requests,
                "papers": sorted(papers, key=lambda p: (p["published"], p["id"]))}
