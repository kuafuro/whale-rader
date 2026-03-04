# form144.py V23 - Sector + AI upgrade
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
    print("Gemini 3.1 Pro engine ready")

def supabase_insert(data):
    if not SUPABASE_URL or not SUPABASE_KEY: return False
    try:
        h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"}
        r = requests.post(f"{SUPABASE_URL}/rest/v1/whale_alerts", headers=h, json=data)
        return r.status_code == 201
    except: return False

def supabase_link_exists(link):
    if not SUPABASE_URL or not SUPABASE_KEY: return False
    try:
        h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        r = requests.get(f"{SUPABASE_URL}/rest/v1/whale_alerts?sec_link=eq.{link}&select=id&limit=1", headers=h)
        return r.status_code == 200 and len(r.json()) > 0
    except: return False

def get_stock_quote(ticker):
    if not FINNHUB_API_KEY or ticker == "N/A": return "N/A", "N/A", 0, 0
    try:
        r = requests.get(f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_API_KEY}")
        if r.status_code == 200:
            d = r.json(); p, c = d.get('c',0), d.get('dp',0)
            if p and p > 0:
                s = "+" if c > 0 else ""
                i = "\U0001f7e2" if c > 0 else ("\U0001f534" if c < 0 else "\u26aa")
                return f"${p:.2f}", f"{i} {s}{c:.2f}%", p, c
    except: pass
    return "N/A", "N/A", 0, 0

def get_company_profile(ticker):
    if not FINNHUB_API_KEY or ticker == "N/A": return {"sector":"N/A","industry":"N/A","marketCap":0}
    try:
        r = requests.get(f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={FINNHUB_API_KEY}")
        if r.status_code == 200:
            d = r.json()
            return {"sector":d.get('finnhubIndustry','N/A'),"industry":d.get('finnhubIndustry','N/A'),"marketCap":d.get('marketCapitalization',0)}
    except: pass
    return {"sector":"N/A","industry":"N/A","marketCap":0}

def ai_is_routine_selling(company_name, ticker):
    """AI pre-screen: return True if this is routine selling (tax/vesting), skip it"""
    if not gemini_client: return False
    try:
        prompt = (
            f"Company: {company_name} ({ticker}) filed Form 144 with SEC.\n"
            f"Search latest news. Is this most likely ROUTINE selling "
            f"(restricted stock vesting, tax withholding, 10b5-1 plan, scheduled sale)?\n"
            f"Reply ONLY 'ROUTINE' or 'NOT_ROUTINE'. One word only."
        )
        resp = gemini_client.models.generate_content(
            model="gemini-3.1-pro-preview", contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ))
        answer = resp.text.strip().upper()
        is_routine = "ROUTINE" in answer and "NOT" not in answer
        print(f"    AI pre-screen: {answer} -> {'SKIP' if is_routine else 'ALERT'}")
        return is_routine
    except Exception as e:
        print(f"    AI pre-screen error: {e}")
        return False

def ai_explain_selling(company_name, ticker, sector, market_cap_m):
    if not gemini_client: return "\u26a0\ufe0f \u6709\u5167\u90e8\u4eba\u58eb\u5df2\u63d0\u4ea4\u62cb\u552e\u610f\u5411\u66f8"
    try:
        mc = f"\u5e02\u503c\uff1a${market_cap_m/1000:.1f}B\u3002" if market_cap_m >= 1000 else ""
        prompt = (
            f"\u516c\u53f8\uff1a{company_name} ({ticker})\uff0c\u677f\u584a\uff1a{sector}\u3002{mc}\n"
            f"\u5167\u90e8\u4eba\u58eb\u5411 SEC \u63d0\u4ea4 Form 144 \u62cb\u552e\u610f\u5411\u66f8\u3002\n\n"
            f"\u8acb\u7528\u7e41\u9ad4\u4e2d\u6587\uff0c80\u5b57\u5167\uff0c\u7c21\u6f54\u5206\u6790\uff1a\n"
            f"1. {sector} \u677f\u584a\u8da8\u52e2\uff08\u770b\u591a\u6216\u770b\u7a7a\uff0c\u4e00\u53e5\uff09\n"
            f"2. \u62cb\u552e\u539f\u56e0\uff08\u641c\u5c0b\u65b0\u805e\uff09\n"
            f"3. \u98a8\u96aa\u5224\u65b7\n\n"
            f"\u7d50\u5c3e\uff1a\U0001f534\u9ad8\u98a8\u96aa / \U0001f7e1\u4e2d\u98a8\u96aa / \U0001f7e2\u4f4e\u98a8\u96aa\n"
            f"\u7981 markdown\u3002\u7981\u5ee2\u8a71\u3002Bloomberg \u98a8\u683c\u3002"
        )
        resp = gemini_client.models.generate_content(
            model="gemini-3.1-pro-preview", contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ))
        return resp.text.strip()
    except Exception as e:
        print(f"  Gemini error: {e}")
        return "\u26a0\ufe0f \u6709\u5167\u90e8\u4eba\u58eb\u5df2\u63d0\u4ea4\u62cb\u552e\u610f\u5411\u66f8"

