"""
Tam URL metin çekme: requests + BeautifulSoup → Tavily extract fallback.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient

logger = logging.getLogger(__name__)

MAX_CHARS = 8000
MIN_CHARS_BEFORE_SKIP_TAVILY = 1000

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
}

_CONTENT_SELECTORS = ("article", "main", ".content", ".post-body")


def _clip(text: str) -> str:
    t = text.strip()
    return t[:MAX_CHARS] if len(t) > MAX_CHARS else t


def _host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _skip_requests_layer(url: str) -> bool:
    h = _host(url)
    if not h:
        return False
    domains = ("linkedin.com", "twitter.com", "x.com", "reddit.com")
    return any(d == h or h.endswith("." + d) for d in domains)


def _extract_dom_text(soup: BeautifulSoup) -> str:
    for sel in _CONTENT_SELECTORS:
        try:
            for el in soup.select(sel):
                txt = el.get_text(separator="\n", strip=True)
                if len(txt) >= 50:
                    return _clip(txt)
        except Exception as exc:
            logger.warning("fetcher: Seçici hatası %r: %s", sel, exc)
            continue
    body = soup.body
    if body:
        try:
            return _clip(body.get_text(separator="\n", strip=True))
        except Exception as exc:
            logger.warning("fetcher: body get_text hatası: %s", exc)
    try:
        return _clip(soup.get_text(separator="\n", strip=True))
    except Exception as exc:
        logger.warning("fetcher: soup get_text hatası: %s", exc)
        return ""


def _fetch_via_requests(url: str) -> str:
    try:
        resp = requests.get(url, timeout=10, headers=_FETCH_HEADERS, allow_redirects=True)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("fetcher: HTTP isteği başarısız (%s): %s", url[:80], exc)
        return ""
    try:
        soup = BeautifulSoup(resp.content, "lxml")
        return _extract_dom_text(soup)
    except Exception as exc:
        logger.warning("fetcher: BeautifulSoup işleme hatası (%s): %s", url[:80], exc)
        return ""


def _fetch_via_tavily(url: str) -> str:
    key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not key:
        logger.warning("fetcher: TAVILY_API_KEY boş; Tavily extract atlanıyor.")
        return ""
    try:
        client = TavilyClient(api_key=key)
        response = client.extract(urls=[url])
        results = response.get("results") or []
        if not results:
            failed = response.get("failed_results") or []
            if failed:
                logger.warning("fetcher: Tavily extract boş, failed_results: %s", failed[:3])
            return ""
        raw = results[0].get("raw_content")
        return _clip(str(raw).strip()) if raw else ""
    except Exception as exc:
        logger.warning("fetcher: Tavily extract hatası (%s): %s", url[:80], exc)
        return ""


def fetch_full_content(url: str) -> str:
    """
    URL için tam metin döndürür (en fazla 8000 karakter).

    1) requests + BeautifulSoup (LinkedIn / X / Reddit hariç); <1000 karakter ise Tavily dene.
    2) Tavily extract API
    3) Başarısızsa boş string
    """
    if not url or not isinstance(url, str):
        logger.warning("fetcher: Geçersiz URL.")
        return ""

    u = url.strip()
    if not u:
        return ""

    primary = ""
    if _skip_requests_layer(u):
        logger.info("fetcher: Sosyal ağ URL'si, requests atlanıyor: %s", u[:80])
    else:
        primary = _fetch_via_requests(u)
        if len(primary.strip()) >= MIN_CHARS_BEFORE_SKIP_TAVILY:
            return primary
        if primary.strip():
            logger.info(
                "fetcher: Metin %s karakter (< %s); Tavily denenecek.",
                len(primary.strip()),
                MIN_CHARS_BEFORE_SKIP_TAVILY,
            )

    tavily_text = _fetch_via_tavily(u)
    if tavily_text.strip():
        return tavily_text

    logger.warning("fetcher: İçerik alınamadı: %s", u[:120])
    return ""
