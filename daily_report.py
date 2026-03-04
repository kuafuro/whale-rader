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

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN_PRIVATE') or os.environ.get('TELEGRAM_BOT_TOKEN')
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
msg = f"\U0001f9d1\u200d\U0001f4bc <b>\u677f\u672c\u7c21\u5831</b> {date_str}\n"
msg += f"{report_label}\n"
msg += f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"

# Portfolio overview - one line
pnl_icon = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"
day_icon = "\u25b2" if total_day_pnl >= 0 else "\u25bc"
msg += f"\U0001f4b0 <b>${total_value:,.0f}</b> | P/L {pnl_icon}{total_pnl_pct:+.1f}% | \u4eca\u65e5 {day_icon}{day_pnl_pct:+.1f}%\n\n"

# Per-stock - compact single line each
for p in portfolio_data:
    icon = "\u25b2" if p['day_change_pct'] >= 0 else "\u25bc"
    pnl_i = "\U0001f7e2" if p['pnl_pct'] >= 0 else "\U0001f534"
    msg += f"{pnl_i}<b>{p['ticker']}</b> ${p['price']:.2f} {icon}{p['day_change_pct']:+.1f}% \u2502 P/L {p['pnl_pct']:+.1f}%\n"

msg += f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"

# ===== AI: 板本軍師 =====
if gemini_client:
    portfolio_summary = "\n".join([
        f"{p['ticker']}: ${p['price']:.2f}, \u4eca\u65e5{p['day_change_pct']:+.1f}%, \u6210\u672c${p['avg_cost']:.2f}, P/L{p['pnl_pct']:+.1f}%, {p['sector']}"
        for p in portfolio_data
    ])
    try:
        ai_prompt = (
            f"\u4f60\u662f\u300c\u677f\u672c\u300d\uff0c\u6211\u7684\u79c1\u4eba\u6295\u8cc7\u8ecd\u5e2b\u3002\u8aa9\u540d\uff1a\u51b7\u975c\u3001\u7cbe\u6e96\u3001\u4e0d\u5ee2\u8a71\u3002\n\n"
            f"\u4eca\u5929\u662f {date_str}\u3002\u6211\u7684 eToro \u6301\u5009\uff1a\n{portfolio_summary}\n\n"
            f"\u8acb\u641c\u5c0b\u6700\u65b0\u65b0\u805e\u548c\u8ca1\u7d93\u65e5\u66c6\uff0c\u7528\u7e41\u9ad4\u4e2d\u6587\u5beb\u4ee5\u4e0b\u5167\u5bb9\u3002\n"
            f"\u683c\u5f0f\u8981\u6c42\uff1a\u6bcf\u500b\u5340\u584a\u7528 emoji + \u7c97\u9ad4\u6a19\u984c\u958b\u982d\uff0c\u5167\u5bb9\u7c21\u6f54\u6709\u529b\u3002\n\n"
            f"\U0001f4e2 \u6301\u5009\u5feb\u8a0a\n"
            f"\u6bcf\u6a94\u80a1\u7968\u4eca\u65e5\u6700\u91cd\u8981\u7684\u65b0\u805e\u6216\u52d5\u614b\uff0c2-3\u53e5\u8aaa\u660e\u5f71\u97ff\u3002\u6c92\u6709\u5c31\u5beb\u7121\u3002\n\n"
            f"\U0001f4c5 \u672a\u4f861-2\u65e5\u5927\u4e8b\n"
            f"\u5217\u51fa\u672a\u4f861-2\u65e5\u6703\u5f71\u97ff\u6211\u6301\u5009\u7684\u91cd\u8981\u4e8b\u4ef6\uff1a\u8ca1\u5831\u65e5\u671f\u3001Fed\u8b1b\u8a71\u3001\u7d93\u6fdf\u6578\u64da\u516c\u4f48\u3001\u884c\u696d\u6703\u8b70\u7b49\u3002\n"
            f"\u6bcf\u689d\u8981\u8aaa\u660e\u70ba\u4ec0\u9ebc\u91cd\u8981\uff0c\u5c0d\u6211\u7684\u6301\u5009\u6709\u4ec0\u9ebc\u5f71\u97ff\uff0c\u6211\u61c9\u8a72\u600e\u9ebc\u61c9\u5c0d\u30022-3\u53e5\u3002\n\n"
            f"\U0001f3af \u4f48\u5c40\u5efa\u8b70\n"
            f"\u6bcf\u6a94\u80a1\u7968\u7d66\u51fa\u5177\u9ad4\u884c\u52d5\uff08\u52a0\u5009/\u6e1b\u5009/\u6301\u6709/\u8a2d\u505c\u640d\uff09\uff0c\u9644\u8a73\u7d30\u7406\u7531\uff1a\n"
            f"\u5305\u62ec\u6280\u8853\u9762\uff08\u652f\u6490\u58d3\u529b\u4f4d\u3001\u5747\u7dda\u3001\u8da8\u52e2\uff09\u548c\u57fa\u672c\u9762\uff08\u4f30\u503c\u3001\u7372\u5229\u3001\u884c\u696d\u524d\u666f\uff09\u3002\n"
            f"\u6bcf\u6a94 3-4 \u53e5\u3002\n"
            f"\u6700\u5f8c\u7d66\u6574\u9ad4\u7d44\u5408\u7684\u98a8\u96aa\u8a55\u4f30\u548c\u5efa\u8b70\u3002\n\n"
            f"\u7981\u6b62\u4f7f\u7528 markdown \u683c\u5f0f\uff08\u7981 * # - \u7b49\uff09\u3002\u7528\u7e41\u9ad4\u4e2d\u6587\u3002\u7c21\u6f54\u6709\u529b\u3002"
        )
        ai_resp = gemini_client.models.generate_content(
            model="gemini-3.1-pro-preview", contents=ai_prompt,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
        msg += f"\n{ai_resp.text.strip()}\n"
    except Exception as e:
        print(f"AI error: {e}")

send_private(msg)
print(f"Report sent! ({len(portfolio_data)} positions, ${total_value:,.2f}, source: {data_source})")