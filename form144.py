import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os  
import gspread 
from google.oauth2.service_account import Credentials
import json
import html # 🌟 防止 HTML 解析報錯

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE') 

GCP_CREDENTIALS = os.environ.get('GCP_CREDENTIALS')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
worksheet = None

MIN_PROPOSED_SALE = 1000000  
STRICT_WATCHLIST = True 

processed_links = set()
CACHE_FILE = 'processed_links_form144.txt'

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

def get_sp500_tickers():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        tickers = set()
        for row in soup.find('table', {'id': 'constituents'}).find_all('tr')[1:]:
            ticker = row.find_all('td')[0].text.strip()
            tickers.add(ticker); tickers.add(ticker.replace('.', '-'))
        return tickers
    except:
        return set()

SP500_TICKERS = get_sp500_tickers()

def send_whale_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        pass

headers = {'User-Agent': 'Form144RadarBot/2.0 (mingcheng@kuafuorhk.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=144&owner=include&count=40&output=atom'

now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=15)

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')

    for entry in entries:
        link = entry.link['href']
        updated_str = entry.updated.text
        
        if link in processed_links:
            continue
        
        try:
            if datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit: 
                break 
        except Exception as e:
            continue

        txt_link = link.replace('-index.htm', '.txt')
        time.sleep(0.15)
        
        txt_response = requests.get(txt_link, headers=headers)
        
        if txt_response.status_code == 200:
            xml_soup = BeautifulSoup(txt_response.content, 'xml')
            try:
                issuer_name_tag = xml_soup.find('issuerName')
                issuer_name = issuer_name_tag.text if issuer_name_tag else "未知公司"
                
                seller_tag = xml_soup.find('nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold')
                seller_name = seller_tag.text if seller_tag else "未知高管/大股東"
                
                # 🌟 清洗特殊符號
                issuer_name = html.escape(issuer_name)
                seller_name = html.escape(seller_name)
                
                ticker_tag = xml_soup.find('issuerTradingSymbol')
                ticker = ticker_tag.text if ticker_tag else "N/A"
                
                if STRICT_WATCHLIST:
                    if not SP500_TICKERS or (ticker not in SP500_TICKERS):
                        continue
                        
                market_value_tag = xml_soup.find('aggregateMarketValue')
                market_value_str = market_value_tag.text if market_value_tag else "0"
                
                try:
                    market_value = float(market_value_str)
                except:
                    market_value = 0
                    
                if market_value >= MIN_PROPOSED_SALE:
                    msg = f"🚨 <b>【水晶球預警：Form 144 準備拋售！】</b>\n"
                    msg += f"🏢 公司: <b>{issuer_name}</b> (${ticker})\n"
                    msg += f"👤 拋售方: <b>{seller_name}</b>\n"
                    msg += f"💀 預計倒貨規模: <b>${market_value:,.0f}</b> 美金\n"
                    msg += f"⚠️ <i>(注意：此為拋售意向，股票可能即將流入市場)</i>\n"
                    msg += f"🔗 <a href='{link}'>查看 SEC 原文</a>"
                    
                    send_whale_telegram(msg)
                    
                    if worksheet:
                        try:
                            time_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
                            row_data = [time_str, ticker, issuer_name, "🔴 準備拋售 (Form 144)", seller_name, market_value, link]
                            worksheet.append_row(row_data)
                        except Exception as e:
                            pass

                    processed_links.add(link)
                    with open(CACHE_FILE, 'a') as f:
                        f.write(link + '\n')

                    time.sleep(1.5)
                    
            except Exception as e:
                pass

except Exception as e:
    print(f"Form 144 雷達發生錯誤: {e}")
