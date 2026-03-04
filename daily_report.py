# ==================== daily_report.py V2 ====================
# Engine 5: Daily Portfolio Report (Private Channel)
# eToro API (live positions) + Supabase fallback + Finnhub + Gemini AI
# Schedule: HKT 07:00 (post-close) + HKT 21:00 (pre-open)
# =============================================================
import requests
from datetime import datetime, timezone, timedelta
import os, json, uuid, time
from google import genai
from google.genai import types

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_PRIVATE = os.environ.get('TELEGRAM_CHAT_ID_PRIVATE')
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
ETORO_USER_KEY = os.environ.get('ETORO_USER_KEY')
ETORO_API_KEY = os.environ.get('ETORO_API_KEY', '')

ETORO_BASE = "https://public-api.etoro.com/api/v1"

gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ===== eToro API =====
def etoro_headers():
    return {
        "x-request-id": str(uuid.uuid4()),
        "x-api-key": ETORO_API_KEY,
        "x-user-key": ETORO_USER_KEY,
        "Content-Type": "application/json"
    }

def etoro_get_positions():
    if not ETORO_USER_KEY:
        print("No ETORO_USER_KEY set")
        return None
    endpoints = [
        f"{ETORO_BASE}/trading/real/open-positions",
        f"{ETORO_BASE}/trading/positions",
        f"{ETORO_BASE}/trading/real/positions",
    ]
    for ep in endpoints:
        try:
            print(f"  Trying eToro: {ep}")
            r = requests.get(ep, headers=etoro_headers(), timeout=15)
            print(f"  Response: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"  eToro API success: {json.dumps(data)[:500]}")
                return data
            else:
                print(f"  {r.status_code}: {r.text[:300]}")
        except Exception as e:
            print(f"  eToro error: {e}")
    return None

# ===== Supabase fallback =====
def get_supabase_holdings():
    if not SUPABASE_URL or not SUPABASE_KEY: return []
    try:
        h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        r = requests.get(f"{SUPABASE_URL}/rest/v1/portfolio_holdings?active=eq.true&order=ticker", headers=h)
        if r.status_code == 200: return r.json()
    except Exception as e:
        print(f"Supabase error: {e}")
    return []

# ===== Finnhub =====
def get_quote(ticker):
    if not FINNHUB_API_KEY: return {}
    try:
        r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_API_KEY}")
        if r.status_code == 200: return r.json()
    except: pass
    return {}

def get_profile(ticker):
    if not FINNHUB_API_KEY: return {}
    try:
        r = requests.get(f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={FINNHUB_API_KEY}")
        if r.status_code == 200: return r.json()
    except: pass
    return {}

# ===== Telegram =====
def send_private(msg):
    if not CHAT_ID_PRIVATE:
        print("No CHAT_ID_PRIVATE set, printing:")
        print(msg)
        return
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        params={'chat_id': CHAT_ID_PRIVATE, 'text': msg, 'parse_mode': 'HTML'})
    if r.status_code != 200:
        print(f"Telegram error: {r.status_code} {r.text[:200]}")

# ===== Main =====
now_utc = datetime.now(timezone.utc)
hkt = now_utc + timedelta(hours=8)
weekday = hkt.weekday()

if weekday >= 5:
    print(f"Weekend (HKT {hkt.strftime('%A')}), skipping")
    exit()

report_type = "morning" if hkt.hour < 12 else "premarket"
report_label = "\U0001f305 收盤報告" if report_type == "morning" else "\U0001f315 盤前報告"
print(f"Report type: {report_type} (HKT {hkt.strftime('%H:%M')})")

# ===== Get Holdings =====
data_source = "supabase"
positions = {}

