"""
Claude API ile içerik puanlama.
Toplu istek ile zenginleştirme; puan olarak her zaman varsayılan (5), Claude düşerse bile e-posta akışı sürer.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from config import CLAUDE_MODEL, SCORER_BATCH_SIZE

logger = logging.getLogger(__name__)

# Tüm son kayıtlar bu puana sabitlenir (MIN_SCORE filtresi main'de kapalı olsa da tutarlı özet).
DEFAULT_SCORE = 5

SYSTEM_INSTRUCTIONS = """Sen çağrı merkezi, müşteri deneyimi (CX) ve müşteri hizmetleri alanında uzman bir analistsin.
Verilen her içerik için aşağıdaki puanlama ölçeğini kullan:

- 9-10: Akademik hakemli makale, büyük danışmanlık raporu (McKinsey, Gartner, Forrester, Deloitte), özgün araştırma verisi içeren rapor, sektörü değiştirebilecek bulgu
- 7-8: Detaylı vaka çalışması, özgün anket verisi, uzman görüşü içeren uzun form içerik, önemli şirket duyurusu
- 5-6: Genel sektör haberi, orta kaliteli blog, ürün lansmanı haberi
- 3-4: Basit haber özeti, genel tavsiye, listicle
- 1-2: Reklam içerikli, çok genel veya konuyla zayıf ilişkili içerik

Yanıtın SADECE geçerli bir JSON nesnesi olmalı (başka metin yok). Şema:
{
  "results": [
    {
      "index": 0,
      "score": <1-10 tam sayı>,
      "category": "<kısa İngilizce kategori kodu örn research_report, case_study, news>",
      "one_liner": "<Türkçe tek cümle özet>",
      "why_relevant": "<Neden önemli - Türkçe tek cümle>",
      "read_time": "<tahmini okuma süresi, örn 5 dk>"
    }
  ]
}
`index`, girdi listesindeki içeriğin 0-tabanlı sırası ile aynı olmalı. Tüm içerikler için tam bir sonuç döndür."""

USER_BATCH_TEMPLATE = """Aşağıdaki {n} içeriği sırayla değerlendir ve yalnızca belirtilen JSON şemasında yanıt ver.

İçerikler (JSON):
{items_json}
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    """Model yanıtından JSON nesnesini ayıklar (```json kod bloğu toleranslı)."""
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


def _build_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def _apply_default_rating(row: dict[str, Any], *, fallback_note: str | None = None) -> None:
    """Tüm çıkışları DEFAULT_SCORE (5) ile hizalar; bildirim alanı için isteğe bağlı not."""
    row["score"] = DEFAULT_SCORE
    if fallback_note:
        row.setdefault("scorer_note", fallback_note)


def _row_from_fallback(
    original: dict[str, Any],
    *,
    one_liner: str,
    why_relevant: str,
    category: str = "fallback",
    note: str | None = None,
) -> dict[str, Any]:
    scored_row = dict(original)
    scored_row["category"] = category
    scored_row["one_liner"] = one_liner
    scored_row["why_relevant"] = why_relevant
    scored_row["read_time"] = "—"
    _apply_default_rating(scored_row, fallback_note=note)
    return scored_row


