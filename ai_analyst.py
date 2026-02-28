# ==================== ai_analyst.py ====================
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os
import google.generativeai as genai  # 🌟 引入 AI 大腦

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 🌟 喚醒 AI 大腦
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # 使用 Flash 模型，速度最快

def send_whale_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.get(url, params={'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'})

# 🌟 專盯 Form 8-K (重大突發事件)
headers = {'User-Agent': 'AI_Analyst (pm_agent@example.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&owner=include&count=20&output=atom'

now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=5)

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'xml')
entries = soup.find_all('entry')

for entry in entries:
    updated_str = entry.updated.text
    
    try:
        if datetime.fromisoformat(updated_str).astimezone(timezone.utc) < time_limit: continue 
    except: pass

    link = entry.link['href']
    title = entry.title.text

    # 獲取純文字版報告，我們只取前 8000 字元給 AI，節省時間並避開垃圾資訊
    txt_link = link.replace('-index.htm', '.txt')
    txt_response = requests.get(txt_link, headers=headers)
    
    if txt_response.status_code == 200:
        content = txt_response.text[:8000]
        
        # 🌟 給 AI 的「頂級分析師 Prompt (提示詞)」
        prompt = f"""
        你是一位華爾街頂級量化分析師。請閱讀以下 SEC 8-K 重大事件報告的開頭片段。
        請用 50-80 字的繁體中文，精準提煉出最重要的資訊（例如：收購、高管辭職、破產、財報發布、重大合約等）。
        最後，請根據這個事件對公司股價的潛在影響，給出一個明確的情緒判定標籤：
        【🚀 強烈看多 / 🟢 偏多 / ⚪ 中立 / 🔴 偏空 / 💀 強烈看空】。

        報告標題：{title}
        報告內容：
        {content}
        """
        
        try:
            # 呼叫 AI 進行解讀
            ai_response = model.generate_content(prompt)
            ai_summary = ai_response.text.strip()
            
            msg = f"🤖 <b>【AI 8-K 突發事件秒讀機】</b>\n"
            msg += f"📄 報告：<code>{title}</code>\n\n"
            msg += f"🧠 <b>AI 總結與判定：</b>\n{ai_summary}\n\n"
            msg += f"🔗 <a href='{link}'>查看 SEC 原始報告</a>"
            
            send_whale_telegram(msg)
            time.sleep(2)
            
        except Exception as e:
            print(f"📡 AI 解析失敗，可能是 API 額度限制或網路錯誤: {e}")
