"""
Resend API ile HTML e-posta gönderimi.
Inline CSS ile e-posta istemcilerine uyumlu, açık/koyu tema dostu düzen.
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import datetime
from typing import Any

import resend

logger = logging.getLogger(__name__)

# Resend, gönderen olarak yalnızca doğrulanmış domain'e izin verir; ücretsiz posta kutuları doğrulanamaz.
_RESEND_FORBIDDEN_FROM_SUFFIXES = (
    "@gmail.com",
    "@googlemail.com",
    "@yahoo.com",
    "@yahoo.co.uk",
    "@hotmail.com",
    "@outlook.com",
    "@live.com",
    "@msn.com",
    "@icloud.com",
    "@me.com",
    "@mail.com",
)


def _validate_resend_from_address(from_email: str) -> None:
    low = from_email.strip().lower()
    for suf in _RESEND_FORBIDDEN_FROM_SUFFIXES:
        if low.endswith(suf):
            raise ValueError(
                f'RESEND_FROM_EMAIL olarak "{from_email}" kullanılamaz: Resend, Gmail/Yahoo vb. '
                "adresleri gönderen (From) olarak doğrulamaz. "
                "Seçenekler: (1) Test için RESEND_FROM_EMAIL=onboarding@resend.dev "
                "(2) Kendi domaininizi https://resend.com/domains üzerinden ekleyip doğrulayın, "
                "ör. no-reply@alanadiniz.com. Alıcı (RESEND_TO_EMAIL) olarak gmail kullanmak sorun değildir."
            )


def _badge_for_score(score: int) -> tuple[str, str, str]:
    """
    Puana göre rozet metni ve yaklaşık renk kodları döner.
    Dönüş: (emoji_etiket_html, kısa_etiket, sınıf_suffix)
    """
    if score >= 9:
        return (
            '<span style="display:inline-block;padding:6px 12px;border-radius:999px;font-weight:700;font-size:13px;background:#c62828;color:#fff;">🔴 MUTLAKA OKU</span>',
            "MUTLAKA OKU",
            "critical",
        )
    if score >= 7:
        return (
            '<span style="display:inline-block;padding:6px 12px;border-radius:999px;font-weight:700;font-size:13px;background:#ef6c00;color:#fff;">🟠 ÖNEMLİ</span>',
            "ÖNEMLİ",
            "high",
        )
    if score >= 5:
        return (
            '<span style="display:inline-block;padding:6px 12px;border-radius:999px;font-weight:700;font-size:13px;background:#f9a825;color:#111;">🟡 İLGİNİ ÇEKEBİLİR</span>',
            "İLGİNİ ÇEKEBİLİR",
            "mid",
        )
    return (
        '<span style="display:inline-block;padding:6px 12px;border-radius:999px;font-weight:700;font-size:13px;background:#78909c;color:#fff;">⚪ GENEL HABERLER</span>',
        "GENEL HABERLER",
        "low",
    )


def _escape_html(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html_email(
    items: list[dict[str, Any]],
    report_date: str,
) -> str:
    """Gösterilecek içerik kartları ile tam HTML gövdesi üretir."""
    origin_counts = Counter(
        (it.get("_collector_origin") or "unknown").lower() for it in items
    )
    rss_n = origin_counts.get("rss", 0)
    tavily_n = origin_counts.get("tavily", 0)

    cards_html = []
    for it in items:
        score = int(it.get("score") or 0)
        badge_html, _, _ = _badge_for_score(score)
        title = _escape_html(it.get("title") or "")
        url = _escape_html(it.get("url") or "#")
        source = _escape_html(it.get("source") or "")
        pub = _escape_html(it.get("published_date") or "—")
        one_liner = _escape_html(it.get("one_liner") or "")
        why = _escape_html(it.get("why_relevant") or "")
        read_time = _escape_html(it.get("read_time") or "—")

        cards_html.append(
            f"""
<tr>
  <td style="padding:16px 0;border-bottom:1px solid #334155;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;background:#1e293b;border-radius:12px;border:1px solid #334155;">
      <tr>
        <td style="padding:16px 18px;">
          <div style="margin-bottom:12px;">{badge_html}</div>
          <h2 style="margin:0 0 10px 0;font-size:18px;line-height:1.35;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
            <a href="{url}" style="color:#38bdf8;text-decoration:none;" target="_blank" rel="noopener noreferrer">{title}</a>
          </h2>
          <p style="margin:0 0 12px 0;font-size:13px;color:#94a3b8;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
            <span style="color:#cbd5e1;">{source}</span>
            <span style="color:#64748b;"> · </span>
            <span>{pub}</span>
          </p>
          <p style="margin:0 0 8px 0;font-size:14px;color:#e2e8f0;line-height:1.5;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
            <strong style="color:#f1f5f9;">Özet:</strong> {one_liner}
          </p>
          <p style="margin:0 0 8px 0;font-size:14px;color:#cbd5e1;line-height:1.5;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
            <strong style="color:#f1f5f9;">Neden önemli:</strong> {why}
          </p>
          <p style="margin:0;font-size:13px;color:#94a3b8;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
            Tahmini okuma: {read_time}
          </p>
        </td>
      </tr>
    </table>
  </td>
