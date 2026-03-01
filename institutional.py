# ==================== institutional.py ====================
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os  
import re # 🌟 引入正則表達式，用來破解複雜的機構申報文件

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE') 

def send_whale_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # 這裡我們加上 parse_mode='HTML' 讓排版更漂亮
    requests.get(url, params={'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'})

# 🌟 專屬機構大戶的 SEC 即時雷達 (掃描全市場)
headers = {'User-Agent': 'InstRadar (pm_agent@example.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&owner=include&count=100&output=atom'

now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=15)

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'xml')
entries = soup.find_all('entry')

for entry in entries:
    updated_str = entry.updated.text
    
    try:
        if datetime.fromisoformat(updated_str).astimezone(timezone.utc) < time_limit: continue 
    except: pass

    # 取得文件類型
    category = entry.category['term'] if entry.category else ""
    
    # 🎯 我們只鎖定 SC 13D (主動) 與 SC 13G (被動) 及其修正案 (/A)
    if category.startswith('SC 13D') or category.startswith('SC 13G'):
        link = entry.link['href']
        txt_link = link.replace('-index.htm', '.txt')
        
        txt_response = requests.get(txt_link, headers=headers)
        if txt_response.status_code == 200:
            txt_content = txt_response.text
            
            # 🌟 使用 Regex 從純文字中挖出「被買的公司」與「出手的大鱷」
            subject_match = re.search(r'<SUBJECT-COMPANY>.*?<CONFORMED-NAME>([^\n]+)', txt_content, re.DOTALL)
            filer_match = re.search(r'<FILED-BY>.*?<CONFORMED-NAME>([^\n]+)', txt_content, re.DOTALL)
            
            subject_name = subject_match.group(1).strip() if subject_match else "未知目標公司"
            filer_name = filer_match.group(1).strip() if filer_match else "未知投資機構"
            
            # 🌟 意圖判定
            is_active = "13D" in category
            action_type = "🎯 <b>主動介入</b> (意圖影響公司決策，逼宮/併購前兆！)" if is_active else "🤝 <b>被動建倉</b> (純粹的長線大資金入駐)"
            alert_icon = "🦈" if is_active else "🏦"
            
            msg = f"{alert_icon} <b>【機構大鱷 5% 舉牌警報】</b>\n"
            msg += f"📄 文件: <code>{category}</code>\n"
            msg += f"🏢 獵物: <b>{subject_name}</b>\n"
            msg += f"💼 獵人: <b>{filer_name}</b>\n"
            msg += f"狀態: {action_type}\n"
            msg += f"⚠️ <i>注意：該機構持股已正式突破 5% 法定門檻！</i>\n"
            msg += f"🔗 <a href='{link}'>查看 SEC 原始報告</a>"
            
            send_whale_telegram(msg)
            time.sleep(1.5)