def score_items(
    items: list[dict[str, Any]],
    anthropic_api_key: str,
    batch_size: int = SCORER_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """
    Her içeriğe score (sabit varsayılan 5), category, one_liner vb. eklenir.

    Claude kullanılırsa bu alanlar modelden gelir; aksi halde veya istek düşerse
    güvenli placeholder ile DEFAULT_SCORE atanır — anahtar eksik/API hatası iş akışını durdurmaz.
    """
    if not items:
        logger.info("Puanlanacak içerik yok.")
        return []

    key = (anthropic_api_key or "").strip()
    if not key:
        logger.warning(
            "ANTHROPIC_API_KEY boş; Claude atlanıyor. Tüm öğeler varsayılan %s puan + fallback metinleri.",
            DEFAULT_SCORE,
        )
        return [
            _row_from_fallback(
                it,
                one_liner="Claude atanmadı; varsayılan özet kullanılıyor.",
                why_relevant="API anahtarı olmadan otomatik eklendi.",
                note="missing_api_key",
            )
            for it in items
        ]

    client = _build_client(key)
    out: list[dict[str, Any]] = []

    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        batch_indices = list(range(start, start + len(batch)))

        minimal = []
        for i, it in enumerate(batch):
            minimal.append(
                {
                    "index": i,
                    "title": it.get("title", ""),
                    "url": it.get("url", ""),
                    "source": it.get("source", ""),
                    "published_date": it.get("published_date", ""),
                    "summary": (it.get("summary") or "")[:4000],
                }
            )

        user_content = USER_BATCH_TEMPLATE.format(
            n=len(minimal),
            items_json=json.dumps(minimal, ensure_ascii=False),
        )

        logger.info(
            "Claude puanlama grubu işleniyor: öğe %s-%s (%s adet)",
            batch_indices[0] + 1,
            batch_indices[-1] + 1,
            len(batch),
        )

        try:
            msg = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                system=SYSTEM_INSTRUCTIONS,
                messages=[{"role": "user", "content": user_content}],
            )
            text_parts = []
            for block in getattr(msg, "content", []) or []:
                if getattr(block, "type", None) == "text":
                    text_parts.append(block.text)
            combined = "".join(text_parts)
            parsed = _extract_json_object(combined)
            raw_results = parsed.get("results") or []

            by_idx: dict[int, dict[str, Any]] = {}
            for r in raw_results:
                if isinstance(r, dict) and "index" in r:
                    try:
                        idx = int(r["index"])
                        by_idx[idx] = r
                    except (TypeError, ValueError):
                        continue

            for local_i, original in enumerate(batch):
                scored_row = dict(original)
                hit = by_idx.get(local_i)
                if hit:
                    scored_row["category"] = str(hit.get("category") or "unknown").strip()
                    scored_row["one_liner"] = str(hit.get("one_liner") or "").strip() or (
                        "Özet oluşturulamadı."
                    )
                    scored_row["why_relevant"] = str(hit.get("why_relevant") or "").strip() or (
                        "Özet oluşturulamadı."
                    )
                    scored_row["read_time"] = str(hit.get("read_time") or "—").strip()
                    _apply_default_rating(scored_row)
                else:
                    logger.warning(
                        "Claude yanıtında indeks eksik: grup içi index=%s, URL=%s — varsayılan metin kullanılacak.",
                        local_i,
                        original.get("url"),
                    )
                    scored_row["category"] = "unknown"
                    scored_row["one_liner"] = "Model bu öğe için eksik döndü; varsayılan puan."
                    scored_row["why_relevant"] = (
                        "Yanıtta bu içerik için sonuç yoktu; günlük e-postasında yine dahil."
                    )
                    scored_row["read_time"] = "—"
                    _apply_default_rating(scored_row, fallback_note="missing_index")

                out.append(scored_row)

        except Exception as exc:
            logger.exception(
                "Claude toplu puanlama düştü (%s); bu grup için varsayılan %s puan uygulanıyor.",
                exc,
                DEFAULT_SCORE,
            )
            for original in batch:
                out.append(
                    _row_from_fallback(
                        original,
                        one_liner="Claude kullanılamadı; günlük özet yine oluşturuldu.",
                        why_relevant="API veya ayrıştırma hatası — varsayılan puan kullanıldı.",
                        category="error_fallback",
                        note=f"batch_error:{type(exc).__name__}",
                    )
                )

    logger.info(
        "Puanlama tamamlandı: toplam %s içerik (tümünde çıkış puanı=%s).",
        len(out),
        DEFAULT_SCORE,
    )
    return out
