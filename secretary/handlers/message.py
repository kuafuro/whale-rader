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
    msg = update.message
    chat_id = update.effective_chat.id

    # Extract text (caption for photos, text for normal messages)
    user_message = msg.caption or msg.text or ""

    # Download photo if present (pick highest resolution)
    image_bytes = None
    if msg.photo:
        photo = msg.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        reply = await _get_agent().handle_message(chat_id, user_message, image_bytes=image_bytes)
        try:
            await msg.reply_text(reply, parse_mode='HTML')
        except Exception:
            await msg.reply_text(reply)
    except Exception as e:
        logger.error(f"Agent error: {e}")
        await msg.reply_text("⚠️ 處理時發生錯誤，請再試一次。")
