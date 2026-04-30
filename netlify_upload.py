"""
Netlify üzerinde günlük ses dosyası yayınlama (Files API).
"""

from __future__ import annotations

import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

NETLIFY_API_BASE = "https://api.netlify.com/api/v1"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def upload_audio(mp3_bytes: bytes, date_str: str) -> str | None:
    """
    MP3'ü Netlify'a yükler.

    Args:
        mp3_bytes: Ham MP3 içeriği.
        date_str: YYYY-MM-DD (örn. 2026-04-30).

    Returns:
        Başarılıysa public URL; aksi halde None.
    """
    if not mp3_bytes:
        logger.warning("netlify_upload: Boş MP3 içeriği.")
        return None

    d = (date_str or "").strip()
    if not _DATE_RE.match(d):
        logger.warning("netlify_upload: Geçersiz date_str (YYYY-MM-DD beklenir): %r", date_str)
        return None

    token = (os.getenv("NETLIFY_AUTH_TOKEN") or "").strip()
    site_id = (os.getenv("NETLIFY_SITE_ID") or "").strip()
    site_name = (os.getenv("NETLIFY_SITE_NAME") or "").strip()

    if not token or not site_id or not site_name:
        logger.warning(
            "netlify_upload: NETLIFY_AUTH_TOKEN, NETLIFY_SITE_ID veya NETLIFY_SITE_NAME eksik."
        )
        return None

    path = f"audio/cx-{d}.mp3"
    url = f"{NETLIFY_API_BASE}/sites/{site_id}/files/{path}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "audio/mpeg",
    }

    try:
        resp = requests.put(
            url,
            data=mp3_bytes,
            headers=headers,
            timeout=120,
        )
        if resp.status_code in (200, 201, 204):
            public = f"https://{site_name}.netlify.app/{path}"
            logger.info("netlify_upload: Yüklendi — %s", public)
            return public
        logger.warning(
            "netlify_upload: HTTP %s — %s",
            resp.status_code,
            (resp.text or "")[:500],
        )
        return None
    except Exception:
        logger.exception("netlify_upload: İstek hatası.")
        return None
