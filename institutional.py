import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os
import re
import gspread 
from google.oauth2.service_account import Credentials
import json
import html

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE') 

GCP_CREDENTIALS = os.environ.get('GCP_CREDENTIALS')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
worksheet = None

processed_links = set()
CACHE_FILE = 'processed_links_institutional.txt'

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        processed_links.update(f.read().splitlines())

if GCP_CREDENTIALS and SPREADSHEET_ID:
    try:
        creds_dict = json.loads(GCP_CREDENTIALS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.sheet1 
        try:
            sheet_links = worksheet.col_values(7)[-200:]
            processed_links.update(sheet_links)
        except Exception:
            pass
    except Exception:
        pass

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception:
        pass

headers = {'User-Agent': 'WhaleRadarBot/2.0 (mingcheng@kuafuorhk.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=SC+13&owner=only&count=40&output=atom'

now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=15)

try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status() 
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')

    found_count = 0

    for entry in entries:
        link = entry.link['href']
        updated_str = entry.updated.text
        
        if link in processed_links:
            continue
        
        try:
            entry_time = datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc)
            if entry_time < time_limit: 
                break 
        except Exception:
            continue 
            
        category = entry.category['term'] if entry.category else ""
        
        if category.startswith('SC 13D') or category.startswith('SC 13G'):
            txt_link = link.replace('-index.htm', '.txt')
            time.sleep(0.15) 
            
            try:
                txt_response = requests.get(txt_link, headers=headers, timeout=10)
            except:
                continue
                
            if txt_response.status_code == 200:
                txt_content = txt_response.text
                
                subject_match = re.search(r'<SUBJECT-COMPANY>.*?<CONFORMED-NAME>([^\r\n]+)', txt_content, re.DOTALL)
                filer_match = re.search(r'<FILED-BY>.*?<CONFORMED-NAME>([^\r\n]+)', txt_content, re.DOTALL)
                
                subject_name = subject_match.group(1).strip() if subject_match else "未知目標公司"
                filer_name = filer_match.group(1).strip() if filer_match else "未知投資機構"
                
                subject_name = html.escape(subject_name)
                filer_name = html.escape(filer_name)
                
                is_active = category.startswith('SC 13D')
                intent = "🔥 <b>主動舉牌 (可能介入經營)</b>" if is_active else "🤝 <b>被動投資 (純財務投資)</b>"
                
                msg = f"🦈 <b>【機構大鱷舉牌雷達】</b>\n"
                msg += f"🎯 獵物: <b>{subject_name}</b>\n"
                msg += f"💼 獵人: <b>{filer_name}</b>\n"
                msg += f"📝 類型: {category}\n"
                msg += f"{intent}\n"
                msg += f"🔗 <a href='{link}'>查看 SEC 原文</a>"
                
                send_telegram_message(msg)
                
                if worksheet:
                    try:
                        time_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
                        row_data = [time_str, "N/A", subject_name, category, filer_name, "N/A", link]
                        worksheet.append_row(row_data)
                    except Exception:
                        pass
                
                processed_links.add(link)
                with open(CACHE_FILE, 'a') as f:
                    f.write(link + '\n')
                
                found_count += 1
                time.sleep(1.5) 
                
        if found_count >= 5:
            break
            
except Exception as e:
    print(f"機構雷達執行發生錯誤: {e}")
