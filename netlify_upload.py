"""
Netlify üzerinde günlük ses dosyası yayınlama (deploy digest + dosya yükleme).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

NETLIFY_API_BASE = "https://api.netlify.com/api/v1"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def upload_audio(mp3_bytes: bytes, date_str: str) -> str | None:
    """
    MP3'ü Netlify'a yükler: özet (SHA1) ile deploy oluşturur, ardından ham dosyayı yükler.

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

    digest_key = f"/audio/cx-{d}.mp3"
    put_relative_path = f"audio/cx-{d}.mp3"
    sha1_hex = hashlib.sha1(mp3_bytes).hexdigest()

    auth_bearer = {"Authorization": f"Bearer {token}"}

    deploy_url = f"{NETLIFY_API_BASE}/sites/{site_id}/deploys"

    try:
        post_resp = requests.post(
            deploy_url,
            json={"files": {digest_key: sha1_hex}},
            headers={**auth_bearer, "Content-Type": "application/json"},
            timeout=90,
        )
        if post_resp.status_code not in (200, 201):
            logger.warning(
                "netlify_upload: Deploy oluşturma HTTP %s — %s",
                post_resp.status_code,
                (post_resp.text or "")[:600],
            )
            return None

        try:
            deploy_data = post_resp.json()
        except json.JSONDecodeError:
            logger.warning("netlify_upload: Deploy yanıtı JSON değil: %s", (post_resp.text or "")[:300])
            return None

        deploy_id = deploy_data.get("id")
        if not deploy_id:
            logger.warning(
                "netlify_upload: Deploy yanıtında id yok: %s",
                str(deploy_data)[:400],
            )
            return None

        file_put_url = f"{NETLIFY_API_BASE}/deploys/{deploy_id}/files/{put_relative_path}"
        put_resp = requests.put(
            file_put_url,
            data=mp3_bytes,
            headers={
                **auth_bearer,
                "Content-Type": "application/octet-stream",
            },
            timeout=120,
        )

        if put_resp.status_code not in (200, 201, 204):
            logger.warning(
                "netlify_upload: Dosya yükleme HTTP %s — %s",
                put_resp.status_code,
                (put_resp.text or "")[:600],
            )
            return None

        public = f"https://{site_name}.netlify.app/{put_relative_path}"
        logger.info(
            "netlify_upload: Yüklendi (deploy=%s) — %s",
            deploy_id[:12],
            public,
        )
        return public
    except Exception:
        logger.exception("netlify_upload: İstek hatası.")
        return None
