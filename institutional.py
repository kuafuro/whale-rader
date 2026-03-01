import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os
import re
import gspread 
from google.oauth2.service_account import Credentials
import json

# 取得環境變數
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE') 

GCP_CREDENTIALS = os.environ.get('GCP_CREDENTIALS')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
worksheet = None

# 🌟 新增：專屬於機構雷達的暫存記憶體 (避免跟 Form 4 衝突)
processed_links = set()
CACHE_FILE = 'processed_links_institutional.txt'

# 讀取本地暫存
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        processed_links.update(f.read().splitlines())

# 🌟 新增：連接 Google Sheets 並抓取歷史網址
if GCP_CREDENTIALS and SPREADSHEET_ID:
    try:
        creds_dict = json.loads(GCP_CREDENTIALS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.sheet1 
        print("✅ Google Sheets 連線成功！(機構雷達)")
        
        try:
            # 假設網址都存在第 7 欄 (G欄)，抓取最近 200 筆即可
            sheet_links = worksheet.col_values(7)[-200:]
            processed_links.update(sheet_links)
            print(f"已載入 {len(sheet_links)} 筆歷史紀錄進行比對。")
        except Exception as e:
            print(f"⚠️ 讀取 Google Sheets 歷史紀錄失敗: {e}")
            
    except Exception as e:
        print(f"❌ Google Sheets 初始化失敗: {e}")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID_WHALE,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram 推播失敗: {e}")

# ✅ 已更新為你的專屬信箱，符合 SEC 規範
headers = {'User-Agent': 'WhaleRadarBot/2.0 (mingcheng@kuafuorhk.com)'}

url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=SC+13&owner=only&count=40&output=atom'

now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=15)

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status() # 攔截 403 等錯誤
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')

    found_count = 0

    for entry in entries:
        link = entry.link['href']
        updated_str = entry.updated.text
        
        # 🌟 新增：查水表！如果這個連結已經處理過，直接跳過 (防重複推播)
        if link in processed_links:
            continue
        
        try:
            # 解析時間
            entry_time = datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc)
            if entry_time < time_limit: 
                break # 超過15分鐘，全軍撤退
        except Exception as e:
            print(f"時間解析失敗，跳過此筆紀錄 ({updated_str}): {e}")
            continue # 解析失敗時跳過，不影響後續執行
            
        category = entry.category['term'] if entry.category else ""
        
        if category.startswith('SC 13D') or category.startswith('SC 13G'):
            txt_link = link.replace('-index.htm', '.txt')
            
            # 遵守 SEC Rate Limit (每秒不超過10次)，保護你的 IP 不被封鎖
            time.sleep(0.15) 
            
            txt_response = requests.get(txt_link, headers=headers)
            if txt_response.status_code == 200:
                txt_content = txt_response.text
                
                # 排除 \r 與 \n，精準抓取公司與機構名稱
                subject_match = re.search(r'<SUBJECT-COMPANY>.*?<CONFORMED-NAME>([^\r\n]+)', txt_content, re.DOTALL)
                filer_match = re.search(r'<FILED-BY>.*?<CONFORMED-NAME>([^\r\n]+)', txt_content, re.DOTALL)
                
                subject_name = subject_match.group(1).strip() if subject_match else "未知目標公司"
                filer_name = filer_match.group(1).strip() if filer_match else "未知投資機構"
                
                # 意圖判定
                is_active = category.startswith('SC 13D')
                intent = "🔥 <b>主動舉牌 (可能介入經營)</b>" if is_active else "🤝 <b>被動投資 (純財務投資)</b>"
                
                msg = f"🦈 <b>【機構大鱷舉牌雷達】</b>\n"
                msg += f"🎯 獵物: <b>{subject_name}</b>\n"
                msg += f"💼 獵人: <b>{filer_name}</b>\n"
                msg += f"📝 類型: {category}\n"
                msg += f"{intent}\n"
                msg += f"🔗 <a href='{link}'>查看 SEC 原文</a>"
                
                send_telegram_message(msg)
                
                # 🌟 新增：寫入 Google Sheets 紀錄
                if worksheet:
                    try:
                        time_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
                        # 格式對齊 [時間, 代碼(N/A), 公司名稱, 類型, 獵人, 總額(N/A), 網址(第7欄)]
                        row_data = [time_str, "N/A", subject_name, category, filer_name, "N/A", link]
                        worksheet.append_row(row_data)
                    except Exception as e:
                        print(f"寫入 Google 表格失敗: {e}")
                
                # 🌟 新增：成功推播後，將網址寫入記憶體與本地暫存，確保下次不再重複發送
                processed_links.add(link)
                with open(CACHE_FILE, 'a') as f:
                    f.write(link + '\n')
                
                found_count += 1
                time.sleep(1.5) # 避免 Telegram 擋下太頻繁的推播
                
        if found_count >= 5:
            break
            
except Exception as e:
    print(f"機構雷達執行發生錯誤: {e}")
