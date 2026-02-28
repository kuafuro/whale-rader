# ==================== 程式碼開始 ====================
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os  

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_TEST = os.environ.get('TELEGRAM_CHAT_ID_TEST')   
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE') 

# 🌟 PM 客製化設定區 🌟
MIN_WHALE_AMOUNT = 500000  # 門檻：50 萬美金
STRICT_WATCHLIST = True    # True = 啟動 S&P 500 過濾器！只看巨頭！

# 🤖 爬蟲小幫手：自動獲取最新 S&P 500 名單
def get_sp500_tickers():
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'id': 'constituents'})
        tickers = set() # 使用 Set 可以大幅加快比對速度 (O(1))
        
        for row in table.find_all('tr')[1:]:
            ticker = row.find_all('td')[0].text.strip()
            tickers.add(ticker)
            # 兼容 SEC 申報格式 (例如 BRK.B 可能會寫成 BRK-B 或 BRKB)
            tickers.add(ticker.replace('.', '-'))
            tickers.add(ticker.replace('.', ''))
        return tickers
    except Exception as e:
        print(f"📡 獲取 S&P 500 名單失敗: {e}")
        return set()

# 在每次啟動時，先去抓最新的 500 家名單！
SP500_TICKERS = get_sp500_tickers()

def send_test_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.get(url, params={'chat_id': CHAT_ID_TEST, 'text': message})

def send_whale_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.get(url, params={'chat_id': CHAT_ID_WHALE, 'text': message})

# 🌟 智慧打卡系統：每 3 小時回報一次
now_utc = datetime.now(timezone.utc)
if now_utc.hour % 3 == 0 and now_utc.minute < 5:
    sp_count = len(SP500_TICKERS)
    send_test_telegram(f"✅ 報告 PM：V15 全自動 S&P 500 雷達運作中！(已載入 {sp_count} 檔成分股) (UTC {now_utc.strftime('%H:%M')})")

send_test_telegram("測試啟動")

headers = {'User-Agent': 'MyFirstApp (your_email@example.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&owner=only&count=40&output=atom'

time_limit = now_utc - timedelta(minutes=5)
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'xml')
entries = soup.find_all('entry')

found_count = 0

for entry in entries:
    link = entry.link['href']
    updated_str = entry.updated.text
    
    try:
        if datetime.fromisoformat(updated_str).astimezone(timezone.utc) < time_limit: continue 
    except: pass

    txt_link = link.replace('-index.htm', '.txt')
    txt_response = requests.get(txt_link, headers=headers)
    
    if txt_response.status_code == 200:
        xml_soup = BeautifulSoup(txt_response.content, 'xml')
        try:
            issuer_name = xml_soup.find('issuerName').text if xml_soup.find('issuerName') else "未知公司"
            reporter_name = xml_soup.find('rptOwnerName').text if xml_soup.find('rptOwnerName') else "未知高管"
            
            # 🌟 取得股票代碼 (Ticker)
            ticker_tag = xml_soup.find('issuerTradingSymbol')
            ticker = ticker_tag.text if ticker_tag else "N/A"
            
            # 🌟 動態 S&P 500 過濾器攔截
            if STRICT_WATCHLIST and SP500_TICKERS and (ticker not in SP500_TICKERS):
                continue
            
            transactions = xml_soup.find_all('nonDerivativeTransaction')
            if transactions:
                msg = f"🐳 【頂級大鯨魚警報】\n🏢 {issuer_name} (${ticker})\n👤 {reporter_name}\n"
                is_whale = False 
                
                for txn in transactions:
                    # 🌟 真金白銀過濾器 (Transaction Code)
                    coding_tag = txn.find('transactionCoding')
                    tx_code = coding_tag.find('transactionCode').text if coding_tag and coding_tag.find('transactionCode') else ""
                    
                    # 只要不是 P (買入) 或 S (賣出)，直接跳過！
                    if tx_code not in ['P', 'S']: 
                        continue

                    # 🌟 10b5-1 自動計畫探測器
                    rule_10b51 = txn.find('rule10b51Transaction')
                    is_10b51 = "🤖 (10b5-1自動計畫)" if rule_10b51 and rule_10b51.text in ['1', 'true', 'True'] else "🔥 (主動決策)"

                    shares_tag = txn.find('transactionShares')
                    shares_str = shares_tag.find('value').text if shares_tag else "0"
                    price_tag = txn.find('transactionPricePerShare')
                    price_str = price_tag.find('value').text if price_tag and price_tag.find('value') else "0"
                    
                    try:
                        shares = float(shares_str)
                        price = float(price_str)
                        total_value = shares * price
                    except:
                        total_value = 0
                        
                    action = "🟢 真金買入" if tx_code == 'P' else "🔴 公開賣出"
                    
                    if total_value >= MIN_WHALE_AMOUNT:
                        is_whale = True
                        msg += f"👉 {action}: {shares:,.0f} 股 {is_10b51}\n💰 總額: ${total_value:,.0f} 美金 (@${price})\n"
                
                msg += f"🔗 來源: {link}"
                
                # 只有當至少有一筆交易符合「真金白銀」且「大於 50 萬美金」時才發送
                if is_whale:
                    send_whale_telegram(msg)
                    found_count += 1
                    time.sleep(1.5)
        except Exception as e:
            pass 
            
    if found_count >= 3:
        break
# ==================== 程式碼結束 ====================
