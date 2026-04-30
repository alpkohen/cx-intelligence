"""
RSS ve Tavily kaynaklarından içerik toplama modülü.
Son 24 saat filtresi; her RSS akışı için en fazla RSS_MAX_ITEMS_PER_FEED öğe.
"""

from __future__ import annotations

import logging
import socket
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser
from tavily import TavilyClient

from config import (
    RSS_FEEDS,
    RSS_MAX_ITEMS_PER_FEED,
    TAVILY_QUERIES,
    TIER1_TAVILY_QUERIES,
    WEEKLY_DEEP_QUERIES,
)

logger = logging.getLogger(__name__)

# Bazı RSS sunucuları varsayılan istemciyi engeller; tarayıcı benzeri User-Agent kullanılır.
_FEED_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CXIntelligenceBot/1.0; +https://example.org/bot)",
}

# Tavily sonuçları için kaynak etiketi
TAVILY_SOURCE_LABEL = "Tavily"


def _normalize_url(url: str | None) -> str | None:
    """URL'yi karşılaştırma için temel normalize eder."""
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    return u if u else None


def _feed_domain(feed_url: str) -> str:
    """RSS URL'sinden okunabilir kaynak adı üretir."""
    try:
        netloc = urlparse(feed_url).netloc or feed_url
        return netloc.replace("www.", "") or feed_url
    except Exception:
        return feed_url


def _parse_entry_datetime(entry: Any) -> datetime | None:
    """feedparser girişinden yayın zamanını UTC naive datetime olarak döndürür."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        tup = getattr(entry, attr, None)
        if tup:
            try:
                return datetime(*tup[:6], tzinfo=timezone.utc).replace(tzinfo=None)
            except (TypeError, ValueError):
                continue
    return None


def _entry_summary(entry: Any) -> str:
    """Özet veya içerikten kısa metin."""
    for field in ("summary", "description", "content"):
        val = getattr(entry, field, None)
        if isinstance(val, list) and val:
            val = val[0].get("value") if isinstance(val[0], dict) else val[0]
        if isinstance(val, str) and val.strip():
            text = val.strip()
            return text[:2000] if len(text) > 2000 else text
    return ""


def collect_from_rss(hours: int = 24) -> list[dict[str, Any]]:
    """
    Tüm RSS_FEED URL'lerinden içerik çeker.

    - Yayın tarihi olan girişler: son `hours` saat içindeyse aday olarak alınır.
    - Tarihsiz girişler: zaman penceresi dışı tarih filtresinden muaf tutulur; akış sırası korunur.
    - Her akış için yalnızca en güncel ``RSS_MAX_ITEMS_PER_FEED`` öğe eklenir.

    Returns:
        title, url, source, published_date (ISO veya boş), summary içeren dict listesi.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    seen_urls: set[str] = set()
    items: list[dict[str, Any]] = []

    for feed_url in RSS_FEEDS:
        source_name = _feed_domain(feed_url)
        try:
            try:
                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(10)
                parsed = feedparser.parse(feed_url, request_headers=_FEED_REQUEST_HEADERS)
            finally:
                socket.setdefaulttimeout(old_timeout)
            if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
                logger.warning(
                    "RSS parse uyarısı (devam ediliyor): %s — %s",
                    feed_url,
                    getattr(parsed, "bozo_exception", "bilinmeyen"),
                )

            entries = list(getattr(parsed, "entries", []) or [])
            dated: list[tuple[datetime | None, Any]] = []
            for e in entries:
                dt = _parse_entry_datetime(e)
                dated.append((dt, e))

            feed_candidates: list[tuple[datetime | None, int, dict[str, Any]]] = []

            for idx_in_feed, (dt, entry) in enumerate(dated):
                link = _normalize_url(getattr(entry, "link", None) or getattr(entry, "id", None))
                if not link:
                    continue
                if dt is not None and dt < cutoff:
                    continue
                title = (getattr(entry, "title", None) or "").strip() or "(Başlıksız)"
                summary = _entry_summary(entry)
                payload: dict[str, Any] = {
                    "title": title,
                    "url": link,
                    "source": source_name,
                    "published_date": dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "",
                    "summary": summary,
                    "_collector_origin": "rss",
                }
                feed_candidates.append((dt, idx_in_feed, payload))

            # Tarihli öğeler önce (en yeni), sonra tarihsizler (akış sırası: genelde yeniden eskiye)
            feed_candidates.sort(
                key=lambda t: (
                    (1, t[0].timestamp()) if t[0] is not None else (0, -t[1]),
                ),
                reverse=True,
            )
            capped = feed_candidates[:RSS_MAX_ITEMS_PER_FEED]

            added_from_feed = 0
            for _dt, _idx, payload in capped:
                link = str(payload.get("url") or "").strip()
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)
                items.append(payload)
                added_from_feed += 1

            logger.info(
                "RSS tamamlandı: kaynak=%s, aday=%s, akış sonrası üst sınır=%s, bu akıştan eklenen=%s",
                source_name,
                len(feed_candidates),
                RSS_MAX_ITEMS_PER_FEED,
                added_from_feed,
            )
        except Exception as exc:
            logger.exception("RSS kaynağı atlanıyor (%s): %s", feed_url, exc)

    return items


