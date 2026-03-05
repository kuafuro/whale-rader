import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

import config
from services.calendar_service import CalendarService
from services.task_store import TaskStore
from services.team_monitor import get_team_status_raw

logger = logging.getLogger(__name__)
HKT = timezone(timedelta(hours=8))

calendar = CalendarService()
tasks = TaskStore()
_scheduler = None


async def generate_briefing() -> str:
    now = datetime.now(HKT)
    today_str = now.strftime('%Y-%m-%d')
    weekday_map = {0:'星期一',1:'星期二',2:'星期三',3:'星期四',4:'星期五',5:'星期六',6:'星期日'}
    weekday = weekday_map[now.weekday()]

    session_label = "🌅 早安簡報" if now.hour < 12 else "🌆 晚間簡報"

    lines = [
        f"<b>{session_label}</b>",
        f"📅 {today_str}（{weekday}）\n",
    ]

    # Today's schedule
    schedule = calendar.get_events(today_str)
    lines.append(schedule)
    lines.append("")

    # Pending tasks
    task_list = tasks.list_tasks(show_completed=False)
    lines.append(task_list)
    lines.append("")

    # Team status
    team_status = await get_team_status_raw()
    lines.append(team_status)

    return "\n".join(lines)


def schedule_daily_briefings(app: Application):
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="Asia/Hong_Kong")

    async def send_briefing():
        if not config.CHAT_ID:
            logger.warning("TELEGRAM_CHAT_ID not set, skipping briefing")
            return
        try:
            briefing = await generate_briefing()
            await app.bot.send_message(
                chat_id=config.CHAT_ID,
                text=briefing,
                parse_mode='HTML'
            )
            logger.info("Daily briefing sent")
        except Exception as e:
            logger.error(f"Briefing error: {e}")

    # HKT 08:00 morning briefing
    _scheduler.add_job(send_briefing, 'cron', hour=config.BRIEFING_MORNING_HOUR, minute=0)
    # HKT 21:00 evening briefing
    _scheduler.add_job(send_briefing, 'cron', hour=config.BRIEFING_EVENING_HOUR, minute=0)

    _scheduler.start()
    logger.info(f"Daily briefings scheduled: {config.BRIEFING_MORNING_HOUR}:00 & {config.BRIEFING_EVENING_HOUR}:00 HKT")