# Try eToro API first
etoro_data = etoro_get_positions()
if etoro_data:
    etoro_list = etoro_data if isinstance(etoro_data, list) else etoro_data.get('positions', etoro_data.get('Positions', []))
    if etoro_list:
        data_source = "etoro"
        print(f"eToro API: {len(etoro_list)} positions")
        for pos in etoro_list:
            ticker = pos.get('symbol', pos.get('Symbol', pos.get('ticker', '')))
            shares = float(pos.get('Amount', pos.get('amount', pos.get('Units', pos.get('units', 0)))))
            open_price = float(pos.get('OpenRate', pos.get('openRate', pos.get('OpenPrice', 0))))
            pnl = float(pos.get('NetProfit', pos.get('netProfit', 0)))
            if not ticker: continue
            if ticker in positions:
                positions[ticker]["shares"] += shares
                positions[ticker]["total_cost"] += shares * open_price
            else:
                positions[ticker] = {"ticker": ticker, "shares": shares, "total_cost": shares * open_price, "open_date": "eToro"}

# Fallback
if not positions:
    print("Falling back to Supabase")
    data_source = "supabase"
    for h in get_supabase_holdings():
        t = h['ticker']
        shares = float(h['shares'])
        cost = float(h['open_price']) * shares
        if t not in positions:
            positions[t] = {"ticker": t, "shares": 0, "total_cost": 0, "open_date": h['open_date']}
        positions[t]["shares"] += shares
        positions[t]["total_cost"] += cost

if not positions:
    send_private("\u26a0\ufe0f 無法取得持倉資料。請檢查 eToro API Key 或 Supabase。")
    exit()

# ===== Fetch Prices =====
portfolio_data = []
total_value = total_cost = total_day_pnl = 0

for t, pos in positions.items():
    quote = get_quote(t)
    profile = get_profile(t)
    time.sleep(0.3)

    price = quote.get('c', 0)
    prev_close = quote.get('pc', 0)
    day_change_pct = quote.get('dp', 0)
    sector = profile.get('finnhubIndustry', 'N/A')

    current_val = pos["shares"] * price
    avg_cost = pos["total_cost"] / pos["shares"] if pos["shares"] > 0 else 0
    pnl = current_val - pos["total_cost"]
    pnl_pct = (pnl / pos["total_cost"] * 100) if pos["total_cost"] > 0 else 0
    day_pnl = pos["shares"] * (price - prev_close) if prev_close > 0 else 0

    total_value += current_val
    total_cost += pos["total_cost"]
    total_day_pnl += day_pnl

    portfolio_data.append({
        "ticker": t, "shares": pos["shares"], "price": price,
        "avg_cost": avg_cost, "current_val": current_val,
        "pnl": pnl, "pnl_pct": pnl_pct,
        "day_change_pct": day_change_pct, "day_pnl": day_pnl,
        "sector": sector
    })

if not portfolio_data:
    print("No valid data")
    exit()

portfolio_data.sort(key=lambda x: x['day_change_pct'], reverse=True)
total_pnl = total_value - total_cost
total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
day_pnl_pct = (total_day_pnl / (total_value - total_day_pnl) * 100) if (total_value - total_day_pnl) > 0 else 0

# ===== Build Report =====
date_str = hkt.strftime('%Y-%m-%d (%a)')
msg = f"\U0001f4cb <b>\u3010\u6bcf\u65e5\u6301\u5009\u5831\u544a\u3011{date_str}</b>\n"
msg += f"{report_label}\n\n"

src_icon = "\U0001f310" if data_source == "etoro" else "\U0001f4be"
msg += f"{src_icon} \u8cc7\u6599\u4f86\u6e90\uff1a{'eToro API' if data_source == 'etoro' else 'Supabase'}\n\n"

pnl_icon = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"
day_icon = "\U0001f7e2" if total_day_pnl >= 0 else "\U0001f534"
msg += f"\U0001f4bc <b>\u7e3d\u89bd</b>\n"
msg += f"\u2022 \u6301\u5009\uff1a{len(portfolio_data)} \u6a94\n"
msg += f"\u2022 \u7e3d\u5e02\u503c\uff1a<b>${total_value:,.2f}</b>\n"
msg += f"\u2022 \u7e3d\u640d\u76ca\uff1a{pnl_icon} ${total_pnl:+,.2f} ({total_pnl_pct:+.1f}%)\n"
msg += f"\u2022 \u4eca\u65e5\u640d\u76ca\uff1a{day_icon} ${total_day_pnl:+,.2f} ({day_pnl_pct:+.1f}%)\n\n"

