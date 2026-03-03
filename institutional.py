import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os
import re

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE')

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.get(url, params={'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'})
    if resp.status_code != 200:
        print(f"Telegram send failed: {resp.status_code}")

headers = {'User-Agent': 'WhaleRadarBot Admin@kuafuorhk.com'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=SC+13&owner=only&count=40&output=atom'

now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=15)

try:
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')
    print(f"Found {len(entries)} SC 13 entries")
    found_count = 0

    for entry in entries:
        updated_str = entry.updated.text
        try:
            if datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit:
                break
        except Exception:
            continue

        category = entry.category['term'] if entry.category else ""

        if category.startswith('SC 13D') or category.startswith('SC 13G'):
            link = entry.link['href']
            txt_link = link.replace('-index.htm', '.txt')

            txt_response = requests.get(txt_link, headers=headers)
            if txt_response.status_code == 200:
                txt_content = txt_response.text

                subject_match = re.search(r'<SUBJECT-COMPANY>.*?<CONFORMED-NAME>([^\n]+)', txt_content, re.DOTALL)
                filer_match = re.search(r'<FILED-BY>.*?<CONFORMED-NAME>([^\n]+)', txt_content, re.DOTALL)

                subject_name = subject_match.group(1).strip() if subject_match else "Unknown Target"
                filer_name = filer_match.group(1).strip() if filer_match else "Unknown Filer"

                if category.startswith('SC 13D'):
                    intent = "\U0001f525 <b>\u4e3b\u52d5\u8209\u724c (\u53ef\u80fd\u4ecb\u5165\u7d93\u71df)</b>"
                else:
                    intent = "\U0001f91d <b>\u88ab\u52d5\u6295\u8cc7 (\u7d14\u8ca1\u52d9\u6295\u8cc7)</b>"

                msg = (
                    "\U0001f988 <b>\u3010\u6a5f\u69cb\u5927\u9c77\u8209\u724c\u96f7\u9054\u3011</b>\n"
                    f"\U0001f3af \u7375\u7269 (\u516c\u53f8): <b>{subject_name}</b>\n"
                    f"\U0001f4bc \u7375\u4eba (\u6a5f\u69cb): <b>{filer_name}</b>\n"
                    f"\U0001f4dd \u985e\u578b: {category}\n"
                    f"{intent}\n"
                    f"\U0001f517 <a href='{link}'>\u67e5\u770b SEC \u539f\u6587</a>"
                )

                send_telegram_message(msg)
                print(f"  Sent: {subject_name} <- {filer_name}")
                found_count += 1
                time.sleep(1.5)

        if found_count >= 5:
            break

except Exception as e:
    print(f"Institutional radar error: {e}")
