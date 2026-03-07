"""
/setting command — per-member configuration via Telegram.

Flow:
  /setting              → show current settings + menu
  /setting name <text>  → set display name
  /setting calendar     → instructions for submitting Google token
  /setting token <b64>  → save Google Calendar token (message deleted after)
  /setting status       → show what's configured
"""
import logging

from telegram import Update
from telegram.ext import ContextTypes

import services.member_settings as ms

logger = logging.getLogger(__name__)

CALENDAR_INSTRUCTIONS = (
    "📅 <b>設定 Google Calendar</b>\n\n"
    "1. 在本地電腦執行：\n"
    "<code>python secretary/auth_setup.py</code>\n\n"
    "2. 完成 Google 授權後，複製輸出的 <code>GOOGLE_TOKEN_B64=...</code> 的值\n\n"
    "3. 發送：\n"
    "<code>/setting token &lt;貼上token&gt;</code>\n\n"
    "⚠️ 發送後 bot 會立即刪除該訊息以保護 token 安全。"
)


async def setting_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = context.args  # list of words after /setting

    # No args → show status + help
    if not args:
        await _show_status(update, chat_id)
        return

    sub = args[0].lower()

    if sub == "status":
        await _show_status(update, chat_id)

    elif sub == "calendar":
        await update.message.reply_text(CALENDAR_INSTRUCTIONS, parse_mode='HTML')

    elif sub == "name":
        if len(args) < 2:
            await update.message.reply_text("用法：/setting name 你的名字")
            return
        name = " ".join(args[1:])
        ok = ms.upsert(chat_id, display_name=name)
        if ok:
            await update.message.reply_text(f"✅ 名稱已更新為：{name}")
        else:
            await update.message.reply_text("⚠️ 儲存失敗，請確認 Supabase 已設定。")

    elif sub == "token":
        if len(args) < 2:
            await update.message.reply_text(
                "用法：/setting token <base64_token>\n"
                "不知道怎麼取得？先執行 /setting calendar"
            )
            return
        token = args[1].strip()
        # Delete the message immediately to protect the token
        try:
            await update.message.delete()
        except Exception:
            pass  # no delete permission, continue anyway
        if not _looks_like_b64(token):
            await update.message.reply_text("⚠️ Token 格式不對，請重新確認。")
            return
        ok = ms.upsert(chat_id, google_token_b64=token)
        if ok:
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Google Calendar token 已儲存！\n輸入「今天有什麼行程？」試試看。"
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ 儲存失敗，請確認 Supabase 已設定。"
            )

    else:
        await update.message.reply_text(
            "❓ 未知選項。可用指令：\n"
            "/setting — 查看設定狀態\n"
            "/setting name <名字> — 設定顯示名稱\n"
            "/setting calendar — 設定 Google Calendar\n"
            "/setting token <token> — 儲存 Calendar token\n"
            "/setting status — 查看設定狀態"
        )


async def _show_status(update: Update, chat_id: int):
    row = ms.get(chat_id)
    name = row.get("display_name") or "（未設定）" if row else "（未設定）"
    has_cal = bool(row.get("google_token_b64")) if row else False
    cal_status = "✅ 已連接" if has_cal else "❌ 未設定"

    text = (
        f"⚙️ <b>你的設定</b>\n\n"
        f"👤 名稱：{name}\n"
        f"📅 Google Calendar：{cal_status}\n\n"
        f"<b>設定指令：</b>\n"
        f"/setting name &lt;名字&gt; — 設定名稱\n"
        f"/setting calendar — 設定 Google Calendar\n"
    )
    await update.message.reply_text(text, parse_mode='HTML')


def _looks_like_b64(s: str) -> bool:
    import base64
    try:
        base64.b64decode(s, validate=True)
        return len(s) > 100  # real tokens are long
    except Exception:
        return False
