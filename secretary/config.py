import os

BOT_TOKEN = os.environ.get('SECRETARY_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
WHALE_RADAR_REPO = os.environ.get('WHALE_RADAR_REPO', 'kuafuro/whale-rader')

# Base64-encoded Google OAuth token JSON (run auth_setup.py once to generate)
# Per-member override: set GOOGLE_TOKEN_B64_<chat_id> for each member
GOOGLE_TOKEN_B64 = os.environ.get('GOOGLE_TOKEN_B64')


def get_google_token(chat_id: int) -> str | None:
    """Return per-member Google token if configured, else fall back to default."""
    return os.environ.get(f'GOOGLE_TOKEN_B64_{chat_id}') or GOOGLE_TOKEN_B64

# Daily briefing time (HKT = UTC+8)
BRIEFING_MORNING_HOUR = 8   # HKT 08:00
BRIEFING_EVENING_HOUR = 21  # HKT 21:00
