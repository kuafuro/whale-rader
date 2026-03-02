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
    requests.get(url, params={'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'})

headers = {'User-Agent': 'MyFirstApp (your_email@example.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=SC+13&owner=only&count=40&output=atom'

now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=15)

try:
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')

    found_count = 0

    for entry in entries:
        updated_str = entry.updated.text
        
        try:
            if datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit: 
                break
        except Exception as e:
            pass
            
        category = entry.category['term'] if entry.category else ""
        
        if category.startswith('SC 13D') or category.startswith('SC 13G'):
            link = entry.link['href']
            txt_link = link.replace('-index.htm', '.txt')
            
            txt_response = requests.get(txt_link, headers=headers)
            if txt_response.status_code == 200:
                txt_content = txt_response.text
                
                subject_match = re.search(r'<SUBJECT-COMPANY>.*?<CONFORMED-NAME>([^\n]+)', txt_content, re.DOTALL)
                filer_match = re.search(r'<FILED-BY>.*?<CONFORMED-NAME>([^\n]+)', txt_content, re.DOTALL)
                
                subject_name = subject_match.group(1).strip() if subject_match else "未知目標公司"
                filer_name = filer_match.group(1).strip() if filer_match else "未知投資機構"
                
                intent = "🔥 <b>主動舉牌 (可能介入經營)</b>" if category.startswith('SC 13D') else "🤝 <b>被動投資 (純財務投資)</b>"
                
                msg = f"🦈 <b>【機構大鱷舉牌雷達】</b>\n"
                msg += f"🎯 獵物 (公司): <b>{subject_name}</b>\n"
                msg += f"💼 獵人 (機構): <b>{filer_name}</b>\n"
                msg += f"📝 類型: {category}\n"
                msg += f"{intent}\n"
                msg += f"🔗 <a href='{link}'>查看 SEC 原文</a>"
                
                send_telegram_message(msg)
                
                found_count += 1
                time.sleep(1.5)
                
        if found_count >= 5:
            break
            
except Exception as e:
    print(f"機構雷達執行發生錯誤: {e}")
