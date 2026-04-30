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

from config import LINKEDIN_SECTION_LABEL

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


def _truncate_title_plain(text: str, max_chars: int = 35) -> str:
    t = text.strip()
    if len(t) <= max_chars:
        return t
    return (t[: max_chars - 1].rstrip() + "…") if max_chars > 1 else "…"


def _audio_meta_line(items: list[dict[str, Any]]) -> str:
    """Tier 1 kısaltılmış başlıklar + Önemli (7–8) sayısı; metin düz."""
    tier1_parts = [
        _truncate_title_plain(str(it.get("title") or ""), 35)
        for it in items
        if int(it.get("score") or 0) >= 9
    ]
    onemli_n = sum(1 for it in items if 7 <= int(it.get("score") or 0) <= 8)
    if tier1_parts:
        return ", ".join(tier1_parts) + f" · Önemli: {onemli_n} makale"
    return f"Önemli: {onemli_n} makale"


def build_summary_section(items: list[dict[str, Any]]) -> str:
    """E-postanın başına eklenen özet kutu: tier sayıları + toplam içerik adedi."""
    if not items:
        return ""

    tier1_count = sum(1 for it in items if int(it.get("score") or 0) >= 9)
    tier2_count = sum(1 for it in items if 7 <= int(it.get("score") or 0) <= 8)
    tier3_count = sum(1 for it in items if 5 <= int(it.get("score") or 0) <= 6)
    total = len(items)

    return f"""
<tr>
  <td style="padding:16px 0 0 0;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
           style="background:#ffffff;border-radius:6px;border:1px solid #e8e5df;border-collapse:collapse;">
      <tr>
        <td style="padding:16px 22px 12px 22px;border-bottom:1px solid #f0ede6;">
          <p style="margin:0;font-size:10px;font-weight:700;letter-spacing:0.14em;
                    text-transform:uppercase;color:#c9a84c;
                    font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Bugünün Özeti</p>
        </td>
      </tr>
      <tr>
        <td style="padding:14px 22px 14px 22px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
            <tr>
              <td align="center" style="border-right:1px solid #f0ede6;">
                <p style="margin:0;font-size:22px;font-weight:700;color:#c9a84c;
                           font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{tier1_count}</p>
                <p style="margin:3px 0 0 0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;
                           color:#aaaaaa;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Mutlaka Oku</p>
                <p style="margin:1px 0 0 0;font-size:10px;color:#cccccc;
                           font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">9–10 puan</p>
              </td>
              <td align="center" style="border-right:1px solid #f0ede6;">
                <p style="margin:0;font-size:22px;font-weight:700;color:#e07b4a;
                           font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{tier2_count}</p>
                <p style="margin:3px 0 0 0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;
                           color:#aaaaaa;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Önemli</p>
                <p style="margin:1px 0 0 0;font-size:10px;color:#cccccc;
                           font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">7–8 puan</p>
              </td>
              <td align="center" style="border-right:1px solid #f0ede6;">
                <p style="margin:0;font-size:22px;font-weight:700;color:#94a3b8;
                           font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{tier3_count}</p>
                <p style="margin:3px 0 0 0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;
                           color:#aaaaaa;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Gündem</p>
                <p style="margin:1px 0 0 0;font-size:10px;color:#cccccc;
                           font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">5–6 puan</p>
              </td>
              <td align="center">
                <p style="margin:0;font-size:22px;font-weight:700;color:#111111;
                           font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{total}</p>
                <p style="margin:3px 0 0 0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;
                           color:#aaaaaa;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Toplam</p>
                <p style="margin:1px 0 0 0;font-size:10px;color:#cccccc;
                           font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">içerik</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </td>
</tr>"""


