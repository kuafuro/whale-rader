import logging
import requests

import config

logger = logging.getLogger(__name__)

_URL = lambda: f"{config.SUPABASE_URL}/rest/v1/member_settings"


def _headers():
    return {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def get(chat_id: int) -> dict | None:
    """Return settings row for chat_id, or None."""
    if not config.SUPABASE_URL:
        return None
    try:
        r = requests.get(
            _URL(),
            headers=_headers(),
            params={"chat_id": f"eq.{chat_id}"},
        )
        rows = r.json() if r.status_code == 200 else []
        return rows[0] if rows else None
    except Exception as e:
        logger.error(f"member_settings.get error: {e}")
        return None


def upsert(chat_id: int, **fields) -> bool:
    """Insert or update settings for chat_id. Returns True on success."""
    if not config.SUPABASE_URL:
        return False
    try:
        data = {"chat_id": str(chat_id), **{k: v for k, v in fields.items()}}
        data["updated_at"] = "now()"
        r = requests.post(
            _URL(),
            headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=representation"},
            json=data,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        logger.error(f"member_settings.upsert error: {e}")
        return False


def get_google_token(chat_id: int) -> str | None:
    """Return stored Google token for chat_id, or None."""
    row = get(chat_id)
    return row.get("google_token_b64") if row else None
