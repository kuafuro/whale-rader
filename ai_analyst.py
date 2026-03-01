import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os
import google.generativeai as genai
import gspread 
from google.oauth2.service_account import Credentials
import json
import html # 🌟 防止 HTML 解析報錯

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

GCP_CREDENTIALS = os.environ.get('GCP_CREDENTIALS')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
worksheet = None

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

processed_links = set()
CACHE_FILE = 'processed_links_ai.txt'

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
        except Exception as e:
            pass
    except Exception as e:
        pass

def send_whale_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        pass

headers = {'User-Agent': 'WhaleRadarBot/2.0 (mingcheng@kuafuorhk.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&owner=include&count=20&output=atom'

now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=15)

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')

    for entry in entries:
        link = entry.link['href']
        title = entry.title.text
        updated_str = entry.updated.text
        
        if link in processed_links:
            continue
        
        try:
            if datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit: 
                break 
        except Exception as e:
            continue 

        time.sleep(0.15)
        
        txt_link = link.replace('-index.htm', '.txt')
        txt_response = requests.get(txt_link, headers=headers)
        
        if txt_response.status_code == 200:
            content = txt_response.text[:8000]
            
            prompt = f"""
            你是一位華爾街頂級量化分析師。請閱讀以下 SEC 8-K 重大事件報告的開頭片段。
            請用 50-80 字的繁體中文，精準提煉出最重要的資訊。
            最後，請根據這個事件對公司股價的潛在影響，給出一個明確的情緒判定標籤：
            【🚀 強烈看多 / 🟢 偏多 / ⚪ 中立 / 🔴 偏空 / 💀 強烈看空】。
            
            注意：請直接輸出純文字，若要強調重點請使用 <b> </b> 標籤，絕對不要使用 Markdown 語法。

            報告標題：{title}
            報告內容：
            {content}
            """
            
            ai_summary = ""
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    ai_response = model.generate_content(prompt)
                    ai_summary = ai_response.text.strip()
                    break 
                except Exception as api_e:
                    if "429" in str(api_e) or "quota" in str(api_e).lower() or "exhausted" in str(api_e).lower():
                        time.sleep(10)
                    else:
                        break
            
            if not ai_summary:
                continue
                
            # 🌟 清洗特殊符號
            title_escaped = html.escape(title)
            ai_summary_escaped = html.escape(ai_summary)
            
            msg = f"🤖 <b>【AI 8-K 突發事件秒讀機】</b>\n"
            msg += f"📄 報告：<code>{title_escaped}</code>\n\n"
            msg += f"🧠 <b>AI 總結與判定：</b>\n{ai_summary_escaped}\n\n"
            msg += f"🔗 <a href='{link}'>查看 SEC 原始報告</a>"
            
            send_whale_telegram(msg)
            
            if worksheet:
                try:
                    time_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
                    row_data = [time_str, "N/A", title, "📑 重大突發 (8-K)", "🤖 AI 分析", "N/A", link]
                    worksheet.append_row(row_data)
                except Exception as e:
                    pass

            processed_links.add(link)
            with open(CACHE_FILE, 'a') as f:
                f.write(link + '\n')
            
            time.sleep(5) 

except Exception as e:
    print(f"AI 8-K 雷達發生錯誤: {e}")
