import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os  
import yfinance as yf
import mplfinance as mpf
import pandas as pd
import gspread 
from google.oauth2.service_account import Credentials
import json

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_TEST = os.environ.get('TELEGRAM_CHAT_ID_TEST')   
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE') 

MIN_WHALE_AMOUNT = 500000  
STRICT_WATCHLIST = True    

GCP_CREDENTIALS = os.environ.get('GCP_CREDENTIALS')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
worksheet = None

# 🌟 新增：用來存放已處理過連結的記憶體
processed_links = set()
CACHE_FILE = 'processed_links.txt'

# 如果本地有暫存檔，先讀取進來 (適合本地測試或後續搭配 Cache 使用)
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
        print("✅ Google Sheets 連線成功！")
        
        # 🌟 新增：從 Google Sheets 抓取歷史記錄來去重
        # 假設連結存在第 7 欄 (G欄)，抓取最近的 200 筆資料比對即可，避免消耗太多 API 額度
        try:
            sheet_links = worksheet.col_values(7)[-200:]
            processed_links.update(sheet_links)
            print(f"已載入 {len(sheet_links)} 筆歷史紀錄進行比對。")
        except Exception as e:
            print(f"⚠️ 讀取 Google Sheets 歷史紀錄失敗: {e}")
            
    except Exception as e:
        print(f"❌ Google Sheets 初始化失敗: {e}")

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

def send_test_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={'chat_id': CHAT_ID_TEST, 'text': message})

def send_telegram_photo(caption, photo_path):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(photo_path, 'rb') as photo:
        payload = {'chat_id': CHAT_ID_WHALE, 'caption': caption, 'parse_mode': 'HTML'}
        requests.post(url, data=payload, files={'photo': photo})
        
def send_whale_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID_WHALE, 'text': message, 'parse_mode': 'HTML'}
    requests.post(url, data=payload)

now_utc = datetime.now(timezone.utc)
if now_utc.hour % 3 == 0 and now_utc.minute <= 12:
    send_test_telegram(f"✅ 報告將軍：V20 終極防禦雷達運作中！(UTC {now_utc.strftime('%H:%M')})")

headers = {'User-Agent': 'WhaleRadarBot/2.0 (mingcheng@kuafuorhk.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&owner=only&count=40&output=atom'

time_limit = now_utc - timedelta(minutes=15)

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')

    found_count = 0

    for entry in entries:
        link = entry.link['href']
        updated_str = entry.updated.text
        
        # 🌟 新增：查水表！如果這個連結已經處理過，直接跳過
        if link in processed_links:
            continue
        
        try:
            if datetime.fromisoformat(updated_str.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit: 
                break 
        except Exception as e:
            print(f"時間解析失敗，跳過此筆 ({updated_str}): {e}")
            continue 

        txt_link = link.replace('-index.htm', '.txt')
        
        time.sleep(0.15) # SEC Rate Limit
        
        txt_response = requests.get(txt_link, headers=headers)
        
        if txt_response.status_code == 200:
            xml_soup = BeautifulSoup(txt_response.content, 'xml')
            try:
                issuer_name = xml_soup.find('issuerName').text if xml_soup.find('issuerName') else "未知公司"
                reporter_name = xml_soup.find('rptOwnerName').text if xml_soup.find('rptOwnerName') else "未知高管"
                
                ticker_tag = xml_soup.find('issuerTradingSymbol')
                ticker = ticker_tag.text if ticker_tag else "N/A"
                
                if STRICT_WATCHLIST:
                    if not SP500_TICKERS or (ticker not in SP500_TICKERS):
                        continue
                
                transactions = xml_soup.find_all('nonDerivativeTransaction')
                if transactions:
                    msg = f"🐳 <b>【頂級大鯨魚警報】</b>\n🏢 {issuer_name} (${ticker})\n👤 {reporter_name}\n"
                    is_whale = False 
                    target_price = 0 
                    total_whale_value = 0 
                    
                    for txn in transactions:
                        coding_tag = txn.find('transactionCoding')
                        tx_code = coding_tag.find('transactionCode').text if coding_tag and coding_tag.find('transactionCode') else ""
                        
                        if tx_code not in ['P', 'S']: continue

                        shares_tag = txn.find('transactionShares')
                        shares_str = shares_tag.find('value').text if shares_tag else "0"
                        price_tag = txn.find('transactionPricePerShare')
                        price_str = price_tag.find('value').text if price_tag and price_tag.find('value') else "0"
                        
                        post_shares_tag = txn.find('sharesOwnedFollowingTransaction')
                        post_shares_str = post_shares_tag.find('value').text if post_shares_tag and post_shares_tag.find('value') else "-1"
                        
                        try:
                            shares = float(shares_str)
                            price = float(price_str)
                            post_shares = float(post_shares_str)
                            total_value = shares * price
                            target_price = price 
                        except:
                            total_value = 0
                            post_shares = -1
                            
                        action = "🟢 買入" if tx_code == 'P' else "🔴 賣出"
                        
                        intent_label = ""
                        if tx_code == 'P' and shares == post_shares and shares > 0:
                            intent_label = "\n🚀 【強烈看多：首次新建倉！】"
                        elif tx_code == 'S' and post_shares == 0:
                            intent_label = "\n💀 【強烈看空：已清倉跳船！】"
                        
                        if total_value >= MIN_WHALE_AMOUNT:
                            is_whale = True
                            total_whale_value += total_value
                            msg += f"👉 {action}: {shares:,.0f} 股\n💰 總額: ${total_value:,.0f} (@${price}){intent_label}\n"
                            
                            if worksheet:
                                try:
                                    time_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
                                    row_data = [time_str, ticker, issuer_name, action, shares, total_value, link]
                                    worksheet.append_row(row_data)
                                except Exception as e:
                                    print(f"寫入 Google 表格失敗: {e}")
                    
                    msg += f"🔗 <a href='{link}'>查看 SEC 來源</a>"
                    
                    if is_whale:
                        # 🌟 新增：只要確立是大鯨魚，就把連結寫入本地與記憶體，避免下次迴圈重複報警
                        processed_links.add(link)
                        with open(CACHE_FILE, 'a') as f:
                            f.write(link + '\n')

                        filename = f"{ticker}_chart_{int(time.time())}.png" 
                        try:
                            end_date = datetime.now()
                            start_date = end_date - timedelta(days=180)
                            df = yf.download(ticker, start=start_date, end=end_date, progress=False)
                            
                            if isinstance(df.columns, pd.MultiIndex):
                                df.columns = df.columns.droplevel(1)
                            
                            if not df.empty:
                                mpf.plot(df, type='candle', style='charles', 
                                         title=f"{ticker} 6-Month K-Line (Whale Price: ${target_price})", 
                                         hlines=dict(hlines=[target_price], colors=['r'], linestyle='--'),
                                         savefig=filename)
                                
                                send_telegram_photo(msg, filename)
                            else:
                                send_whale_telegram(msg)
                        except Exception as e:
                            print(f"畫圖或推播失敗: {e}")
                            send_whale_telegram(msg) 
                        finally:
                            if os.path.exists(filename):
                                os.remove(filename)
                            
                        found_count += 1
                        time.sleep(1.5)
            except Exception as e:
                print(f"解析此份申報內部資料時發生錯誤: {e}")
                
        if found_count >= 3:
            break

except Exception as e:
    print(f"Form 4 雷達執行發生嚴重錯誤: {e}")
