# ==================== form144.py ====================
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os  

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE') 

# 🌟 Form 144 門檻通常較高，我們設定追蹤「準備拋售超過 100 萬美金」的大案子
MIN_PROPOSED_SALE = 1000000  

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
    requests.get(url, params={'chat_id': CHAT_ID_WHALE, 'text': message})

# 🌟 專屬 Form 144 的 SEC 網址 (type=144)
headers = {'User-Agent': 'Form144Radar (pm_agent@example.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=144&owner=include&count=40&output=atom'

now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=5)

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'xml')
entries = soup.find_all('entry')

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
            # Form 144 的標籤結構與 Form 4 不同
            issuer_name_tag = xml_soup.find('issuerName')
            issuer_name = issuer_name_tag.text if issuer_name_tag else "未知公司"
            
            # 準備賣股票的人
            seller_tag = xml_soup.find('nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold')
            seller_name = seller_tag.text if seller_tag else "未知高管/大股東"
            
            ticker_tag = xml_soup.find('issuerTradingSymbol') # 有些 144 不一定有這個標籤
            ticker = ticker_tag.text if ticker_tag else "N/A"
            
            if SP500_TICKERS and ticker != "N/A" and (ticker not in SP500_TICKERS):
                continue
                
            # 預計拋售的總金額 (Aggregate Market Value)
            market_value_tag = xml_soup.find('aggregateMarketValue')
            market_value_str = market_value_tag.text if market_value_tag else "0"
            
            try:
                market_value = float(market_value_str)
            except:
                market_value = 0
                
            if market_value >= MIN_PROPOSED_SALE:
                msg = f"🚨 【水晶球預警：Form 144 準備拋售！】\n"
                msg += f"🏢 公司: {issuer_name} (${ticker})\n"
                msg += f"👤 拋售方: {seller_name}\n"
                msg += f"💀 預計倒貨規模: ${market_value:,.0f} 美金\n"
                msg += f"⚠️ (注意：此為拋售意向，股票可能即將流入市場)\n"
                msg += f"🔗 來源: {link}"
                
                send_whale_telegram(msg)
                time.sleep(1.5)
                
        except Exception as e:
            pass