def build_linkedin_section(suggestions: list[dict[str, Any]]) -> str:
    """LinkedIn öneri kartlarını HTML olarak üretir. E-postanın sonuna eklenir."""
    if not suggestions:
        return ""

    cards = []
    for it in suggestions:
        title = _escape_html(it.get("title") or "")
        url = _escape_html(it.get("url") or "#")
        source = _escape_html(it.get("source") or "")
        pillar = _escape_html(it.get("li_pillar") or "")
        angle = _escape_html(it.get("li_angle") or "")
        hook = _escape_html(it.get("li_hook") or "")
        fit = int(it.get("li_fit_score") or 0)

        cards.append(f"""
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
       style="border-collapse:collapse;background:#ffffff;border-radius:6px;
              border:1px solid #e8e5df;border-top:3px solid #0077b5;
              box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:12px;">
  <tr>
    <td style="padding:18px 22px 14px 22px;">
      <p style="margin:0 0 10px 0;font-size:10px;font-weight:700;letter-spacing:0.12em;
                text-transform:uppercase;color:#0077b5;
                font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">
        {pillar} &nbsp;·&nbsp; Uyum {fit}/10
      </p>
      <h3 style="margin:0 0 8px 0;font-size:15px;font-weight:700;line-height:1.4;">
        <a href="{url}" style="color:#111111;text-decoration:none;
                               font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;"
           target="_blank" rel="noopener noreferrer">{title}</a>
      </h3>
      <p style="margin:0 0 12px 0;font-size:12px;color:#999999;
                font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{source}</p>
      <div style="height:1px;background:#f0ede6;margin-bottom:12px;"></div>
      <p style="margin:0 0 4px 0;font-size:10px;font-weight:700;letter-spacing:0.1em;
                text-transform:uppercase;color:#bbbbbb;
                font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Açı</p>
      <p style="margin:0 0 12px 0;font-size:13px;color:#444444;line-height:1.55;
                font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{angle}</p>
      <p style="margin:0 0 4px 0;font-size:10px;font-weight:700;letter-spacing:0.1em;
                text-transform:uppercase;color:#bbbbbb;
                font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Önerilen Hook</p>
      <p style="margin:0;font-size:13px;color:#555555;line-height:1.5;font-style:italic;
                font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">"{hook}"</p>
    </td>
  </tr>
  <tr>
    <td style="padding:10px 22px;border-top:1px solid #f0ede6;">
      <p style="margin:0;font-size:11px;color:#aaaaaa;line-height:1.6;
                font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">
        Alp LinkedIn projesine kopyala-yapıştır:
      </p>
      <p style="margin:6px 0 0 0;font-size:11px;color:#777777;line-height:1.7;
                font-family:'Courier New',monospace;background:#f8f6f2;
                padding:8px 10px;border-radius:4px;word-break:break-word;">
        Bu makaleyi LinkedIn postuna dönüştür<br>
        Makale: {url}<br>
        Pillar: {pillar}<br>
        Hook: {hook}
      </p>
    </td>
  </tr>
</table>""")

    section_header = f"""
<tr>
  <td style="padding:24px 0 12px 0;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
      <tr>
        <td style="padding-bottom:12px;">
          <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:0.14em;
                    text-transform:uppercase;color:#0077b5;
                    font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">
            &#9670; LinkedIn Post Adayları
          </p>
          <p style="margin:4px 0 0 0;font-size:12px;color:#aaaaaa;
                    font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">
            {LINKEDIN_SECTION_LABEL}
          </p>
        </td>
      </tr>
      <tr><td>""" + "\n".join(cards) + """</td></tr>
    </table>
  </td>
</tr>"""

    return section_header


