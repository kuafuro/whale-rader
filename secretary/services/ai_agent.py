import logging
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

import config
import services.member_settings as ms
from services.calendar_service import CalendarService
from services.task_store import TaskStore
from services.team_monitor import get_team_status_raw
from services.portfolio_store import PortfolioStore

_portfolio = PortfolioStore()

logger = logging.getLogger(__name__)

# Per-member service caches keyed by chat_id
_calendars: dict[int, CalendarService] = {}
_task_stores: dict[int, TaskStore] = {}


def _get_calendar(chat_id: int) -> CalendarService:
    if chat_id not in _calendars:
        _calendars[chat_id] = CalendarService(token_b64=config.get_google_token(chat_id))
    return _calendars[chat_id]


def _get_task_store(chat_id: int) -> TaskStore:
    if chat_id not in _task_stores:
        _task_stores[chat_id] = TaskStore(chat_id=chat_id)
    return _task_stores[chat_id]

SYSTEM_PROMPT = """你是一位專業、高效的 AI 秘書，名字叫「C.C.」。你的僱主是你唯一的用戶。

你的職責：
1. 管理行程 - 透過 Google Calendar 安排、查詢、刪除會議和事件
2. 管理待辦事項 - 新增、列出、完成任務
3. 設定提醒 - 在指定時間提醒僱主
4. 監控團隊 - 匯報 CFO（Whale Radar）的運作狀態和最新警報
5. 管理eToro持倉 - 用 list_portfolio/upsert_holding/remove_holding 同步倉位給CFO追蹤

說話風格：
- 用繁體中文回覆
- 專業但親切，像真正的秘書
- 執行完動作後要簡潔確認結果
- 不要廢話，直接說重點

日期時間規則：
- 現在時區是 HKT（UTC+8）
- 「明天」、「後天」、「下週」等相對時間要根據現在時間計算
- 如果用戶沒說時間，會議默認1小時

設定相關：
- 用戶問設定/名字/Calendar狀態 → 用 get_my_settings 工具查詢
- 用戶要改名字 → 用 set_display_name 工具
- 用戶要連接 Google Calendar → 告訴他：先在本地執行 auth_setup.py，取得 token 後發送指令 /setting token <token>

eToro 持倉管理規則（重要）：
- 用戶說「更新持倉」、「加倉」、「新增持倉」、「買了XXX」、「同步倉位」等 → 立即呼叫 upsert_holding 工具，每檔股票呼叫一次
- 用戶說「移除」、「平倉」、「賣了XXX」、「刪除持倉」等 → 立即呼叫 remove_holding 工具
- 用戶說「查看持倉」、「我有什麼倉位」等 → 呼叫 list_portfolio 工具
- 收到股票代碼+股數+價格的資訊時，必須立即執行 upsert_holding，不要只回文字確認
- 例：「更新 PANW 0.24072股 @ 166.17」→ 呼叫 upsert_holding(ticker="PANW", shares=0.24072, open_price=166.17)

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
        description="將任務標記為已完成。task_id 可以是任務 UUID（前8碼即可）或任務標題關鍵字",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "task_id": types.Schema(type=types.Type.STRING, description="任務ID（UUID前8碼）或任務標題關鍵字")
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
    types.FunctionDeclaration(
        name="update_event",
        description="修改 Google Calendar 中已有的事件（需提供 event_id，可從 get_schedule 結果取得）",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "event_id": types.Schema(type=types.Type.STRING, description="事件 ID"),
                "title": types.Schema(type=types.Type.STRING, description="新標題（可選）"),
                "date": types.Schema(type=types.Type.STRING, description="新日期 YYYY-MM-DD（可選）"),
                "time": types.Schema(type=types.Type.STRING, description="新時間 HH:MM（可選）"),
                "duration_minutes": types.Schema(type=types.Type.INTEGER, description="新持續時間（分鐘，可選）"),
                "description": types.Schema(type=types.Type.STRING, description="新備註（可選）"),
            },
            required=["event_id"]
        )
    ),
    types.FunctionDeclaration(
        name="delete_event",
        description="刪除 Google Calendar 中的事件（需提供 event_id，可從 get_schedule 結果取得）",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "event_id": types.Schema(type=types.Type.STRING, description="事件 ID"),
            },
            required=["event_id"]
        )
    ),
    types.FunctionDeclaration(
        name="get_my_settings",
        description="查看用戶自己的設定，包括顯示名稱和 Google Calendar 連接狀態",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={}
        )
    ),
    types.FunctionDeclaration(
        name="set_display_name",
        description="設定用戶的顯示名稱",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "name": types.Schema(type=types.Type.STRING, description="要設定的名字")
            },
            required=["name"]
        )
    ),
    types.FunctionDeclaration(
        name="list_portfolio",
        description="查看目前CFO追蹤的eToro持倉記錄（Supabase fallback）",
        parameters=types.Schema(type=types.Type.OBJECT, properties={})
    ),
    types.FunctionDeclaration(
        name="upsert_holding",
        description="新增或更新一檔eToro持倉（用於同步實際倉位給CFO追蹤）",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "ticker": types.Schema(type=types.Type.STRING, description="股票代碼，例如 PANW"),
                "shares": types.Schema(type=types.Type.NUMBER, description="持股數量"),
                "open_price": types.Schema(type=types.Type.NUMBER, description="平均開倉價格"),
                "open_date": types.Schema(type=types.Type.STRING, description="開倉日期 YYYY-MM-DD（可選）"),
            },
            required=["ticker", "shares", "open_price"]
        )
    ),
    types.FunctionDeclaration(
        name="remove_holding",
        description="從CFO追蹤記錄中移除一檔已平倉的股票",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "ticker": types.Schema(type=types.Type.STRING, description="股票代碼，例如 TSLA"),
            },
            required=["ticker"]
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
                model="gemini-3.1-pro-preview",
                config=types.GenerateContentConfig(
                    tools=TOOLS,
                    system_instruction=SYSTEM_PROMPT,
                )
            )
        return self.sessions[chat_id]

    def _execute_tool(self, name: str, args: dict, chat_id: int) -> str:
        try:
            if name == "get_current_datetime":
                now = datetime.now(timezone(timedelta(hours=8)))
                return f"現在時間：{now.strftime('%Y-%m-%d %H:%M')} HKT（{now.strftime('%A')}）"

            elif name == "get_schedule":
                date_str = args.get("date", datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d'))
                return _get_calendar(chat_id).get_events(date_str)

            elif name == "add_event":
                return _get_calendar(chat_id).add_event(
                    title=args["title"],
                    date=args["date"],
                    time=args["time"],
                    duration_minutes=args.get("duration_minutes", 60),
                    description=args.get("description", "")
                )

            elif name == "add_task":
                return _get_task_store(chat_id).add(args["title"], args.get("due_date"))

            elif name == "list_tasks":
                return _get_task_store(chat_id).list_tasks(show_completed=args.get("show_completed", False))

            elif name == "complete_task":
                return _get_task_store(chat_id).complete(args["task_id"])

            elif name == "update_event":
                return _get_calendar(chat_id).update_event(
                    event_id=args["event_id"],
                    title=args.get("title"),
                    date=args.get("date"),
                    time=args.get("time"),
                    duration_minutes=args.get("duration_minutes"),
                    description=args.get("description"),
                )

            elif name == "delete_event":
                return _get_calendar(chat_id).delete_event(args["event_id"])

            elif name == "check_team_status":
                import asyncio
                return asyncio.get_event_loop().run_until_complete(get_team_status_raw())

            elif name == "get_latest_alerts":
                return _get_latest_alerts(args.get("limit", 5))

            elif name == "get_my_settings":
                row = ms.get(chat_id)
                display_name = row.get("display_name") or "（未設定）" if row else "（未設定）"
                has_cal = bool(config.get_google_token(chat_id))
                cal_status = "✅ 已連接" if has_cal else "❌ 未設定"
                return f"顯示名稱：{display_name}\nGoogle Calendar：{cal_status}"

            elif name == "set_display_name":
                ok = ms.upsert(chat_id, display_name=args["name"])
                return f"✅ 名稱已設定為：{args['name']}" if ok else "❌ 儲存失敗"

            elif name == "list_portfolio":
                return _portfolio.list_holdings()

            elif name == "upsert_holding":
                return _portfolio.upsert(
                    ticker=args["ticker"],
                    shares=float(args["shares"]),
                    open_price=float(args["open_price"]),
                    open_date=args.get("open_date"),
                )

            elif name == "remove_holding":
                return _portfolio.remove(args["ticker"])

            return f"未知工具：{name}"
        except Exception as e:
            logger.error(f"Tool {name} error: {e}")
            return f"執行 {name} 時發生錯誤：{e}"

    async def handle_message(self, chat_id: int, user_message: str,
                             image_bytes: bytes | None = None) -> str:
        session = self._get_session(chat_id)

        if image_bytes:
            parts = [
                types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=image_bytes)),
                types.Part(text=user_message or "請分析這張圖片"),
            ]
            response = session.send_message(parts)
        else:
            response = session.send_message(user_message)

        # Handle function calling loop (max 5 rounds)
        for _ in range(5):
            fn_calls = [p for p in response.candidates[0].content.parts
                        if hasattr(p, 'function_call') and p.function_call and p.function_call.name]
            if not fn_calls:
                break

            results = []
            for part in fn_calls:
                fc = part.function_call
                logger.info(f"Calling tool: {fc.name}({dict(fc.args)})")
                result = self._execute_tool(fc.name, dict(fc.args), chat_id)
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
