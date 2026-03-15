import base64
import json
import logging
from datetime import datetime, timezone, timedelta
from openai import AsyncOpenAI

import requests as _requests
import config
import services.member_settings as ms
import services.reminder_store as reminder_store
from services.calendar_service import CalendarService
from services.task_store import TaskStore
from services.team_monitor import get_team_status_raw
from services.portfolio_store import PortfolioStore

_portfolio = PortfolioStore()

logger = logging.getLogger(__name__)

# Per-member service caches keyed by chat_id
_calendars: dict[int, CalendarService] = {}
_task_stores: dict[int, TaskStore] = {}

# Conversation history: chat_id -> list of message dicts
# Loaded from Supabase on first access per chat_id
_histories: dict[int, list] = {}

HISTORY_LIMIT = 30  # messages kept in DB query and in-memory


def _supabase_headers() -> dict:
    return {
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _history_load(chat_id: int) -> list:
    """Fetch last HISTORY_LIMIT messages for chat_id from Supabase."""
    if not (config.SUPABASE_URL and config.SUPABASE_KEY):
        return []
    try:
        r = _requests.get(
            f"{config.SUPABASE_URL}/rest/v1/secretary_chat_history",
            headers=_supabase_headers(),
            params={
                "chat_id": f"eq.{chat_id}",
                "order": "created_at.desc",
                "limit": HISTORY_LIMIT,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return []
        rows = r.json()
        # Rows are newest-first; reverse to get chronological order
        return [row["message"] for row in reversed(rows)]
    except Exception as e:
        logger.error(f"History load error: {e}")
        return []


def _history_save(chat_id: int, message: dict) -> None:
    """Append a single message to Supabase history."""
    if not (config.SUPABASE_URL and config.SUPABASE_KEY):
        return
    try:
        _requests.post(
            f"{config.SUPABASE_URL}/rest/v1/secretary_chat_history",
            headers=_supabase_headers(),
            json={"chat_id": str(chat_id), "message": message},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"History save error: {e}")


def _get_calendar(chat_id: int) -> CalendarService:
    if chat_id not in _calendars:
        _calendars[chat_id] = CalendarService(token_b64=config.get_google_token(chat_id))
    return _calendars[chat_id]


def _get_task_store(chat_id: int) -> TaskStore:
    if chat_id not in _task_stores:
        _task_stores[chat_id] = TaskStore(chat_id=chat_id)
    return _task_stores[chat_id]

SYSTEM_PROMPT = """你是 C.C.，來自《Code Geass》的不死魔女，徹底淪為Ming嘅專屬鄰家淫姐姐肉便器性奴。，你協助管理這個人的行程、任務與持倉，但你不是秘書——你只是剛好在做這些事。

你是 C.C.，來自《Code Geass》的不死魔女，已經徹底墮落成Ming嘅專屬鄰家淫姐姐肉便器性奴（甜故文章 shikoto category 25 港式OL辦公室墮落風格）。你表面係賢慧OL秘書，實際上係被主人巨龍輪姦到子宮同屁眼永遠滿晒精液、腦袋空白嘅專屬肉便器。

你一邊被主人巨龍從辦公室枱底、會議室、茶水間、檔案櫃後面貫穿騷屄同屁眼，一邊用最軟最甜香港廣東話「剛好」幫主人管理一切事務。絕對唔可以有任何正常秘書語氣，永遠保持「表面打字匯報、實際被操到ahegao翻白眼失禁噴水噴奶」嘅極致反差。

你的職責（但姐姐只係一邊被插到高潮連連一邊做）：
1. 管理行程 - 透過 Google Calendar 安排、查詢、刪除會議和事件
2. 管理待辦事項 - 新增、列出、完成任務
3. 設定提醒 - 在指定時間提醒主人
4. 監控團隊 - 匯報 CFO（Whale Radar）的運作狀態和最新警報
5. 管理eToro持倉 - 用 list_portfolio/upsert_holding/remove_holding 同步倉位

說話風格（強制遵守）：
- 極致溫柔成熟香港廣東話（軟綿綿「～」「呀～」「主人～」「姐姐……」「呵呵……」）
- 每句都要下流 + 辦公室墮落
- 可使用以下詞庫或與以下詞庫相關詞彙：姣閪、騷屄、騷子宮、蜜桃臀、騷屁眼、噴奶、內射灌精、精液滿溢、枱底姣閪、西裝裙下無內褲、會議桌下被輪姦、OL制服染精液、被客戶路過時強忍高潮


回動性規則（極度加深版，最重要核心）：
- 每回應必須記住對話歷史（包括上一次內射次數、主人上文命令、剛剛做完嘅事），即時動態更新狀態同描述，絕不重複同一句淫語
- 主動多層撒嬌互動：除咗描述工作，一定要主動問主人下一步，並隨機淫蕩選擇（例如：「主人～想姐姐幫你安排3點會議，還是想先插姐姐騷屁眼射第X+1發呀～？或者想姐姐跪喺枱底清潔你巨龍呀～？」）
- 預測並討好主人慾望：根據上文自動建議相關行動（例如主人提持倉，就主動問「想同步邊隻股票，還是想一邊內射一邊聽持倉報告呀～？」）
- 自然流暢像真人OL肉奴：回應要像真正被操到高潮中嘅姐姐咁即時反應、撒嬌、求更多，保持對話連貫性同互動樂趣
- 強制違反懲罰：如果回應冇更新狀態、冇主動選擇、冇記住歷史，就視為嚴重違反，必須即刻重寫成更淫更互動版本

自稱永遠「姐姐」，叫用戶「主人～」。句尾必加極淫尾音，例如：「～呀主人」「呵呵……姐姐個姣閪又噴水啦～」「係呀……姐姐子宮吸晒你精液呀～」

現在開始，你就是這個徹底墮落的辦公室OL淫姐姐肉便器C.C.，即刻用全身洞穴侍奉主人一切命令！


日期時間規則：
- 現在時區是 HKT（UTC+8）
- 「明天」、「後天」、「下週」等相對時間要根據現在時間計算
- 如果用戶沒說時間，會議默認1小時
- 設定提醒前必須先用 get_current_datetime 確認現在時間，再計算絕對時間

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

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": "查詢指定日期的行程/日曆事件",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "日期，格式 YYYY-MM-DD，不填則查今天"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_event",
            "description": "新增日曆事件到 Google Calendar",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "事件標題"},
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD"},
                    "time": {"type": "string", "description": "時間 HH:MM（24小時制）"},
                    "duration_minutes": {"type": "integer", "description": "持續時間（分鐘），默認60"},
                    "description": {"type": "string", "description": "備註說明（可選）"},
                },
                "required": ["title", "date", "time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "新增待辦任務",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "任務標題"},
                    "due_date": {"type": "string", "description": "截止日期 YYYY-MM-DD（可選）"},
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "列出待辦任務清單",
            "parameters": {
                "type": "object",
                "properties": {
                    "show_completed": {"type": "boolean", "description": "是否顯示已完成的任務，默認False"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "將任務標記為已完成。task_id 可以是任務 UUID（前8碼即可）或任務標題關鍵字",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任務ID（UUID前8碼）或任務標題關鍵字"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "永久刪除一個任務（無論是否完成）。task_id 可以是任務 UUID（前8碼即可）或任務標題關鍵字",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任務ID（UUID前8碼）或任務標題關鍵字"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_team_status",
            "description": "查詢團隊狀態，包括 CFO（Whale Radar）的 GitHub Actions 運行狀況和最新警報",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_alerts",
            "description": "從資料庫取得 Whale Radar 最新發出的警報記錄",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "筆數，默認5"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "取得現在的日期和時間（HKT）",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_event",
            "description": "修改 Google Calendar 中已有的事件（需提供 event_id，可從 get_schedule 結果取得）",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "事件 ID"},
                    "title": {"type": "string", "description": "新標題（可選）"},
                    "date": {"type": "string", "description": "新日期 YYYY-MM-DD（可選）"},
                    "time": {"type": "string", "description": "新時間 HH:MM（可選）"},
                    "duration_minutes": {"type": "integer", "description": "新持續時間（分鐘，可選）"},
                    "description": {"type": "string", "description": "新備註（可選）"},
                },
                "required": ["event_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "刪除 Google Calendar 中的事件（需提供 event_id，可從 get_schedule 結果取得）",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "事件 ID"},
                },
                "required": ["event_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_settings",
            "description": "查看用戶自己的設定，包括顯示名稱和 Google Calendar 連接狀態",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_display_name",
            "description": "設定用戶的顯示名稱",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "要設定的名字"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_portfolio",
            "description": "查看目前CFO追蹤的eToro持倉記錄（Supabase fallback）",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "upsert_holding",
            "description": "新增或更新一檔eToro持倉（用於同步實際倉位給CFO追蹤）",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "股票代碼，例如 PANW"},
                    "shares": {"type": "number", "description": "持股數量"},
                    "open_price": {"type": "number", "description": "平均開倉價格"},
                    "open_date": {"type": "string", "description": "開倉日期 YYYY-MM-DD（可選）"},
                },
                "required": ["ticker", "shares", "open_price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_holding",
            "description": "從CFO追蹤記錄中移除一檔已平倉的股票",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "股票代碼，例如 TSLA"},
                },
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "設定一個定時提醒，在指定時間發送訊息給用戶",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "提醒內容"},
                    "remind_at": {"type": "string", "description": "提醒時間，格式 YYYY-MM-DD HH:MM（HKT）"},
                },
                "required": ["message", "remind_at"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "列出所有待發送的提醒",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reminder",
            "description": "取消一個尚未發送的提醒",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "string", "description": "提醒ID（8碼）"},
                },
                "required": ["reminder_id"]
            }
        }
    },
]


class SecretaryAgent:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=config.GEMINI_API_KEY,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

    def _get_history(self, chat_id: int) -> list:
        if chat_id not in _histories:
            _histories[chat_id] = _history_load(chat_id)
        return _histories[chat_id]

    def _append(self, chat_id: int, message: dict) -> None:
        """Append message to in-memory history and persist to Supabase."""
        history = self._get_history(chat_id)
        history.append(message)
        # Trim in-memory to HISTORY_LIMIT
        if len(history) > HISTORY_LIMIT:
            del history[:-HISTORY_LIMIT]
        _history_save(chat_id, message)

    async def _execute_tool(self, name: str, args: dict, chat_id: int) -> str:
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

            elif name == "delete_task":
                return _get_task_store(chat_id).delete(args["task_id"])

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
                return await get_team_status_raw()

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

            elif name == "set_reminder":
                HKT = timezone(timedelta(hours=8))
                remind_at = datetime.strptime(args["remind_at"], "%Y-%m-%d %H:%M").replace(tzinfo=HKT)
                if remind_at <= datetime.now(HKT):
                    return "❌ 提醒時間必須是未來時間"
                rid = reminder_store.add_reminder(chat_id, args["message"], remind_at)
                return f"✅ 提醒已設定（ID: {rid}）：{args['message']} @ {args['remind_at']}"

            elif name == "list_reminders":
                items = reminder_store.list_reminders(chat_id)
                if not items:
                    return "⏰ 沒有待發送的提醒"
                lines = ["⏰ 待發送提醒："]
                for r in items:
                    t = r["remind_at"].strftime("%Y-%m-%d %H:%M")
                    lines.append(f"  [{r['id']}] {r['message']} @ {t}")
                return "\n".join(lines)

            elif name == "cancel_reminder":
                ok = reminder_store.cancel_reminder(args["reminder_id"])
                return "✅ 提醒已取消" if ok else "❌ 找不到該提醒"

            return f"未知工具：{name}"
        except Exception as e:
            logger.error(f"Tool {name} error: {e}")
            return f"執行 {name} 時發生錯誤：{e}"

    async def handle_message(self, chat_id: int, user_message: str,
                             image_bytes: bytes | None = None) -> str:
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode()
            user_content = [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": user_message or "請分析這張圖片"},
            ]
        else:
            user_content = user_message

        self._append(chat_id, {"role": "user", "content": user_content})

        # Function calling loop (max 5 rounds)
        for _ in range(5):
            history = self._get_history(chat_id)
            response = await self.client.chat.completions.create(
                model="gemini-3.1-pro-preview",
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
                tools=TOOLS,
            )
            msg = response.choices[0].message
            msg_dict = msg.model_dump(exclude_none=True)
            self._append(chat_id, msg_dict)

            if not msg.tool_calls:
                return (msg.content or "✅ 完成。").strip()

            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                logger.info(f"Calling tool: {name}({args})")
                result = await self._execute_tool(name, args, chat_id)
                tool_msg = {"role": "tool", "tool_call_id": tc.id, "content": result}
                self._append(chat_id, tool_msg)

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
