import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

import config
from handlers.commands import start_command, help_command, status_command, brief_command
from handlers.message import handle_message
from handlers.setting import setting_command
from services.briefing import schedule_daily_briefings

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    if not config.BOT_TOKEN:
        raise ValueError("SECRETARY_BOT_TOKEN not set")
    if not config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")

    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("brief", brief_command))
    app.add_handler(CommandHandler("setting", setting_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.post_init = schedule_daily_briefings

    logger.info("🤖 Secretary Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