def build_html_email(
    items: list[dict[str, Any]],
    report_date: str,
    linkedin_suggestions: list[dict[str, Any]] | None = None,
    audio_url: str | None = None,
) -> str:
    origin_counts = Counter(
        (it.get("_collector_origin") or "unknown").lower() for it in items
    )
    rss_n = origin_counts.get("rss", 0)
    tavily_n = origin_counts.get("tavily", 0)

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

        enrich_block = ""
        if score >= 7:
            ks_raw = str(it.get("key_insight") or "").strip()
            if ks_raw:
                ks_esc = _escape_html(ks_raw)
                enrich_block = f"""
          <p style="margin:0 0 12px 0;font-size:13px;color:#c9a84c;font-style:italic;line-height:1.5;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">KRİTİK BULGU<br>{ks_esc}</p>
"""

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
          <p style="margin:0 0 12px 0;font-size:14px;color:#444444;line-height:1.55;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{one_liner}</p>{enrich_block}
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

    summary_html = build_summary_section(items)
    linkedin_html = build_linkedin_section(linkedin_suggestions or [])

    audio_html = ""
    if audio_url:
        safe_audio = _escape_html(audio_url)
        audio_meta_esc = _escape_html(_audio_meta_line(items))
        play_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="14" '
            'viewBox="0 0 24 24" aria-hidden="true" style="display:block;">'
            '<path fill="#111111" d="M8 5v14l11-7z"/></svg>'
        )
        audio_html = f"""
<tr>
  <td style="padding:8px 0 0 0;">
    <a href="{safe_audio}" style="display:block;text-decoration:none;color:inherit;background:#1a1a1a;border-left:3px solid #c9a84c;padding:14px 24px;-webkit-font-smoothing:antialiased;">
      <div style="display:flex;flex-direction:row;align-items:center;width:100%;">
        <div style="flex-shrink:0;width:36px;height:36px;border-radius:18px;background:#c9a84c;display:flex;align-items:center;justify-content:center;margin-right:16px;">
          {play_svg}
        </div>
        <div style="flex:1 1 auto;min-width:0;margin-right:12px;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">
          <p style="margin:0 0 2px;font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#c9a84c;line-height:1.2;">SESLİ ÖZET</p>
          <p style="margin:0 0 4px;font-size:13px;color:#888888;line-height:1.35;">Bugünün bülteni &nbsp;·&nbsp; dinle &rarr;</p>
          <p style="margin:0;font-size:11px;color:#555555;line-height:1.4;">{audio_meta_esc}</p>
        </div>
        <div style="flex-shrink:0;align-self:stretch;display:flex;align-items:flex-end;">
          <table role="presentation" cellspacing="0" cellpadding="0" style="margin:0;border-collapse:collapse;">
            <tr>
              <td style="width:3px;height:7px;background:#c9a84c;border-radius:2px;opacity:0.35;padding:0 2px 0 0;vertical-align:bottom;"></td>
              <td style="width:3px;height:15px;background:#c9a84c;border-radius:2px;opacity:0.9;padding:0 2px 0 0;vertical-align:bottom;"></td>
              <td style="width:3px;height:22px;background:#c9a84c;border-radius:2px;opacity:1;padding:0 2px 0 0;vertical-align:bottom;"></td>
              <td style="width:3px;height:11px;background:#c9a84c;border-radius:2px;opacity:0.55;padding:0 2px 0 0;vertical-align:bottom;"></td>
              <td style="width:3px;height:17px;background:#c9a84c;border-radius:2px;opacity:0.75;padding:0 2px 0 0;vertical-align:bottom;"></td>
              <td style="width:3px;height:13px;background:#c9a84c;border-radius:2px;opacity:0.45;padding:0;vertical-align:bottom;"></td>
            </tr>
          </table>
        </div>
      </div>
    </a>
  </td>
</tr>"""

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>CX Intelligence Daily</title>
</head>
<body style="margin:0;padding:0;background:#f0ede6;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f0ede6;">
    <tr>
      <td align="center" style="padding:0 12px 32px 12px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;border-collapse:collapse;">

          <!-- HEADER -->
          <tr>
            <td style="background:#111111;padding:28px 32px 24px 32px;border-radius:0;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;width:100%;">
                <div style="flex:1 1 auto;min-width:0;padding-right:16px;">
                  <p style="margin:0 0 8px 0;font-size:11px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:#c9a84c;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Günlük Bülten</p>
                  <h1 style="margin:0 0 6px 0;font-size:24px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;line-height:1.2;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">CX Intelligence Daily</h1>
                  <p style="margin:0;font-size:13px;color:#777777;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{ _escape_html(report_date) } &nbsp;·&nbsp; {len(items)} içerik seçildi</p>
                </div>
                <div style="flex-shrink:0;text-align:right;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">
                  <p style="margin:0 0 8px;font-size:7px;letter-spacing:0.18em;text-transform:uppercase;color:#888888;line-height:1.35;">THE CUSTOMER<br>TRUTH COMPANY</p>
                  <p style="margin:0;font-size:20px;font-weight:800;color:#ffffff;font-family:Georgia,serif;line-height:1;">real</p>
                  <p style="margin:0;font-size:20px;font-weight:800;color:#c9a84c;font-family:Georgia,serif;line-height:1;">&amp;co.</p>
                </div>
              </div>
              <div style="margin-top:20px;height:1px;background:linear-gradient(90deg,#c9a84c 0%,#c9a84c 40%,transparent 100%);"></div>
            </td>
          </tr>

{audio_html}
          {summary_html}

          <!-- CARDS -->
          <tr>
            <td style="padding:20px 0 0 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                {body_inner}
              </table>
            </td>
          </tr>

          {linkedin_html}

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
                        <td align="center">
                          <p style="margin:0;font-size:20px;font-weight:700;color:#111111;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">{tavily_n}</p>
                          <p style="margin:4px 0 0 0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#aaaaaa;font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;">Tavily</p>
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
    return f"🧠 CX Intelligence Daily | {date_label} | {item_count} içerik"


def format_subject_with_prefix(
    prefix: str,
    item_count: int,
    date_label: str | None = None,
) -> str:
    """İsteğe bağlı önek (ör. haftalık tarama konu başlığı)."""
    core = format_subject(item_count, date_label)
    stripped = prefix.strip()
    return f"{stripped} {core}" if stripped else core