def send_telegram_message(msg):
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", params={'chat_id':CHAT_ID_WHALE,'text':msg,'parse_mode':'HTML'})

SEC_HEADERS = {'User-Agent': 'WhaleRadarBot Admin@kuafuorhk.com'}
def get_sec_ticker_map():
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SEC_HEADERS)
        return {str(v['cik_str']): v['ticker'] for v in r.json().values()}
    except: return {}

CIK_TICKER_MAP = get_sec_ticker_map()
print(f"Loaded {len(CIK_TICKER_MAP)} CIK-Ticker mappings")

SECTOR_EMOJI = {"Technology":"\U0001f4bb","Healthcare":"\U0001f3e5","Financial Services":"\U0001f3e6","Energy":"\u26fd","Consumer Cyclical":"\U0001f6cd\ufe0f","Industrials":"\U0001f3ed","Communication Services":"\U0001f4e1","Consumer Defensive":"\U0001f6d2","Real Estate":"\U0001f3e0","Utilities":"\U0001f4a1","Basic Materials":"\u26cf\ufe0f"}
def get_sector_emoji(sector):
    for k,v in SECTOR_EMOJI.items():
        if k.lower() in sector.lower(): return v
    return "\U0001f4c8"

url = 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=144&owner=only&count=40&output=atom'
now_utc = datetime.now(timezone.utc)
time_limit = now_utc - timedelta(minutes=30)
try:
    response = requests.get(url, headers=SEC_HEADERS)
    soup = BeautifulSoup(response.content, 'xml')
    entries = soup.find_all('entry')
    print(f"Found {len(entries)} Form 144 entries")
    found_count = 0
    for entry in entries:
        updated_tag = entry.find('updated')
        if not updated_tag: continue
        try:
            if datetime.fromisoformat(updated_tag.text.replace('Z','+00:00')).astimezone(timezone.utc) < time_limit: break
        except: continue
        link = entry.link['href']
        if supabase_link_exists(link): continue
        title_text = entry.title.text if entry.title else ""
        txt_link = link.replace('-index.htm', '.txt')
        txt_response = requests.get(txt_link, headers=SEC_HEADERS)
        if txt_response.status_code == 200:
            txt_content = txt_response.text
            ticker = "N/A"
            issuer_name = "\u672a\u77e5\u516c\u53f8"
            sym = re.search(r'<(?:issuerSymbol|issuerTradingSymbol)>\s*([^<]+?)\s*</(?:issuerSymbol|issuerTradingSymbol)>', txt_content, re.IGNORECASE)
            if sym: ticker = sym.group(1).strip().upper()
            nm = re.search(r'<(?:nameOfIssuer|issuerName)>\s*([^<]+?)\s*</(?:nameOfIssuer|issuerName)>', txt_content, re.IGNORECASE)
            if nm: issuer_name = nm.group(1).strip()
            if ticker == "N/A" or issuer_name == "\u672a\u77e5\u516c\u53f8":
                sgml = re.search(r'(?:SUBJECT COMPANY|ISSUER)[:\s]*(.*?)(?:FILED BY:|REPORTING-OWNER:|<SEC-DOCUMENT>|</SEC-HEADER>|\Z)', txt_content[:5000], re.DOTALL|re.IGNORECASE)
                if sgml:
                    block = sgml.group(1)
                    if issuer_name == "\u672a\u77e5\u516c\u53f8":
                        cn = re.search(r'COMPANY CONFORMED NAME:\s*([^\n\r]+)', block)
                        if cn: issuer_name = cn.group(1).strip()
                    if ticker == "N/A":
                        ck = re.search(r'CENTRAL INDEX KEY:\s*(\d+)', block)
                        if ck: ticker = CIK_TICKER_MAP.get(str(int(ck.group(1).strip())), "N/A")
            if ticker == "N/A":
                cm = re.search(r'\((\d+)\)\s*\(Subject\)', title_text)
                if cm: ticker = CIK_TICKER_MAP.get(str(int(cm.group(1))), "N/A")
            if issuer_name == "\u672a\u77e5\u516c\u53f8":
                tn = re.search(r'144\s*-\s*(.+?)\s*\(\d+\)', title_text)
                if tn: issuer_name = tn.group(1).strip()
            if issuer_name == "\u672a\u77e5\u516c\u53f8":
                alt = re.search(r'COMPANY CONFORMED NAME:\s*([^\n\r]+)', txt_content[:5000])
                if alt: issuer_name = alt.group(1).strip()
            print(f"  {issuer_name} ({ticker})")
            price_str, change_str, current_price, change_pct = get_stock_quote(ticker)
            profile = get_company_profile(ticker)
            sector = profile["sector"]
            market_cap_m = profile["marketCap"]
            sector_emoji = get_sector_emoji(sector)

            # Gate 1: market cap > $5B only
            MIN_MARKET_CAP = 5000  # $5B in millions
            if market_cap_m < MIN_MARKET_CAP:
                print(f"    Skipped: market cap ${market_cap_m:.0f}M < ${MIN_MARKET_CAP}M")
                continue

            # Gate 2: AI pre-screen - skip routine selling
            if ai_is_routine_selling(issuer_name, ticker):
                print(f"    Skipped: routine selling (tax/vesting)")
                # Still log to DB as routine, but don't send Telegram
                supabase_insert({
                    "source": "form144", "ticker": ticker, "company_name": issuer_name,
                    "action": "\u2705 \u5e38\u898f\u62cb\u552e\uff08\u5df2\u904e\u6ffe\uff09",
                    "price": current_price, "change_pct": change_pct,
                    "sec_link": link,
                    "extra_data": json.dumps({"sector": sector, "market_cap_m": market_cap_m, "filtered": True})
                })
                continue

            # Write to Supabase FIRST to prevent duplicates
            inserted = supabase_insert({
                "source": "form144", "ticker": ticker, "company_name": issuer_name,
                "action": "\u26a0\ufe0f Form 144 \u62cb\u552e\u9810\u8b66",
                "price": current_price, "change_pct": change_pct,
                "sec_link": link,
                "extra_data": json.dumps({"sector": sector, "industry": profile["industry"], "market_cap_m": market_cap_m})
            })
            if not inserted:
                print(f"    Skipped: already in DB or insert failed")
                continue

            ai_analysis = ai_explain_selling(issuer_name, ticker, sector, market_cap_m)
            msg = "\U0001f6a8 <b>\u3010Form 144 \u5167\u90e8\u9ad8\u7ba1\u9003\u751f\u9810\u8b66\u3011</b>\n"
            msg += f"\U0001f3e2 \u516c\u53f8\uff1a<b>{issuer_name} ({ticker})</b>\n"
            msg += f"{sector_emoji} \u677f\u584a\uff1a<b>{sector}</b>\n"
            msg += f"\U0001f4b2 \u80a1\u50f9\uff1a<b>{price_str}</b>  {change_str}\n"
            msg += f"\U0001f4b0 \u5e02\u503c\uff1a<b>${market_cap_m/1000:.1f}B</b>\n"
            msg += f"\U0001f9e0 <b>AI \u5206\u6790\uff1a</b>\n{ai_analysis}\n"
            msg += f"\U0001f517 <a href='{link}'>\u67e5\u770b SEC \u539f\u6587</a>"
            send_telegram_message(msg)

            # Update DB with AI summary
            if SUPABASE_URL and SUPABASE_KEY:
                try:
                    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
                    requests.patch(f"{SUPABASE_URL}/rest/v1/whale_alerts?sec_link=eq.{link}", headers=h, json={"ai_summary": ai_analysis})
                except: pass

            found_count += 1
            time.sleep(2)
        if found_count >= 5: break
except Exception as e:
    print(f"Form 144 engine error: {e}")