# ==================== ai_analyst.py V22 ====================
# Engine 4: AI 8-K Filing Analyzer
# Upgrade: Gemini 3.1 Pro + Supabase + Finnhub + Ticker
# ============================================================
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timezone, timedelta
import os, re, json
from google import genai
from google.genai import types

from utils.supabase import supabase_insert, supabase_link_exists
from utils.finnhub import get_stock_quote
from utils.telegram import send_whale_telegram

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    print("Gemini 3.1 Pro ready")


def extract_ticker(txt):
    m = re.search(r'<(?:issuerTradingSymbol|tradingSymbol)>\s*([^<]+?)\s*</', txt, re.IGNORECASE)
    if m:
        return m.group(1).strip().upper()
    m = re.search(r'TICKER SYMBOL:\s*([^\n\r]+)', txt[:5000])
    if m:
        return m.group(1).strip().upper()
    return "N/A"


def main():
    hdrs = {'User-Agent': 'WhaleRadarBot Admin@kuafuorhk.com'}
    now_utc = datetime.now(timezone.utc)
    time_limit = now_utc - timedelta(minutes=15)

    resp = requests.get(
        'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&owner=include&count=40&output=atom',
        headers=hdrs
    )
    soup = BeautifulSoup(resp.content, 'xml')
    entries = soup.find_all('entry')
    print(f"Found {len(entries)} 8-K entries")
    found = 0

    for entry in entries:
        try:
            if datetime.fromisoformat(entry.updated.text.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit:
                break
        except Exception:
            continue

        link = entry.link['href']
        if supabase_link_exists(link):
            continue
        if not gemini_client:
            break

        company = entry.title.text.split(' - ')[0].strip() if entry.title else "Unknown"
        txt_resp = requests.get(link.replace('-index.htm', '.txt'), headers=hdrs)

        if txt_resp.status_code != 200:
            continue

        content = txt_resp.text
        ticker = extract_ticker(content)
        price_str, change_str, cur_price, chg_pct = get_stock_quote(ticker)

        prompt = (
            "This is a partial US SEC 8-K filing. Act as a professional Wall Street analyst. "
            "Summarize the key points in Traditional Chinese in 3-5 sentences. "
            "Judge if bullish, bearish, or neutral. Use emoji: 🚀 bullish, 📉 bearish, 😐 neutral.\n\n"
            f"Filing:\n{content[:15000]}"
        )
        try:
            ai_resp = gemini_client.models.generate_content(
                model="gemini-3.1-pro-preview", contents=prompt,
                config=types.GenerateContentConfig(http_options=types.HttpOptions(timeout=20000))
            )
            summary = ai_resp.text.strip()
            sentiment = "bullish" if "🚀" in summary else ("bearish" if "📉" in summary else "neutral")

            msg = "🤖 <b>【AI 8-K 財報秒讀機】</b>\n"
            msg += f"🏢 公司: <b>{company} ({ticker})</b>\n"
            if ticker != "N/A":
                msg += f"💲 股價: <b>{price_str}</b>  {change_str}\n"
            msg += f"📝 <b>AI 總結:</b>\n{summary}\n\n"
            msg += f"🔗 <a href='{link}'>查看 8-K 原文</a>"

            send_whale_telegram(msg)
            print(f"  Sent: {company} ({ticker})")
            supabase_insert({
                "source": "8k", "ticker": ticker, "company_name": company,
                "action": "8-K", "price": cur_price, "change_pct": chg_pct,
                "ai_summary": summary, "sentiment": sentiment, "sec_link": link
            })
            found += 1
            time.sleep(2)
        except Exception as e:
            print(f"AI error: {e}")

        if found >= 3:
            break


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"8-K engine error: {e}")
