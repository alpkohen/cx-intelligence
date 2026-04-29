"""
CX Intelligence ana orkestrasyon betiği.

Adımlar:
1) RSS + Tavily ile içerik toplama
2) Google Sheets üzerinden mükerrer URL elemesi
3) Claude ile toplu puanlama
4) Minimum skor ve üst limit filtreleri
5) HTML e-posta gönderimi (Resend)
6) Gönderilenleri Sheets'e işleme
7) Özet istatistik günlüğü
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from collector import collect_all
from config import MAX_ITEMS_PER_EMAIL, MIN_SCORE_TO_SEND
from emailer import build_html_email, format_subject, send_daily_email
from scorer import score_items
from sheets import get_sent_count, load_sent_url_set, mark_as_sent


def _configure_logging() -> None:
    """Standart çıktı için Türkçe günlük formatı."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


def main() -> int:
    _configure_logging()
    log = logging.getLogger("cx-intelligence")

    log.info("=== CX Intelligence günlük çalışması başladı ===")

    load_dotenv()

    tavily_key = os.getenv("TAVILY_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

    # --- 1. Toplama ---
    log.info("Adım 1/9: RSS ve Tavily kaynaklarından içerik toplanıyor.")
    raw_items = collect_all(tavily_api_key=tavily_key)
    log.info("Toplam toplanan benzersiz içerik sayısı: %s", len(raw_items))

    # --- 2. Mükerrer kontrolü ---
    log.info("Adım 2/9: Google Sheets üzerinden mükerrer URL kontrolü yapılıyor.")
    sent_urls = load_sent_url_set()
    log.info("Sheets'te kayıtlı benzersiz URL sayısı (özet): %s", len(sent_urls))

    fresh_items = []
    skipped_dup = 0
    for it in raw_items:
        url = str(it.get("url") or "").strip()
        if not url:
            continue
        if url in sent_urls:
            skipped_dup += 1
            continue
        fresh_items.append(it)

    log.info(
        "Mükerrer nedeniyle atlanan içerik: %s | puanlamaya aday içerik: %s",
        skipped_dup,
        len(fresh_items),
    )

    if not fresh_items:
        log.warning(
            "Puanlanacak yeni içerik yok; iş akışı sonlandırılıyor (e-posta gönderilmeyecek)."
        )
        try:
            total_sent = get_sent_count()
            log.info("Sheets'teki birikmiş gönderilmiş kayıt sayısı: %s", total_sent)
        except Exception:
            log.exception("Özet için Sheets okunamadı.")
        log.info("=== CX Intelligence günlük çalışması tamamlandı ===")
        return 0

    # --- 3. Puanlama ---
    log.info("Adım 3/9: Claude ile içerikler puanlanıyor.")
    scored = score_items(fresh_items, anthropic_api_key=anthropic_key)

    # --- 4. Minimum skor filtresi ---
    log.info(
        "Adım 4/9: Minimum skor filtresi uygulanıyor (MIN_SCORE_TO_SEND=%s).",
        MIN_SCORE_TO_SEND,
    )
    passed = [x for x in scored if int(x.get("score") or 0) >= MIN_SCORE_TO_SEND]
    dropped_low = len(scored) - len(passed)
    log.info(
        "Minimum skorun altında kalan içerik: %s | geçen içerik: %s",
        dropped_low,
        len(passed),
    )

    # --- 5. Sıralama ---
    log.info("Adım 5/9: İçerikler puana göre yüksekten düşüğe sıralanıyor.")
    passed.sort(key=lambda z: int(z.get("score") or 0), reverse=True)

    # --- 6. Üst limit ---
    log.info(
        "Adım 6/9: En fazla %s içerik seçiliyor (MAX_ITEMS_PER_EMAIL).",
        MAX_ITEMS_PER_EMAIL,
    )
    selected = passed[:MAX_ITEMS_PER_EMAIL]

    if not selected:
        log.warning(
            "Gönderilecek uygun içerik bulunamadı (hepsi düşük puanlı olabilir)."
        )
        log.info("=== CX Intelligence günlük çalışması tamamlandı ===")
        return 0

    # --- 7. E-posta ---
    log.info("Adım 7/9: HTML e-posta oluşturuluyor ve Resend ile gönderiliyor.")
    today_tr = datetime.now().strftime("%d.%m.%Y")
    html_body = build_html_email(selected, report_date=today_tr)
    subject = format_subject(len(selected), date_label=today_tr)

    send_daily_email(html_body=html_body, subject=subject)
    log.info("E-posta gönderimi tamamlandı.")

    # --- 8. Sheets güncelleme ---
    log.info("Adım 8/9: Gönderilen içerikler Google Sheets'e kaydediliyor.")
    mark_as_sent(selected)

    # --- 9. Özet ---
    log.info("Adım 9/9: Özet istatistikler.")
    try:
        total_sent = get_sent_count()
        log.info("Sheets'te birikmiş toplam gönderilmiş kayıt (başlık hariç): %s", total_sent)
    except Exception:
        log.exception("Özet için Sheets kayıt sayısı okunamadı.")

    log.info(
        "Özet: gönderilen içerik=%s | toplanan ham=%s | mükerrer atlanan=%s | düşük puan elenen=%s",
        len(selected),
        len(raw_items),
        skipped_dup,
        dropped_low,
    )
    log.info("=== CX Intelligence günlük çalışması başarıyla tamamlandı ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
