# ==================== institutional.py V22 ====================
# Engine 3: SC 13D/G Institutional Ownership Radar
# Upgrade: Supabase + Finnhub + Gemini 3.1 Pro background info
# ==============================================================
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

SEC_HEADERS = {'User-Agent': 'WhaleRadarBot Admin@kuafuorhk.com'}


def get_sec_ticker_map():
    try:
        resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS)
        return {str(v['cik_str']): v['ticker'] for v in resp.json().values()}
    except Exception as e:
        print(f"⚠️ SEC ticker map failed: {e}")
        return {}


def ai_institution_background(filer_name, subject_name, category):
    if not gemini_client:
        return ""
    try:
        prompt = (
            f"You are a Wall Street analyst. The institution '{filer_name}' just filed a {category} "
            f"with the SEC regarding '{subject_name}'. "
            f"Search for info about '{filer_name}' and provide a brief background in Traditional Chinese "
            f"within 80 words. Include: firm type (hedge fund, PE, activist, etc), "
            f"AUM if known, notable past investments, and reputation. "
            f"End with threat level: 🔴 aggressive activist, 🟡 notable player, 🟢 passive investor."
        )
        response = gemini_client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                http_options=types.HttpOptions(timeout=20000),
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"  Gemini error: {e}")
        return ""


def main():
    cik_ticker_map = get_sec_ticker_map()
    now_utc = datetime.now(timezone.utc)
    time_limit = now_utc - timedelta(minutes=15)

    resp = requests.get(
        'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=SC+13&owner=only&count=40&output=atom',
        headers=SEC_HEADERS
    )
    soup = BeautifulSoup(resp.content, 'xml')
    entries = soup.find_all('entry')
    print(f"Found {len(entries)} SC 13 entries")
    found = 0

    for entry in entries:
        try:
            if datetime.fromisoformat(entry.updated.text.replace('Z', '+00:00')).astimezone(timezone.utc) < time_limit:
                break
        except Exception:
            continue

        category = entry.category['term'] if entry.category else ""
        if not (category.startswith('SC 13D') or category.startswith('SC 13G')):
            continue

        link = entry.link['href']
        if supabase_link_exists(link):
            continue

        txt_resp = requests.get(link.replace('-index.htm', '.txt'), headers=SEC_HEADERS)
        if txt_resp.status_code != 200:
            continue

        txt = txt_resp.text
        subj_match = re.search(r'<SUBJECT-COMPANY>.*?<CONFORMED-NAME>([^\n]+)', txt, re.DOTALL)
        filer_match = re.search(r'<FILED-BY>.*?<CONFORMED-NAME>([^\n]+)', txt, re.DOTALL)
        subject_name = subj_match.group(1).strip() if subj_match else "Unknown Target"
        filer_name = filer_match.group(1).strip() if filer_match else "Unknown Filer"

        ticker = "N/A"
        cik_match = re.search(r'<SUBJECT-COMPANY>.*?CENTRAL INDEX KEY:\s*(\d+)', txt[:5000], re.DOTALL)
        if cik_match:
            ticker = cik_ticker_map.get(str(int(cik_match.group(1).strip())), "N/A")

        price_str, change_str, cur_price, chg_pct = get_stock_quote(ticker)

        if category.startswith('SC 13D'):
            intent = "🔥 <b>主動舉牌 (可能介入經營)</b>"
        else:
            intent = "🤝 <b>被動投資 (純財務投資)</b>"

        bg = ai_institution_background(filer_name, subject_name, category)

        msg = "🦈 <b>【機構大鯊舉牌雷達】</b>\n"
        msg += f"🎯 獵物 (公司): <b>{subject_name} ({ticker})</b>\n"
        if ticker != "N/A":
            msg += f"💲 股價: <b>{price_str}</b>  {change_str}\n"
        msg += f"💼 獵人 (機構): <b>{filer_name}</b>\n"
        msg += f"📝 類型: {category}\n"
        msg += f"{intent}\n"
        if bg:
            msg += f"🧠 <b>機構背景：</b>\n{bg}\n"
        msg += f"🔗 <a href='{link}'>查看 SEC 原文</a>"

        send_whale_telegram(msg)
        print(f"  Sent: {subject_name} <- {filer_name}")

        supabase_insert({
            "source": "sc13", "ticker": ticker, "company_name": subject_name,
            "action": category, "reporter_name": filer_name,
            "price": cur_price, "change_pct": chg_pct,
            "ai_summary": bg, "sec_link": link,
            "extra_data": json.dumps({"intent": "activist" if category.startswith('SC 13D') else "passive"})
        })
        found += 1
        time.sleep(2)

        if found >= 5:
            break


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"SC 13 engine error: {e}")
