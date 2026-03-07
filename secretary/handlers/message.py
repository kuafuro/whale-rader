import logging
from telegram import Update
from telegram.ext import ContextTypes

from services.ai_agent import SecretaryAgent

logger = logging.getLogger(__name__)
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = SecretaryAgent()
    return _agent


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        reply = await _get_agent().handle_message(chat_id, user_message)
        await update.message.reply_text(reply, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Agent error: {e}")
        await update.message.reply_text("⚠️ 處理時發生錯誤，請再試一次。")
