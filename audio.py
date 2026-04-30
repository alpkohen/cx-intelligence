"""
Türkçe sesli günlük brifing metni (Claude) ve MP3 üretimi (OpenAI TTS).
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Callable

import anthropic

from config import CLAUDE_MODEL

logger = logging.getLogger(__name__)


def _call_with_retry(fn: Callable[[], Any], *, retries: int = 3, base_delay: float = 5.0):
    last_exc = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                wait = base_delay * (2**attempt)
                logger.warning(
                    "Briefing Claude çağrısı başarısız (deneme %s/%s): %s — %.0fs sonra yeniden denenecek.",
                    attempt + 1,
                    retries,
                    exc,
                    wait,
                )
                time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def _score(it: dict[str, Any]) -> int:
    try:
        return int(it.get("score") or 0)
    except (TypeError, ValueError):
        return 0


def _linkedin_angle(items: list[dict[str, Any]]) -> str:
    """İlk li_angle içeren öğe (LinkedIn adayları seçili listeye işlendiyse)."""
    for it in items:
        angle = str(it.get("li_angle") or "").strip()
        if angle:
            return angle
    return ""


def _tier_payload(items: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    tier1 = [it for it in items if _score(it) >= 9]
    tier2 = [it for it in items if 7 <= _score(it) <= 8]
    return tier1, tier2


def _minimal_for_briefing(it: dict[str, Any], *, tier: str) -> dict[str, Any]:
    row = {
        "title": it.get("title") or "",
        "source": it.get("source") or "",
        "score": _score(it),
    }
    if tier == "1":
        row["key_insight"] = (it.get("key_insight") or "").strip()
        row["one_liner"] = (it.get("one_liner") or "").strip()
    else:
        row["one_liner"] = (it.get("one_liner") or "").strip()
    return row


_BRIEFING_SYSTEM = """Sen Türkçe sesli günlük özet yazarısın. Çıktın yalnızca doğrudan okunacak düz metin olmalı.
Başlık, madde işareti, markdown, JSON veya tırnak kullanma. Doğal, sıcak konuşma dili kullan; gereksiz İngilizce teknik terimden kaçın."""


def generate_briefing_script(items: list[dict[str, Any]], anthropic_api_key: str) -> str:
    """
    Seçilen içeriklerden Türkçe sesli brifing metni üretir (Claude Haiku).
    Tier 3 ve altı özette kullanılmaz; girişte toplam içerik sayısı kullanılabilir.
    """
    key = (anthropic_api_key or "").strip()
    if not key:
        logger.warning("generate_briefing_script: ANTHROPIC_API_KEY boş.")
        return ""

    today = datetime.now().strftime("%d.%m.%Y")
    total = len(items)
    tier1, tier2 = _tier_payload(items)
    li_angle = _linkedin_angle(items)

    t1_json = json.dumps(
        [_minimal_for_briefing(it, tier="1") for it in tier1],
        ensure_ascii=False,
        indent=2,
    )
    t2_json = json.dumps(
        [_minimal_for_briefing(it, tier="2") for it in tier2],
        ensure_ascii=False,
        indent=2,
    )

    li_hint = (
        li_angle
        if li_angle
        else "(LinkedIn önerisi yoksa kapanışı kısa ve genel tut; 'Bugünün LinkedIn önerisi' cümlesini kullanma.)"
    )

    user_content = f"""Aşağıdaki veriye göre tek parça Türkçe sesli günlük brifing metni yaz.

Hedef uzunluk: 280–350 kelime (bu aralıkta tut).

İç yapı:

1. Giriş — tam şu kalıpla başla:
   "Bugün {today}, CX Intelligence günlük özeti. {total} içerik, {len(tier1)} mutlaka okunacak."

2. Makale sırası: önce Tier 1 listesindeki (JSON sırasına uy), sonra Tier 2 listesindeki (JSON sırasına uy).

3. Her makale için cümle kalıpları:

   Tier 1 (9–10) — tam bu yapıyı kullan (source, başlık ve key_insight alanları JSON'dan; doğal Türkçe okunuşa çevir):
   "Kaynak [source] raporuna göre, [başlık]. En kritik bulgu: [key_insight]"
   key_insight boşsa, kritik mesajı one_liner alanından tek cümleye indirgeme ve bu kalıpta ver.

   Tier 2 (7–8) — makale başına tek blok:
   "Ayrıca [source]'dan: [başlık]. [one_liner — tek tam cümle]"

4. Geçiş cümleleri: İlk makaleden sonra başlayarak, her iki makale arasına (son makaleden sonra değil) kısa köprü ekle; sırayla
   "Bir diğer önemli gelişme...", "Buna ek olarak..." ve benzer doğal varyasyonlar kullan.

5. Kapanış:
   - Eğer "LinkedIn açısı" bölümünde somut bir metin varsa, şu kalıpla bitir:
     "Bugünün LinkedIn önerisi: " ve ardından o açıyı 1–2 cümleyle özetle.
   - LinkedIn açısı yoksa kısa bir veda cümlesiyle bitir (LinkedIn cümlesini kullanma).

Tier 1 içerikler (JSON):
{t1_json}

Tier 2 içerikler (JSON):
{t2_json}

LinkedIn açısı (ilk öneri, varsa):
{li_hint}
"""

    client = anthropic.Anthropic(api_key=key)

    def _do():
        return client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2500,
            system=_BRIEFING_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )

    try:
        msg = _call_with_retry(_do)
    except Exception:
        logger.exception("generate_briefing_script: Claude başarısız.")
        return ""

    parts = [
        block.text
        for block in (getattr(msg, "content", []) or [])
        if getattr(block, "type", None) == "text"
    ]
    text = "".join(parts).strip()
    if not text:
        logger.warning("generate_briefing_script: Boş yanıt.")
    return text


def generate_audio(script: str) -> bytes | None:
    """
    OpenAI TTS ile MP3 üretir. Hata veya boş script'te None döner.
    """
    if not script or not script.strip():
        logger.warning("generate_audio: Boş script.")
        return None

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logger.warning("generate_audio: OPENAI_API_KEY boş.")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.audio.speech.create(
            model="tts-1-hd",
            voice="nova",
            input=script.strip(),
        )
        data = response.content
        if not isinstance(data, (bytes, bytearray)) or not data:
            logger.warning("generate_audio: Boş ses çıktısı.")
            return None
        return bytes(data)
    except Exception:
        logger.exception("generate_audio: OpenAI TTS hatası.")
        return None
