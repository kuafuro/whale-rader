import logging
import uuid
from datetime import datetime, timezone, timedelta

import requests
from apscheduler.jobstores.base import JobLookupError

import config
from services.scheduler import get_scheduler

logger = logging.getLogger(__name__)
HKT = timezone(timedelta(hours=8))

_app = None
_reminders: dict[str, dict] = {}
_use_supabase = False


def set_app(app) -> None:
    global _app, _use_supabase
    _app = app
    _use_supabase = bool(config.SUPABASE_URL and config.SUPABASE_KEY)


def _headers() -> dict:
    return {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _db_insert(reminder_id: str, chat_id: int, message: str, remind_at: datetime) -> None:
    try:
        requests.post(
            f"{config.SUPABASE_URL}/rest/v1/secretary_reminders",
            headers=_headers(),
            json={
                "id": reminder_id,
                "chat_id": str(chat_id),
                "message": message,
                "remind_at": remind_at.isoformat(),
                "sent": False,
            },
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Reminder DB insert error: {e}")


def _db_mark_sent(reminder_id: str) -> None:
    try:
        requests.patch(
            f"{config.SUPABASE_URL}/rest/v1/secretary_reminders",
            headers=_headers(),
            params={"id": f"eq.{reminder_id}"},
            json={"sent": True},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Reminder DB mark_sent error: {e}")


def _db_delete(reminder_id: str) -> None:
    try:
        requests.delete(
            f"{config.SUPABASE_URL}/rest/v1/secretary_reminders",
            headers=_headers(),
            params={"id": f"eq.{reminder_id}"},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"Reminder DB delete error: {e}")


def _schedule_job(reminder_id: str, chat_id: int, message: str, remind_at: datetime) -> None:
    async def _send():
        if _app:
            await _app.bot.send_message(chat_id=chat_id, text=f"⏰ 提醒：{message}")
        _reminders.pop(reminder_id, None)
        if _use_supabase:
            _db_mark_sent(reminder_id)

    get_scheduler().add_job(_send, "date", run_date=remind_at, id=reminder_id, replace_existing=True)


def add_reminder(chat_id: int, message: str, remind_at: datetime) -> str:
    reminder_id = str(uuid.uuid4())[:8]
    _reminders[reminder_id] = {
        "id": reminder_id,
        "message": message,
        "remind_at": remind_at,
        "chat_id": chat_id,
    }
    if _use_supabase:
        _db_insert(reminder_id, chat_id, message, remind_at)
    _schedule_job(reminder_id, chat_id, message, remind_at)
    logger.info(f"Reminder {reminder_id} set for {remind_at} (chat {chat_id})")
    return reminder_id


def list_reminders(chat_id: int) -> list[dict]:
    if _use_supabase:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            r = requests.get(
                f"{config.SUPABASE_URL}/rest/v1/secretary_reminders",
                headers=_headers(),
                params={
                    "chat_id": f"eq.{chat_id}",
                    "sent": "eq.false",
                    "remind_at": f"gt.{now_iso}",
                    "order": "remind_at.asc",
                },
                timeout=10,
            )
            if r.status_code == 200:
                return [
                    {
                        "id": row["id"],
                        "message": row["message"],
                        "remind_at": datetime.fromisoformat(row["remind_at"]),
                        "chat_id": int(row["chat_id"]),
                    }
                    for row in r.json()
                ]
        except Exception as e:
            logger.error(f"Reminder DB list error: {e}")
    return [r for r in _reminders.values() if r["chat_id"] == chat_id]


def cancel_reminder(reminder_id: str) -> bool:
    if reminder_id not in _reminders:
        return False
    try:
        get_scheduler().remove_job(reminder_id)
    except JobLookupError:
        pass
    del _reminders[reminder_id]
    if _use_supabase:
        _db_delete(reminder_id)
    return True


def load_pending_reminders() -> None:
    """Load unsent future reminders from Supabase and reschedule them.
    Call once at bot startup after set_app()."""
    if not _use_supabase:
        return
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        r = requests.get(
            f"{config.SUPABASE_URL}/rest/v1/secretary_reminders",
            headers=_headers(),
            params={
                "sent": "eq.false",
                "remind_at": f"gt.{now_iso}",
                "order": "remind_at.asc",
            },
            timeout=10,
        )
        if r.status_code != 200:
            logger.error(f"Failed to load pending reminders: {r.status_code}")
            return
        rows = r.json()
        for row in rows:
            rid = row["id"]
            chat_id = int(row["chat_id"])
            message = row["message"]
            remind_at = datetime.fromisoformat(row["remind_at"])
            if remind_at.tzinfo is None:
                remind_at = remind_at.replace(tzinfo=timezone.utc)
            _reminders[rid] = {
                "id": rid,
                "message": message,
                "remind_at": remind_at,
                "chat_id": chat_id,
            }
            _schedule_job(rid, chat_id, message, remind_at)
        logger.info(f"Loaded {len(rows)} pending reminders from Supabase")
    except Exception as e:
        logger.error(f"Error loading pending reminders: {e}")
