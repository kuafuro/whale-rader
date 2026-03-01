import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os
import google.generativeai as genai
import gspread 
from google.oauth2.service_account import Credentials
import json

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

GCP_CREDENTIALS = os.environ.get('GCP_CREDENTIALS')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
worksheet = None

# 🌟 喚醒 AI 大腦
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 🌟 新增：專屬於 AI 引擎的暫存記憶體 (去重防線)
processed_links = set()
CACHE_FILE = 'processed_links_ai.txt'

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        processed_links.update(f.read().splitlines())

# 連接 Google Sheets 並抓取歷史網址
if GCP_CREDENTIALS and SPREADSHEET_ID:
    try:
        creds_dict = json.loads(GCP_CREDENTIALS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.sheet1 
        print("✅ Google Sheets 連線成功！(AI 8-K 引擎)")
        
        try:
            # 抓取第 7 欄 (G欄) 的最近 200 筆歷史網址
            sheet_links = worksheet.col_values(7)[-200:]
            processed_links.update(sheet_links)
        except Exception as e:
            print(f"⚠️ 讀取 Google Sheets 歷史紀錄失敗: {e}")
            
    except Exception as e:
        print(f"❌ Google Sheets 初始化失敗: {e}")

# 🌟 修正：全面改用 POST，避免 AI 生成的長文被 URL 截斷
def send_whale_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram 推播失敗: {e}")

# 🌟 修正：換上真實信箱，躲避 SEC 狙擊
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
        
        # 🌟 新增：如果這份 8-K 已經讀過，直接跳過
        if link in processed_links:
            continue
        
        try:
            if datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit: 
                break 
        except Exception as e:
            print(f"時間解析失敗，跳過此筆紀錄 ({updated_str}): {e}")
            continue # 🌟 修正：時間壞掉直接跳過

        # 🌟 修正：加上 SEC 速率限制保護
        time.sleep(0.15)
        
        txt_link = link.replace('-index.htm', '.txt')
        txt_response = requests.get(txt_link, headers=headers)
        
        if txt_response.status_code == 200:
            content = txt_response.text[:8000]
            
            # 🌟 修正：強化 Prompt，強迫 AI 不要使用 Telegram 討厭的 Markdown (如 **)
            prompt = f"""
            你是一位華爾街頂級量化分析師。請閱讀以下 SEC 8-K 重大事件報告的開頭片段。
            請用 50-80 字的繁體中文，精準提煉出最重要的資訊（例如：收購、高管辭職、破產、財報發布、重大合約等）。
            最後，請根據這個事件對公司股價的潛在影響，給出一個明確的情緒判定標籤：
            【🚀 強烈看多 / 🟢 偏多 / ⚪ 中立 / 🔴 偏空 / 💀 強烈看空】。
            
            注意：請直接輸出純文字，若要強調重點請使用 <b> </b> 標籤，絕對不要使用 Markdown 語法 (如 **粗體** 或 # 標題)，這會導致系統出錯。

            報告標題：{title}
            報告內容：
            {content}
            """
            
            # 🌟 新增：Gemini API 防爆頻與智慧重試機制
            ai_summary = ""
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    ai_response = model.generate_content(prompt)
                    ai_summary = ai_response.text.strip()
                    break # 成功獲取則跳出重試迴圈
                except Exception as api_e:
                    if "429" in str(api_e) or "quota" in str(api_e).lower() or "exhausted" in str(api_e).lower():
                        print(f"⚠️ Gemini API 頻率限制，等待 10 秒後重試 ({attempt+1}/{max_retries})...")
                        time.sleep(10)
                    else:
                        print(f"❌ AI 解析發生未知錯誤: {api_e}")
                        break
            
            # 如果重試 3 次還是失敗，就跳過這份報告
            if not ai_summary:
                print(f"⏭️ AI 無法處理此份 8-K ({title})，自動跳過。")
                continue
                
            msg = f"🤖 <b>【AI 8-K 突發事件秒讀機】</b>\n"
            msg += f"📄 報告：<code>{title}</code>\n\n"
            msg += f"🧠 <b>AI 總結與判定：</b>\n{ai_summary}\n\n"
            msg += f"🔗 <a href='{link}'>查看 SEC 原始報告</a>"
            
            send_whale_telegram(msg)
            
            # 🌟 新增：對齊寫入 Google Sheets 紀錄
            if worksheet:
                try:
                    time_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
                    # 格式對齊 [時間, 代碼(N/A), 公司名稱(以標題代替), 類型, AI判定, 總額(N/A), 網址(第7欄)]
                    row_data = [time_str, "N/A", title, "📑 重大突發 (8-K)", "🤖 AI 分析", "N/A", link]
                    worksheet.append_row(row_data)
                except Exception as e:
                    print(f"寫入 Google 表格失敗: {e}")

            # 🌟 新增：寫入記憶體與本地暫存檔，防重複推播
            processed_links.add(link)
            with open(CACHE_FILE, 'a') as f:
                f.write(link + '\n')
            
            # 🌟 新增：強制冷卻 AI 引擎，保護你的 Gemini API 免費額度
            time.sleep(5) 

except Exception as e:
    print(f"AI 8-K 雷達執行發生嚴重錯誤: {e}")
