from __future__ import annotations

import re
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import feedparser
import httpx
from bs4 import BeautifulSoup

from app.core.cache import ttl_cache


@dataclass(frozen=True)
class NewsItem:
    title: str
    summary: str
    url: str
    source: str
    publish_time: Optional[str]
    image_url: Optional[str]
    tags: List[str]


@dataclass(frozen=True)
class SourceConfig:
    source: str
    region: str  # vn | global
    rss_urls: List[str]
    html_seed_urls: List[str]


DEFAULT_SOURCES: Dict[str, SourceConfig] = {
    # Vietnam
    "vnexpress": SourceConfig(
        source="vnexpress",
        region="vn",
        rss_urls=[
            "https://vnexpress.net/rss/kinh-doanh.rss",
            # Some installs of VNExpress have section feeds; fallback handled by try/except
            "https://vnexpress.net/rss/tin-moi-nhat.rss",
        ],
        html_seed_urls=[
            "https://vnexpress.net/kinh-doanh/chung-khoan",
        ],
    ),
    "cafef": SourceConfig(
        source="cafef",
        region="vn",
        rss_urls=[],
        html_seed_urls=[
            "https://cafef.vn/thi-truong-chung-khoan.chn",
            "https://cafef.vn/chung-khoan.chn",
        ],
    ),
    "tinnhanhchungkhoan": SourceConfig(
        source="tinnhanhchungkhoan",
        region="vn",
        rss_urls=[],
        html_seed_urls=[
            "https://www.tinnhanhchungkhoan.vn/",
            "https://www.tinnhanhchungkhoan.vn/chung-khoan/",
        ],
    ),
    "vietstock": SourceConfig(
        source="vietstock",
        region="vn",
        rss_urls=[
            # Vietstock/Stockbiz RSS endpoints (often reliable)
            "https://en.stockbiz.vn/RSS/News/Market.ashx",
            "https://en.stockbiz.vn/RSS/News/TopStories.ashx",
        ],
        html_seed_urls=[
            "https://vietstock.vn/",
            "https://finance.vietstock.vn/",
        ],
    ),
    # Global
    "bloomberg": SourceConfig(
        source="bloomberg",
        region="global",
        rss_urls=["https://feeds.bloomberg.com/markets/news.rss"],
        html_seed_urls=["https://www.bloomberg.com/markets/"],
    ),
}


