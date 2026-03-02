import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os
import re
import gspread 
from google.oauth2.service_account import Credentials
import json

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE') 
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY')
GCP_CREDENTIALS = os.environ.get('GCP_CREDENTIALS')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')

# 🌟 1. 初始化 Google Sheets 資料庫連線
worksheet = None
seen_links = set()

if GCP_CREDENTIALS and SPREADSHEET_ID:
    try:
        creds_dict = json.loads(GCP_CREDENTIALS)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.sheet1 
        
        all_links = worksheet.col_values(7)
        seen_links = set(all_links[-200:])
        print("✅ DB連線成功，已武裝防重複過濾網！")
    except Exception as e:
        print(f"❌ DB初始化失敗: {e}")

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.get(url, params={'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'})

SEC_HEADERS = {'User-Agent': 'WhaleRadarBot Admin@kuafuorhk.com'}

def get_sec_ticker_map():
    try:
        resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS)
        data = resp.json()
        return {str(v['cik_str']): v['ticker'] for v in data.values()}
    except Exception as e:
        return {}

CIK_TICKER_MAP = get_sec_ticker_map()
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=144&owner=only&count=40&output=atom'

now_utc = datetime.now(timezone.utc)
# 🌟 2. 雷達波段拉到 30 分鐘，絕對不漏接！
time_limit = now_utc - timedelta(minutes=30)

try:
    response = requests.get(url, headers=SEC_HEADERS)
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')

    found_count = 0

    for entry in entries:
        updated_tag = entry.find('updated')
        if not updated_tag: continue
        updated_str = updated_tag.text
        
        try:
            if datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit: 
                break
        except Exception:
            continue
            
        link = entry.link['href']
        
        # 🌟 3. 資料庫防重複攔截！
        if link in seen_links:
            continue
            
        txt_link = link.replace('-index.htm', '.txt')
        txt_response = requests.get(txt_link, headers=SEC_HEADERS)
        
        if txt_response.status_code == 200:
            txt_content = txt_response.text
            ticker = "N/A"
            issuer_name = "未知公司"
            
            sym_match = re.search(r'<(?:issuerSymbol|issuerTradingSymbol)>([^<]+)</(?:issuerSymbol|issuerTradingSymbol)>', txt_content, re.IGNORECASE)
            if sym_match: ticker = sym_match.group(1).strip().upper()
            
            name_match = re.search(r'<(?:nameOfIssuer|issuerName)>([^<]+)</(?:nameOfIssuer|issuerName)>', txt_content, re.IGNORECASE)
            if name_match: issuer_name = name_match.group(1).strip()
            
            if ticker == "N/A" or issuer_name == "未知公司":
                sgml_block = re.search(r'(?:SUBJECT COMPANY|ISSUER):(.*?)(?:FILED BY:|REPORTING-OWNER:|<SEC-DOCUMENT>|</SEC-HEADER>)', txt_content, re.DOTALL | re.IGNORECASE)
                if sgml_block:
                    block = sgml_block.group(1)
                    if issuer_name == "未知公司":
                        c_name = re.search(r'COMPANY CONFORMED NAME:\s*([^\n\r]+)', block)
                        if c_name: issuer_name = c_name.group(1).
