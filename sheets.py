"""
Google Sheets entegrasyonu (service account).
'Sent Items' sayfasında gönderilmiş URL kaydı ve mükerrer kontrolü.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SENT_SHEET_TITLE = "Sent Items"
HEADER_ROW = ["URL", "Title", "Score", "Date Sent", "Source"]

_SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _load_credentials_from_env() -> Credentials:
    """GOOGLE_SERVICE_ACCOUNT_JSON ortam değişkeninden service account kimlik bilgisini yükler."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON tanımlı değil. Service account JSON içeriğini ortam değişkenine ekleyin."
        )
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON geçerli bir JSON değil. GitHub Secrets'ta kaçış karakterlerini kontrol edin."
        ) from exc
    return Credentials.from_service_account_info(info, scopes=_SCOPE)


def _open_sheet():
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID ortam değişkeni boş.")

    creds = _load_credentials_from_env()
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)

    try:
        ws = sh.worksheet(SENT_SHEET_TITLE)
    except gspread.WorksheetNotFound:
        logger.info(
            "'%s' sayfası bulunamadı; oluşturuluyor ve başlık satırı yazılıyor.",
            SENT_SHEET_TITLE,
        )
        ws = sh.add_worksheet(title=SENT_SHEET_TITLE, rows=1000, cols=10)
        ws.append_row(HEADER_ROW, value_input_option="USER_ENTERED")

    return ws


def _ensure_header(ws: gspread.Worksheet) -> None:
    """İlk satır başlık değilse başlığı ekle (koruyucu)."""
    try:
        first = ws.row_values(1)
    except Exception:
        first = []
    if not first or first[0].strip().upper() != "URL":
        logger.warning(
            "Sayfa başlığı beklenen formatta değil; ilk satıra başlık yazılıyor."
        )
        existing = ws.get_all_values()
        if existing:
            ws.insert_row(HEADER_ROW, index=1)
        else:
            ws.append_row(HEADER_ROW, value_input_option="USER_ENTERED")


def load_sent_url_set() -> set[str]:
    """
    Gönderilmiş tüm URL'leri tek okumada döndürür (mükerrer kontrolü için).
    Başlık satırı atlanır.
    """
    try:
        ws = _open_sheet()
        _ensure_header(ws)
        urls = ws.col_values(1)
        if len(urls) <= 1:
            return set()
        return {(u or "").strip() for u in urls[1:] if (u or "").strip()}
    except Exception as exc:
        logger.exception("Google Sheets URL listesi okunamadı: %s", exc)
        raise


def is_duplicate(url: str, sent_urls: set[str] | None = None) -> bool:
    """
    Verilen URL daha önce gönderildi mi?

    İlk satır başlık kabul edilir; A sütunundaki URL'ler kontrol edilir.
    `sent_urls` verilirse ek ağ çağrısı yapılmaz (toplu işlemlerde önerilir).
    """
    if not url or not str(url).strip():
        return False
    url = str(url).strip()

    if sent_urls is not None:
        return url in sent_urls

    try:
        sent = load_sent_url_set()
        return url in sent
    except Exception as exc:
        logger.exception("Google Sheets mükerrer kontrolü başarısız: %s", exc)
        raise


def mark_as_sent(items: list[dict[str, Any]]) -> None:
    """Gönderilen içerikleri sayfaya ekler."""
    if not items:
        logger.info("Sheets'e yazılacak kayıt yok.")
        return

    try:
        ws = _open_sheet()
        _ensure_header(ws)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rows = []
        for it in items:
            rows.append(
                [
                    str(it.get("url") or ""),
                    str(it.get("title") or ""),
                    str(it.get("score") if it.get("score") is not None else ""),
                    now,
                    str(it.get("source") or ""),
                ]
            )
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        logger.info("Google Sheets'e %s satır eklendi.", len(rows))
    except Exception as exc:
        logger.exception("Google Sheets yazma hatası: %s", exc)
        raise


def get_sent_count() -> int:
    """Başlık hariç toplam gönderilmiş kayıt sayısı."""
    try:
        ws = _open_sheet()
        _ensure_header(ws)
        urls = ws.col_values(1)
        return max(0, len(urls) - 1)
    except Exception as exc:
        logger.exception("Google Sheets kayıt sayısı okunamadı: %s", exc)
        raise
