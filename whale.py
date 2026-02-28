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
