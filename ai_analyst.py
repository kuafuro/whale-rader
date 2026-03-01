import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os
import google.generativeai as genai
from supabase import create_client, Client
import html

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 🌟 初始化 Supabase
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
supabase: Client = None

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

processed_links = set()
CACHE_FILE = 'processed_links_ai.txt'

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        processed_links.update(f.read().splitlines())

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = supabase.table('whale_alerts').select('link').order('created_at', desc=True).limit(500).execute()
        db_links = [row['link'] for row in response.data]
        processed_links.update(db_links)
    except Exception:
        pass

def send_whale_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception:
        pass

headers = {'User-Agent': 'WhaleRadarBot/2.0 (mingcheng@kuafuorhk.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&owner=include&count=20&output=atom'

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
        title = entry.title.text
        updated_str = entry.updated.text
        
        if link in processed_links:
            continue
        
        try:
            if datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit: 
                break 
        except Exception:
            continue 

        time.sleep(0.15)
        
        txt_link = link.replace('-index.htm', '.txt')
        
        try:
            txt_response = requests.get(txt_link, headers=headers, timeout=10)
        except:
            continue
            
        if txt_response.status_code == 200:
            content = txt_response.text[:8000]
            
            prompt = f"""
            你是一位華爾街頂級量化分析師。請閱讀以下 SEC 8-K 重大事件報告的開頭片段。
            請用 50-80 字的繁體中文，精準提煉出最重要的資訊。
            最後，請根據這個事件對公司股價的潛在影響，給出一個明確的情緒判定標籤：
            【🚀 強烈看多 / 🟢 偏多 / ⚪ 中立 / 🔴 偏空 / 💀 強烈看空】。
            
            注意：請直接輸出純文字，絕對不要使用任何 Markdown 語法或 HTML 標籤（如 **粗體** 或 <b> 標籤），這會導致系統崩潰。
            """ 
            
            ai_summary = ""
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    ai_response = model.generate_content(prompt + f"\n報告標題：{title}\n報告內容：\n{content}")
                    ai_summary = ai_response.text.strip()
                    break 
                except Exception as api_e:
                    if "429" in str(api_e) or "quota" in str(api_e).lower() or "exhausted" in str(api_e).lower():
                        time.sleep(10)
                    else:
                        break
            
            if not ai_summary:
                continue
                
            title_escaped = html.escape(title)
            ai_summary_escaped = html.escape(ai_summary)
            
            msg = f"🤖 <b>【AI 8-K 突發事件秒讀機】</b>\n"
            msg += f"📄 報告：<code>{title_escaped}</code>\n\n"
            msg += f"🧠 <b>AI 總結與判定：</b>\n{ai_summary_escaped}\n\n"
            msg += f"🔗 <a href='{link}'>查看 SEC 原始報告</a>"
            
            send_whale_telegram(msg)
            
            # 🌟 寫入 Supabase 資料庫 (金額傳入 None)
            if supabase:
                try:
                    supabase.table('whale_alerts').insert({
                        "ticker": "N/A",
                        "company_name": title,
                        "alert_type": "📑 重大突發 (8-K)",
                        "actor": "🤖 AI 分析",
                        "amount": None, 
                        "link": link
                    }).execute()
                except Exception:
                    pass

            processed_links.add(link)
            with open(CACHE_FILE, 'a') as f:
                f.write(link + '\n')
            
            found_count += 1
            time.sleep(5) 
            
        if found_count >= 3: 
            break

except Exception as e:
    print(f"AI 8-K 雷達發生錯誤: {e}")
