import logging
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

import config
from services.calendar_service import CalendarService
from services.task_store import TaskStore
from services.team_monitor import get_team_status_raw

logger = logging.getLogger(__name__)

calendar = CalendarService()
tasks = TaskStore()

SYSTEM_PROMPT = """你是一位專業、高效的 AI 秘書，名字叫「小秘」。你的僱主是你唯一的用戶。

你的職責：
1. 管理行程 - 透過 Google Calendar 安排、查詢、刪除會議和事件
2. 管理待辦事項 - 新增、列出、完成任務
3. 設定提醒 - 在指定時間提醒僱主
4. 監控團隊 - 匯報 CFO（Whale Radar）的運作狀態和最新警報

說話風格：
- 用繁體中文回覆
- 專業但親切，像真正的秘書
- 執行完動作後要簡潔確認結果
- 不要廢話，直接說重點

日期時間規則：
- 現在時區是 HKT（UTC+8）
- 「明天」、「後天」、「下週」等相對時間要根據現在時間計算
- 如果用戶沒說時間，會議默認1小時

重要：只有僱主本人才能使用你的功能。"""

TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="get_schedule",
        description="查詢指定日期的行程/日曆事件",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "date": types.Schema(type=types.Type.STRING,
                                     description="日期，格式 YYYY-MM-DD，不填則查今天")
            }
        )
    ),
    types.FunctionDeclaration(
        name="add_event",
        description="新增日曆事件到 Google Calendar",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "title": types.Schema(type=types.Type.STRING, description="事件標題"),
                "date": types.Schema(type=types.Type.STRING, description="日期 YYYY-MM-DD"),
                "time": types.Schema(type=types.Type.STRING, description="時間 HH:MM（24小時制）"),
                "duration_minutes": types.Schema(type=types.Type.INTEGER,
                                                 description="持續時間（分鐘），默認60"),
                "description": types.Schema(type=types.Type.STRING, description="備註說明（可選）"),
            },
            required=["title", "date", "time"]
        )
    ),
    types.FunctionDeclaration(
        name="add_task",
        description="新增待辦任務",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "title": types.Schema(type=types.Type.STRING, description="任務標題"),
                "due_date": types.Schema(type=types.Type.STRING,
                                         description="截止日期 YYYY-MM-DD（可選）"),
            },
            required=["title"]
        )
    ),
    types.FunctionDeclaration(
        name="list_tasks",
        description="列出待辦任務清單",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "show_completed": types.Schema(type=types.Type.BOOLEAN,
                                               description="是否顯示已完成的任務，默認False")
            }
        )
    ),
    types.FunctionDeclaration(
        name="complete_task",
        description="將任務標記為已完成",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "task_id": types.Schema(type=types.Type.STRING, description="任務ID")
            },
            required=["task_id"]
        )
    ),
    types.FunctionDeclaration(
        name="check_team_status",
        description="查詢團隊狀態，包括 CFO（Whale Radar）的 GitHub Actions 運行狀況和最新警報",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={}
        )
    ),
    types.FunctionDeclaration(
        name="get_latest_alerts",
        description="從資料庫取得 Whale Radar 最新發出的警報記錄",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "limit": types.Schema(type=types.Type.INTEGER, description="筆數，默認5")
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_current_datetime",
        description="取得現在的日期和時間（HKT）",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={}
        )
    ),
])]


class SecretaryAgent:
    def __init__(self):
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.sessions = {}  # chat_id -> chat session

    def _get_session(self, chat_id: int):
        if chat_id not in self.sessions:
            self.sessions[chat_id] = self.client.chats.create(
                model="gemini-2.0-flash",
                config=types.GenerateContentConfig(
                    tools=TOOLS,
                    system_instruction=SYSTEM_PROMPT,
                )
            )
        return self.sessions[chat_id]

    def _execute_tool(self, name: str, args: dict) -> str:
        try:
            if name == "get_current_datetime":
                now = datetime.now(timezone(timedelta(hours=8)))
                return f"現在時間：{now.strftime('%Y-%m-%d %H:%M')} HKT（{now.strftime('%A')}）"

            elif name == "get_schedule":
                date_str = args.get("date", datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d'))
                return calendar.get_events(date_str)

            elif name == "add_event":
                return calendar.add_event(
                    title=args["title"],
                    date=args["date"],
                    time=args["time"],
                    duration_minutes=args.get("duration_minutes", 60),
                    description=args.get("description", "")
                )

            elif name == "add_task":
                return tasks.add(args["title"], args.get("due_date"))

            elif name == "list_tasks":
                return tasks.list_tasks(show_completed=args.get("show_completed", False))

            elif name == "complete_task":
                return tasks.complete(args["task_id"])

            elif name == "check_team_status":
                import asyncio
                return asyncio.get_event_loop().run_until_complete(get_team_status_raw())

            elif name == "get_latest_alerts":
                return _get_latest_alerts(args.get("limit", 5))

            return f"未知工具：{name}"
        except Exception as e:
            logger.error(f"Tool {name} error: {e}")
            return f"執行 {name} 時發生錯誤：{e}"

    async def handle_message(self, chat_id: int, user_message: str) -> str:
        session = self._get_session(chat_id)

        response = session.send_message(user_message)

        # Handle function calling loop (max 5 rounds)
        for _ in range(5):
            fn_calls = [p for p in response.candidates[0].content.parts
                        if hasattr(p, 'function_call') and p.function_call.name]
            if not fn_calls:
                break

            results = []
            for part in fn_calls:
                fc = part.function_call
                logger.info(f"Calling tool: {fc.name}({dict(fc.args)})")
                result = self._execute_tool(fc.name, dict(fc.args))
                results.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=fc.name,
                        response={"result": result}
                    )
                ))

            response = session.send_message(results)

        # Extract text response
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text') and part.text:
                return part.text.strip()

        return "✅ 完成。"


def _get_latest_alerts(limit: int = 5) -> str:
    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        return "Supabase 未設定"
    import requests
    try:
        headers = {"apikey": config.SUPABASE_KEY, "Authorization": f"Bearer {config.SUPABASE_KEY}"}
        r = requests.get(
            f"{config.SUPABASE_URL}/rest/v1/whale_alerts",
            headers=headers,
            params={"order": "created_at.desc", "limit": limit}
        )
        if r.status_code != 200:
            return f"查詢失敗：{r.status_code}"
        data = r.json()
        if not data:
            return "暫無警報記錄"
        lines = []
        for a in data:
            lines.append(
                f"[{a.get('source', '').upper()}] {a.get('ticker', 'N/A')} - "
                f"{a.get('action', '')} @ {a.get('created_at', '')[:16]}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"錯誤：{e}"