</tr>
"""
        )

    body_inner = "\n".join(cards_html)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>CX Intelligence</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0f172a;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;border-collapse:collapse;">
          <tr>
            <td style="padding:20px 4px 8px 4px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
              <h1 style="margin:0;font-size:22px;color:#f8fafc;">Günlük CX &amp; Çağrı Merkezi Intelligence</h1>
              <p style="margin:8px 0 0 0;font-size:14px;color:#94a3b8;">Tarih: { _escape_html(report_date) }</p>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 4px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#cbd5e1;font-size:14px;line-height:1.6;">
              <p style="margin:0;">
                Bu özet; RSS kaynakları ve Tavily web aramasıyla toplanan içeriklerin yapay zekâ ile puanlanmasıyla oluşturulmuştur.
              </p>
            </td>
          </tr>
          {body_inner}
          <tr>
            <td style="padding:24px 4px 8px 4px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#94a3b8;font-size:13px;line-height:1.7;">
              <hr style="border:none;border-top:1px solid #334155;margin:16px 0;">
              <p style="margin:0 0 8px 0;"><strong style="color:#e2e8f0;">Özet istatistikler</strong></p>
              <p style="margin:0;">Toplam içerik: <strong style="color:#e2e8f0;">{len(items)}</strong></p>
              <p style="margin:8px 0 0 0;">Kaynak dağılımı: RSS <strong style="color:#e2e8f0;">{rss_n}</strong> · Tavily <strong style="color:#e2e8f0;">{tavily_n}</strong></p>
              <p style="margin:16px 0 0 0;font-size:12px;color:#64748b;">
                Sistem: Python toplayıcı → Claude puanlama → Google Sheets mükerrer kontrolü → Resend ile gönderim.
                Renk kodları: 🔴 MUTLAKA OKU (9–10), 🟠 ÖNEMLİ (7–8), 🟡 İLGİNİ ÇEKEBİLİR (5–6), ⚪ GENEL HABERLER (1–4).
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return html


def send_daily_email(html_body: str, subject: str) -> dict[str, Any]:
    """
    Resend ile HTML e-posta gönderir.

    Ortam değişkenleri:
    - RESEND_API_KEY
    - RESEND_FROM_EMAIL (doğrulanmış gönderen)
    - RESEND_TO_EMAIL (alıcı; virgülle çoklu olabilir)
    """
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_email = os.environ.get("RESEND_FROM_EMAIL", "").strip()
    to_raw = os.environ.get("RESEND_TO_EMAIL", "").strip()

    if not api_key:
        raise ValueError("RESEND_API_KEY boş.")
    if not from_email:
        raise ValueError("RESEND_FROM_EMAIL boş.")
    if not to_raw:
        raise ValueError("RESEND_TO_EMAIL boş.")

    _validate_resend_from_address(from_email)

    resend.api_key = api_key

    to_list = [x.strip() for x in to_raw.split(",") if x.strip()]
    logger.info(
        "Resend gönderim ön kontrolü: API anahtarı uzunluk=%s, gönderen=%s, alıcı sayısı=%s",
        len(api_key),
        from_email,
        len(to_list),
    )

    params: dict[str, Any] = {
        "from": from_email,
        "to": to_list,
        "subject": subject,
        "html": html_body,
    }

    logger.info(
        "Resend ile e-posta gönderiliyor: alıcı sayısı=%s, konu=%r",
        len(to_list),
        subject[:120],
    )

    try:
        result = resend.Emails.send(params)
        logger.info("Resend yanıtı: %s", result)
        return result if isinstance(result, dict) else {"result": result}
    except Exception as exc:
        logger.exception("Resend gönderim hatası: %s", exc)
        raise


def format_subject(item_count: int, date_label: str | None = None) -> str:
    """Konu satırını oluşturur."""
    if date_label is None:
        date_label = datetime.now().strftime("%d.%m.%Y")
    return f"🧠 CX Intelligence | {date_label} | {item_count} içerik"
