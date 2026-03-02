import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os
import google.generativeai as genai

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE') 
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.get(url, params={'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'})

headers = {'User-Agent': 'MyFirstApp (your_email@example.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&owner=only&count=40&output=atom'

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
            
        link = entry.link['href']
        company_name = entry.title.text.split(' - ')[0] if entry.title else "未知公司"
        
        txt_link = link.replace('-index.htm', '.txt')
        txt_response = requests.get(txt_link, headers=headers)
        
        if txt_response.status_code == 200 and GEMINI_API_KEY:
            content = txt_response.text[:15000] 
            
            prompt = f"""
            這是一份美國 SEC 8-K 財報文件的部分內容。請你扮演專業的華爾街分析師，用繁體中文，在 3 到 5 句話以內總結這份文件的重點。
            請判斷這份文件對公司股價是利多、利空還是中性，並加上對應的表情符號 (🚀 利多, 📉 利空, 😐 中性)。
            文件內容如下：
            {content}
            """
            
            try:
                ai_response = model.generate_content(prompt)
                summary = ai_response.text.strip()
                
                msg = f"🤖 <b>【AI 8-K 財報秒讀機】</b>\n"
                msg += f"🏢 公司: <b>{company_name}</b>\n"
                msg += f"📝 <b>AI 總結:</b>\n{summary}\n\n"
                msg += f"🔗 <a href='{link}'>查看 8-K 原文</a>"
                
                send_telegram_message(msg)
                
                found_count += 1
                time.sleep(2)
            except Exception as e:
                print(f"AI 解析失敗: {e}")
                
        if found_count >= 3:
            break
except Exception as e:
    print(f"AI 分析雷達發生錯誤: {e}")
