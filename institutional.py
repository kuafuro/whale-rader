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

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID_WHALE = os.environ.get('TELEGRAM_CHAT_ID_WHALE')
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    print("Gemini 3.1 Pro ready")

def supabase_insert(data):
    if not SUPABASE_URL or not SUPABASE_KEY: return False
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/whale_alerts", headers=headers, json=data)
        return resp.status_code == 201
    except: return False

def supabase_link_exists(link):
    if not SUPABASE_URL or not SUPABASE_KEY: return False
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        resp = requests.get(f"{SUPABASE_URL}/rest/v1/whale_alerts?sec_link=eq.{link}&select=id&limit=1", headers=headers)
        return resp.status_code == 200 and len(resp.json()) > 0
    except: return False

def get_stock_quote(ticker):
    if not FINNHUB_API_KEY or ticker == "N/A": return "N/A", "N/A", 0, 0
    try:
        resp = requests.get(f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_API_KEY}")
        if resp.status_code == 200:
            d = resp.json()
            p, c = d.get('c',0), d.get('dp',0)
            if p and p > 0:
                s = "+" if c > 0 else ""
                i = "\U0001f7e2" if c > 0 else ("\U0001f534" if c < 0 else "\u26aa")
                return f"${p:.2f}", f"{i} {s}{c:.2f}%", p, c
    except: pass
    return "N/A", "N/A", 0, 0

def ai_institution_background(filer_name, subject_name, category):
    if not gemini_client: return ""
    try:
        prompt = (
            f"You are a Wall Street analyst. The institution '{filer_name}' just filed a {category} "
            f"with the SEC regarding '{subject_name}'. "
            f"Search for info about '{filer_name}' and provide a brief background in Traditional Chinese "
            f"within 80 words. Include: firm type (hedge fund, PE, activist, etc), "
            f"AUM if known, notable past investments, and reputation. "
            f"End with threat level: \U0001f534 aggressive activist, \U0001f7e1 notable player, \U0001f7e2 passive investor."
        )
        response = gemini_client.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )
        )
        return response.text.strip()
    except Exception as e:
        print(f"  Gemini error: {e}")
        return ""

def send_telegram(msg):
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", params={'chat_id': CHAT_ID_WHALE, 'text': msg, 'parse_mode': 'HTML'})

SEC_HEADERS = {'User-Agent': 'WhaleRadarBot Admin@kuafuorhk.com'}
def get_sec_ticker_map():
    try:
        resp = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS)
        return {str(v['cik_str']): v['ticker'] for v in resp.json().values()}
    except: return {}

CIK_TICKER_MAP = get_sec_ticker_map()
now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=15)

try:
    resp = requests.get('https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=SC+13&owner=only&count=40&output=atom', headers=SEC_HEADERS)
    soup = BeautifulSoup(resp.content, 'xml')
    entries = soup.find_all('entry')
    print(f"Found {len(entries)} SC 13 entries")
    found = 0

    for entry in entries:
        try:
            if datetime.fromisoformat(entry.updated.text.replace('Z','+00:00')).astimezone(timezone.utc) < time_limit: break
        except: continue

        category = entry.category['term'] if entry.category else ""
        if not (category.startswith('SC 13D') or category.startswith('SC 13G')): continue

        link = entry.link['href']
        if supabase_link_exists(link): continue

        txt_resp = requests.get(link.replace('-index.htm','.txt'), headers=SEC_HEADERS)
        if txt_resp.status_code == 200:
            txt = txt_resp.text
            subj_match = re.search(r'<SUBJECT-COMPANY>.*?<CONFORMED-NAME>([^\n]+)', txt, re.DOTALL)
            filer_match = re.search(r'<FILED-BY>.*?<CONFORMED-NAME>([^\n]+)', txt, re.DOTALL)
            subject_name = subj_match.group(1).strip() if subj_match else "Unknown Target"
            filer_name = filer_match.group(1).strip() if filer_match else "Unknown Filer"

            ticker = "N/A"
            cik_match = re.search(r'<SUBJECT-COMPANY>.*?CENTRAL INDEX KEY:\s*(\d+)', txt[:5000], re.DOTALL)
            if cik_match:
                ticker = CIK_TICKER_MAP.get(str(int(cik_match.group(1).strip())), "N/A")

            price_str, change_str, cur_price, chg_pct = get_stock_quote(ticker)

            if category.startswith('SC 13D'):
                intent = "\U0001f525 <b>\u4e3b\u52d5\u8209\u724c (\u53ef\u80fd\u4ecb\u5165\u7d93\u71df)</b>"
            else:
                intent = "\U0001f91d <b>\u88ab\u52d5\u6295\u8cc7 (\u7d14\u8ca1\u52d9\u6295\u8cc7)</b>"

            bg = ai_institution_background(filer_name, subject_name, category)

            msg = "\U0001f988 <b>\u3010\u6a5f\u69cb\u5927\u9c77\u8209\u724c\u96f7\u9054\u3011</b>\n"
            msg += f"\U0001f3af \u7375\u7269 (\u516c\u53f8): <b>{subject_name} ({ticker})</b>\n"
            if ticker != "N/A": msg += f"\U0001f4b2 \u80a1\u50f9: <b>{price_str}</b>  {change_str}\n"
            msg += f"\U0001f4bc \u7375\u4eba (\u6a5f\u69cb): <b>{filer_name}</b>\n"
            msg += f"\U0001f4dd \u985e\u578b: {category}\n"
            msg += f"{intent}\n"
            if bg: msg += f"\U0001f9e0 <b>\u6a5f\u69cb\u80cc\u666f\uff1a</b>\n{bg}\n"
            msg += f"\U0001f517 <a href='{link}'>\u67e5\u770b SEC \u539f\u6587</a>"

            send_telegram(msg)
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

        if found >= 5: break
except Exception as e: print(f"SC 13 engine error: {e}")
