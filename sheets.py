"""
Google Sheets entegrasyonu (service account).
'Sent Items' sayfasında gönderilmiş URL kaydı ve mükerrer kontrolü.
"""

from __future__ import annotations

import base64
import binascii
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

_SHEETS_ID_FROM_URL = re.compile(
    r"/spreadsheets/d/([a-zA-Z0-9-_]+)", re.IGNORECASE
)


def _normalize_private_key_pem(creds: dict[str, Any]) -> None:
    """PEM bazen tek satırda literal \\\\n ile gelir; pyasn1 hatasını önlemek için gerçek satır sonlarına çevir."""
    pk = creds.get("private_key")
    if not isinstance(pk, str):
        return
    if "\\n" not in pk:
        return
    creds["private_key"] = pk.replace("\\n", "\n")
    logger.info(
        "GOOGLE_SERVICE_ACCOUNT_JSON: private_key içinde %s adet literal '\\\\n' gerçek satır sonuna çevrildi.",
        pk.count("\\n"),
    )


def _parse_credentials_dict(raw: str) -> dict[str, Any]:
    """
    GOOGLE_SERVICE_ACCOUNT_JSON için önce düz JSON, sonra base64 kodlu JSON dener.

    Ham metin güvenlik nedeniyle loglanmaz; yalnızca uzunluk ve hata ayrıntıları yazılır.
    """
    if not raw or not raw.strip():
        logger.error(
            "GOOGLE_SERVICE_ACCOUNT_JSON boş veya yalnızca boşluk; ortam değişkenini doldurun."
        )
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON tanımlı değil veya boş. Service account kimliğini ekleyin."
        )

    raw = raw.strip()
    logger.info(
        "GOOGLE_SERVICE_ACCOUNT_JSON yükleme başladı: ham_uzunluk=%s (kimlik içeriği günlüklenmez)",
        len(raw),
    )

    # 1) Düz JSON
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            logger.warning(
                "GOOGLE_SERVICE_ACCOUNT_JSON düz JSON parse edildi ancak kök tip dict değil (%s); base64 yolu deneniyor.",
                type(data).__name__,
            )
        else:
            logger.info(
                "GOOGLE_SERVICE_ACCOUNT_JSON: düz json.loads başarılı (client_email=%r).",
                data.get("client_email", ""),
            )
            _normalize_private_key_pem(data)
            return data
    except json.JSONDecodeError as exc:
        logger.info(
            "GOOGLE_SERVICE_ACCOUNT_JSON düz JSON parse reddedildi: %s "
            "(satır %s, sütun %s, pozisyon %s); base64 yolu deneniyor.",
            exc.msg,
            exc.lineno,
            exc.colno,
            exc.pos,
        )

    # 2) Base64 decode + JSON
    padded = raw + "=" * ((-len(raw)) % 4)
    try:
        decoded = base64.b64decode(padded)
    except (binascii.Error, ValueError, TypeError) as exc:
        logger.error(
            "GOOGLE_SERVICE_ACCOUNT_JSON base64 çözümü başarısız: %r. "
            "Düz JSON da parse edilemedi; secret formatını kontrol edin.",
            exc,
            exc_info=True,
        )
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON ne geçerli düz JSON ne de çözülebilir base64. "
            "Yerelde ham JSON kullanın veya Secrets için tek satır base64 kullanın."
        ) from exc

    try:
        text = decoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        logger.error(
            "Base64 çıktısı UTF-8 metne çevrilemiyor: %s (başlangıç=%r, uzunluk=%s)",
            exc,
            decoded[:40],
            len(decoded),
            exc_info=True,
        )
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON base64 sonrası UTF-8 değil."
        ) from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error(
            "Base64 sonrası json.loads başarısız: %s (satır %s sütun %s pos %s)",
            exc.msg,
            exc.lineno,
            exc.colno,
            exc.pos,
            exc_info=True,
        )
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON base64 doğru görünüyor ancak içerdeki JSON geçersiz."
        ) from exc

    if not isinstance(data, dict):
        logger.error(
            "Base64 sonrası JSON kök tipi dict beklenirdi, gelen=%s.",
            type(data).__name__,
        )
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON içindeki JSON bir nesne (object) değil."
        )

    logger.info(
        "GOOGLE_SERVICE_ACCOUNT_JSON: base64 decode + json.loads başarılı (client_email=%r).",
        data.get("client_email", ""),
    )
    _normalize_private_key_pem(data)
    return data


def _load_credentials_from_env() -> Credentials:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    try:
        creds_dict = _parse_credentials_dict(raw)
    except ValueError:
        raise
    except Exception as exc:
        logger.exception(
            "GOOGLE_SERVICE_ACCOUNT_JSON işlenirken beklenmeyen hata: %s",
            exc,
        )
        raise

    try:
        return Credentials.from_service_account_info(creds_dict, scopes=_SCOPE)
    except Exception as exc:
        logger.exception(
            "Service account Credential oluşturulamıyor (dosya yapısı, private_key veya scopes): %s",
            exc,
        )
        raise


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
