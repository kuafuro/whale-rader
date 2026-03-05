import base64
import json
import logging
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

import config

logger = logging.getLogger(__name__)
HKT = timezone(timedelta(hours=8))
SCOPES = ['https://www.googleapis.com/auth/calendar']


def _load_credentials():
    if not config.GOOGLE_TOKEN_B64:
        return None
    try:
        token_json = base64.b64decode(config.GOOGLE_TOKEN_B64).decode()
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except Exception as e:
        logger.error(f"Calendar credentials error: {e}")
        return None


class CalendarService:
    def __init__(self):
        self._creds = None

    def _get_service(self):
        if not self._creds or not self._creds.valid:
            self._creds = _load_credentials()
        if not self._creds:
            return None
        return build('calendar', 'v3', credentials=self._creds, cache_discovery=False)

    def get_events(self, date_str: str) -> str:
        service = self._get_service()
        if not service:
            return "⚠️ Google Calendar 未連接（GOOGLE_TOKEN_B64 未設定）"
        try:
            day = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=HKT)
            time_min = day.isoformat()
            time_max = (day + timedelta(days=1)).isoformat()
            result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = result.get('items', [])
            if not events:
                return f"📅 {date_str} 沒有行程"
            lines = [f"📅 {date_str} 行程："]
            for e in events:
                start = e['start'].get('dateTime', e['start'].get('date', ''))
                if 'T' in start:
                    t = datetime.fromisoformat(start).astimezone(HKT).strftime('%H:%M')
                else:
                    t = '全天'
                lines.append(f"  • {t} {e.get('summary', '（無標題）')}")
            return "\n".join(lines)
        except Exception as e:
            return f"查詢失敗：{e}"

    def add_event(self, title: str, date: str, time: str, duration_minutes: int = 60,
                  description: str = "") -> str:
        service = self._get_service()
        if not service:
            return "⚠️ Google Calendar 未連接"
        try:
            start_dt = datetime.strptime(f"{date} {time}", '%Y-%m-%d %H:%M').replace(tzinfo=HKT)
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            event = {
                'summary': title,
                'description': description,
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Asia/Hong_Kong'},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Asia/Hong_Kong'},
            }
            created = service.events().insert(calendarId='primary', body=event).execute()
            return f"✅ 已新增：{title}（{date} {time}，{duration_minutes}分鐘）\nID: {created['id']}"
        except Exception as e:
            return f"新增失敗：{e}"
