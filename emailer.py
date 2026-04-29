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
    if score >= 9:
        return (
            '<span style="display:inline-block;padding:4px 10px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;background:#111111;color:#c9a84c;font-family:-apple-system,\'Helvetica Neue\',Arial,sans-serif;">MUTLAKA OKU &nbsp;{}/10</span>'.format(score),
            "MUTLAKA OKU",
            "gold",
        )
    if score >= 7:
        return (
            '<span style="display:inline-block;padding:4px 10px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;background:#2d1a0a;color:#e07b4a;font-family:-apple-system,\'Helvetica Neue\',Arial,sans-serif;">ÖNEMLİ &nbsp;{}/10</span>'.format(score),
            "ÖNEMLİ",
            "orange",
        )
    if score >= 5:
        return (
            '<span style="display:inline-block;padding:4px 10px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;background:#eef0f4;color:#5a6a80;font-family:-apple-system,\'Helvetica Neue\',Arial,sans-serif;">GÜNDEM &nbsp;{}/10</span>'.format(score),
            "GÜNDEM",
            "steel",
        )
    return (
        '<span style="display:inline-block;padding:4px 10px;border-radius:3px;font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;background:#f0ede6;color:#aaaaaa;font-family:-apple-system,\'Helvetica Neue\',Arial,sans-serif;">GENEL &nbsp;{}/10</span>'.format(score),
        "GENEL",
        "muted",
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
    origin_counts = Counter(
        (it.get("_collector_origin") or "unknown").lower() for it in items
    )
    rss_n = origin_counts.get("rss", 0)
    tavily_n = origin_counts.get("tavily", 0)

    avg_score = (
        sum(int(it.get("score") or 0) for it in items) / len(items)
        if items else 0
    )

    def top_border(score: int) -> str:
        if score >= 9:
            return "border-top:3px solid #c9a84c;"
        if score >= 7:
            return "border-top:3px solid #e07b4a;"
        if score >= 5:
            return "border-top:3px solid #94a3b8;"
        return "border-top:3px solid #dddddd;"

    cards_html = []
    for it in items:
        score = int(it.get("score") or 0)
        badge_html, _, _ = _badge_for_score(score)
        title     = _escape_html(it.get("title") or "")
        url       = _escape_html(it.get("url") or "#")
        source    = _escape_html(it.get("source") or "")
        pub       = _escape_html(it.get("published_date") or "—")
        one_liner = _escape_html(it.get("one_liner") or "")
        why       = _escape_html(it.get("why_relevant") or "")
        read_time = _escape_html(it.get("read_time") or "—")
        tb        = top_border(score)

        cards_html.append(f"""
<tr>
  <td style="padding:0 0 14px 0;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
           style="border-collapse:collapse;background:#ffffff;border-radius:6px;
                  border:1px solid #e8e5df;{tb}
                  box-shadow:0 1px 3px rgba(0,0,0,0.06);">
      <tr>
        <td style="padding:20px 22px 0 22px;">
          <div style="margin-bottom:12px;">{badge_html}</div>
          <h2 style="margin:0 0 8px 0;font-size:17px;line-height:1.4;font-weight:700;">
            <a href="{url}"
               style="color:#111111;text-decoration:none;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;"
               target="_blank" rel="noopener noreferrer">{title}</a>
          </h2>
          <p style="margin:0 0 14px 0;font-size:12px;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;color:#999999;">
            <span style="color:#777777;font-weight:500;">{source}</span>
            <span style="color:#dddddd;">&nbsp;·&nbsp;</span>
            <span>{pub}</span>
          </p>
          <div style="height:1px;background:#f0ede6;margin-bottom:14px;"></div>
          <p style="margin:0 0 4px 0;font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#bbbbbb;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Özet</p>
          <p style="margin:0 0 12px 0;font-size:14px;color:#444444;line-height:1.55;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{one_liner}</p>
          <p style="margin:0 0 4px 0;font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#bbbbbb;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Neden Önemli</p>
          <p style="margin:0 0 16px 0;font-size:13px;color:#777777;line-height:1.5;font-style:italic;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{why}</p>
        </td>
      </tr>
      <tr>
        <td style="padding:10px 22px;border-top:1px solid #f0ede6;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
            <tr>
              <td>
                <a href="{url}"
                   style="font-size:12px;font-weight:700;color:#c9a84c;text-decoration:none;letter-spacing:0.03em;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;"
                   target="_blank" rel="noopener noreferrer">Makaleyi oku &rarr;</a>
              </td>
              <td align="right">
                <span style="font-size:11px;color:#cccccc;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{read_time}</span>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </td>
</tr>
""")

    body_inner = "\n".join(cards_html)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>CX Intelligence</title>
</head>
<body style="margin:0;padding:0;background:#f0ede6;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f0ede6;">
    <tr>
      <td align="center" style="padding:0 12px 32px 12px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;border-collapse:collapse;">

          <!-- HEADER -->
          <tr>
            <td style="background:#111111;padding:28px 32px 24px 32px;border-radius:0;">
              <p style="margin:0 0 8px 0;font-size:11px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:#c9a84c;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Günlük Bülten</p>
              <h1 style="margin:0 0 6px 0;font-size:24px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;line-height:1.2;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">CX &amp; Çağrı Merkezi Intelligence</h1>
              <p style="margin:0;font-size:13px;color:#777777;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{ _escape_html(report_date) } &nbsp;·&nbsp; {len(items)} içerik seçildi</p>
              <div style="margin-top:20px;height:1px;background:linear-gradient(90deg,#c9a84c 0%,#c9a84c 40%,transparent 100%);"></div>
            </td>
          </tr>

          <!-- CARDS -->
          <tr>
            <td style="padding:20px 0 0 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                {body_inner}
              </table>
            </td>
          </tr>

          <!-- FOOTER STATS -->
          <tr>
            <td style="padding:20px 0 8px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
                     style="background:#ffffff;border-radius:6px;border:1px solid #e8e5df;">
                <tr>
                  <td style="padding:18px 22px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                      <tr>
                        <td align="center" style="border-right:1px solid #f0ede6;padding:0 0 0 0;">
                          <p style="margin:0;font-size:20px;font-weight:700;color:#111111;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{len(items)}</p>
                          <p style="margin:4px 0 0 0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#aaaaaa;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">İçerik</p>
                        </td>
                        <td align="center" style="border-right:1px solid #f0ede6;">
                          <p style="margin:0;font-size:20px;font-weight:700;color:#111111;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{rss_n}</p>
                          <p style="margin:4px 0 0 0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#aaaaaa;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">RSS</p>
                        </td>
                        <td align="center" style="border-right:1px solid #f0ede6;">
                          <p style="margin:0;font-size:20px;font-weight:700;color:#111111;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{tavily_n}</p>
                          <p style="margin:4px 0 0 0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#aaaaaa;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Tavily</p>
                        </td>
                        <td align="center">
                          <p style="margin:0;font-size:20px;font-weight:700;color:#c9a84c;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{avg_score:.1f}</p>
                          <p style="margin:4px 0 0 0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#aaaaaa;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Ort. Puan</p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="padding:0 22px 16px 22px;border-top:1px solid #f0ede6;">
                    <p style="margin:14px 0 8px 0;font-size:11px;color:#cccccc;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;line-height:1.7;">
                      RSS + Tavily &rarr; Claude Haiku puanlama &rarr; Google Sheets de-dup &rarr; Resend
                    </p>
                    <p style="margin:0;font-size:11px;color:#cccccc;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">
                      <span style="color:#c9a84c;font-weight:700;">&#9632;</span> Mutlaka Oku (9–10) &nbsp;
                      <span style="color:#e07b4a;font-weight:700;">&#9632;</span> Önemli (7–8) &nbsp;
                      <span style="color:#94a3b8;font-weight:700;">&#9632;</span> Gündem (5–6) &nbsp;
                      <span style="color:#dddddd;font-weight:700;">&#9632;</span> Genel (1–4)
                    </p>
                  </td>
                </tr>
              </table>
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
