"""
Haftalık derin whitepaper/rapor taraması.
GitHub Actions tarafından her Pazartesi 06:30 UTC'de tetiklenebilir.
Sonuçlar puanlanır ve özet maili olarak gönderilir.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from tavily import TavilyClient

from collector import collect_weekly_deep_scan
from emailer import build_html_email, format_subject, send_daily_email
from scorer import get_threshold, score_items
from sheets import load_sent_url_set, mark_as_sent
from summarizer import enrich_high_score_items

logger = logging.getLogger("cx-intelligence-weekly")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


def run_weekly_scan() -> int:
    _configure_logging()
    load_dotenv()

    logger.info("=== Haftalık derin tarama başlıyor ===")

    tavily_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not tavily_key:
        logger.error("TAVILY_API_KEY boş; çıkılıyor.")
        return 1

    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()

    tavily_client = TavilyClient(api_key=tavily_key)
    articles = collect_weekly_deep_scan(tavily_client)
    if not articles:
        logger.warning("Haftalık taramada makale bulunamadı.")
        return 0

    try:
        sent_urls = load_sent_url_set()
    except Exception:
        logger.exception("Google Sheets mükerrer listesi okunamadı; filtresiz devam ediliyor.")
        sent_urls = set()

    fresh = []
    skipped_dup = 0
    for it in articles:
        url = str(it.get("url") or "").strip()
        if not url:
            continue
        if url in sent_urls:
            skipped_dup += 1
            continue
        fresh.append(it)

    logger.info(
        "Haftalık tarama: ham=%s, Sheets mükerrer atlanan=%s, puana gönderilen=%s",
        len(articles),
        skipped_dup,
        len(fresh),
    )

    if not fresh:
        logger.warning("Yeni (daha önce gönderilmemiş) içerik yok; çıkılıyor.")
        return 0

    scored = score_items(fresh, anthropic_api_key=anthropic_key)
    qualified = [a for a in scored if int(a.get("score") or 0) >= get_threshold(a)]
    qualified.sort(key=lambda z: int(z.get("score") or 0), reverse=True)

    logger.info("[Haftalık] Geçirilen içerik sayısı: %s", len(qualified))

    if not qualified:
        logger.warning("Gönderilebilecek içerik yok (eşik altı veya tamamı Sheets'te olabilir), mail atlanıyor.")
        return 0

    summarized = enrich_high_score_items(qualified, anthropic_key)

    today_tr = datetime.now().strftime("%d.%m.%Y")
    html_body = build_html_email(
        summarized,
        report_date=f"{today_tr} (Haftalık derin tarama)",
        linkedin_suggestions=None,
        audio_url=None,
    )
    subject = format_subject(len(summarized), date_label=today_tr)
    send_daily_email(
        html_body=html_body,
        subject="[Haftalık Tarama] " + subject,
    )
    logger.info("Haftalık e-postası gönderildi.")
    try:
        mark_as_sent(summarized)
        logger.info("Sheets: haftalık gönderim URL'leri kaydedildi.")
    except Exception:
        logger.exception("Sheets güncellenemedi; e-posta yine iletildi.")

    logger.info("=== Haftalık derin tarama tamamlandı ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_weekly_scan())
