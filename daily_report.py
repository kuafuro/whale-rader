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


def get_supabase_holdings():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        r = requests.get(f"{SUPABASE_URL}/rest/v1/portfolio_holdings", headers=h,
                         params={"active": "eq.true", "order": "ticker"})
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Supabase error: {e}")
    return []


def get_quote(ticker):
    if not FINNHUB_API_KEY:
        return {}
    try:
        r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_API_KEY}")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Finnhub quote error: {e}")
    return {}


def get_profile(ticker):
    if not FINNHUB_API_KEY:
        return {}
    try:
        r = requests.get(f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={FINNHUB_API_KEY}")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Finnhub profile error: {e}")
    return {}


def send_private(msg):
    if not CHAT_ID_PRIVATE:
        print("No CHAT_ID_PRIVATE set, printing:")
        print(msg)
        return
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                     params={'chat_id': CHAT_ID_PRIVATE, 'text': msg, 'parse_mode': 'HTML'})
    if r.status_code != 200:
        print(f"Telegram error: {r.status_code} {r.text[:200]}")


def main():
    now_utc = datetime.now(timezone.utc)
    hkt = now_utc + timedelta(hours=8)

    # Skip Sunday entirely; skip Saturday afternoon/evening (only Saturday morning runs)
    if hkt.weekday() == 6 or (hkt.weekday() == 5 and hkt.hour >= 12):
        print(f"Weekend (HKT {hkt.strftime('%A')} {hkt.strftime('%H:%M')}), skipping")
        return

    report_type = "morning" if hkt.hour < 12 else "premarket"
    report_label = "🌅 收盤報告" if report_type == "morning" else "🌕 盤前報告"
    print(f"Report type: {report_type} (HKT {hkt.strftime('%H:%M')})")

    # Get Holdings
    data_source = "supabase"
    positions = {}

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
                if not ticker:
                    continue
                if ticker in positions:
                    positions[ticker]["shares"] += shares
                    positions[ticker]["total_cost"] += shares * open_price
                else:
                    positions[ticker] = {"ticker": ticker, "shares": shares, "total_cost": shares * open_price, "open_date": "eToro"}

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
        send_private("⚠️ 無法取得持倉資料。請檢查 eToro API Key 或 Supabase。")
        return

    # Fetch Prices
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
        return

    portfolio_data.sort(key=lambda x: x['day_change_pct'], reverse=True)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    day_pnl_pct = (total_day_pnl / (total_value - total_day_pnl) * 100) if (total_value - total_day_pnl) > 0 else 0

    # Build Report
    date_str = hkt.strftime('%Y-%m-%d (%a)')
    msg = f"🧑‍💼 <b>板本簡報</b> {date_str}\n"
    msg += f"{report_label}\n"
    msg += f"───────────────\n"

    pnl_icon = "🟢" if total_pnl >= 0 else "🔴"
    day_icon = "▲" if total_day_pnl >= 0 else "▼"
    msg += f"💰 <b>${total_value:,.0f}</b> | P/L {pnl_icon}{total_pnl_pct:+.1f}% | 今日 {day_icon}{day_pnl_pct:+.1f}%\n\n"

    for p in portfolio_data:
        icon = "▲" if p['day_change_pct'] >= 0 else "▼"
        pnl_i = "🟢" if p['pnl_pct'] >= 0 else "🔴"
        msg += f"{pnl_i}<b>{p['ticker']}</b> ${p['price']:.2f} {icon}{p['day_change_pct']:+.1f}% │ P/L {p['pnl_pct']:+.1f}%\n"

    msg += f"───────────────\n"

    # AI: 板本軍師
    if gemini_client:
        portfolio_summary = "\n".join([
            f"{p['ticker']}: ${p['price']:.2f}, 今日{p['day_change_pct']:+.1f}%, 成本${p['avg_cost']:.2f}, P/L{p['pnl_pct']:+.1f}%, {p['sector']}"
            for p in portfolio_data
        ])
        try:
            ai_prompt = (
                f"你是「板本」，我的私人投資軍師。蔣名：冷靜、精準、不廢話。\n\n"
                f"今天是 {date_str}。我的 eToro 持倉：\n{portfolio_summary}\n\n"
                f"請搜尋最新新聞和財經日曆，用繁體中文寫以下內容。\n"
                f"格式要求：每個區塊用 emoji + 粗體標題開頭，內容簡潔有力。\n\n"
                f"📢 持倉快訊\n"
                f"每檔股票今日最重要的新聞或動態，2-3句說明影響。沒有就寫無。\n\n"
                f"📅 未來1-2日大事\n"
                f"列出未來1-2日會影響我持倉的重要事件：財報日期、Fed講話、經濟數據公佈、行業會議等。\n"
                f"每條要說明為什麼重要，對我的持倉有什麼影響，我應該怎麼應對。2-3句。\n\n"
                f"🎯 佈局建議\n"
                f"每檔股票給出具體行動（加倉/減倉/持有/設停損），附詳細理由：\n"
                f"包括技術面（支撐壓力位、均線、趨勢）和基本面（估值、獲利、行業前景）。\n"
                f"每檔 3-4 句。\n"
                f"最後給整體組合的風險評估和建議。\n\n"
                f"禁止使用 markdown 格式（禁 * # - 等）。用繁體中文。簡潔有力。"
            )
            ai_resp = gemini_client.models.generate_content(
                model="gemini-3.1-pro-preview", contents=ai_prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
            msg += f"\n{ai_resp.text.strip()}\n"
        except Exception as e:
            print(f"AI error: {e}")

    send_private(msg)
    print(f"Report sent! ({len(portfolio_data)} positions, ${total_value:,.2f}, source: {data_source})")


if __name__ == "__main__":
    main()
