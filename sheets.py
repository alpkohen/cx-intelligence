"""
Google Sheets entegrasyonu (service account).
'Sent Items' sayfasında gönderilmiş URL kaydı ve mükerrer kontrolü.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound
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


_SHEETS_ID_FROM_URL = re.compile(
    r"/spreadsheets/d/([a-zA-Z0-9-_]+)", re.IGNORECASE
)


def _normalize_google_sheet_id(raw: str | None) -> str:
    """Tırnak, BOM, baş/son boşluk ve tam URL içinden tablo kimliğini çıkarır."""
    if raw is None:
        return ""
    s = raw.strip()
    if s.startswith("\ufeff"):
        s = s.lstrip("\ufeff").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()
    m = _SHEETS_ID_FROM_URL.search(s)
    if m:
        return m.group(1)
    return s


def _open_spreadsheet(gc: gspread.Client, spreadsheet_key: str):
    """Önce open_by_key, SpreadsheetNotFound olursa open_by_url dener."""
    try:
        return gc.open_by_key(spreadsheet_key)
    except SpreadsheetNotFound:
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_key}/edit"
        logger.warning(
            "open_by_key tabloyu bulamadı (404); open_by_url deneniyor: %s",
            url,
        )
        return gc.open_by_url(url)


def _canonical_tab_title(title: str) -> str:
    """Sekme adlarını görünmez Unicode / boşluk / büyük-küçük harf kaynaklı fark için karşılaştırır."""
    t = unicodedata.normalize("NFKC", title or "").strip()
    return " ".join(t.split()).casefold()


def _find_worksheet_by_title(sh: gspread.Spreadsheet, title: str) -> gspread.Worksheet | None:
    """Önce tam başlık eşleşmesi; sonra NFKC/normalize+küçük harf ile eşleşme."""
    sheets = sh.worksheets()
    for ws in sheets:
        if ws.title == title:
            return ws
    want = _canonical_tab_title(title)
    for ws in sheets:
        if _canonical_tab_title(ws.title) == want:
            logger.info(
                "Sekme başlığı esnek eşleştirildi: aranan=%r, kullanılan=%r",
                title,
                ws.title,
            )
            return ws
    logger.warning(
        "Sekme bulunamadı (%r). Mevcut başlıklar (repr): %s",
        title,
        [repr(w.title) for w in sheets],
    )
    return None


def _open_sheet():
    raw = os.environ.get("GOOGLE_SHEET_ID")
    normalized_id = _normalize_google_sheet_id(raw if raw is not None else "")
    logger.info(
        "GOOGLE_SHEET_ID okuma: ortamda_tanımlı=%s, ham_uzunluk=%s, ham_repr=%s, normalize_id=%s",
        raw is not None,
        len(raw) if raw else 0,
        repr(raw) if raw is not None else "<ortamda yok>",
        normalized_id if normalized_id else "<boş veya çıkarılamadı>",
    )
    if not normalized_id:
        raise ValueError("GOOGLE_SHEET_ID ortam değişkeni boş veya geçersiz.")

    creds = _load_credentials_from_env()
    gc = gspread.authorize(creds)
    sh = _open_spreadsheet(gc, normalized_id)

    ws = _find_worksheet_by_title(sh, SENT_SHEET_TITLE)
    if ws is None:
        logger.info(
            "'%s' sayfası yok veya başlık farklı; oluşturulmayı deniyorum.",
            SENT_SHEET_TITLE,
        )
        try:
            ws = sh.add_worksheet(title=SENT_SHEET_TITLE, rows=1000, cols=10)
            ws.append_row(HEADER_ROW, value_input_option="USER_ENTERED")
        except APIError as exc:
            err_low = str(exc).lower()
            if (
                "already exists" not in err_low
                and "duplicate" not in err_low
            ):
                raise
            logger.warning(
                "Sekme eklenemedi (muhtemelen aynı isim API tarafından zaten kayıtlı): %s "
                "- mevcut sekmeler tekrar taranıyor.",
                exc,
            )
            ws = _find_worksheet_by_title(sh, SENT_SHEET_TITLE)
            if ws is None:
                raise RuntimeError(
                    f"'{SENT_SHEET_TITLE}' sekmesi oluşturulamadı ve yine bulunamadı. "
                    "Google Sheets'te sekme başlığını elle 'Sent Items' yapın veya "
                    "tüm sekmelerin listesindeki çıktıya bakın.",
                ) from exc

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
