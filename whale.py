# ==================== 程式碼開始 ====================
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os  # 🌟 用來去保險箱拿密碼

# 🌟 資安升級：程式現在不會把密碼寫死，而是去雲端保險箱拿！
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
MIN_WHALE_AMOUNT = 100000 

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # 👇 真正發射訊息的按鈕 (剛剛就是缺了這行)
    response = requests.get(url, params={'chat_id': CHAT_ID, 'text': message})
    
    # 🌟 除錯印表機
    print(f"📡 呼叫 Telegram 狀態碼: {response.status_code}")
    print(f"📡 Telegram 回傳訊息: {response.text}")

# 👇 系統開機廣播 (測試用，確認保險箱密碼正確)
send_telegram("✅ 報告 PM：保險箱新密碼讀取成功！大鯨魚雷達正在守護中！")

headers = {'User-Agent': 'MyFirstApp (your_email@example.com)'}
url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&owner=only&count=40&output=atom'

# 🌟 核心升級：記憶體改為「過去 5 分鐘」
now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=5)

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'xml')
entries = soup.find_all('entry')

found_count = 0

for entry in entries:
    link = entry.link['href']
    updated_str = entry.updated.text
    
    try:
        entry_time = datetime.fromisoformat(updated_str).astimezone(timezone.utc)
        if entry_time < time_limit:
            continue # 超過 5 分鐘的老文件，直接跳過！
    except:
        pass

    txt_link = link.replace('-index.htm', '.txt')
    txt_response = requests.get(txt_link, headers=headers)
    
    if txt_response.status_code == 200:
        xml_soup = BeautifulSoup(txt_response.content, 'xml')
        try:
            issuer_name = xml_soup.find('issuerName').text if xml_soup.find('issuerName') else "未知公司"
            reporter_name = xml_soup.find('rptOwnerName').text if xml_soup.find('rptOwnerName') else "未知高管"
            transactions = xml_soup.find_all('nonDerivativeTransaction')
            
            if transactions:
                msg = f"🐳 【大鯨魚警報 (5分鐘快訊)】\n🏢 公司: {issuer_name}\n👤 高管: {reporter_name}\n"
                is_whale = False 
                
                for txn in transactions:
                    acq_disp_tag = txn.find('transactionAcquiredDisposedCode')
                    acquired_disposed = acq_disp_tag.find('value').text if acq_disp_tag else "N/A"
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
                        
                    action = "🟢 買入" if acquired_disposed == 'A' else "🔴 賣出" if acquired_disposed == 'D' else "⚪ 其他"
                    
                    if total_value >= MIN_WHALE_AMOUNT:
                        is_whale = True
                        msg += f"👉 {action}: {shares:,.0f} 股\n💰 總額: ${total_value:,.0f} 美金 (約每股 ${price})\n"
                
                msg += f"🔗 來源: {link}"
                
                if is_whale:
                    send_telegram(msg)
                    found_count += 1
                    time.sleep(1.5)
        except Exception as e:
            pass 
            
    if found_count >= 3:
        break
# ==================== 程式碼結束 ====================