def _gather_from_tavily_queries(
    client: TavilyClient,
    *,
    queries: list[str],
    max_results_per_query: int,
    source_tier_label: str,
    include_raw_content: bool | None = None,
    log_prefix: str = "",
) -> list[dict[str, Any]]:
    """
    Ortak Tavily arama döngüsü — son 24 saat filtresi, URL normalize, çıktı yapısı collect_from_tavily ile aynı.
    """
    seen_urls: set[str] = set()
    items: list[dict[str, Any]] = []
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)

    for query in queries:
        try:
            search_kw: dict[str, Any] = {
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results_per_query,
            }
            if include_raw_content is not None:
                search_kw["include_raw_content"] = include_raw_content

            response = client.search(**search_kw)
            results = response.get("results") if isinstance(response, dict) else getattr(response, "results", None)
            results = results or []
            added = 0

            for r in results:
                url = _normalize_url(r.get("url") if isinstance(r, dict) else getattr(r, "url", None))
                if not url or url in seen_urls:
                    continue
                title = (
                    ((r.get("title") if isinstance(r, dict) else getattr(r, "title", "")) or "")
                    .strip()
                    or "(Başlıksız)"
                )
                raw_summary = (
                    (r.get("content") if isinstance(r, dict) else getattr(r, "content", None))
                    or (r.get("raw_content") if isinstance(r, dict) else getattr(r, "raw_content", None))
                    or ""
                ).strip()

                pub_raw = r.get("published_date") if isinstance(r, dict) else getattr(r, "published_date", None)

                published_date = ""
                include_item = True
                if not pub_raw:
                    published_date = ""
                    include_item = True
                elif pub_raw:
                    try:
                        if "T" in str(pub_raw):
                            dt_parse = datetime.fromisoformat(str(pub_raw).replace("Z", "+00:00"))
                        else:
                            dt_parse = datetime.strptime(str(pub_raw)[:10], "%Y-%m-%d")
                            dt_parse = dt_parse.replace(tzinfo=timezone.utc)
                        if dt_parse.tzinfo:
                            dt_naive = dt_parse.astimezone(timezone.utc).replace(tzinfo=None)
                        else:
                            dt_naive = dt_parse
                        published_date = dt_naive.strftime("%Y-%m-%d %H:%M UTC")
                        include_item = dt_naive >= cutoff
                    except (ValueError, TypeError):
                        published_date = str(pub_raw)[:64]
                        include_item = True

                if not include_item:
                    continue

                seen_urls.add(url)
                src_meta = (
                    (r.get("source") if isinstance(r, dict) else getattr(r, "source", None)) or TAVILY_SOURCE_LABEL
                )
                items.append(
                    {
                        "title": title,
                        "url": url,
                        "source": src_meta,
                        "published_date": published_date,
                        "summary": raw_summary[:2000] if raw_summary else "",
                        "_collector_origin": "tavily",
                        "source_tier": source_tier_label,
                    }
                )
                added += 1

            lp = (log_prefix + " ") if log_prefix else ""
            logger.info(
                "%sTavily tamamlandı: sorgu=%r, eklenen=%s",
                lp,
                query[:80],
                added,
            )
        except Exception as exc:
            lp = (log_prefix + " ") if log_prefix else ""
            logger.exception("%sTavily sorgusu atlanıyor (%s): %s", lp, query[:80], exc)

    return items


