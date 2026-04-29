"""
Claude API ile içerik puanlama.
10'luk gruplar halinde tek API isteği ile toplu puanlama (CLAUDE_MODEL: Claude 3.5 Sonnet, config'de tanımlı).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from config import CLAUDE_MODEL, SCORER_BATCH_SIZE

logger = logging.getLogger(__name__)

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


def score_items(
    items: list[dict[str, Any]],
    anthropic_api_key: str,
    batch_size: int = SCORER_BATCH_SIZE,
) -> list[dict[str, Any]]:
    """
    Her içeriğe score, category, one_liner, why_relevant, read_time alanlarını ekler.
    Başarısız veya eksik sonuçlar için konservatif varsayılan atanır (düşük puan).
    """
    if not items:
        logger.info("Puanlanacak içerik yok.")
        return []

    if not anthropic_api_key or not anthropic_api_key.strip():
        raise ValueError("ANTHROPIC_API_KEY boş olamaz.")

    client = _build_client(anthropic_api_key.strip())
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
                    try:
                        scored_row["score"] = int(hit.get("score", 0))
                    except (TypeError, ValueError):
                        scored_row["score"] = 0
                    scored_row["category"] = str(hit.get("category") or "unknown")
                    scored_row["one_liner"] = str(hit.get("one_liner") or "").strip()
                    scored_row["why_relevant"] = str(hit.get("why_relevant") or "").strip()
                    scored_row["read_time"] = str(hit.get("read_time") or "—").strip()
                else:
                    logger.warning(
                        "Claude yanıtında indeks eksik: toplu grup içi index=%s, URL=%s",
                        local_i,
                        original.get("url"),
                    )
                    scored_row["score"] = 0
                    scored_row["category"] = "unknown"
                    scored_row["one_liner"] = "Otomatik puanlama başarısız."
                    scored_row["why_relevant"] = "Model yanıtı bu öğe için tamamlanmadı."
                    scored_row["read_time"] = "—"

                # Makul aralıkta tut
                sc = scored_row.get("score", 0)
                if isinstance(sc, int):
                    scored_row["score"] = max(1, min(10, sc))
                else:
                    scored_row["score"] = 1

                out.append(scored_row)

        except Exception as exc:
            logger.exception(
                "Claude toplu puanlama hatası (varsayılan düşük puan atanacı): %s",
                exc,
            )
            for original in batch:
                scored_row = dict(original)
                scored_row["score"] = 1
                scored_row["category"] = "error"
                scored_row["one_liner"] = "Puanlama sırasında hata oluştu."
                scored_row["why_relevant"] = "API veya ayrıştırma hatası nedeniyle elendi."
                scored_row["read_time"] = "—"
                out.append(scored_row)

    logger.info("Puanlama tamamlandı: toplam %s içerik işlendi.", len(out))
    return out
