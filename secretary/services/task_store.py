import logging
import requests
import uuid

import config

logger = logging.getLogger(__name__)


class TaskStore:
    """Task storage backed by Supabase secretary_tasks table.
    Falls back to in-memory if Supabase is not configured.
    Each instance is scoped to a single chat_id for member isolation."""

    def __init__(self, chat_id: int = None):
        self._chat_id = str(chat_id) if chat_id is not None else None
        self._memory = []  # fallback
        self._use_supabase = bool(config.SUPABASE_URL and config.SUPABASE_KEY)

    def _headers(self):
        return {
            "apikey": config.SUPABASE_KEY,
            "Authorization": f"Bearer {config.SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    def add(self, title: str, due_date: str = None) -> str:
        if self._use_supabase:
            try:
                data = {"title": title, "completed": False}
                if due_date:
                    data["due_date"] = due_date
                if self._chat_id:
                    data["chat_id"] = self._chat_id
                r = requests.post(
                    f"{config.SUPABASE_URL}/rest/v1/secretary_tasks",
                    headers=self._headers(), json=data
                )
                if r.status_code in (200, 201):
                    row = r.json()[0] if isinstance(r.json(), list) else r.json()
                    return f"✅ 任務已新增：{title}（ID: {str(row.get('id',''))[:8]}）"
                return f"新增失敗：{r.status_code}"
            except Exception as e:
                return f"錯誤：{e}"
        else:
            task_id = str(uuid.uuid4())[:8]
            self._memory.append({"id": task_id, "title": title, "due_date": due_date, "completed": False})
            return f"✅ 任務已新增：{title}（ID: {task_id}）"

    def list_tasks(self, show_completed: bool = False) -> str:
        if self._use_supabase:
            try:
                params = {"order": "created_at.asc"}
                if not show_completed:
                    params["completed"] = "eq.false"
                if self._chat_id:
                    params["chat_id"] = f"eq.{self._chat_id}"
                r = requests.get(
                    f"{config.SUPABASE_URL}/rest/v1/secretary_tasks",
                    headers=self._headers(), params=params
                )
                items = r.json() if r.status_code == 200 else []
            except Exception as e:
                return f"查詢失敗：{e}"
        else:
            items = [t for t in self._memory if show_completed or not t["completed"]]

        if not items:
            return "📋 沒有待辦任務"
        lines = ["📋 待辦任務："]
        for t in items:
            check = "✅" if t.get("completed") else "⬜"
            due = f"（截止：{t['due_date']}）" if t.get("due_date") else ""
            lines.append(f"  {check} [{str(t['id'])[:8]}] {t['title']}{due}")
        return "\n".join(lines)

    def complete(self, task_id: str) -> str:
        if self._use_supabase:
            try:
                import re
                is_uuid = bool(re.match(r'^[0-9a-f-]{8,}', task_id.lower()))
                if is_uuid:
                    params = {"id": f"like.{task_id}%"}
                else:
                    params = {"title": f"ilike.*{task_id}*"}
                if self._chat_id:
                    params["chat_id"] = f"eq.{self._chat_id}"
                r = requests.patch(
                    f"{config.SUPABASE_URL}/rest/v1/secretary_tasks",
                    headers=self._headers(),
                    params=params,
                    json={"completed": True}
                )
                if r.status_code in (200, 204):
                    return f"✅ 任務已標記完成：{task_id}"
                return f"更新失敗：{r.status_code} {r.text}"
            except Exception as e:
                return f"錯誤：{e}"
        else:
            for t in self._memory:
                if t["id"] == task_id:
                    t["completed"] = True
                    return f"✅ 任務已完成：{t['title']}"
            return "找不到該任務"
