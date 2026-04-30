"""
Skoru 7+ olan içerikler için tam makale metninden (fetcher) derin özet üretimi.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable

import anthropic

from config import CLAUDE_MODEL
from fetcher import fetch_full_content

from scorer import get_threshold

logger = logging.getLogger(__name__)

MIN_CONTENT_CHARS_FOR_CLAUDE = 500
MAX_CONTENT_CHARS_FOR_MODEL = 12000


def _call_with_retry(fn: Callable[[], Any], *, retries: int = 3, base_delay: float = 5.0):
    """scorer.py ile aynı: exponential backoff."""
    last_exc = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                wait = base_delay * (2**attempt)
                logger.warning(
                    "Summarizer API çağrısı başarısız (deneme %s/%s): %s — %.0fs sonra yeniden denenecek.",
                    attempt + 1,
                    retries,
                    exc,
                    wait,
                )
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw)
    if fence:
        raw = fence.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]
    return json.loads(raw)


_SYSTEM = """Sen müşteri deneyimi (CX) ve çağrı merkezi alanında uzmansın.
Aşağıdaki makale tam metnine dayanarak yalnızca istenen alanları Türkçe doldur.
Metinde olmayan bilgi uydurma; özet tamamen verilen içeriğe dayansın.
Yanıtın SADECE geçerli bir JSON nesnesi olmalı (başka metin, markdown yok)."""

_USER_TEMPLATE = """Makale başlığı: {title}
Kaynak: {source}
İçerik:
{full_content}

Şunları üret (JSON):
{{
"deep_summary": "4-5 cümle, makalenin gerçek içeriğinden — ne araştırıldı, yöntem, bulgular",
"key_insight": "1 cümle, en kritik tek bulgu",
"action_point": "1 cümle, CX/çağrı merkezi danışmanı olarak somut kullanım"
}}
Sadece JSON döndür."""


def _summarize_with_claude(
    *,
    title: str,
    source: str,
    full_content: str,
    api_key: str,
) -> dict[str, str]:
    body = full_content.strip()
    if len(body) > MAX_CONTENT_CHARS_FOR_MODEL:
        body = body[:MAX_CONTENT_CHARS_FOR_MODEL]

    user_content = _USER_TEMPLATE.format(
        title=title or "(Başlıksız)",
        source=source or "—",
        full_content=body,
    )

    client = anthropic.Anthropic(api_key=api_key)

    def _do_call():
        return client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )

    msg = _call_with_retry(_do_call)
    text_parts = []
    for block in getattr(msg, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    combined = "".join(text_parts)
    parsed = _extract_json_object(combined)

    deep = str(parsed.get("deep_summary") or "").strip()
    key_i = str(parsed.get("key_insight") or "").strip()
    action = str(parsed.get("action_point") or "").strip()
    if not deep or not key_i or not action:
        raise ValueError("Claude yanıtında deep_summary / key_insight / action_point eksik.")
    return {
        "deep_summary": deep,
        "key_insight": key_i,
        "action_point": action,
    }


def enrich_high_score_items(items: list[dict], anthropic_api_key: str) -> list[dict]:
    """
    Makale için eşik: `get_threshold(item)` (standart kaynaklar 7+, T1/T2_weekly ise 6+).

    - Tam metin > 500 karakter: deep_summary, key_insight, action_point eklenir.
    - <= 500 veya boş: one_liner/why_relevant korunur, enrich_note='paywall_limited' (kopya üzerinde).
    - Claude / fetch hatası: orijinal item referansı olduğu gibi döner.
    - Eşiğin altı: işlenmeden aynı referans döner.
    """
    key = (anthropic_api_key or "").strip()
    out: list[dict] = []

    for item in items:
        try:
            score = int(item.get("score") or 0)
        except (TypeError, ValueError):
            score = 0

        if score < get_threshold(item):
            out.append(item)
            continue

        url = str(item.get("url") or "").strip()
        if not url:
            out.append(item)
            continue

        try:
            full = fetch_full_content(url)
        except Exception:
            logger.exception(
                "summarizer: fetch_full_content hatası, öğe değiştirilmeden bırakılıyor: %s",
                url[:120],
            )
            out.append(item)
            continue

        stripped = (full or "").strip()
        if len(stripped) <= MIN_CONTENT_CHARS_FOR_CLAUDE:
            enriched = dict(item)
            enriched["enrich_note"] = "paywall_limited"
            out.append(enriched)
            logger.info(
                "summarizer: Kısa/boş içerik (≤%s karakter), paywall_limited: %s",
                MIN_CONTENT_CHARS_FOR_CLAUDE,
                url[:80],
            )
            continue

        if not key:
            logger.warning(
                "summarizer: ANTHROPIC_API_KEY boş; Claude atlanıyor (öğe değiştirilmedi): %s",
                url[:80],
            )
            out.append(item)
            continue

        title = str(item.get("title") or "")
        source = str(item.get("source") or "")

        try:
            fields = _summarize_with_claude(
                title=title,
                source=source,
                full_content=stripped,
                api_key=key,
            )
        except Exception:
            logger.exception(
                "summarizer: Claude özet hatası, öğe değiştirilmeden bırakılıyor: %s",
                url[:120],
            )
            out.append(item)
            continue

        enriched = dict(item)
        enriched["deep_summary"] = fields["deep_summary"]
        enriched["key_insight"] = fields["key_insight"]
        enriched["action_point"] = fields["action_point"]
        out.append(enriched)
        logger.info("summarizer: Zenginleştirildi (score=%s): %s", score, url[:80])

    return out
