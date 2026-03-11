from telegram import Update
from telegram.ext import ContextTypes

from services.briefing import generate_briefing
from services.team_monitor import get_team_status
from services.portfolio_store import PortfolioStore

_portfolio = PortfolioStore()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 你好！我是你的 AI 秘書。\n\n"
        "你可以直接用中文跟我說話，例如：\n"
        "• 「幫我安排下週三下午3點開會」\n"
        "• 「提醒我明天10點打電話給客戶」\n"
        "• 「今天有什麼行程？」\n"
        "• 「CFO 系統現在正常嗎？」\n\n"
        "指令：\n"
        "/brief — 立即生成每日簡報\n"
        "/status — 查看團隊狀態\n"
        "/portfolio — 管理eToro持倉\n"
        "/help — 顯示幫助",
        parse_mode='HTML'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>📖 使用指南</b>\n\n"
        "<b>直接說話（推薦）：</b>\n"
        "• 「安排明天早上9點會議，1小時」\n"
        "• 「提醒我下午5點交報告」\n"
        "• 「這週三有什麼事？」\n"
        "• 「加一個任務：整理財務報告」\n"
        "• 「CFO 今天有沒有發警報？」\n"
        "• 「團隊現在狀態如何？」\n\n"
        "<b>指令：</b>\n"
        "/brief — 每日簡報（行程 + 團隊狀態）\n"
        "/status — 快速查看團隊狀態\n"
        "/portfolio — 管理eToro持倉（給CFO追蹤）\n"
        "/start — 重新開始\n"
        "/help — 顯示此說明",
        parse_mode='HTML'
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 正在查詢團隊狀態...")
    status = await get_team_status()
    await update.message.reply_text(status, parse_mode='HTML')


async def brief_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 正在生成簡報，請稍候...")
    briefing = await generate_briefing()
    await update.message.reply_text(briefing, parse_mode='HTML')


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /portfolio              — 列出所有持倉
    /portfolio add TICKER SHARES PRICE [DATE]   — 新增/更新持倉
    /portfolio remove TICKER                    — 移除持倉
    """
    args = context.args  # list of words after /portfolio

    if not args:
        result = _portfolio.list_holdings()
        await update.message.reply_text(result)
        return

    sub = args[0].lower()

    if sub == "add":
        # /portfolio add PANW 0.24072 166.17 [2025-01-15]
        if len(args) < 4:
            await update.message.reply_text(
                "用法：/portfolio add TICKER 股數 均價 [日期]\n"
                "例：/portfolio add PANW 0.24072 166.17"
            )
            return
        try:
            ticker = args[1].upper()
            shares = float(args[2])
            price = float(args[3])
            date = args[4] if len(args) >= 5 else None
            result = _portfolio.upsert(ticker, shares, price, date)
            await update.message.reply_text(result)
        except ValueError:
            await update.message.reply_text("❌ 股數和均價必須是數字")

    elif sub == "remove":
        if len(args) < 2:
            await update.message.reply_text("用法：/portfolio remove TICKER\n例：/portfolio remove TSLA")
            return
        ticker = args[1].upper()
        result = _portfolio.remove(ticker)
        await update.message.reply_text(result)

    else:
        await update.message.reply_text(
            "📊 <b>/portfolio 指令用法</b>\n\n"
            "/portfolio — 列出全部持倉\n"
            "/portfolio add TICKER 股數 均價 — 新增/更新\n"
            "/portfolio remove TICKER — 移除\n\n"
            "例：\n"
            "/portfolio add PANW 0.24072 166.17\n"
            "/portfolio remove TSLA",
            parse_mode='HTML'
        )