def _strip_html(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(" ", strip=True)


def _to_iso(dt_struct) -> Optional[str]:
    try:
        if not dt_struct:
            return None
        dt = datetime(*dt_struct[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _extract_image_from_entry(entry: Any) -> Optional[str]:
    for key in ("media_content", "media_thumbnail"):
        val = getattr(entry, key, None)
        if isinstance(val, list) and val:
            url = val[0].get("url")
            if url:
                return str(url)
    enclosures = getattr(entry, "enclosures", None)
    if isinstance(enclosures, list) and enclosures:
        href = enclosures[0].get("href") or enclosures[0].get("url")
        if href:
            return str(href)

    summary = getattr(entry, "summary", "") or ""
    if summary:
        soup = BeautifulSoup(summary, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return str(img.get("src"))
    return None


async def _fetch_rss_items(
    client: httpx.AsyncClient,
    source: str,
    rss_urls: Sequence[str],
    limit: int,
) -> List[NewsItem]:
    headers = {
        "User-Agent": "VN-Stock-Monitor/0.1 (+https://localhost)",
        "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
    }

    items: List[NewsItem] = []
    for url in rss_urls:
        try:
            resp = await client.get(url, headers=headers, follow_redirects=True, timeout=15)
            if resp.status_code != 200:
                continue
            parsed = feedparser.parse(resp.content)
            for entry in parsed.entries[: max(10, limit)]:
                title = str(getattr(entry, "title", "") or "").strip()
                link = str(getattr(entry, "link", "") or "").strip()
                if not title or not link:
                    continue
                summary_raw = str(getattr(entry, "summary", "") or "")
                summary = _strip_html(summary_raw)
                publish_time = (
                    _to_iso(getattr(entry, "published_parsed", None))
                    or _to_iso(getattr(entry, "updated_parsed", None))
                )
                tags = []
                if hasattr(entry, "tags") and entry.tags:
                    tags = [str(t.get("term", "")).strip() for t in entry.tags if t.get("term")]
                image_url = _extract_image_from_entry(entry)
                items.append(
                    NewsItem(
                        title=title,
                        summary=summary,
                        url=link,
                        source=source,
                        publish_time=publish_time,
                        image_url=image_url,
                        tags=tags[:10],
                    )
                )
            if items:
                break
        except Exception:
            continue

    return items[:limit]


def _extract_links_from_html(html: str, base_url: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: List[Tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "").strip()
        title = a.get_text(" ", strip=True)
        if not href or not title:
            continue
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        if href.startswith("/"):
            href = base_url.rstrip("/") + href
        if not href.startswith("http"):
            continue
        links.append((title, href))
    return links


def _dedupe_keep_order(pairs: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen = set()
    out = []
    for title, url in pairs:
        key = url
        if key in seen:
            continue
        seen.add(key)
        out.append((title, url))
    return out


async def _fetch_html_items(
    client: httpx.AsyncClient,
    source: str,
    seed_urls: Sequence[str],
    limit: int,
) -> List[NewsItem]:
    headers = {
        "User-Agent": "VN-Stock-Monitor/0.1 (+https://localhost)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    collected: List[Tuple[str, str]] = []

    for seed in seed_urls:
        try:
            resp = await client.get(seed, headers=headers, follow_redirects=True, timeout=15)
            if resp.status_code != 200:
                continue
            base = seed.split("/", 3)[:3]
            base_url = "/".join(base)
            collected.extend(_extract_links_from_html(resp.text, base_url=base_url))
        except Exception:
            continue

    pairs = _dedupe_keep_order(collected)

    # Heuristic: prioritize article-like URLs
    article_like = []
    other = []
    for title, url in pairs:
        if re.search(r"(post|\.html|\.chn|/news|/chung-khoan|/thi-truong)", url, re.IGNORECASE):
            article_like.append((title, url))
        else:
            other.append((title, url))

    chosen = (article_like + other)[:limit]
    return [
        NewsItem(
            title=t,
            summary="",
            url=u,
            source=source,
            publish_time=None,
            image_url=None,
            tags=[],
        )
        for t, u in chosen
    ]


class NewsService:
    def __init__(self, sources: Optional[Dict[str, SourceConfig]] = None) -> None:
        self.sources = sources or DEFAULT_SOURCES

    def get_available_sources(self) -> List[str]:
        return sorted(self.sources.keys())

    async def latest(
        self,
        region: str = "vn",
        sources: Optional[Sequence[str]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        region = region.lower()
        limit = max(1, min(int(limit), 200))
        sources_norm = [s.lower().strip() for s in (sources or []) if s and s.strip()]

        # Determine selected sources
        selected: List[SourceConfig] = []
        for key, cfg in self.sources.items():
            if region in ("all", "both"):
                region_ok = True
            else:
                region_ok = (cfg.region == region)
            if not region_ok:
                continue
            if sources_norm and key not in sources_norm:
                continue
            selected.append(cfg)

        selected = selected[:10]  # safety cap
        cache_key = f"news_latest:{region}:{','.join(sorted([c.source for c in selected]))}:{limit}"
        cached = ttl_cache.get(cache_key)
        if cached is not None:
            return cached

        async with httpx.AsyncClient() as client:
            per_source_limit = max(5, min(30, limit // max(1, len(selected))))
            tasks = []
            for cfg in selected:
                if cfg.rss_urls:
                    tasks.append(_fetch_rss_items(client, cfg.source, cfg.rss_urls, per_source_limit))
                else:
                    tasks.append(_fetch_html_items(client, cfg.source, cfg.html_seed_urls, per_source_limit))

            results: List[List[NewsItem]] = []
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=False)

        merged: List[NewsItem] = []
        for items in results:
            merged.extend(items)

        def sort_key(item: NewsItem):
            if not item.publish_time:
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                return datetime.fromisoformat(item.publish_time.replace("Z", "+00:00"))
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        merged_sorted = sorted(merged, key=sort_key, reverse=True)
        output = [asdict(x) for x in merged_sorted[:limit]]
        ttl_cache.set(cache_key, output, ttl_seconds=300)
        return output


news_service = NewsService()

