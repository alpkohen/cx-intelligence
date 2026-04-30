"""
RSS ve Tavily kaynaklarından içerik toplama modülü.
Son 24 saat filtresi; her RSS akışı için en fazla RSS_MAX_ITEMS_PER_FEED öğe.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import feedparser
from tavily import TavilyClient

from config import RSS_FEEDS, TAVILY_QUERIES

logger = logging.getLogger(__name__)

# Bazı RSS sunucuları varsayılan istemciyi engeller; tarayıcı benzeri User-Agent kullanılır.
_FEED_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CXIntelligenceBot/1.0; +https://example.org/bot)",
}

# Tavily sonuçları için kaynak etiketi
TAVILY_SOURCE_LABEL = "Tavily"

# Akış başına en fazla kaç öğe (yenideneskige); tek kaynakların (örn. arXiv) listeyi doldurmasını engeller.
RSS_MAX_ITEMS_PER_FEED = 3


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
            parsed = feedparser.parse(feed_url, request_headers=_FEED_REQUEST_HEADERS)
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


def collect_from_tavily(api_key: str, max_results_per_query: int = 8) -> list[dict[str, Any]]:
    """
    Tavily ile tanımlı sorgular üzerinden web sonuçları toplar.

    Tavily'nin döndürdüğü `published_date` varsa son 24 saat ile uyumluluğa çalışılır;
    yoksa sonuç yine de dahil edilir (web araması güncelliği için).
    """
    if not api_key or not api_key.strip():
        logger.warning("Tavily API anahtarı boş; Tavily adımı atlanıyor.")
        return []

    seen_urls: set[str] = set()
    items: list[dict[str, Any]] = []
    client = TavilyClient(api_key=api_key.strip())
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)

    for query in TAVILY_QUERIES:
        try:
            response = client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results_per_query,
            )
            results = response.get("results") or []
            added = 0
            for r in results:
                url = _normalize_url(r.get("url"))
                if not url or url in seen_urls:
                    continue
                title = (r.get("title") or "").strip() or "(Başlıksız)"
                summary = (r.get("content") or r.get("raw_content") or "").strip()
                pub_raw = r.get("published_date")

                published_date = ""
                include = True
                if not pub_raw:
                    published_date = ""
                    include = True
                elif pub_raw:
                    try:
                        # Tavily ISO formatları için basit parse
                        if "T" in str(pub_raw):
                            dt = datetime.fromisoformat(str(pub_raw).replace("Z", "+00:00"))
                        else:
                            dt = datetime.strptime(str(pub_raw)[:10], "%Y-%m-%d")
                            dt = dt.replace(tzinfo=timezone.utc)
                        if dt.tzinfo:
                            dt_naive = dt.astimezone(timezone.utc).replace(tzinfo=None)
                        else:
                            dt_naive = dt
                        published_date = dt_naive.strftime("%Y-%m-%d %H:%M UTC")
                        include = dt_naive >= cutoff
                    except (ValueError, TypeError):
                        published_date = str(pub_raw)[:64]
                        include = True

                if not include:
                    continue

                seen_urls.add(url)
                items.append(
                    {
                        "title": title,
                        "url": url,
                        "source": r.get("source") or TAVILY_SOURCE_LABEL,
                        "published_date": published_date,
                        "summary": summary[:2000] if summary else "",
                        "_collector_origin": "tavily",
                    }
                )
                added += 1

            logger.info(
                "Tavily tamamlandı: sorgu=%r, eklenen=%s",
                query[:80],
                added,
            )
        except Exception as exc:
            logger.exception("Tavily sorgusu atlanıyor (%s): %s", query[:80], exc)

    return items


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
    RSS + Tavily toplama ana giriş noktası.
    """
    logger.info("İçerik toplama başlıyor (RSS + Tavily).")
    rss = collect_from_rss(hours=24)
    tavily = collect_from_tavily(tavily_api_key)
    return merge_and_dedupe(rss, tavily)