best = portfolio_data[0]
worst = portfolio_data[-1]
msg += f"\U0001f3c6 <b>\u4eca\u65e5\u6700\u4f73</b>: {best['ticker']} {best['day_change_pct']:+.1f}%\n"
msg += f"\U0001f480 <b>\u4eca\u65e5\u6700\u5dee</b>: {worst['ticker']} {worst['day_change_pct']:+.1f}%\n\n"

SECTOR_EMOJI = {
    "Technology":"\U0001f4bb","Healthcare":"\U0001f3e5","Financial Services":"\U0001f3e6",
    "Energy":"\u26fd","Industrials":"\U0001f3ed","Communication Services":"\U0001f4e1",
    "Consumer Cyclical":"\U0001f6cd\ufe0f","Consumer Defensive":"\U0001f6d2",
    "Real Estate":"\U0001f3e0","Utilities":"\U0001f4a1","Semiconductors":"\U0001f9ec"
}

msg += f"\U0001f4ca <b>\u9010\u6a94\u660e\u7d30</b>\n"
for p in portfolio_data:
    icon = "\U0001f7e2" if p['pnl'] >= 0 else "\U0001f534"
    day_i = "\u25b2" if p['day_change_pct'] >= 0 else "\u25bc"
    se = next((v for k,v in SECTOR_EMOJI.items() if k.lower() in p['sector'].lower()), "\U0001f4c8")
    msg += f"{icon} <b>{p['ticker']}</b> {se}{p['sector']}\n"
    msg += f"   ${p['price']:.2f} ({day_i}{p['day_change_pct']:+.1f}%) | \u6210\u672c ${p['avg_cost']:.2f} | P/L {p['pnl_pct']:+.1f}%\n"

# AI
if gemini_client:
    ticker_info = ", ".join([f"{p['ticker']}({p['day_change_pct']:+.1f}%)" for p in portfolio_data])
    try:
        ai_prompt = (
            f"\u4f60\u662f\u6211\u7684\u79c1\u4eba\u83ef\u723e\u8857\u5206\u6790\u5e2b\u3002\u6211\u7684\u6301\u5009\uff1a{ticker_info}\u3002\n"
            f"\u4eca\u5929\u662f {date_str}\u3002\n\n"
            f"\u8acb\u7528\u7e41\u9ad4\u4e2d\u6587\uff0c80\u5b57\u5167\uff0c\u7c21\u6f54\u5206\u6790\uff1a\n"
            f"1. \u6211\u7684\u6301\u5009\u4e2d\u4eca\u65e5\u6709\u54ea\u4e9b\u91cd\u5927\u65b0\u805e\u9700\u8981\u6ce8\u610f\n"
            f"2. \u6574\u9ad4\u5e02\u5834\u98a8\u5411\u5c0d\u6211\u7684\u6301\u5009\u7684\u5f71\u97ff\n"
            f"3. \u662f\u5426\u6709\u9700\u8981\u64d4\u5fc3\u7684\u98a8\u96aa\n\n"
            f"\u7981 markdown\u3002\u7c21\u6f54\u76f4\u63a5\u3002"
        )
        ai_resp = gemini_client.models.generate_content(
            model="gemini-3.1-pro-preview", contents=ai_prompt,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
        msg += f"\n\U0001f9e0 <b>AI \u5e02\u5834\u89c0\u5bdf</b>\n{ai_resp.text.strip()}\n"
    except Exception as e:
        print(f"AI error: {e}")

if report_type == "morning":
    msg += f"\n\u23f0 \u4e0b\u6b21\u5831\u544a\uff1a\u4eca\u665a 21:00 HKT\uff08\u76e4\u524d\uff09"
else:
    msg += f"\n\u23f0 \u4e0b\u6b21\u5831\u544a\uff1a\u660e\u65e9 07:00 HKT\uff08\u6536\u76e4\uff09"

msg += f"\n\n\u26a0\ufe0f <i>\u50c5\u4f9b\u53c3\u8003\uff0c\u4e0d\u69cb\u6210\u6295\u8cc7\u5efa\u8b70</i>"

send_private(msg)
print(f"Report sent! ({len(portfolio_data)} positions, ${total_value:,.2f}, source: {data_source})")