def collect_tier1_sources(tavily_client: TavilyClient) -> list[dict[str, Any]]:
    """
    TIER1_TAVILY_QUERIES listesindeki her sorgu için Tavily'de arama yapar.
    Her makaleye source_tier = "T1" etiketi ekler. Günlük collect_all içinde kullanılır.
    """
    rows = _gather_from_tavily_queries(
        tavily_client,
        queries=list(TIER1_TAVILY_QUERIES),
        max_results_per_query=5,
        source_tier_label="T1",
        include_raw_content=False,
        log_prefix="[T1]",
    )
    logger.info("[T1] %s Tier-1 Tavily makalesi toplandı.", len(rows))
    return rows


def collect_weekly_deep_scan(tavily_client: TavilyClient) -> list[dict[str, Any]]:
    """
    WEEKLY_DEEP_QUERIES ile derin whitepaper / rapor taraması (Pazartesi iş akışı için).
    Her sonuca source_tier = "T2_weekly".
    """
    rows = _gather_from_tavily_queries(
        tavily_client,
        queries=list(WEEKLY_DEEP_QUERIES),
        max_results_per_query=10,
        source_tier_label="T2_weekly",
        include_raw_content=False,
        log_prefix="[T2_weekly]",
    )
    logger.info("[T2_weekly] %s haftalık derin tarama makalesi toplandı.", len(rows))
    return rows


def collect_from_tavily(
    api_key: str,
    max_results_per_query: int = 8,
    client: TavilyClient | None = None,
) -> list[dict[str, Any]]:
    """
    Tavily ile tanımlı sorgular üzerinden web sonuçları toplar.
    Varsayılan `source_tier` etiketi: "standard".

    Tavily'nin döndürdüğü `published_date` varsa son 24 saat ile uyumluluğa çalışılır;
    yoksa sonuç yine de dahil edilir (web araması güncelliği için).
    """
    if not api_key or not api_key.strip():
        logger.warning("Tavily API anahtarı boş; Tavily adımı atlanıyor.")
        return []

    if client is None:
        client = TavilyClient(api_key=api_key.strip())

    return _gather_from_tavily_queries(
        client,
        queries=list(TAVILY_QUERIES),
        max_results_per_query=max_results_per_query,
        source_tier_label="standard",
        include_raw_content=None,
        log_prefix="",
    )


def merge_and_dedupe(
    rss_items: list[dict[str, Any]],
    tavily_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """İki listeyi birleştirir; aynı URL tek kez kalır (önce RSS öncelikli)."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []

    for it in rss_items + tavily_items:
        u = _normalize_url(it.get("url"))
        if not u or u in seen:
            continue
        seen.add(u)
        merged.append(it)

    logger.info(
        "Birleştirme tamamlandı: RSS=%s, Tavily=%s, birleşik benzersiz=%s",
        len(rss_items),
        len(tavily_items),
        len(merged),
    )
    return merged


def collect_all(tavily_api_key: str) -> list[dict[str, Any]]:
    """
    RSS + Tier-1 hedefli Tavily + standart Tavily sorguları — ana günlük toplama.
    """
    logger.info("İçerik toplama başlıyor (RSS + Tier1 Tavily + Tavily).")
    rss_items = collect_from_rss(hours=24)

    tier1_items: list[dict[str, Any]] = []
    standard_tavily: list[dict[str, Any]] = []
    api_key_clean = (tavily_api_key or "").strip()
    if api_key_clean:
        t_client = TavilyClient(api_key=api_key_clean)
        tier1_items = collect_tier1_sources(t_client)
        standard_tavily = collect_from_tavily(tavily_api_key, client=t_client)

    merged = merge_and_dedupe(rss_items, tier1_items + standard_tavily)

    for it in merged:
        it.setdefault("source_tier", "standard")

    return merged
