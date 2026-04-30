"""
LinkedIn post adayı tespit modülü.
Yüksek puanlı içerikler arasından LinkedIn için uygun olanları işaretler ve post açısı önerir.
Ana akışı durdurmaz — hata durumunda boş liste döner.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import anthropic

from config import CLAUDE_MODEL

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 3
MIN_SCORE_FOR_LINKEDIN = 7

_PROFILE_PATH = Path(__file__).parent / "linkedin_profile.md"

_SYSTEM = """Sen B2B LinkedIn içerik stratejistisin. Verilen içerikler arasından LinkedIn'de en iyi performans gösterecek olanları seçiyorsun.
Yanıtın SADECE geçerli bir JSON nesnesi olmalı, başka metin yok.
Şema:
{
  "suggestions": [
    {
      "candidate_index": <aday listedeki 0-tabanlı index>,
      "fit_score": <1-10 tam sayı>,
      "pillar": "<Win the Room | Think Twice Leader | Loyal by Design | Decoded>",
      "angle": "<Türkçe 2 cümle: bu içeriği hangi somut açıdan işleyebilirsin — bilişsel önyargı, yönetim tekniği veya saha gözlemiyle nasıl pekiştirirsin>",
      "hook": "<Türkçe önerilen açılış cümlesi — dikkat çekici, soru veya güçlü ifade, pazarlama kokusu yok>"
    }
  ]
}
fit_score'a göre azalan sırada döndür. Yalnızca en iyi 3 öneriyi döndür."""

_USER_TEMPLATE = """LinkedIn profil ve içerik stratejisi:
{profile}

---
Aşağıdaki {n} içerikten LinkedIn için en uygun 3 tanesini seç.
Özellikle araştırma bulguları, sektör verileri ve best practice içeriklerini tercih et.
Bilişsel önyargılar, yönetim teknikleri veya saha hikayesiyle nasıl işlenebileceğini belirt.

Adaylar:
{items_json}
"""


def _load_profile() -> str:
    try:
        return _PROFILE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("linkedin_profile.md bulunamadı.")
        return "CX ve çağrı merkezi danışmanı, 37 yıl deneyim. Türkiye ve uluslararası projeler."


def _extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw)
    if fence:
        raw = fence.group(1)
    else:
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e != -1:
            raw = raw[s:e+1]
    return json.loads(raw)


def _call_with_retry(fn, *, retries: int = 3, base_delay: float = 5.0):
    """Exponential backoff ile API çağrısını yeniden dener."""
    last_exc = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                wait = base_delay * (2**attempt)
                logger.warning(
                    "LinkedIn API çağrısı başarısız (deneme %s/%s): %s — %.0fs sonra yeniden denenecek.",
                    attempt + 1,
                    retries,
                    exc,
                    wait,
                )
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def suggest_linkedin_posts(
    scored_items: list[dict[str, Any]],
    anthropic_api_key: str,
) -> list[dict[str, Any]]:
    """
    Yüksek puanlı içerikler arasından LinkedIn adaylarını döndürür.
    Her öneri: title, url, pillar, angle, hook içerir.
    """
    if not anthropic_api_key or not anthropic_api_key.strip():
        logger.warning("ANTHROPIC_API_KEY yok; LinkedIn adımı atlanıyor.")
        return []

    candidates = [
        it for it in scored_items
        if int(it.get("score") or 0) >= MIN_SCORE_FOR_LINKEDIN
    ]

    if not candidates:
        logger.info("LinkedIn için yeterli puanlı içerik yok (min=%s).", MIN_SCORE_FOR_LINKEDIN)
        return []

    logger.info("LinkedIn adayı tespiti: %s içerik değerlendiriliyor.", len(candidates))

    profile = _load_profile()
    minimal = [
        {
            "index": i,
            "title": it.get("title", ""),
            "source": it.get("source", ""),
            "score": it.get("score", 0),
            "one_liner": it.get("one_liner", ""),
            "why_relevant": it.get("why_relevant", ""),
        }
        for i, it in enumerate(candidates)
    ]

    user_content = _USER_TEMPLATE.format(
        profile=profile,
        n=len(minimal),
        items_json=json.dumps(minimal, ensure_ascii=False),
    )

    try:
        client = anthropic.Anthropic(api_key=anthropic_api_key.strip())
        msg = _call_with_retry(
            lambda: client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1500,
                system=_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
        )
        text = "".join(
            block.text for block in (msg.content or [])
            if getattr(block, "type", None) == "text"
        )
        parsed = _extract_json(text)
        raw = parsed.get("suggestions") or []

        results = []
        for s in raw[:MAX_SUGGESTIONS]:
            idx = int(s.get("candidate_index") or 0)
            if 0 <= idx < len(candidates):
                item = dict(candidates[idx])
                item["li_pillar"] = str(s.get("pillar") or "")
                item["li_angle"] = str(s.get("angle") or "")
                item["li_hook"] = str(s.get("hook") or "")
                item["li_fit_score"] = int(s.get("fit_score") or 0)
                results.append(item)

        logger.info("LinkedIn önerileri hazır: %s öneri.", len(results))
        return results

    except Exception as exc:
        logger.exception("LinkedIn öneri adımı başarısız (ana akış etkilenmez): %s", exc)
        return []
